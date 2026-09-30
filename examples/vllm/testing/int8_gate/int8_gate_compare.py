# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

"""Compare vLLM's AITER INT8 gate routes on ROCm."""

import argparse
import os
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version

import torch
import torch.nn.functional as F

os.environ.setdefault("VLLM_ROCM_USE_AITER", "1")

import aiter  # noqa: E402
import vllm  # noqa: E402
import vllm._aiter_ops as vllm_aiter_ops  # noqa: E402


DEFAULT_SHAPES = (
    (1, 1280, 8192),
    (32, 8192, 1024),
    (256, 1280, 8192),
)
ABSOLUTE_TOLERANCE = 0.02
RELATIVE_TOLERANCE = 0.02


def parse_shape(value: str) -> tuple[int, int, int]:
    parts = value.lower().replace("x", ",").split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("shape must be M,N,K or MxNxK")
    ret = tuple(int(part) for part in parts)
    if any(dimension <= 0 for dimension in ret):
        raise argparse.ArgumentTypeError("shape dimensions must be positive")
    return ret


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shape",
        action="append",
        type=parse_shape,
        help="M,N,K shape; repeat for more shapes (defaults to three representative cases)",
    )
    parser.add_argument("--warmup", type=int, default=10, help="warm-up launches per implementation")
    parser.add_argument("--iterations", type=int, default=200, help="timed launches per implementation")
    ret = parser.parse_args()
    if ret.warmup < 0 or ret.iterations <= 0:
        parser.error("--warmup must be non-negative and --iterations must be positive")
    return ret


def architecture_name() -> str:
    ret = torch.cuda.get_device_properties(0).gcnArchName.split(":", 1)[0]
    return ret


def package_version(package_name: str) -> str:
    try:
        ret = version(package_name)
    except PackageNotFoundError:
        ret = "unknown"
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


def make_case(
    rows: int,
    columns: int,
    inner: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    torch.manual_seed(1234)
    activations = torch.randint(-16, 17, (rows, inner), device="cuda", dtype=torch.int8)
    weights = torch.randint(-16, 17, (columns, inner), device="cuda", dtype=torch.int8)
    activation_scales = torch.rand((rows, 1), device="cuda", dtype=torch.float32) * 0.01
    weight_scales = torch.rand((columns, 1), device="cuda", dtype=torch.float32) * 0.01
    reference = F.linear(
        activations.float() * activation_scales,
        weights.float() * weight_scales,
    ).bfloat16()
    ret = activations, weights, activation_scales, weight_scales, reference
    return ret


def relative_error(output: torch.Tensor, reference: torch.Tensor) -> float:
    difference = (output.float() - reference.float()).abs().mean()
    denominator = reference.float().abs().mean().clamp_min(1.0e-12)
    ret = (difference / denominator).item()
    return ret


def current_gate_support() -> bool:
    ret = bool(vllm_aiter_ops.rocm_aiter_ops.is_int8_linear_enabled())
    return ret


def current_route_status(case: tuple[torch.Tensor, ...]) -> str:
    try:
        vllm_aiter_ops._rocm_aiter_w8a8_gemm_impl(
            *case[:4],
            output_dtype=torch.bfloat16,
        )
    except RuntimeError as error:
        ret = f"FAIL ({str(error).splitlines()[0]})"
    else:
        ret = "PASS"
    return ret


def print_summary(rows: list[dict[str, object]]) -> None:
    headings = (
        ("Shape MxNxK", 20),
        ("Implementation", 29),
        ("Time (us)", 11),
        ("vs Triton", 11),
        ("Rel. error", 12),
        ("Status", 8),
    )
    print("  ".join(f"{name:<{width}}" for name, width in headings))
    print("-" * (sum(width for _, width in headings) + 2 * (len(headings) - 1)))
    for row in rows:
        speedup = row["speedup"]
        speedup_text = "-" if speedup is None else f"{speedup:.2f}x"
        print(
            f"{row['shape']:<20}  "
            f"{row['implementation']:<29}  "
            f"{row['microseconds']:<11.3f}  "
            f"{speedup_text:<11}  "
            f"{row['relative_error']:<12.6f}  "
            f"{row['status']:<8}"
        )


def main() -> None:
    arguments = parse_arguments()
    if not torch.cuda.is_available():
        raise RuntimeError("A ROCm GPU is required")

    architecture = architecture_name()
    device = torch.cuda.get_device_name(0)
    properties = torch.cuda.get_device_properties(0)
    print("vLLM AITER INT8 gate comparison")
    print(f"Device: {device}")
    print(f"Architecture: {architecture}")
    print(f"Compute units: {properties.multi_processor_count}")
    print(f"AITER version: {package_version('aiter')}")
    print(f"vLLM version: {vllm.__version__}")
    print(f"Shipped INT8 gate enabled: {current_gate_support()}")

    probe_case = make_case(32, 8192, 1024)
    print(f"Current vLLM route: {current_route_status(probe_case)}")
    print()

    shapes = arguments.shape if arguments.shape else DEFAULT_SHAPES
    rows = []
    for rows_count, columns, inner in shapes:
        activations, weights, activation_scales, weight_scales, reference = make_case(
            rows_count,
            columns,
            inner,
        )
        implementations = (
            (
                "gate-disabled Triton",
                lambda: aiter.gemm_a8w8_Triton(
                    activations,
                    weights,
                    activation_scales,
                    weight_scales,
                ),
            ),
            (
                "AITER default",
                lambda: aiter.gemm_a8w8(
                    activations,
                    weights,
                    activation_scales,
                    weight_scales,
                ),
            ),
            (
                "vLLM gate-enabled route",
                lambda: vllm_aiter_ops._rocm_aiter_w8a8_gemm_impl(
                    activations,
                    weights,
                    activation_scales,
                    weight_scales,
                    output_dtype=torch.bfloat16,
                ),
            ),
        )
        shape_rows = []
        triton_time = None
        for name, function in implementations:
            output = function()
            torch.testing.assert_close(
                output,
                reference,
                rtol=RELATIVE_TOLERANCE,
                atol=ABSOLUTE_TOLERANCE,
            )
            elapsed = benchmark_us(function, arguments.warmup, arguments.iterations)
            if triton_time is None:
                triton_time = elapsed
            shape_rows.append(
                {
                    "shape": f"{rows_count}x{columns}x{inner}",
                    "implementation": name,
                    "microseconds": elapsed,
                    "speedup": triton_time / elapsed,
                    "relative_error": relative_error(output, reference),
                    "status": "PASS",
                }
            )
        rows.extend(shape_rows)

    print_summary(rows)


if __name__ == "__main__":
    main()
