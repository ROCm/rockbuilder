// SPDX-License-Identifier: MIT
// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

#include "aiter_enum.h"

#include <hip/hip_fp16.h>
#include <hip/hip_fp8.h>
#include <hip/hip_runtime.h>
#include <rocblas/rocblas.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace aiter {
void wvSplitKQ_(void* in_a,
                void* in_b,
                void* out_c,
                const float* scale_a,
                const float* scale_b,
                int M_in,
                int K_in,
                int Kp_in,
                int N_in,
                hipStream_t stream,
                int CuCount,
                int warp_size,
                AiterDtype a_scalar_type,
                AiterDtype c_scalar_type);
int wvSplitKQGetSplitCount(int M, int K, int N, int CuCount, int warp_size);
void wvSplitKQSplitK_(void* in_a,
                      void* in_b,
                      void* out_c,
                      const float* scale_a,
                      const float* scale_b,
                      float* workspace,
                      int M,
                      int K,
                      int Kp,
                      int N,
                      hipStream_t stream,
                      int CuCount,
                      int warp_size,
                      int split_count,
                      AiterDtype a_scalar_type,
                      AiterDtype c_scalar_type);
} // namespace aiter

namespace {

constexpr int kWarmupIterations = 5;
constexpr int kBenchmarkIterations = 20;
constexpr float kAbsoluteTolerance = 1.0e-2f;
constexpr float kRelativeTolerance = 1.0e-2f;

struct Shape
{
    int rows;
    int columns;
    int inner;
};

constexpr Shape kShapes[] = {
    {1, 4, 16},
    {1, 7, 496},
    {1, 4096, 32768},
    {2, 60, 96},
    {3, 17, 6192},
    {3, 65, 1024},
    {4, 320, 16400},
    {4, 2048, 16384},
};

struct ErrorMetrics
{
    double max_absolute = 0.0;
    double max_relative = 0.0;
    double nrmse = 0.0;
    bool passed = true;
};

struct Result
{
    std::string implementation;
    double microseconds = 0.0;
    double effective_tflops = 0.0;
    double speedup = 0.0;
    int split_count = 0;
    std::vector<float> output;
    ErrorMetrics error;
    bool has_error = false;
};

void check_hip(hipError_t status, const char* expression)
{
    if(status != hipSuccess)
    {
        throw std::runtime_error(
            std::string(expression) + " failed: " + hipGetErrorString(status));
    }
}

void check_rocblas(rocblas_status status, const char* expression)
{
    if(status != rocblas_status_success)
    {
        throw std::runtime_error(
            std::string(expression) + " failed with rocBLAS status " +
            std::to_string(static_cast<int>(status)));
    }
}

#define HIP_CHECK(expression) check_hip((expression), #expression)
#define ROCBLAS_CHECK(expression) check_rocblas((expression), #expression)

template <typename T>
class DeviceBuffer
{
public:
    explicit DeviceBuffer(size_t count) : count_(count)
    {
        HIP_CHECK(hipMalloc(reinterpret_cast<void**>(&data_), count_ * sizeof(T)));
    }

    ~DeviceBuffer()
    {
        if(data_ != nullptr)
        {
            static_cast<void>(hipFree(data_));
        }
    }

    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;

    T* data()
    {
        T* ret = data_;
        return ret;
    }

    const T* data() const
    {
        const T* ret = data_;
        return ret;
    }

    size_t size() const
    {
        size_t ret = count_;
        return ret;
    }

    void copy_from(const std::vector<T>& source)
    {
        if(source.size() != count_)
        {
            throw std::runtime_error("DeviceBuffer source size mismatch");
        }
        HIP_CHECK(hipMemcpy(
            data_, source.data(), count_ * sizeof(T), hipMemcpyHostToDevice));
    }

    std::vector<T> copy_to_host() const
    {
        std::vector<T> ret_arr(count_);
        HIP_CHECK(hipMemcpy(
            ret_arr.data(), data_, count_ * sizeof(T), hipMemcpyDeviceToHost));
        return ret_arr;
    }

private:
    T* data_ = nullptr;
    size_t count_ = 0;
};

class RocblasHandle
{
public:
    RocblasHandle()
    {
        ROCBLAS_CHECK(rocblas_create_handle(&handle_));
        ROCBLAS_CHECK(rocblas_set_stream(handle_, nullptr));
    }

