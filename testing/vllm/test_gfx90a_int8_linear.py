#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

"""Run the vLLM AITER INT8 routing tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import find_source_test, run_test_command, validate_test_environment  # noqa: E402


RELATIVE_TEST_PATH = "tests/rocm/aiter/test_gfx90a_int8_linear.py"


def main() -> int:
    ret = 1
    try:
        validate_test_environment()
        test_file = find_source_test("vllm", RELATIVE_TEST_PATH)
    except RuntimeError as error:
        print(f"vLLM AITER INT8 routing: FAILED\n{error}", file=sys.stderr)
    else:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "--import-mode=importlib",
            f"--confcutdir={test_file.parent}",
            "-q",
            str(test_file),
        ]
        ret = run_test_command("vLLM AITER INT8 routing", command)
    return ret


if __name__ == "__main__":
    sys.exit(main())
