#!/usr/bin/env python3

import argparse
import os
import platform
import subprocess
import sys

IS_WINDOWS = (platform.system() == "Windows")

def activate_venv(venv_name):
    venv_path = os.path.abspath(venv_name)
    if IS_WINDOWS:
        bin_dir = os.path.join(venv_path, "Scripts")
    else:
        bin_dir = os.path.join(venv_path, "bin")
    if not os.path.isdir(bin_dir):
        print(
            "rcb_config.py python venv activation skipped "
            f"({bin_dir} not found)"
        )
        return
    os.environ["VIRTUAL_ENV"] = venv_path
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ.pop("PYTHONHOME", None)
    print(f"rcb_config.py python venv activated: {venv_path}")


# Return a filesystem-safe bundle name for explicit GPU targets.
# Input: a semicolon-separated GPU target string.
# Returns: a string without XNACK feature punctuation.
# Example: "gfx942:xnack-;gfx942:xnack+" returns
# "gfx942_xnackminus_gfx942_xnackplus".
def get_dist_bundle_name(amdgpu_targets):
    ret = amdgpu_targets.replace(";", "_")
    ret = ret.replace(":xnack+", "_xnackplus")
    ret = ret.replace(":xnack-", "_xnackminus")
    ret = ret.replace(":", "_").replace("+", "plus")
    return ret


def parse_arguments():
    """Parse optional command-line configuration values.

    Example:
        With --sanitizer ASAN, this returns a namespace whose sanitizer
        value is "ASAN".
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--sanitizer", default=None)
    ret = parser.parse_args()
    return ret


def main(sanitizer=None):
    """Configure TheRock from RockBuilder selections.

    Example:
        main("ASAN") passes -DTHEROCK_SANITIZER=ASAN to CMake and exits
        with its status.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"rcb_config.py current directory: {os.getcwd()}")

    activate_venv(".venv")

    result = subprocess.run(
        ["cmake", "--version"],
        capture_output=True,
        text=True,
    )
    cmake_version = result.stdout.strip()
    print(f"rcb_config.py CMAKE_VERSION: {cmake_version}")

    amdgpu_targets = os.environ.get("RCB_AMDGPU_TARGETS", "")
    safe_cpu_count_compile = os.environ.get(
        "RCB_SAFE_CPU_JOB_COUNT_COMPILE",
        "",
    )
    safe_cpu_count_link = os.environ.get("RCB_SAFE_CPU_JOB_COUNT_LINK", "")
    cmake_cmd = [
        "cmake",
        "-B", "build",
        "-GNinja",
    ]
    cmake_cmd.append("-DTHEROCK_VERBOSE=1")
    cmake_cmd.append("-DTHEROCK_ENABLE_ROCPROFSYS=0")
    if sanitizer is not None:
        sanitizer = sanitizer.strip().upper()
    if sanitizer in {"ASAN", "HOST_ASAN"}:
        cmake_cmd.append(f"-DTHEROCK_SANITIZER={sanitizer}")
    elif sanitizer in {None, "NONE"}:
        cmake_cmd.append("-DTHEROCK_SANITIZER=")
    else:
        raise ValueError(
            "Unsupported sanitizer value: " + sanitizer
        )
    cmake_cmd.append(f"-DTHEROCK_AMDGPU_FAMILIES={amdgpu_targets}")
    # Limit enabled subprojects that use USE_TEST_AMDGPU_TARGETS:
    # rccl, rccl-tests, rocshmem, hipfile, hipthreads, hip-tests, rocrtst, rocr-debug-agent-tests, aqlprofile,
    # rocprofiler-sdk, and rocprofiler-systems-examples.
    cmake_cmd.append(f"-DTHEROCK_TEST_AMDGPU_TARGETS={amdgpu_targets}")
    print(
        f"safe_cpu_count_compile: {safe_cpu_count_compile} "
        f"safe_cpu_count_link: {safe_cpu_count_link}"
    )
    if safe_cpu_count_compile != "":
        cmake_cmd.append(
            "-DLLVM_PARALLEL_COMPILE_JOBS="
            + safe_cpu_count_compile
        )
        flang_safe_cpu_compile_count = max(1, int(safe_cpu_count_compile) // 2)
        flang_safe_cpu_compile_count = max(1, flang_safe_cpu_compile_count)
        flang_safe_cpu_compile_count = str(flang_safe_cpu_compile_count)
        cmake_cmd.append(
            "-DFLANG_PARALLEL_COMPILE_JOBS="
            + flang_safe_cpu_compile_count
        )
    if safe_cpu_count_link != "":
        cmake_cmd.append(f"-DLLVM_PARALLEL_LINK_JOBS={safe_cpu_count_link}")
    if IS_WINDOWS:
        cmake_cmd.append("-DTHEROCK_AMDGPU_DIST_BUNDLE_NAME=windows")
    elif ";" in amdgpu_targets or ":" in amdgpu_targets:
        bundle_name = get_dist_bundle_name(amdgpu_targets)
        cmake_cmd.append(f"-DTHEROCK_AMDGPU_DIST_BUNDLE_NAME={bundle_name}")
    cmake_cmd.append(".")

    cmake_cmd_str = " ".join(cmake_cmd)
    with open("rcb_config.txt", "w") as f_handle:
        f_handle.write(cmake_cmd_str)
    print(f"rcb_config.py, therock config_cmd: {cmake_cmd_str}")
    result = subprocess.run(cmake_cmd)
    print(f"rcb_config.py therock config done, res: {result.returncode}")
    sys.exit(result.returncode)


if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments.sanitizer)