    ~RocblasHandle()
    {
        if(handle_ != nullptr)
        {
            rocblas_destroy_handle(handle_);
        }
    }

    rocblas_handle get() const
    {
        rocblas_handle ret = handle_;
        return ret;
    }

private:
    rocblas_handle handle_ = nullptr;
};

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

bool uses_fnuz(const std::string& architecture)
{
    bool ret = architecture == "gfx90a" || architecture == "gfx942";
    return ret;
}

float fp8_maximum(bool fnuz)
{
    float ret = fnuz ? 240.0f : 448.0f;
    return ret;
}

uint8_t encode_fp8(float value, bool fnuz)
{
    __hip_fp8_interpretation_t interpretation =
        fnuz ? __HIP_E4M3_FNUZ : __HIP_E4M3;
    uint8_t ret = static_cast<uint8_t>(
        __hip_cvt_float_to_fp8(value, __HIP_SATFINITE, interpretation));
    return ret;
}

float decode_fp8(uint8_t bits, bool fnuz)
{
    float ret = 0.0f;
    if(fnuz)
    {
        __hip_fp8_e4m3_fnuz value;
        value.__x = static_cast<__hip_fp8_storage_t>(bits);
        ret = static_cast<float>(value);
    }
    else
    {
        __hip_fp8_e4m3 value;
        value.__x = static_cast<__hip_fp8_storage_t>(bits);
        ret = static_cast<float>(value);
    }
    return ret;
}

std::vector<float> make_input(size_t count, float phase)
{
    std::vector<float> ret_arr(count);
    for(size_t index = 0; index < count; ++index)
    {
        float x = static_cast<float>(index) + phase;
        ret_arr[index] = 0.75f * std::sin(x * 0.017f) +
                         0.25f * std::cos(x * 0.031f);
    }
    return ret_arr;
}

float calculate_scale(const std::vector<float>& values, bool fnuz)
{
    float maximum = 0.0f;
    for(float value : values)
    {
        maximum = std::max(maximum, std::abs(value));
    }
    float ret = maximum / fp8_maximum(fnuz);
    if(ret == 0.0f)
    {
        ret = 1.0f;
    }
    return ret;
}

std::vector<uint8_t> quantize(
    const std::vector<float>& values, float scale, bool fnuz)
{
    std::vector<uint8_t> ret_arr(values.size());
    for(size_t index = 0; index < values.size(); ++index)
    {
        ret_arr[index] = encode_fp8(values[index] / scale, fnuz);
    }
    return ret_arr;
}

std::vector<float> calculate_cpu_reference(const std::vector<uint8_t>& x,
                                           const std::vector<uint8_t>& weight,
                                           const Shape& shape,
                                           float x_scale,
                                           float weight_scale,
                                           bool fnuz)
{
    std::vector<float> ret_arr(
        static_cast<size_t>(shape.rows) * shape.columns, 0.0f);
    const float combined_scale = x_scale * weight_scale;
    for(int row = 0; row < shape.rows; ++row)
    {
        for(int column = 0; column < shape.columns; ++column)
        {
            float accumulator = 0.0f;
            for(int inner = 0; inner < shape.inner; ++inner)
            {
                float a = decode_fp8(
                    x[static_cast<size_t>(row) * shape.inner + inner], fnuz);
                float b = decode_fp8(
                    weight[static_cast<size_t>(column) * shape.inner + inner], fnuz);
                accumulator += a * b;
            }
            ret_arr[static_cast<size_t>(row) * shape.columns + column] =
                accumulator * combined_scale;
        }
    }
    return ret_arr;
}

std::vector<float> half_to_float(const std::vector<__half>& values)
{
    std::vector<float> ret_arr(values.size());
    for(size_t index = 0; index < values.size(); ++index)
    {
        ret_arr[index] = __half2float(values[index]);
    }
    return ret_arr;
}

ErrorMetrics calculate_error(const std::vector<float>& actual,
                             const std::vector<float>& reference)
{
    if(actual.size() != reference.size())
    {
        throw std::runtime_error("Accuracy vectors have different sizes");
    }

    ErrorMetrics ret;
    double squared_error = 0.0;
    double squared_reference = 0.0;
    for(size_t index = 0; index < actual.size(); ++index)
    {
        double difference =
            std::abs(static_cast<double>(actual[index]) - reference[index]);
        double reference_magnitude = std::abs(static_cast<double>(reference[index]));
        double relative = difference / std::max(reference_magnitude, 1.0e-12);
        ret.max_absolute = std::max(ret.max_absolute, difference);
        ret.max_relative = std::max(ret.max_relative, relative);
        squared_error += difference * difference;
        squared_reference +=
            static_cast<double>(reference[index]) * reference[index];
        if(difference >
           kAbsoluteTolerance + kRelativeTolerance * reference_magnitude)
        {
            ret.passed = false;
        }
    }
    ret.nrmse = std::sqrt(
        squared_error / std::max(squared_reference, std::numeric_limits<double>::min()));
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

__global__ void dequantize_fp8_kernel(
    const uint8_t* input, __half* output, float scale, size_t count)
{
    size_t index = static_cast<size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if(index < count)
    {
        float decoded = 0.0f;
#if defined(__gfx90a__) || defined(__gfx942__)
        __hip_fp8_e4m3_fnuz value;
        value.__x = static_cast<__hip_fp8_storage_t>(input[index]);
        decoded = static_cast<float>(value);
#else
        __hip_fp8_e4m3 value;
        value.__x = static_cast<__hip_fp8_storage_t>(input[index]);
        decoded = static_cast<float>(value);
#endif
        output[index] = __float2half(decoded * scale);
    }
}

void launch_dequantize(
    const DeviceBuffer<uint8_t>& input, DeviceBuffer<__half>& output, float scale)
{
    constexpr int block_size = 256;
    int grid_size =
        static_cast<int>((input.size() + block_size - 1) / block_size);
    dequantize_fp8_kernel<<<grid_size, block_size>>>(
        input.data(), output.data(), scale, input.size());
    HIP_CHECK(hipGetLastError());
}

void launch_rocblas_fallback(rocblas_handle handle,
                             const DeviceBuffer<uint8_t>& x,
                             const DeviceBuffer<uint8_t>& weight,
                             DeviceBuffer<__half>& x_half,
                             DeviceBuffer<__half>& weight_half,
                             DeviceBuffer<__half>& output,
                             const Shape& shape,
                             float x_scale,
                             float weight_scale)
{
    launch_dequantize(x, x_half, x_scale);
    launch_dequantize(weight, weight_half, weight_scale);

    const float alpha = 1.0f;
    const float beta = 0.0f;
    ROCBLAS_CHECK(rocblas_gemm_ex(handle,
                                  rocblas_operation_transpose,
                                  rocblas_operation_none,
                                  shape.columns,
                                  shape.rows,
                                  shape.inner,
                                  &alpha,
                                  weight_half.data(),
                                  rocblas_datatype_f16_r,
                                  shape.inner,
                                  x_half.data(),
                                  rocblas_datatype_f16_r,
                                  shape.inner,
                                  &beta,
                                  output.data(),
                                  rocblas_datatype_f16_r,
                                  shape.columns,
                                  output.data(),
                                  rocblas_datatype_f16_r,
                                  shape.columns,
                                  rocblas_datatype_f32_r,
                                  rocblas_gemm_algo_standard,
                                  0,
                                  0));
}

std::string shape_name(const Shape& shape)
{
    std::string ret = std::to_string(shape.rows) + "x" +
                      std::to_string(shape.columns) + "x" +
                      std::to_string(shape.inner);
    return ret;
}

std::vector<Result> run_shape(const Shape& shape,
                              const hipDeviceProp_t& properties,
                              bool fnuz,
                              bool run_legacy,
                              bool run_splitk,
                              bool run_fallback,
                              bool run_cpu,
                              rocblas_handle rocblas)
{
    std::vector<float> x_host = make_input(
        static_cast<size_t>(shape.rows) * shape.inner, 11.0f);
    std::vector<float> weight_host = make_input(
        static_cast<size_t>(shape.columns) * shape.inner, 97.0f);
    float x_scale = calculate_scale(x_host, fnuz);
    float weight_scale = calculate_scale(weight_host, fnuz);
    std::vector<uint8_t> x_quantized = quantize(x_host, x_scale, fnuz);
    std::vector<uint8_t> weight_quantized =
        quantize(weight_host, weight_scale, fnuz);

    DeviceBuffer<uint8_t> x_device(x_quantized.size());
    DeviceBuffer<uint8_t> weight_device(weight_quantized.size());
    DeviceBuffer<__half> output_device(
        static_cast<size_t>(shape.rows) * shape.columns);
    DeviceBuffer<float> x_scale_device(1);
    DeviceBuffer<float> weight_scale_device(1);
    x_device.copy_from(x_quantized);
    weight_device.copy_from(weight_quantized);
    x_scale_device.copy_from(std::vector<float>{x_scale});
    weight_scale_device.copy_from(std::vector<float>{weight_scale});

    std::vector<Result> ret_arr;
    if(run_legacy)
    {
        auto launch_legacy = [&] {
            aiter::wvSplitKQ_(weight_device.data(),
                              x_device.data(),
                              output_device.data(),
                              weight_scale_device.data(),
                              x_scale_device.data(),
                              shape.columns,
                              shape.inner,
                              shape.inner,
                              shape.rows,
                              nullptr,
                              properties.multiProcessorCount,
                              properties.warpSize,
                              AITER_DTYPE_fp8,
                              AITER_DTYPE_fp16);
            HIP_CHECK(hipGetLastError());
        };
        Result result;
        result.implementation = "AITER legacy";
        result.microseconds = benchmark_gpu(launch_legacy);
        result.output = half_to_float(output_device.copy_to_host());
        ret_arr.push_back(std::move(result));
    }

    if(run_splitk)
    {
        DeviceBuffer<float> workspace(
            static_cast<size_t>(16) * shape.rows * shape.columns);
        int split_count = 0;
        const char* split_environment =
            std::getenv("AITER_WVSPLITKQ_SPLIT_COUNT");
        if(split_environment == nullptr)
        {
            split_count = aiter::wvSplitKQGetSplitCount(
                shape.columns,
                shape.inner,
                shape.rows,
                properties.multiProcessorCount,
                properties.warpSize);
        }
        else
        {
            split_count = std::stoi(split_environment);
            if(split_count != 1 && split_count != 2 && split_count != 4 &&
               split_count != 8 && split_count != 16)
            {
                throw std::runtime_error(
                    "AITER_WVSPLITKQ_SPLIT_COUNT must be 1, 2, 4, 8, or 16");
            }
        }
        auto launch_splitk = [&] {
            aiter::wvSplitKQSplitK_(weight_device.data(),
                                    x_device.data(),
                                    output_device.data(),
                                    weight_scale_device.data(),
                                    x_scale_device.data(),
                                    workspace.data(),
                                    shape.columns,
                                    shape.inner,
                                    shape.inner,
                                    shape.rows,
                                    nullptr,
                                    properties.multiProcessorCount,
                                    properties.warpSize,
                                    split_count,
                                    AITER_DTYPE_fp8,
                                    AITER_DTYPE_fp16);
            HIP_CHECK(hipGetLastError());
        };
        Result result;
        result.implementation = "AITER split-K";
        result.split_count = split_count;
        result.microseconds = benchmark_gpu(launch_splitk);
        result.output = half_to_float(output_device.copy_to_host());
        ret_arr.push_back(std::move(result));
    }

    if(run_fallback)
    {
        DeviceBuffer<__half> x_half(x_quantized.size());
        DeviceBuffer<__half> weight_half(weight_quantized.size());
        auto launch_fallback = [&] {
            launch_rocblas_fallback(rocblas,
                                    x_device,
                                    weight_device,
                                    x_half,
                                    weight_half,
                                    output_device,
                                    shape,
                                    x_scale,
                                    weight_scale);
        };
        Result result;
        result.implementation = "HIP dequant + rocBLAS";
        result.microseconds = benchmark_gpu(launch_fallback);
        result.output = half_to_float(output_device.copy_to_host());
        ret_arr.push_back(std::move(result));
    }

    if(run_cpu)
    {
        auto start = std::chrono::steady_clock::now();
        std::vector<float> output = calculate_cpu_reference(
            x_quantized,
            weight_quantized,
            shape,
            x_scale,
            weight_scale,
            fnuz);
        auto stop = std::chrono::steady_clock::now();
        std::chrono::duration<double, std::micro> elapsed = stop - start;
        Result result;
        result.implementation = "CPU FP32 reference";
        result.microseconds = elapsed.count();
        result.output = std::move(output);
        ret_arr.push_back(std::move(result));
    }

    const std::vector<float>* reference = nullptr;
    for(const Result& result : ret_arr)
    {
        if(result.implementation == "CPU FP32 reference")
        {
            reference = &result.output;
        }
    }
    if(reference == nullptr && run_fallback)
    {
        for(const Result& result : ret_arr)
        {
            if(result.implementation == "HIP dequant + rocBLAS")
            {
                reference = &result.output;
            }
        }
    }
    if(reference != nullptr)
    {
        for(Result& result : ret_arr)
        {
            result.error = calculate_error(result.output, *reference);
            result.has_error = true;
        }
    }
    double legacy_microseconds = 0.0;
    for(const Result& result : ret_arr)
    {
        if(result.implementation == "AITER legacy")
        {
            legacy_microseconds = result.microseconds;
        }
    }
    const double operations =
        2.0 * shape.rows * shape.columns * shape.inner;
    for(Result& result : ret_arr)
    {
        result.effective_tflops =
            operations / (result.microseconds * 1.0e6);
        if(legacy_microseconds > 0.0)
        {
            result.speedup = legacy_microseconds / result.microseconds;
        }
    }
    return ret_arr;
}

void print_summary(
    const std::vector<std::pair<Shape, std::vector<Result>>>& all_results,
    const std::string& reference_name)
{
    std::cout << "\nSummary\n";
    std::cout << "Accuracy reference: " << reference_name << "\n\n";
    std::cout << std::left << std::setw(14) << "Shape"
              << std::setw(24) << "Implementation"
              << std::right << std::setw(12) << "Time (us)"
              << std::setw(10) << "Splits"
              << std::setw(14) << "Eff TFLOP/s"
              << std::setw(12) << "Speedup"
              << std::setw(14) << "Max abs"
              << std::setw(14) << "Max rel"
              << std::setw(14) << "NRMSE"
              << std::setw(10) << "Status"
              << '\n';
    std::cout << std::string(138, '-') << '\n';

    for(const auto& entry : all_results)
    {
        const std::string shape = shape_name(entry.first);
        for(const Result& result : entry.second)
        {
            std::cout << std::left << std::setw(14) << shape
                      << std::setw(24) << result.implementation
                      << std::right << std::fixed << std::setprecision(3)
                      << std::setw(12) << result.microseconds
                      << std::setw(10)
                      << (result.split_count == 0
                              ? "-"
                              : std::to_string(result.split_count))
                      << std::setw(14) << result.effective_tflops
                      << std::setw(12)
                      << (result.speedup == 0.0
                              ? "-"
                              : std::to_string(result.speedup));
            if(result.has_error)
            {
                std::cout << std::scientific << std::setprecision(3)
                          << std::setw(14) << result.error.max_absolute
                          << std::setw(14) << result.error.max_relative
                          << std::setw(14) << result.error.nrmse
                          << std::setw(10) << (result.error.passed ? "PASS" : "FAIL");
            }
            else
            {
                std::cout << std::setw(14) << "n/a"
                          << std::setw(14) << "n/a"
                          << std::setw(14) << "n/a"
                          << std::setw(10) << "n/a";
            }
            std::cout << '\n';
        }
    }
}

bool is_supported_architecture(const std::string& architecture)
{
    bool ret = architecture == "gfx90a" || architecture == "gfx942" ||
               architecture == "gfx1100" || architecture == "gfx1200" ||
               architecture == "gfx1201";
    return ret;
}

int run(bool query)
{
    int device = 0;
    HIP_CHECK(hipGetDevice(&device));
    hipDeviceProp_t properties{};
    HIP_CHECK(hipGetDeviceProperties(&properties, device));
    std::string architecture = properties.gcnArchName;
    size_t feature_separator = architecture.find(':');
    if(feature_separator != std::string::npos)
    {
        architecture.resize(feature_separator);
    }
    if(!is_supported_architecture(architecture))
    {
        throw std::runtime_error(
            "Expected gfx90a, gfx942, gfx1100, gfx1200, or gfx1201; found " +
            architecture);
    }

    std::cout << "Wave Split-K FP8 comparison\n";
    std::cout << "GPU: " << properties.name << " (" << architecture << ")\n";
    std::cout << "Each GPU benchmark uses " << kWarmupIterations
              << " warm-up and " << kBenchmarkIterations << " measured iterations.\n\n";

    bool run_legacy = false;
    bool run_splitk = false;
    bool run_fallback = false;
    bool run_cpu = false;
    const char* selection_environment = std::getenv("AITER_WVSPLITKQ_COMPARE");
    if(query)
    {
        run_legacy = prompt_yes_no("Run legacy AITER wvSplitKQ");
        run_splitk = architecture != "gfx942" &&
                     prompt_yes_no("Run optimized AITER split-K");
        run_fallback =
            prompt_yes_no("Run HIP FP8 dequantization plus rocBLAS FP16 GEMM");
        run_cpu = prompt_yes_no("Run CPU FP32 accuracy reference");
    }
    else if(selection_environment == nullptr)
    {
        run_legacy = true;
        run_splitk = architecture != "gfx942";
        run_fallback = true;
        run_cpu = true;
    }
    else
    {
        const std::string selection(selection_environment);
        const bool run_all = selection == "all";
        run_legacy = run_all || selection == "legacy";
        run_splitk =
            architecture != "gfx942" && (run_all || selection == "splitk");
        run_fallback = run_all || selection == "rocblas";
        run_cpu = run_all || selection == "cpu";
        if(selection != "all" && selection != "legacy" &&
           selection != "splitk" && selection != "rocblas" &&
           selection != "cpu")
        {
            throw std::runtime_error(
                "AITER_WVSPLITKQ_COMPARE must be all, legacy, splitk, "
                "rocblas, or cpu");
        }
    }
    if(!run_legacy && !run_splitk && !run_fallback && !run_cpu)
    {
        throw std::runtime_error("No comparison was selected");
    }

    std::unique_ptr<RocblasHandle> rocblas;
    if(run_fallback)
    {
        rocblas = std::make_unique<RocblasHandle>();
    }

    std::vector<std::pair<Shape, std::vector<Result>>> all_results;
    bool fnuz = uses_fnuz(architecture);
    for(const Shape& shape : kShapes)
    {
        std::cout << "Running shape " << shape_name(shape) << "...\n";
        rocblas_handle handle = rocblas == nullptr ? nullptr : rocblas->get();
        all_results.emplace_back(
            shape,
            run_shape(shape,
                      properties,
                      fnuz,
                      run_legacy,
                      run_splitk,
                      run_fallback,
                      run_cpu,
                      handle));
    }

    std::string reference_name = "none";
    if(run_cpu)
    {
        reference_name = "CPU FP32";
    }
    else if(run_fallback)
    {
        reference_name = "HIP dequantization + rocBLAS";
    }
    print_summary(all_results, reference_name);

    int ret = 0;
    for(const auto& entry : all_results)
    {
        for(const Result& result : entry.second)
        {
            if(result.has_error && !result.error.passed)
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
            throw std::runtime_error("Usage: wvsplitkq_compare [-q]");
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
