#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

"""Run the Rockbuilder vLLM AITER INT8 runtime boundary matrix."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import ROCKBUILDER_ROOT, run_test_command, validate_test_environment  # noqa: E402


INT8_GATE_COMPARE = (
    ROCKBUILDER_ROOT / "examples" / "vllm" / "testing" / "int8_gate" / "int8_gate_compare.py"
)
SHAPES_BY_ARCHITECTURE = {
    "gfx1201": (
        "8x11008x4096",
        "9x11008x4096",
        "15x11008x4096",
        "16x11008x4096",
        "15x1280x8192",
        "16x1280x8192",
        "32x4096x11008",
        "40x4096x11008",
        "64x28672x8192",
        "80x28672x8192",
        "128x28672x4096",
        "256x28672x4096",
        "8x6144x4096",
        "16x6144x4096",
    ),
    "gfx1100": (
        "32x1280x8192",
        "48x1280x8192",
        "64x1280x8192",
        "80x1280x8192",
        "96x1280x8192",
        "128x1280x8192",
        "256x1280x8192",
        "512x1280x8192",
        "16x11008x4096",
        "24x11008x4096",
        "32x11008x4096",
        "64x11008x4096",
        "96x11008x4096",
        "128x11008x4096",
        "256x11008x4096",
        "512x11008x4096",
        "16x4096x11008",
        "24x4096x11008",
        "32x4096x11008",
        "48x4096x11008",
        "64x4096x11008",
        "80x4096x11008",
        "128x4096x11008",
        "256x4096x11008",
        "1x28672x4096",
        "16x28672x4096",
        "32x28672x4096",
        "48x28672x4096",
        "64x28672x4096",
        "80x28672x4096",
        "128x28672x4096",
        "256x28672x4096",
    ),
    "gfx90a": (
        "63x1280x8192",
        "64x1280x8192",
        "128x1280x8192",
        "256x1280x8192",
        "32x11008x4096",
        "128x11008x4096",
        "32x4096x11008",
        "128x4096x11008",
        "32x28672x4096",
        "128x28672x4096",
    ),
}


def visible_gpu_architecture() -> str:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("a visible ROCm GPU is required")
    ret = torch.cuda.get_device_properties(0).gcnArchName.split(":", 1)[0]
    return ret


def main() -> int:
    ret = 1
    try:
        validate_test_environment()
        architecture = visible_gpu_architecture()
        if architecture not in SHAPES_BY_ARCHITECTURE:
            supported = ", ".join(SHAPES_BY_ARCHITECTURE)
            raise RuntimeError(f"unsupported GPU architecture {architecture}; expected one of: {supported}")
        if not INT8_GATE_COMPARE.is_file():
            raise RuntimeError(f"could not find {INT8_GATE_COMPARE}")
    except RuntimeError as error:
        print(f"vLLM AITER INT8 runtime: FAILED\n{error}", file=sys.stderr)
    else:
        command = [
            sys.executable,
            str(INT8_GATE_COMPARE),
            "--warmup",
            "20",
            "--iterations",
            "300",
        ]
        for shape in SHAPES_BY_ARCHITECTURE[architecture]:
            command.extend(("--shape", shape))
        ret = run_test_command(f"vLLM AITER INT8 runtime ({architecture})", command)
    return ret


if __name__ == "__main__":
    sys.exit(main())
