#!/usr/bin/env python3

import os
import platform
import subprocess
import sys
import time

IS_WINDOWS = (platform.system() == "Windows")

def activate_venv(venv_name):
    venv_path = os.path.abspath(venv_name)
    if IS_WINDOWS:
        bin_dir = os.path.join(venv_path, "Scripts")
    else:
        bin_dir = os.path.join(venv_path, "bin")
    if not os.path.isdir(bin_dir):
        print(f"rcb_config.py python venv activation skipped ({bin_dir} not found)")
        return
    os.environ["VIRTUAL_ENV"] = venv_path
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ.pop("PYTHONHOME", None)
    print(f"rcb_config.py python venv activated: {venv_path}")


def input_with_timeout(prompt, timeout_seconds, default=""):
    # Non-interactive processes cannot answer a prompt, so use
    # the default immediately. Interactive input is delegated to
    # the implementation supported by the current platform.
    if not sys.stdin.isatty():
        print(prompt)
        ret = default
    elif IS_WINDOWS:
        ret = _input_with_timeout_windows(
            prompt, timeout_seconds, default
        )
    else:
        ret = _input_with_timeout_posix(
            prompt, timeout_seconds, default
        )
    return ret


def _input_with_timeout_posix(prompt, timeout_seconds, default):
    # select() waits for terminal input without blocking beyond
    # the requested timeout.
    import select

    ret = default
    print(prompt, end="", flush=True)
    readable, _, _ = select.select(
        [sys.stdin], [], [], timeout_seconds
    )
    if readable:
        answer = sys.stdin.readline()
        if answer:
            ret = answer.strip() or default
        else:
            print()
    else:
        print()
    return ret


def _input_with_timeout_windows(prompt, timeout_seconds, default):
    # Windows console input cannot be monitored with select(),
    # so poll it until input arrives or the deadline expires.
    import msvcrt

    ret = default
    print(prompt, end="", flush=True)
    answer = []
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not msvcrt.kbhit():
            time.sleep(0.05)
            continue
        character = msvcrt.getwch()
        if character in ("\r", "\n"):
            print()
            ret = "".join(answer).strip() or default
            break
        if character == "\x03":
            raise KeyboardInterrupt
        if character in ("\x00", "\xe0"):
            msvcrt.getwch()
            continue
        if character == "\b":
            if answer:
                answer.pop()
                print("\b \b", end="", flush=True)
            continue
        if character.isprintable():
            answer.append(character)
            print(character, end="", flush=True)
    else:
        print()
    return ret


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"rcb_config.py current directory: {os.getcwd()}")

    activate_venv(".venv")

    result = subprocess.run(["cmake", "--version"], capture_output=True, text=True)
    cmake_version = result.stdout.strip()
    print(f"rcb_config.py CMAKE_VERSION: {cmake_version}")

    amdgpu_targets = os.environ.get("RCB_AMDGPU_TARGETS", "")
    safe_cpu_count_compile = os.environ.get("RCB_SAFE_CPU_JOB_COUNT_COMPILE", "")
    safe_cpu_count_link = os.environ.get("RCB_SAFE_CPU_JOB_COUNT_LINK", "")
    cmake_cmd = [
        "cmake",
        "-B", "build",
        "-GNinja",
    ]
    cmake_cmd.append("-DTHEROCK_VERBOSE=1")
    cmake_cmd.append("-DTHEROCK_ENABLE_ROCPROFSYS=0")
    asan_gpu_families = {"gfx90a", "gfx942", "gfx950"}
    sanitizer = os.environ.get("RCB_THEROCK_SANITIZER", "")
    if sanitizer:
        cmake_cmd.append(f"-DTHEROCK_SANITIZER={sanitizer}")
    else:
        for asan_gpu_item in asan_gpu_families:
            if asan_gpu_item in amdgpu_targets:
                separator = "------------------"
                timeout_seconds = 30
                prompt = (
                    f"{separator}\n"
                    "RCB_THEROCK_SANITIZER is not set and target is "
                    f"{amdgpu_targets}.\n"
                    "Enable ASAN build? [y/N] "
                    f"(default after {timeout_seconds} seconds): "
                )
                answer = input_with_timeout(
                    prompt, timeout_seconds, default="N"
                ).strip().lower()
                print(f"Selected value: {answer.lower()}")
                print(separator)
                time.sleep(3)
                if answer == "y":
                    cmake_cmd.append("-DTHEROCK_SANITIZER=ASAN")
                    break
    cmake_cmd.append(f"-DTHEROCK_AMDGPU_FAMILIES={amdgpu_targets}")
    print(f"safe_cpu_count_compile: {safe_cpu_count_compile} safe_cpu_count_link: {safe_cpu_count_link}")
    if safe_cpu_count_compile != "":
        cmake_cmd.append(f"-DLLVM_PARALLEL_COMPILE_JOBS={safe_cpu_count_compile}")
        flang_safe_cpu_compile_count = max(1, int(safe_cpu_count_compile) // 2)
        flang_safe_cpu_compile_count = max(1, flang_safe_cpu_compile_count)
        flang_safe_cpu_compile_count = str(flang_safe_cpu_compile_count)
        cmake_cmd.append(f"-DFLANG_PARALLEL_COMPILE_JOBS={flang_safe_cpu_compile_count}")
    if safe_cpu_count_link != "":
        cmake_cmd.append(f"-DLLVM_PARALLEL_LINK_JOBS={safe_cpu_count_link}")
    if IS_WINDOWS:
        cmake_cmd.append("-DTHEROCK_AMDGPU_DIST_BUNDLE_NAME=windows")
    elif ";" in amdgpu_targets:
        bundle_name = amdgpu_targets.replace(";", "_")
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
    main()
