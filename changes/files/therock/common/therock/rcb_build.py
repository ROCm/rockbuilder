#!/usr/bin/env python3

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
        print(f"rcb_build.py python venv activation skipped ({bin_dir} not found)")
        return
    os.environ["VIRTUAL_ENV"] = venv_path
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ.pop("PYTHONHOME", None)
    print(f"rcb_build.py python venv activated: {venv_path}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"rcb_build.py current directory: {os.getcwd()}")

    activate_venv(".venv")

    result = subprocess.run(["cmake", "--version"], capture_output=True, text=True)
    cmake_version = result.stdout.strip()
    print(f"rcb_build.py CMAKE_VERSION: {cmake_version}")

    print("rcb_build.py therock cmake build command started")
    result = subprocess.run(["cmake", "--build", "build"])
    print(f"rcb_build.py therock cmake build command done, res: {result.returncode}")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
