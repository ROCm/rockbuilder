// SPDX-License-Identifier: MIT
// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

#define AITER_NO_TORCH_TYPES
#include "aiter_stream.h"
#include "topk_per_row.h"
#include "topk_plain.h"

#include <hip/hip_runtime.h>
#include <hipcub/hipcub.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr int kWarmupIterations = 5;
constexpr int kBenchmarkIterations = 20;
constexpr int kFallbackBlockSize = 256;
constexpr int kMaximumFallbackColumns = 4096;
constexpr float kValueTolerance = 1.0e-6f;

struct Shape
{
    int rows;
    int columns;
    int topk;
    bool largest;
};

constexpr Shape kShapes[] = {
    {8, 32, 1, true},
    {8, 64, 16, true},
    {8, 128, 16, false},
    {8, 4096, 16, true},
    {8, 4096, 64, true},
    {8, 4096, 128, true},
    {256, 4096, 128, true},
    {1024, 4096, 128, true},
};

struct Output
{
    std::vector<int32_t> ids;
    std::vector<float> values;
};

struct ErrorMetrics
{
    size_t mismatched_ids = 0;
    size_t invalid_ids = 0;
    double max_value_error = 0.0;
    bool passed = true;
};

struct Result
{
    std::string implementation;
    double microseconds = 0.0;
    double effective_tbps = 0.0;
    double speedup = 0.0;
    Output output;
    ErrorMetrics error;
    bool has_accuracy = false;
};

void check_hip(hipError_t status, const char* expression)
{
    if(status != hipSuccess)
    {
        throw std::runtime_error(
            std::string(expression) + " failed: " + hipGetErrorString(status));
    }
}

#define HIP_CHECK(expression) check_hip((expression), #expression)

std::string base_architecture(const hipDeviceProp_t& properties)
{
    std::string ret = properties.gcnArchName;
    const size_t separator = ret.find(':');
    if(separator != std::string::npos)
    {
        ret.resize(separator);
    }
    return ret;
}

bool is_supported_architecture(const std::string& architecture)
{
    bool ret = architecture == "gfx90a" || architecture == "gfx942" ||
               architecture == "gfx1100" || architecture == "gfx1200" ||
               architecture == "gfx1201";
    return ret;
}

bool prompt_yes_no(const std::string& question)
{
    bool ret = false;
    bool answered = false;
    while(!answered)
    {
        std::cout << question << " [y/n]: " << std::flush;
        std::string response;
        if(!std::getline(std::cin, response))
        {
            throw std::runtime_error("Unable to read interactive response");
        }
        if(response == "y" || response == "Y")
        {
            ret = true;
            answered = true;
        }
        else if(response == "n" || response == "N")
        {
            answered = true;
        }
        else
        {
            std::cout << "Please answer y or n.\n";
        }
    }
    return ret;
}

std::optional<aiter_tensor_t> tensor_optional(AiterTensor& tensor)
{
    std::optional<aiter_tensor_t> ret(
        static_cast<aiter_tensor_t&>(tensor));
    return ret;
}

template <typename T>
void copy_to_device(AiterTensor& destination, const std::vector<T>& source)
{
    if(destination.numel() != source.size())
    {
        throw std::runtime_error("Device tensor source size mismatch");
    }
    HIP_CHECK(hipMemcpy(destination.data_ptr(),
                        source.data(),
                        source.size() * sizeof(T),
                        hipMemcpyHostToDevice));
}

template <typename T>
std::vector<T> copy_to_host(const AiterTensor& source)
{
    std::vector<T> ret_arr(source.numel());
    HIP_CHECK(hipMemcpy(ret_arr.data(),
                        source.data_ptr(),
                        ret_arr.size() * sizeof(T),
                        hipMemcpyDeviceToHost));
    return ret_arr;
}

