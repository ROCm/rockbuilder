#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.

"""Common utilities for Rockbuilder AITER and vLLM validation scripts."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


ROCKBUILDER_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_PACKAGES = ("aiter", "vllm")


def validate_test_environment() -> None:
    """Validate the ROCm SDK, active virtual environment, and required packages."""
    errors = []
    rocm_home_value = os.environ.get("ROCM_HOME")
    virtual_env_value = os.environ.get("VIRTUAL_ENV")

    if not rocm_home_value:
        errors.append("ROCM_HOME is not set")
    elif not Path(rocm_home_value).is_dir():
        errors.append(f"ROCM_HOME does not exist: {rocm_home_value}")

    if not virtual_env_value:
        errors.append("a Python virtual environment is not active; source ./init_rcb_env.sh")
    elif Path(sys.prefix).resolve() != Path(virtual_env_value).resolve():
        errors.append(
            f"VIRTUAL_ENV points to {virtual_env_value}, but Python is running from {sys.prefix}"
        )

    package_specs = {}
    for package_name in REQUIRED_PACKAGES:
        package_specs[package_name] = importlib.util.find_spec(package_name)
        if package_specs[package_name] is None:
            errors.append(f"the active virtual environment does not contain {package_name}")
        elif virtual_env_value and package_specs[package_name].origin:
            package_path = Path(package_specs[package_name].origin).resolve()
            try:
                package_path.relative_to(Path(virtual_env_value).resolve())
            except ValueError:
                errors.append(f"{package_name} resolves outside the active virtual environment: {package_path}")

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"test environment validation failed:\n{details}")

    print(f"ROCM_HOME: {Path(rocm_home_value).resolve()}")
    print(f"Virtual environment: {Path(virtual_env_value).resolve()}")
    for package_name, package_spec in package_specs.items():
        print(f"{package_name}: {package_spec.origin}")


def find_source_test(
    application_name: str,
    relative_test_path: str,
) -> Path:
    """Find one application source test, with an optional source-directory override."""
    override_name = f"{application_name.upper()}_SOURCE_DIR"
    override_value = os.environ.get(override_name)
    candidates = []

    if override_value:
        candidate = Path(override_value).resolve() / relative_test_path
        if candidate.is_file():
            candidates.append(candidate)
    else:
        source_root = ROCKBUILDER_ROOT / "src_apps"
        candidates = sorted(source_root.glob(f"{application_name}*/{relative_test_path}"))

    if not candidates:
        hint = (
            f"set {override_name} to the checked-out {application_name} source directory"
            if override_value
            else f"check out {application_name}, or set {override_name} to its source directory"
        )
        raise RuntimeError(f"could not find {relative_test_path}; {hint}")
    if len(candidates) > 1:
        matches = "\n".join(f"- {candidate}" for candidate in candidates)
        raise RuntimeError(
            f"found multiple {application_name} source tests:\n{matches}\n"
            f"set {override_name} to select one source directory"
        )

    ret = candidates[0]
    return ret


def run_test_command(test_name: str, command: Sequence[str]) -> int:
    """Run a test command and print a consistent pass/fail result."""
    print(f"\nRunning {test_name}")
    print(f"Command: {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROCKBUILDER_ROOT, check=False)
    if completed.returncode == 0:
        print(f"\n{test_name}: PASSED")
    else:
        print(f"\n{test_name}: FAILED (exit code {completed.returncode})", file=sys.stderr)
    ret = completed.returncode
    return ret


def main() -> int:
    """Validate the test environment when this module is executed directly."""
    ret = 0
    try:
        validate_test_environment()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        ret = 1
    return ret


if __name__ == "__main__":
    sys.exit(main())
