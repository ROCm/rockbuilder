# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

"""Compare vLLM's shipped, stock, and forced fast FP8 decoder paths."""

import argparse
from collections.abc import Callable

import torch
import triton
import vllm
import vllm.model_executor.layers.quantization.utils.fp8_utils as fp8_utils


BLOCK_SIZE = 128
FP8_MAXIMUM = 448.0
ABSOLUTE_TOLERANCE = 0.02
RELATIVE_TOLERANCE = 0.02
TRITON_CONFIG = {
    "BLOCK_SIZE_M": 64,
    "BLOCK_SIZE_N": 128,
    "BLOCK_SIZE_K": 128,
    "GROUP_SIZE_M": 32,
    "num_warps": 4,
    "num_stages": 2,
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=32, help="activation rows")
    parser.add_argument("--columns", type=int, default=7168, help="output columns")
    parser.add_argument("--inner", type=int, default=5120, help="reduction dimension")
    parser.add_argument("--warmup", type=int, default=5, help="warm-up launches per implementation")
    parser.add_argument("--iterations", type=int, default=20, help="timed launches per implementation")
    ret = parser.parse_args()
    dimensions = (ret.rows, ret.columns, ret.inner)
    if any(dimension <= 0 for dimension in dimensions):
        parser.error("all dimensions must be positive")
    if any(dimension % BLOCK_SIZE != 0 for dimension in (ret.columns, ret.inner)):
        parser.error("--columns and --inner must be multiples of 128")
    if ret.warmup < 0 or ret.iterations <= 0:
        parser.error("--warmup must be non-negative and --iterations must be positive")
    return ret


def architecture_name() -> str:
    ret = torch.cuda.get_device_properties(0).gcnArchName.split(":", 1)[0]
    return ret


