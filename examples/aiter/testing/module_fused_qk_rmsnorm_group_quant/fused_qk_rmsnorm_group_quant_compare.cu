// SPDX-License-Identifier: MIT
// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

#define AITER_NO_TORCH_TYPES
#include "aiter_stream.h"
#include "fused_qk_rmsnorm_group_quant.h"

#include <hip/hip_fp16.h>
#include <hip/hip_fp8.h>
#include <hip/hip_runtime.h>

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
constexpr int kRmsBlockSize = 256;
constexpr int kQuantBlockSize = 128;
constexpr int kGroupSize = 128;
constexpr float kEpsilon = 1.0e-6f;

struct Shape
{
    int tokens;
    int q_hidden;
    int k_hidden;
    bool residual;
};

constexpr Shape kShapes[] = {
    {17, 128, 128, false},
    {32, 1536, 512, false},
    {32, 1536, 512, true},
    {256, 1536, 512, false},
    {256, 1536, 512, true},
    {513, 4096, 1024, true},
    {8192, 1536, 512, false},
    {8192, 1536, 512, true},
    {16384, 1536, 512, false},
    {16384, 1536, 512, true},
    {32768, 1536, 512, false},
    {32768, 1536, 512, true},
};

struct ErrorMetrics
{
    double max_absolute = 0.0;
    double max_relative = 0.0;
    double nrmse = 0.0;
    bool passed = true;
};

struct Output
{
    std::vector<float> q_dequantized;
    std::vector<float> q_scales;
    std::vector<float> k;
    std::vector<float> residual;
};

struct Result
{
    std::string implementation;
    double microseconds = 0.0;
    double effective_tbps = 0.0;
    double speedup = 0.0;
    Output output;
    ErrorMetrics q_error;
    ErrorMetrics scale_error;
    ErrorMetrics k_error;
    ErrorMetrics residual_error;
    size_t invalid_values = 0;
    bool has_accuracy = false;
    bool passed = true;
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
    bool ret = architecture == "gfx90a" || architecture == "gfx1100" ||
               architecture == "gfx1201";
    return ret;
}

bool uses_fnuz(const std::string& architecture)
{
    bool ret = architecture == "gfx90a";
    return ret;
}

float fp8_maximum(bool fnuz)
{
    float ret = fnuz ? 240.0f : 448.0f;
    return ret;
}