std::vector<float> make_input(const Shape& shape)
{
    std::vector<float> ret_arr(
        static_cast<size_t>(shape.rows) * shape.columns);
    for(int row = 0; row < shape.rows; ++row)
    {
        for(int column = 0; column < shape.columns; ++column)
        {
            const uint32_t permutation =
                (static_cast<uint32_t>(column) * 4051u +
                 static_cast<uint32_t>(row) * 997u) %
                static_cast<uint32_t>(shape.columns);
            ret_arr[static_cast<size_t>(row) * shape.columns + column] =
                static_cast<float>(permutation) * 0.03125f +
                static_cast<float>(row) * 0.0001f;
        }
    }
    return ret_arr;
}

bool candidate_before(float lhs_value,
                      int32_t lhs_id,
                      float rhs_value,
                      int32_t rhs_id,
                      bool largest)
{
    bool ret = false;
    if(lhs_value == rhs_value)
    {
        ret = lhs_id < rhs_id;
    }
    else
    {
        ret = largest ? lhs_value > rhs_value : lhs_value < rhs_value;
    }
    return ret;
}

Output calculate_cpu_reference(const std::vector<float>& input,
                               const Shape& shape)
{
    Output ret;
    ret.ids.resize(static_cast<size_t>(shape.rows) * shape.topk);
    ret.values.resize(static_cast<size_t>(shape.rows) * shape.topk);
    for(int row = 0; row < shape.rows; ++row)
    {
        std::vector<std::pair<float, int32_t>> candidates(shape.columns);
        for(int column = 0; column < shape.columns; ++column)
        {
            candidates[column] = {
                input[static_cast<size_t>(row) * shape.columns + column],
                column,
            };
        }
        auto comparator = [&](const auto& lhs, const auto& rhs) {
            bool compare = candidate_before(
                lhs.first, lhs.second, rhs.first, rhs.second, shape.largest);
            return compare;
        };
        std::partial_sort(candidates.begin(),
                          candidates.begin() + shape.topk,
                          candidates.end(),
                          comparator);
        for(int rank = 0; rank < shape.topk; ++rank)
        {
            const size_t output_index =
                static_cast<size_t>(row) * shape.topk + rank;
            ret.values[output_index] = candidates[rank].first;
            ret.ids[output_index] = candidates[rank].second;
        }
    }
    return ret;
}

void normalize_output(Output& output, const Shape& shape)
{
    for(int row = 0; row < shape.rows; ++row)
    {
        std::vector<std::pair<float, int32_t>> selected(shape.topk);
        for(int rank = 0; rank < shape.topk; ++rank)
        {
            const size_t output_index =
                static_cast<size_t>(row) * shape.topk + rank;
            selected[rank] = {
                output.values[output_index],
                output.ids[output_index],
            };
        }
        auto comparator = [&](const auto& lhs, const auto& rhs) {
            bool compare = candidate_before(
                lhs.first, lhs.second, rhs.first, rhs.second, shape.largest);
            return compare;
        };
        std::sort(selected.begin(), selected.end(), comparator);
        for(int rank = 0; rank < shape.topk; ++rank)
        {
            const size_t output_index =
                static_cast<size_t>(row) * shape.topk + rank;
            output.values[output_index] = selected[rank].first;
            output.ids[output_index] = selected[rank].second;
        }
    }
}

ErrorMetrics calculate_error(const Output& actual,
                             const Output& reference,
                             const Shape& shape)
{
    ErrorMetrics ret;
    if(actual.ids.size() != reference.ids.size() ||
       actual.values.size() != reference.values.size())
    {
        throw std::runtime_error("TopK output sizes do not match");
    }
    for(size_t index = 0; index < actual.ids.size(); ++index)
    {
        if(actual.ids[index] < 0 || actual.ids[index] >= shape.columns)
        {
            ++ret.invalid_ids;
        }
        if(actual.ids[index] != reference.ids[index])
        {
            ++ret.mismatched_ids;
        }
        const double value_error = std::abs(
            static_cast<double>(actual.values[index]) -
            reference.values[index]);
        ret.max_value_error = std::max(ret.max_value_error, value_error);
    }
    ret.passed = ret.invalid_ids == 0 &&
                 ret.mismatched_ids == 0 &&
                 ret.max_value_error <= kValueTolerance;
    return ret;
}

