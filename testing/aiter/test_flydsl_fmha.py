#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

"""Run the focused AITER FlyDSL FlashAttention validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import find_source_test, run_test_command, validate_test_environment  # noqa: E402


RELATIVE_TEST_PATH = "op_tests/flydsl_tests/test_flydsl_fmha.py"
TEST_CASES = (
    "test_flydsl_fmha_correctness_bf16[2-1024-8-128]",
    "test_flydsl_fmha_correctness_causal_small",
)


def main() -> int:
    ret = 1
    try:
        validate_test_environment()
        test_file = find_source_test("aiter", RELATIVE_TEST_PATH)
    except RuntimeError as error:
        print(f"AITER FlyDSL FlashAttention: FAILED\n{error}", file=sys.stderr)
    else:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "--import-mode=importlib",
            "-q",
            *(f"{test_file}::{test_case}" for test_case in TEST_CASES),
        ]
        ret = run_test_command("AITER FlyDSL FlashAttention", command)
    return ret


if __name__ == "__main__":
    sys.exit(main())