uint8_t encode_fp8(float value, bool fnuz)
{
    const __hip_fp8_interpretation_t interpretation =
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

std::vector<__half> make_input(size_t count, float phase, float amplitude, float offset)
{
    std::vector<__half> ret_arr(count);
    for(size_t index = 0; index < count; ++index)
    {
        const float x = static_cast<float>(index) + phase;
        const float value = offset +
                            amplitude * (0.75f * std::sin(x * 0.017f) +
                                         0.25f * std::cos(x * 0.031f));
        ret_arr[index] = __float2half(value);
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

void initialize_outputs(AiterTensor& q_quantized,
                        AiterTensor& q_scales,
                        AiterTensor& k_output,
                        AiterTensor* residual_output,
                        bool fnuz)
{
    const int fp8_sentinel = fnuz ? 0x80 : 0x7f;
    HIP_CHECK(hipMemset(q_quantized.data_ptr(),
                        fp8_sentinel,
                        q_quantized.numel() * q_quantized.element_size()));
    HIP_CHECK(hipMemset(q_scales.data_ptr(),
                        0xff,
                        q_scales.numel() * q_scales.element_size()));
    HIP_CHECK(hipMemset(k_output.data_ptr(),
                        0xff,
                        k_output.numel() * k_output.element_size()));
    if(residual_output != nullptr)
    {
        HIP_CHECK(hipMemset(residual_output->data_ptr(),
                            0xff,
                            residual_output->numel() *
                                residual_output->element_size()));
    }
}

std::optional<aiter_tensor_t> tensor_optional(AiterTensor& tensor)
{
    std::optional<aiter_tensor_t> ret(
        static_cast<aiter_tensor_t&>(tensor));
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

__device__ uint8_t encode_device_fp8(float value)
{
    uint8_t ret = 0;
#if defined(__gfx90a__)
    ret = static_cast<uint8_t>(
        __hip_cvt_float_to_fp8(value, __HIP_SATFINITE, __HIP_E4M3_FNUZ));
#else
    ret = static_cast<uint8_t>(
        __hip_cvt_float_to_fp8(value, __HIP_SATFINITE, __HIP_E4M3));
#endif
    return ret;
}

__global__ void rmsnorm_fallback_kernel(const __half* input,
                                        const __half* weight,
                                        const __half* residual,
                                        __half* output,
                                        __half* residual_output,
                                        int hidden,
                                        float epsilon)
{
    __shared__ float reduction[kRmsBlockSize];
    __shared__ float inverse_rms;

    const int row = blockIdx.x;
    float square_sum = 0.0f;
    for(int column = threadIdx.x; column < hidden; column += blockDim.x)
    {
        const size_t index = static_cast<size_t>(row) * hidden + column;
        float value = __half2float(input[index]);
        if(residual != nullptr)
        {
            value += __half2float(residual[index]);
            residual_output[index] = __float2half(value);
        }
        square_sum += value * value;
    }
    reduction[threadIdx.x] = square_sum;
    __syncthreads();

    for(int offset = blockDim.x / 2; offset > 0; offset /= 2)
    {
        if(threadIdx.x < offset)
        {
            reduction[threadIdx.x] += reduction[threadIdx.x + offset];
        }
        __syncthreads();
    }
    if(threadIdx.x == 0)
    {
        inverse_rms = rsqrtf(reduction[0] / hidden + epsilon);
    }
    __syncthreads();

    for(int column = threadIdx.x; column < hidden; column += blockDim.x)
    {
        const size_t index = static_cast<size_t>(row) * hidden + column;
        float value = __half2float(input[index]);
        if(residual != nullptr)
        {
            value += __half2float(residual[index]);
        }
        value *= inverse_rms * __half2float(weight[column]);
        output[index] = __float2half(value);
    }
}

__global__ void group_quant_fallback_kernel(const __half* input,
                                            uint8_t* output,
                                            float* scales,
                                            int hidden,
                                            int group_size,
                                            float maximum)
{
    __shared__ float reduction[kQuantBlockSize];
    __shared__ float quant_scale;

    const int groups_per_row = hidden / group_size;
    const int row = blockIdx.x / groups_per_row;
    const int group = blockIdx.x % groups_per_row;
    const int group_offset = row * hidden + group * group_size;

    float thread_maximum = 1.0e-10f;
    for(int element = threadIdx.x; element < group_size; element += blockDim.x)
    {
        thread_maximum =
            fmaxf(thread_maximum, fabsf(__half2float(input[group_offset + element])));
    }
    reduction[threadIdx.x] = thread_maximum;
    __syncthreads();

    for(int offset = blockDim.x / 2; offset > 0; offset /= 2)
    {
        if(threadIdx.x < offset)
        {
            reduction[threadIdx.x] =
                fmaxf(reduction[threadIdx.x], reduction[threadIdx.x + offset]);
        }
        __syncthreads();
    }
    if(threadIdx.x == 0)
    {
        quant_scale = reduction[0] / maximum;
        scales[static_cast<size_t>(row) * groups_per_row + group] = quant_scale;
    }
    __syncthreads();

    for(int element = threadIdx.x; element < group_size; element += blockDim.x)
    {
        const float value = __half2float(input[group_offset + element]) /
                            quant_scale;
        output[group_offset + element] = encode_device_fp8(value);
    }
}

void launch_fallback(const AiterTensor& q,
                     const AiterTensor& q_weight,
                     const AiterTensor* residual,
                     AiterTensor& q_normalized,
                     AiterTensor& q_quantized,
                     AiterTensor& q_scales,
                     AiterTensor* residual_output,
                     const AiterTensor& k,
                     const AiterTensor& k_weight,
                     AiterTensor& k_output,
                     const Shape& shape,
                     bool fnuz)
{
    const __half* residual_pointer =
        residual == nullptr ? nullptr : static_cast<const __half*>(residual->data_ptr());
    __half* residual_output_pointer =
        residual_output == nullptr ? nullptr : static_cast<__half*>(residual_output->data_ptr());

    rmsnorm_fallback_kernel<<<shape.tokens, kRmsBlockSize>>>(
        static_cast<const __half*>(q.data_ptr()),
        static_cast<const __half*>(q_weight.data_ptr()),
        residual_pointer,
        static_cast<__half*>(q_normalized.data_ptr()),
        residual_output_pointer,
        shape.q_hidden,
        kEpsilon);
    rmsnorm_fallback_kernel<<<shape.tokens, kRmsBlockSize>>>(
        static_cast<const __half*>(k.data_ptr()),
        static_cast<const __half*>(k_weight.data_ptr()),
        nullptr,
        static_cast<__half*>(k_output.data_ptr()),
        nullptr,
        shape.k_hidden,
        kEpsilon);

    const int quant_blocks = shape.tokens * shape.q_hidden / kGroupSize;
    group_quant_fallback_kernel<<<quant_blocks, kQuantBlockSize>>>(
        static_cast<const __half*>(q_normalized.data_ptr()),
        static_cast<uint8_t*>(q_quantized.data_ptr()),
        static_cast<float*>(q_scales.data_ptr()),
        shape.q_hidden,
        kGroupSize,
        fp8_maximum(fnuz));
    HIP_CHECK(hipGetLastError());
}

void launch_fused(AiterTensor& q_quantized,
                  AiterTensor& q_scales,
                  AiterTensor& q,
                  AiterTensor& q_weight,
                  AiterTensor& k_output,
                  AiterTensor& k,
                  AiterTensor& k_weight,
                  AiterTensor* residual_output,
                  AiterTensor* residual)
{
    std::optional<aiter_tensor_t> residual_output_optional = std::nullopt;
    std::optional<aiter_tensor_t> residual_optional = std::nullopt;
    if(residual_output != nullptr)
    {
        residual_output_optional = tensor_optional(*residual_output);
        residual_optional = tensor_optional(*residual);
    }

    aiter::fused_qk_rmsnorm_group_quant(tensor_optional(q_quantized),
                                        tensor_optional(q_scales),
                                        tensor_optional(q),
                                        tensor_optional(q_weight),
                                        kEpsilon,
                                        std::nullopt,
                                        tensor_optional(k_output),
                                        residual_output_optional,
                                        tensor_optional(k),
                                        tensor_optional(k_weight),
                                        kEpsilon,
                                        residual_optional,
                                        kGroupSize,
                                        false,
                                        false);
    HIP_CHECK(hipGetLastError());
}

Output calculate_cpu_reference(const std::vector<__half>& q,
                               const std::vector<__half>& q_weight,
                               const std::vector<__half>& k,
                               const std::vector<__half>& k_weight,
                               const std::vector<__half>& residual,
                               const Shape& shape,
                               bool fnuz)
{
    Output ret;
    ret.q_dequantized.resize(q.size());
    ret.q_scales.resize(
        static_cast<size_t>(shape.tokens) * shape.q_hidden / kGroupSize);
    ret.k.resize(k.size());
    if(shape.residual)
    {
        ret.residual.resize(q.size());
    }

    std::vector<float> q_normalized(q.size());
    for(int row = 0; row < shape.tokens; ++row)
    {
        float square_sum = 0.0f;
        for(int column = 0; column < shape.q_hidden; ++column)
        {
            const size_t index = static_cast<size_t>(row) * shape.q_hidden + column;
            float value = __half2float(q[index]);
            if(shape.residual)
            {
                value += __half2float(residual[index]);
                ret.residual[index] = __half2float(__float2half(value));
            }
            q_normalized[index] = value;
            square_sum += value * value;
        }
        const float inverse_rms =
            1.0f / std::sqrt(square_sum / shape.q_hidden + kEpsilon);
        for(int column = 0; column < shape.q_hidden; ++column)
        {
            const size_t index = static_cast<size_t>(row) * shape.q_hidden + column;
            q_normalized[index] *= inverse_rms * __half2float(q_weight[column]);
        }
    }

    const int groups_per_row = shape.q_hidden / kGroupSize;
    for(int row = 0; row < shape.tokens; ++row)
    {
        for(int group = 0; group < groups_per_row; ++group)
        {
            const size_t offset =
                static_cast<size_t>(row) * shape.q_hidden + group * kGroupSize;
            float maximum = 1.0e-10f;
            for(int element = 0; element < kGroupSize; ++element)
            {
                maximum = std::max(maximum, std::abs(q_normalized[offset + element]));
            }
            const float scale = maximum / fp8_maximum(fnuz);
            ret.q_scales[static_cast<size_t>(row) * groups_per_row + group] = scale;
            for(int element = 0; element < kGroupSize; ++element)
            {
                const uint8_t bits =
                    encode_fp8(q_normalized[offset + element] / scale, fnuz);
                ret.q_dequantized[offset + element] = decode_fp8(bits, fnuz) * scale;
            }
        }
    }

    for(int row = 0; row < shape.tokens; ++row)
    {
        float square_sum = 0.0f;
        for(int column = 0; column < shape.k_hidden; ++column)
        {
            const size_t index = static_cast<size_t>(row) * shape.k_hidden + column;
            const float value = __half2float(k[index]);
            square_sum += value * value;
        }
        const float inverse_rms =
            1.0f / std::sqrt(square_sum / shape.k_hidden + kEpsilon);
        for(int column = 0; column < shape.k_hidden; ++column)
        {
            const size_t index = static_cast<size_t>(row) * shape.k_hidden + column;
            const float value =
                __half2float(k[index]) * inverse_rms * __half2float(k_weight[column]);
            ret.k[index] = __half2float(__float2half(value));
        }
    }
    return ret;
}

Output collect_output(const AiterTensor& q_quantized,
                      const AiterTensor& q_scales,
                      const AiterTensor& k_output,
                      const AiterTensor* residual_output,
                      const Shape& shape,
                      bool fnuz)
{
    Output ret;
    const std::vector<uint8_t> quantized =
        copy_to_host<uint8_t>(q_quantized);
    ret.q_scales = copy_to_host<float>(q_scales);
    ret.k = half_to_float(copy_to_host<__half>(k_output));
    if(residual_output != nullptr)
    {
        ret.residual =
            half_to_float(copy_to_host<__half>(*residual_output));
    }

    ret.q_dequantized.resize(quantized.size());
    const int groups_per_row = shape.q_hidden / kGroupSize;
    for(int row = 0; row < shape.tokens; ++row)
    {
        for(int column = 0; column < shape.q_hidden; ++column)
        {
            const size_t index = static_cast<size_t>(row) * shape.q_hidden + column;
            const size_t scale_index =
                static_cast<size_t>(row) * groups_per_row + column / kGroupSize;
            ret.q_dequantized[index] =
                decode_fp8(quantized[index], fnuz) * ret.q_scales[scale_index];
        }
    }
    return ret;
}

ErrorMetrics calculate_error(const std::vector<float>& actual,
                             const std::vector<float>& reference,
                             double absolute_tolerance,
                             double relative_tolerance,
                             double nrmse_tolerance)
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
        if(!std::isfinite(actual[index]) || !std::isfinite(reference[index]))
        {
            ret.max_absolute = std::numeric_limits<double>::infinity();
            ret.max_relative = std::numeric_limits<double>::infinity();
            ret.passed = false;
            continue;
        }
        const double difference =
            std::abs(static_cast<double>(actual[index]) - reference[index]);
        const double reference_magnitude =
            std::abs(static_cast<double>(reference[index]));
        const double relative =
            difference / std::max(reference_magnitude, 1.0e-12);
        ret.max_absolute = std::max(ret.max_absolute, difference);
        ret.max_relative = std::max(ret.max_relative, relative);
        squared_error += difference * difference;
        squared_reference +=
            static_cast<double>(reference[index]) * reference[index];
        if(difference >
           absolute_tolerance + relative_tolerance * reference_magnitude)
        {
            ret.passed = false;
        }
    }
    ret.nrmse = std::sqrt(
        squared_error /
        std::max(squared_reference, std::numeric_limits<double>::min()));
    ret.passed = ret.passed && ret.nrmse <= nrmse_tolerance;
    return ret;
}

size_t count_invalid_values(const Output& output)
{
    size_t ret = 0;
    const std::vector<const std::vector<float>*> arrays = {
        &output.q_dequantized,
        &output.q_scales,
        &output.k,
        &output.residual,
    };
    for(const std::vector<float>* values : arrays)
    {
        for(float value : *values)
        {
            if(!std::isfinite(value))
            {
                ++ret;
            }
        }
    }
    return ret;
}

void calculate_accuracy(Result& result, const Output& reference, bool has_residual)
{
    result.q_error = calculate_error(
        result.output.q_dequantized, reference.q_dequantized, 8.0e-2, 8.0e-2, 3.0e-2);
    result.scale_error = calculate_error(
        result.output.q_scales, reference.q_scales, 1.0e-5, 2.0e-3, 2.0e-3);
    result.k_error = calculate_error(
        result.output.k, reference.k, 5.0e-3, 5.0e-3, 5.0e-3);
    if(has_residual)
    {
        result.residual_error = calculate_error(
            result.output.residual, reference.residual, 1.0e-3, 1.0e-3, 1.0e-3);
    }
    result.has_accuracy = true;
    result.passed = result.q_error.passed && result.scale_error.passed &&
                    result.k_error.passed &&
                    (!has_residual || result.residual_error.passed) &&
                    result.invalid_values == 0;
}

double semantic_bytes(const Shape& shape)
{
    const double q_elements =
        static_cast<double>(shape.tokens) * shape.q_hidden;
    const double k_elements =
        static_cast<double>(shape.tokens) * shape.k_hidden;
    const double scale_elements =
        static_cast<double>(shape.tokens) * shape.q_hidden / kGroupSize;
    double ret = 2.0 * q_elements + 2.0 * shape.q_hidden +
                 2.0 * k_elements + 2.0 * shape.k_hidden +
                 q_elements + 4.0 * scale_elements + 2.0 * k_elements;
    if(shape.residual)
    {
        ret += 4.0 * q_elements;
    }
    return ret;
}

std::string shape_name(const Shape& shape)
{
    std::string ret = std::to_string(shape.tokens) + "x" +
                      std::to_string(shape.q_hidden) + "+" +
                      std::to_string(shape.k_hidden) +
                      (shape.residual ? "+res" : "");
    return ret;
}

std::vector<Result> run_shape(const Shape& shape,
                              int device,
                              bool fnuz,
                              bool run_fused,
                              bool run_fallback,
                              bool run_cpu)
{
    const std::vector<__half> q_host = make_input(
        static_cast<size_t>(shape.tokens) * shape.q_hidden, 11.0f, 1.0f, 0.0f);
    const std::vector<__half> q_weight_host =
        make_input(shape.q_hidden, 37.0f, 0.25f, 0.9f);
    const std::vector<__half> k_host = make_input(
        static_cast<size_t>(shape.tokens) * shape.k_hidden, 71.0f, 0.8f, 0.0f);
    const std::vector<__half> k_weight_host =
        make_input(shape.k_hidden, 103.0f, 0.2f, 1.0f);
    std::vector<__half> residual_host;
    if(shape.residual)
    {
        residual_host = make_input(
            static_cast<size_t>(shape.tokens) * shape.q_hidden, 151.0f, 0.2f, 0.0f);
    }

    AiterTensor q =
        AiterTensor::empty({shape.tokens, shape.q_hidden}, AITER_DTYPE_fp16, device);
    AiterTensor q_weight =
        AiterTensor::empty({shape.q_hidden}, AITER_DTYPE_fp16, device);
    AiterTensor k =
        AiterTensor::empty({shape.tokens, shape.k_hidden}, AITER_DTYPE_fp16, device);
    AiterTensor k_weight =
        AiterTensor::empty({shape.k_hidden}, AITER_DTYPE_fp16, device);
    AiterTensor q_quantized =
        AiterTensor::empty({shape.tokens, shape.q_hidden}, AITER_DTYPE_fp8, device);
    AiterTensor q_scales = AiterTensor::empty(
        {shape.tokens, shape.q_hidden / kGroupSize}, AITER_DTYPE_fp32, device);
    AiterTensor k_output =
        AiterTensor::empty({shape.tokens, shape.k_hidden}, AITER_DTYPE_fp16, device);
    AiterTensor q_normalized =
        AiterTensor::empty({shape.tokens, shape.q_hidden}, AITER_DTYPE_fp16, device);
    std::optional<AiterTensor> residual;
    std::optional<AiterTensor> residual_output;
    if(shape.residual)
    {
        residual.emplace(AiterTensor::empty(
            {shape.tokens, shape.q_hidden}, AITER_DTYPE_fp16, device));
        residual_output.emplace(AiterTensor::empty(
            {shape.tokens, shape.q_hidden}, AITER_DTYPE_fp16, device));
    }

    copy_to_device(q, q_host);
    copy_to_device(q_weight, q_weight_host);
    copy_to_device(k, k_host);
    copy_to_device(k_weight, k_weight_host);
    if(shape.residual)
    {
        copy_to_device(residual.value(), residual_host);
    }

    std::vector<Result> ret_arr;
    if(run_fused)
    {
        initialize_outputs(q_quantized,
                           q_scales,
                           k_output,
                           shape.residual ? &residual_output.value() : nullptr,
                           fnuz);
        auto launch = [&] {
            launch_fused(q_quantized,
                         q_scales,
                         q,
                         q_weight,
                         k_output,
                         k,
                         k_weight,
                         shape.residual ? &residual_output.value() : nullptr,
                         shape.residual ? &residual.value() : nullptr);
        };
        Result result;
        result.implementation = "AITER fused";
        result.microseconds = benchmark_gpu(launch);
        result.output = collect_output(q_quantized,
                                       q_scales,
                                       k_output,
                                       shape.residual ? &residual_output.value() : nullptr,
                                       shape,
                                       fnuz);
        result.invalid_values = count_invalid_values(result.output);
        ret_arr.push_back(std::move(result));
    }

    if(run_fallback)
    {
        initialize_outputs(q_quantized,
                           q_scales,
                           k_output,
                           shape.residual ? &residual_output.value() : nullptr,
                           fnuz);
        auto launch = [&] {
            launch_fallback(q,
                            q_weight,
                            shape.residual ? &residual.value() : nullptr,
                            q_normalized,
                            q_quantized,
                            q_scales,
                            shape.residual ? &residual_output.value() : nullptr,
                            k,
                            k_weight,
                            k_output,
                            shape,
                            fnuz);
        };
        Result result;
        result.implementation = "Separate HIP";
        result.microseconds = benchmark_gpu(launch);
        result.output = collect_output(q_quantized,
                                       q_scales,
                                       k_output,
                                       shape.residual ? &residual_output.value() : nullptr,
                                       shape,
                                       fnuz);
        result.invalid_values = count_invalid_values(result.output);
        ret_arr.push_back(std::move(result));
    }

    std::optional<Output> cpu_reference;
    if(run_cpu)
    {
        const auto start = std::chrono::steady_clock::now();
        cpu_reference = calculate_cpu_reference(q_host,
                                                q_weight_host,
                                                k_host,
                                                k_weight_host,
                                                residual_host,
                                                shape,
                                                fnuz);
        const auto stop = std::chrono::steady_clock::now();
        const std::chrono::duration<double, std::micro> elapsed = stop - start;
        Result result;
        result.implementation = "CPU reference";
        result.microseconds = elapsed.count();
        result.output = cpu_reference.value();
        ret_arr.push_back(std::move(result));
    }

    if(cpu_reference.has_value())
    {
        for(Result& result : ret_arr)
        {
            calculate_accuracy(result, cpu_reference.value(), shape.residual);
        }
    }

    double fallback_microseconds = 0.0;
    for(const Result& result : ret_arr)
    {
        if(result.implementation == "Separate HIP")
        {
            fallback_microseconds = result.microseconds;
        }
    }
    const double bytes = semantic_bytes(shape);
    for(Result& result : ret_arr)
    {
        result.effective_tbps = bytes / result.microseconds / 1.0e6;
        if(fallback_microseconds > 0.0)
        {
            result.speedup = fallback_microseconds / result.microseconds;
        }
    }
    return ret_arr;
}

void print_summary(
    const std::vector<std::pair<Shape, std::vector<Result>>>& all_results)
{
    std::cout << "\nSummary\n";
    std::cout << std::left << std::setw(22) << "Shape"
              << std::setw(16) << "Implementation"
              << std::right << std::setw(12) << "Time (us)"
              << std::setw(12) << "TB/s"
              << std::setw(12) << "Speedup"
              << std::setw(13) << "Q NRMSE"
              << std::setw(13) << "Scale max"
              << std::setw(13) << "K max"
              << std::setw(13) << "Res max"
              << std::setw(11) << "Invalid"
              << std::setw(10) << "Status"
              << '\n';
    std::cout << std::string(145, '-') << '\n';

    for(const auto& entry : all_results)
    {
        const std::string shape = shape_name(entry.first);
        for(const Result& result : entry.second)
        {
            std::cout << std::left << std::setw(22) << shape
                      << std::setw(16) << result.implementation
                      << std::right << std::fixed << std::setprecision(3)
                      << std::setw(12) << result.microseconds
                      << std::setw(12) << result.effective_tbps
                      << std::setw(12)
                      << (result.speedup == 0.0
                              ? "-"
                              : std::to_string(result.speedup));
            if(result.has_accuracy)
            {
                std::cout << std::scientific << std::setprecision(3)
                          << std::setw(13) << result.q_error.nrmse
                          << std::setw(13) << result.scale_error.max_absolute
                          << std::setw(13) << result.k_error.max_absolute
                          << std::setw(13)
                          << (entry.first.residual
                                  ? result.residual_error.max_absolute
                                  : 0.0)
                          << std::setw(11) << result.invalid_values
                          << std::setw(10)
                          << (result.passed ? "PASS" : "FAIL");
            }
            else
            {
                std::cout << std::setw(13) << "n/a"
                          << std::setw(13) << "n/a"
                          << std::setw(13) << "n/a"
                          << std::setw(13) << "n/a"
                          << std::setw(11) << result.invalid_values
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
            "Expected gfx90a, gfx1100, or gfx1201; found " + architecture);
    }

    std::cout << "Fused QK RMSNorm group-quant comparison\n";
    std::cout << "GPU: " << properties.name << " (" << architecture << ")\n";
    std::cout << "Input: FP16, output: FP8 E4M3, group size: "
              << kGroupSize << "\n";
    std::cout << "GPU timing: " << kWarmupIterations << " warm-up and "
              << kBenchmarkIterations << " measured iterations.\n\n";

    bool run_fused = false;
    bool run_fallback = false;
    bool run_cpu = false;
    const char* selection_environment =
        std::getenv("AITER_FUSED_QK_COMPARE");
    if(query)
    {
        run_fused = prompt_yes_no("Run current AITER fused kernel");
        run_fallback =
            prompt_yes_no("Run separate HIP RMSNorm and quantization");
        run_cpu = prompt_yes_no("Run scalar CPU accuracy reference");
    }
    else if(selection_environment == nullptr)
    {
        run_fused = true;
        run_fallback = true;
        run_cpu = true;
    }
    else
    {
        const std::string selection(selection_environment);
        const bool run_all = selection == "all";
        run_fused = run_all || selection == "fused";
        run_fallback = run_all || selection == "fallback";
        run_cpu = run_all || selection == "cpu";
        if(selection != "all" && selection != "fused" &&
           selection != "fallback" && selection != "cpu")
        {
            throw std::runtime_error(
                "AITER_FUSED_QK_COMPARE must be all, fused, fallback, or cpu");
        }
    }
    if(!run_fused && !run_fallback && !run_cpu)
    {
        throw std::runtime_error("No comparison was selected");
    }

    aiter::setCurrentHIPStream(nullptr);
    const bool fnuz = uses_fnuz(architecture);
    std::vector<std::pair<Shape, std::vector<Result>>> all_results;
    for(const Shape& shape : kShapes)
    {
        std::cout << "Running " << shape_name(shape) << "...\n";
        all_results.emplace_back(
            shape,
            run_shape(shape,
                      device,
                      fnuz,
                      run_fused,
                      run_fallback,
                      run_cpu));
    }
    print_summary(all_results);

    int ret = 0;
    for(const auto& entry : all_results)
    {
        for(const Result& result : entry.second)
        {
            if(result.has_accuracy && !result.passed)
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
                "Usage: fused_qk_rmsnorm_group_quant_compare [-q]");
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