template <typename Function>
double benchmark_gpu(Function&& function)
{
    for(int iteration = 0; iteration < kWarmupIterations; ++iteration)
    {
        function();
    }
    HIP_CHECK(hipDeviceSynchronize());

    hipEvent_t start = nullptr;
    hipEvent_t stop = nullptr;
    HIP_CHECK(hipEventCreate(&start));
    HIP_CHECK(hipEventCreate(&stop));
    HIP_CHECK(hipEventRecord(start));
    for(int iteration = 0; iteration < kBenchmarkIterations; ++iteration)
    {
        function();
    }
    HIP_CHECK(hipEventRecord(stop));
    HIP_CHECK(hipEventSynchronize(stop));

    float milliseconds = 0.0f;
    HIP_CHECK(hipEventElapsedTime(&milliseconds, start, stop));
    HIP_CHECK(hipEventDestroy(start));
    HIP_CHECK(hipEventDestroy(stop));
    double ret = static_cast<double>(milliseconds) * 1000.0 /
                 kBenchmarkIterations;
    return ret;
}

template <int ItemsPerThread>
__global__ void fallback_topk_radix_kernel(const float* input,
                                           int32_t* output_ids,
                                           float* output_values,
                                           int columns,
                                           int topk,
                                           bool largest)
{
    using BlockRadixSort = hipcub::BlockRadixSort<float,
                                                  kFallbackBlockSize,
                                                  ItemsPerThread,
                                                  int32_t>;
    __shared__ typename BlockRadixSort::TempStorage sort_storage;

    float keys[ItemsPerThread];
    int32_t ids[ItemsPerThread];
    const int row = blockIdx.x;
#pragma unroll
    for(int item = 0; item < ItemsPerThread; ++item)
    {
        const int column = threadIdx.x + item * kFallbackBlockSize;
        if(column < columns)
        {
            keys[item] =
                input[static_cast<size_t>(row) * columns + column];
            ids[item] = column;
        }
        else
        {
            keys[item] = largest
                             ? -std::numeric_limits<float>::infinity()
                             : std::numeric_limits<float>::infinity();
            ids[item] = std::numeric_limits<int32_t>::max();
        }
    }

    if(largest)
    {
        BlockRadixSort(sort_storage).SortDescending(keys, ids);
    }
    else
    {
        BlockRadixSort(sort_storage).Sort(keys, ids);
    }

#pragma unroll
    for(int item = 0; item < ItemsPerThread; ++item)
    {
        const int rank = threadIdx.x * ItemsPerThread + item;
        if(rank < topk)
        {
            const size_t output_index =
                static_cast<size_t>(row) * topk + rank;
            output_values[output_index] = keys[item];
            output_ids[output_index] = ids[item];
        }
    }
}

void initialize_outputs(AiterTensor& ids, AiterTensor& values)
{
    HIP_CHECK(hipMemset(
        ids.data_ptr(), 0xff, ids.numel() * ids.element_size()));
    HIP_CHECK(hipMemset(
        values.data_ptr(), 0xff, values.numel() * values.element_size()));
}

Output collect_output(const AiterTensor& ids,
                      const AiterTensor& values,
                      const Shape& shape)
{
    Output ret;
    ret.ids = copy_to_host<int32_t>(ids);
    ret.values = copy_to_host<float>(values);
    normalize_output(ret, shape);
    return ret;
}

void launch_aiter_plain(AiterTensor& input,
                        AiterTensor& ids,
                        AiterTensor& values,
                        AiterTensor& workspace,
                        const Shape& shape)
{
    topk_plain(input,
               ids,
               values,
               shape.topk,
               shape.largest,
               std::nullopt,
               std::nullopt,
               -1,
               1,
               tensor_optional(workspace));
    HIP_CHECK(hipGetLastError());
}

void launch_aiter_per_row(AiterTensor& input,
                          AiterTensor& row_starts,
                          AiterTensor& row_ends,
                          AiterTensor& ids,
                          AiterTensor& values,
                          AiterTensor& workspace,
                          const Shape& shape)
{
    top_k_per_row_prefill(input,
                          row_starts,
                          row_ends,
                          ids,
                          tensor_optional(values),
                          shape.rows,
                          shape.columns,
                          1,
                          shape.topk,
                          tensor_optional(workspace),
                          true);
    HIP_CHECK(hipGetLastError());
}