def make_case(
    rows: int,
    columns: int,
    inner: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    torch.manual_seed(1234)
    activations_source = torch.randn(rows, inner, device="cuda", dtype=torch.bfloat16) / 4
    weights_source = torch.randn(columns, inner, device="cuda", dtype=torch.bfloat16) / 4

    weights_view = weights_source.float().view(
        columns // BLOCK_SIZE,
        BLOCK_SIZE,
        inner // BLOCK_SIZE,
        BLOCK_SIZE,
    )
    weight_scales = weights_view.abs().amax(dim=(1, 3)).clamp(min=1.0e-6) / FP8_MAXIMUM
    weights = (
        (weights_view / weight_scales[:, None, :, None])
        .clamp(-FP8_MAXIMUM, FP8_MAXIMUM)
        .to(torch.float8_e4m3fn)
        .view(columns, inner)
    )

    activations_view = activations_source.float().view(rows, inner // BLOCK_SIZE, BLOCK_SIZE)
    activation_scales = activations_view.abs().amax(dim=2).clamp(min=1.0e-6) / FP8_MAXIMUM
    activations = (
        (activations_view / activation_scales[:, :, None])
        .clamp(-FP8_MAXIMUM, FP8_MAXIMUM)
        .to(torch.float8_e4m3fn)
        .view(rows, inner)
    )

    dequantized_activations = (
        activations.float().view(rows, inner // BLOCK_SIZE, BLOCK_SIZE)
        * activation_scales[:, :, None]
    ).view(rows, inner)
    dequantized_weights = (
        weights.float().view(
            columns // BLOCK_SIZE,
            BLOCK_SIZE,
            inner // BLOCK_SIZE,
            BLOCK_SIZE,
        )
        * weight_scales[:, None, :, None]
    ).view(columns, inner)
    reference = (dequantized_activations @ dequantized_weights.t()).to(torch.bfloat16)
    ret = activations, weights, activation_scales.contiguous(), weight_scales.contiguous(), reference
    return ret


def launch_private_kernel(
    activations: torch.Tensor,
    weights: torch.Tensor,
    activation_scales: torch.Tensor,
    weight_scales: torch.Tensor,
    fast_decode: bool,
) -> torch.Tensor:
    rows, inner = activations.shape
    columns = weights.shape[0]
    output = torch.empty((rows, columns), device=activations.device, dtype=torch.bfloat16)
    kernel_activations = activations.view(torch.uint8) if fast_decode else activations
    kernel_weights = weights.view(torch.uint8) if fast_decode else weights

    def grid(meta: dict[str, int]) -> tuple[int]:
        block_count = triton.cdiv(rows, meta["BLOCK_SIZE_M"]) * triton.cdiv(columns, meta["BLOCK_SIZE_N"])
        ret = (block_count,)
        return ret

    fp8_utils._w8a8_triton_block_scaled_mm[grid](
        kernel_activations,
        kernel_weights,
        output,
        activation_scales,
        weight_scales,
        rows,
        columns,
        inner,
        BLOCK_SIZE,
        BLOCK_SIZE,
        kernel_activations.stride(0),
        kernel_activations.stride(1),
        kernel_weights.stride(1),
        kernel_weights.stride(0),
        output.stride(0),
        output.stride(1),
        activation_scales.stride(0),
        activation_scales.stride(1),
        weight_scales.stride(1),
        weight_scales.stride(0),
        FAST_FP8_DECODE=fast_decode,
        **TRITON_CONFIG,
    )
    ret = output
    return ret


def benchmark_us(function: Callable[[], torch.Tensor], warmup: int, iterations: int) -> float:
    for _ in range(warmup):
        function()
    torch.cuda.synchronize()
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(iterations):
        function()
    end.record()
    end.synchronize()
    ret = start.elapsed_time(end) * 1000.0 / iterations
    return ret


def relative_error(output: torch.Tensor, reference: torch.Tensor) -> float:
    difference = (output.float() - reference.float()).abs().mean()
    denominator = reference.float().abs().mean().clamp_min(1.0e-12)
    ret = (difference / denominator).item()
    return ret


def nan_propagation_status() -> str:
    activations = torch.full((1, BLOCK_SIZE), float("nan"), device="cuda").to(torch.float8_e4m3fn)
    weights = torch.ones((BLOCK_SIZE, BLOCK_SIZE), device="cuda").to(torch.float8_e4m3fn)
    activation_scales = torch.ones((1, 1), device="cuda")
    weight_scales = torch.ones((1, 1), device="cuda")
    output = fp8_utils.w8a8_triton_block_scaled_mm(
        activations,
        weights,
        activation_scales,
        weight_scales,
        [BLOCK_SIZE, BLOCK_SIZE],
        torch.bfloat16,
    )
    ret = "PASS" if torch.isnan(output).all().item() else "FAIL"
    return ret


def print_summary(rows: list[dict[str, object]]) -> None:
    headings = (
        ("Implementation", 24),
        ("Time (us)", 12),
        ("vs stock", 11),
        ("Rel. error", 13),
        ("Status", 8),
    )
    print("  ".join(f"{name:<{width}}" for name, width in headings))
    print("-" * (sum(width for _, width in headings) + 2 * (len(headings) - 1)))
    for row in rows:
        speedup_text = f"{row['speedup']:.2f}x"
        print(
            f"{row['implementation']:<24}  "
            f"{row['microseconds']:<12.3f}  "
            f"{speedup_text:<11}  "
            f"{row['relative_error']:<13.6f}  "
            f"{row['status']:<8}"
        )


def main() -> None:
    arguments = parse_arguments()
    if not torch.cuda.is_available():
        raise RuntimeError("A ROCm GPU is required")

    architecture = architecture_name()
    device = torch.cuda.get_device_name(0)
    properties = torch.cuda.get_device_properties(0)
    case = make_case(arguments.rows, arguments.columns, arguments.inner)
    activations, weights, activation_scales, weight_scales, reference = case
    block_size = [BLOCK_SIZE, BLOCK_SIZE]
    shipped_eligible = fp8_utils._gfx90a_fast_fp8_eligible(
        activations,
        weights,
        activation_scales,
        weight_scales,
        block_size,
    )

    print("vLLM fast FP8 decoder comparison")
    print(f"Device: {device}")
    print(f"Architecture: {architecture}")
    print(f"Compute units: {properties.multi_processor_count}")
    print(f"vLLM version: {vllm.__version__}")
    print(f"Shape MxNxK: {arguments.rows}x{arguments.columns}x{arguments.inner}")
    print(f"Shipped fast decoder eligible: {shipped_eligible}")
    print(f"Shipped NaN propagation: {nan_propagation_status()}")
    print()

    implementations = (
        (
            "shipped wrapper",
            lambda: fp8_utils.w8a8_triton_block_scaled_mm(
                activations,
                weights,
                activation_scales,
                weight_scales,
                block_size,
                torch.bfloat16,
            ),
        ),
        (
            "stock decoder",
            lambda: launch_private_kernel(
                activations,
                weights,
                activation_scales,
                weight_scales,
                False,
            ),
        ),
        (
            "forced fast decoder",
            lambda: launch_private_kernel(
                activations,
                weights,
                activation_scales,
                weight_scales,
                True,
            ),
        ),
    )

    results = []
    stock_time = None
    for name, function in implementations:
        output = function()
        torch.testing.assert_close(
            output,
            reference,
            rtol=RELATIVE_TOLERANCE,
            atol=ABSOLUTE_TOLERANCE,
        )
        elapsed = benchmark_us(function, arguments.warmup, arguments.iterations)
        if name == "stock decoder":
            stock_time = elapsed
        results.append(
            {
                "implementation": name,
                "microseconds": elapsed,
                "relative_error": relative_error(output, reference),
                "status": "PASS",
            }
        )

    if stock_time is None:
        raise RuntimeError("stock decoder timing was not recorded")
    for result in results:
        result["speedup"] = stock_time / result["microseconds"]
    print_summary(results)


if __name__ == "__main__":
    main()