void launch_fallback(AiterTensor& input,
                     AiterTensor& ids,
                     AiterTensor& values,
                     const Shape& shape)
{
    const float* input_pointer =
        static_cast<const float*>(input.data_ptr());
    int32_t* ids_pointer = static_cast<int32_t*>(ids.data_ptr());
    float* values_pointer = static_cast<float*>(values.data_ptr());
    if(shape.columns <= 256)
    {
        fallback_topk_radix_kernel<1><<<shape.rows, kFallbackBlockSize>>>(
            input_pointer,
            ids_pointer,
            values_pointer,
            shape.columns,
            shape.topk,
            shape.largest);
    }
    else if(shape.columns <= 512)
    {
        fallback_topk_radix_kernel<2><<<shape.rows, kFallbackBlockSize>>>(
            input_pointer,
            ids_pointer,
            values_pointer,
            shape.columns,
            shape.topk,
            shape.largest);
    }
    else if(shape.columns <= 1024)
    {
        fallback_topk_radix_kernel<4><<<shape.rows, kFallbackBlockSize>>>(
            input_pointer,
            ids_pointer,
            values_pointer,
            shape.columns,
            shape.topk,
            shape.largest);
    }
    else if(shape.columns <= 2048)
    {
        fallback_topk_radix_kernel<8><<<shape.rows, kFallbackBlockSize>>>(
            input_pointer,
            ids_pointer,
            values_pointer,
            shape.columns,
            shape.topk,
            shape.largest);
    }
    else
    {
        fallback_topk_radix_kernel<16><<<shape.rows, kFallbackBlockSize>>>(
            input_pointer,
            ids_pointer,
            values_pointer,
            shape.columns,
            shape.topk,
            shape.largest);
    }
    HIP_CHECK(hipGetLastError());
}

std::string shape_name(const Shape& shape)
{
    std::string ret = std::to_string(shape.rows) + "x" +
                      std::to_string(shape.columns) + " k=" +
                      std::to_string(shape.topk) +
                      (shape.largest ? " max" : " min");
    return ret;
}

std::vector<Result> run_shape(const Shape& shape,
                              int device,
                              bool run_plain,
                              bool run_per_row,
                              bool run_fallback,
                              bool run_cpu)
{
    if(shape.topk <= 0 || shape.topk > shape.columns ||
       shape.columns > kMaximumFallbackColumns)
    {
        throw std::runtime_error("Unsupported TopK test shape");
    }

    const std::vector<float> input_host = make_input(shape);
    AiterTensor input = AiterTensor::empty(
        {shape.rows, shape.columns}, AITER_DTYPE_fp32, device);
    AiterTensor ids = AiterTensor::empty(
        {shape.rows, shape.topk}, AITER_DTYPE_i32, device);
    AiterTensor values = AiterTensor::empty(
        {shape.rows, shape.topk}, AITER_DTYPE_fp32, device);
    copy_to_device(input, input_host);

    std::vector<Result> ret_arr;
    if(run_plain)
    {
        const int64_t workspace_size =
            topk_plain_workspace_size(shape.rows, shape.columns, shape.topk);
        AiterTensor workspace = AiterTensor::empty(
            {std::max<int64_t>(workspace_size, 1)}, AITER_DTYPE_u8, device);
        initialize_outputs(ids, values);
        auto launch = [&] {
            launch_aiter_plain(
                input, ids, values, workspace, shape);
        };
        Result result;
        result.implementation = "AITER topk_plain";
        result.microseconds = benchmark_gpu(launch);
        result.output = collect_output(ids, values, shape);
        ret_arr.push_back(std::move(result));
    }

    if(run_per_row && shape.largest)
    {
        std::vector<int32_t> row_starts_host(shape.rows, 0);
        std::vector<int32_t> row_ends_host(shape.rows, shape.columns);
        AiterTensor row_starts = AiterTensor::empty(
            {shape.rows}, AITER_DTYPE_i32, device);
        AiterTensor row_ends = AiterTensor::empty(
            {shape.rows}, AITER_DTYPE_i32, device);
        copy_to_device(row_starts, row_starts_host);
        copy_to_device(row_ends, row_ends_host);
        const int64_t workspace_size =
            topk_ob_workspace_size(
                shape.rows, shape.columns, shape.topk, false);
        AiterTensor workspace = AiterTensor::empty(
            {std::max<int64_t>(workspace_size, 1)}, AITER_DTYPE_u8, device);
        initialize_outputs(ids, values);
        auto launch = [&] {
            launch_aiter_per_row(input,
                                 row_starts,
                                 row_ends,
                                 ids,
                                 values,
                                 workspace,
                                 shape);
        };
        Result result;
        result.implementation = "AITER per-row";
        result.microseconds = benchmark_gpu(launch);
        result.output = collect_output(ids, values, shape);
        ret_arr.push_back(std::move(result));
    }

    if(run_fallback)
    {
        initialize_outputs(ids, values);
        auto launch = [&] {
            launch_fallback(input, ids, values, shape);
        };
        Result result;
        result.implementation = "HIP fallback";
        result.microseconds = benchmark_gpu(launch);
        result.output = collect_output(ids, values, shape);
        ret_arr.push_back(std::move(result));
    }

    std::optional<Output> cpu_reference;
    if(run_cpu)
    {
        const auto start = std::chrono::steady_clock::now();
        cpu_reference = calculate_cpu_reference(input_host, shape);
        const auto stop = std::chrono::steady_clock::now();
        const std::chrono::duration<double, std::micro> elapsed = stop - start;
        Result result;
        result.implementation = "CPU reference";
        result.microseconds = elapsed.count();
        result.output = cpu_reference.value();
        ret_arr.push_back(std::move(result));
    }

    const Output* reference = nullptr;
    if(cpu_reference.has_value())
    {
        reference = &cpu_reference.value();
    }
    else
    {
        for(const Result& result : ret_arr)
        {
            if(result.implementation == "HIP fallback")
            {
                reference = &result.output;
            }
        }
    }
    if(reference != nullptr)
    {
        for(Result& result : ret_arr)
        {
            result.error = calculate_error(
                result.output, *reference, shape);
            result.has_accuracy = true;
        }
    }

    double fallback_microseconds = 0.0;
    for(const Result& result : ret_arr)
    {
        if(result.implementation == "HIP fallback")
        {
            fallback_microseconds = result.microseconds;
        }
    }
    const double semantic_bytes =
        static_cast<double>(shape.rows) * shape.columns * sizeof(float) +
        static_cast<double>(shape.rows) * shape.topk *
            (sizeof(float) + sizeof(int32_t));
    for(Result& result : ret_arr)
    {
        result.effective_tbps =
            semantic_bytes / result.microseconds / 1.0e6;
        if(fallback_microseconds > 0.0)
        {
            result.speedup =
                fallback_microseconds / result.microseconds;
        }
    }
    return ret_arr;
}

void print_summary(
    const std::vector<std::pair<Shape, std::vector<Result>>>& all_results)
{
    std::cout << "\nSummary\n";
    std::cout << "Accuracy reference: CPU TopK\n\n";
    std::cout << std::left << std::setw(24) << "Shape"
              << std::setw(20) << "Implementation"
              << std::right << std::setw(12) << "Time (us)"
              << std::setw(12) << "TB/s"
              << std::setw(12) << "Speedup"
              << std::setw(13) << "ID mismatch"
              << std::setw(12) << "Invalid"
              << std::setw(14) << "Max value err"
              << std::setw(10) << "Status"
              << '\n';
    std::cout << std::string(127, '-') << '\n';

    for(const auto& entry : all_results)
    {
        const std::string shape = shape_name(entry.first);
        for(const Result& result : entry.second)
        {
            std::cout << std::left << std::setw(24) << shape
                      << std::setw(20) << result.implementation
                      << std::right << std::fixed << std::setprecision(3)
                      << std::setw(12) << result.microseconds
                      << std::setw(12) << result.effective_tbps
                      << std::setw(12)
                      << (result.speedup == 0.0
                              ? "-"
                              : std::to_string(result.speedup));
            if(result.has_accuracy)
            {
                std::cout << std::setw(13) << result.error.mismatched_ids
                          << std::setw(12) << result.error.invalid_ids
                          << std::scientific << std::setprecision(3)
                          << std::setw(14) << result.error.max_value_error
                          << std::setw(10)
                          << (result.error.passed ? "PASS" : "FAIL");
            }
            else
            {
                std::cout << std::setw(13) << "n/a"
                          << std::setw(12) << "n/a"
                          << std::setw(14) << "n/a"
                          << std::setw(10) << "n/a";
            }
            std::cout << '\n';
        }
    }
}

int run(bool query)
{
    int device = 0;
    HIP_CHECK(hipGetDevice(&device));
    hipDeviceProp_t properties{};
    HIP_CHECK(hipGetDeviceProperties(&properties, device));
    const std::string architecture = base_architecture(properties);
    if(!is_supported_architecture(architecture))
    {
        throw std::runtime_error(
            "Unsupported GPU architecture: " + architecture);
    }

    std::cout << "TopK plain comparison\n";
    std::cout << "GPU: " << properties.name << " (" << architecture << ")\n";
    std::cout << "Input and output values: FP32, indices: int32\n";
    std::cout << "GPU timing: " << kWarmupIterations << " warm-up and "
              << kBenchmarkIterations << " measured iterations.\n\n";

    bool run_plain = false;
    bool run_per_row = false;
    bool run_fallback = false;
    bool run_cpu = false;
    const char* selection_environment =
        std::getenv("AITER_TOPK_PLAIN_COMPARE");
    if(query)
    {
        run_plain = prompt_yes_no("Run AITER topk_plain");
        run_per_row =
            prompt_yes_no("Run alternate AITER per-row TopK");
        run_fallback = prompt_yes_no("Run standalone HIP fallback");
        run_cpu = prompt_yes_no("Run CPU accuracy reference");
    }
    else if(selection_environment == nullptr)
    {
        run_plain = true;
        run_per_row = true;
        run_fallback = true;
        run_cpu = true;
    }
    else
    {
        const std::string selection(selection_environment);
        const bool run_all = selection == "all";
        run_plain = run_all || selection == "plain";
        run_per_row = run_all || selection == "per-row";
        run_fallback = run_all || selection == "hip";
        run_cpu = run_all || selection == "cpu";
        if(selection != "all" && selection != "plain" &&
           selection != "per-row" && selection != "hip" &&
           selection != "cpu")
        {
            throw std::runtime_error(
                "AITER_TOPK_PLAIN_COMPARE must be all, plain, "
                "per-row, hip, or cpu");
        }
    }
    if(!run_plain && !run_per_row && !run_fallback && !run_cpu)
    {
        throw std::runtime_error("No comparison was selected");
    }

    aiter::setCurrentHIPStream(nullptr);
    std::vector<std::pair<Shape, std::vector<Result>>> all_results;
    for(const Shape& shape : kShapes)
    {
        std::cout << "Running " << shape_name(shape) << "...\n";
        all_results.emplace_back(
            shape,
            run_shape(shape,
                      device,
                      run_plain,
                      run_per_row,
                      run_fallback,
                      run_cpu));
    }
    print_summary(all_results);

    int ret = 0;
    for(const auto& entry : all_results)
    {
        for(const Result& result : entry.second)
        {
            if(result.has_accuracy && !result.error.passed)
            {
                ret = 1;
            }
        }
    }
    return ret;
}

} // namespace

int main(int argc, char* argv[])
{
    int ret = 0;
    try
    {
        if(argc > 2 || (argc == 2 && std::string(argv[1]) != "-q"))
        {
            throw std::runtime_error(
                "Usage: topk_plain_compare [-q]");
        }
        ret = run(argc == 2);
    }
    catch(const std::exception& exception)
    {
        std::cerr << "ERROR: " << exception.what() << '\n';
        ret = 1;
    }
    return ret;
}
