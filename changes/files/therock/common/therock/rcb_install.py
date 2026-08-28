#!/usr/bin/env python3

import os
import subprocess
from pathlib import Path

INSTALL_DIR_ENV_VAR = "RCB_ROCM_SDK_INSTALL_DIR"


def get_install_dir():
    install_dir_value = os.environ.get(INSTALL_DIR_ENV_VAR)
    if not install_dir_value:
        raise RuntimeError(
            f"{INSTALL_DIR_ENV_VAR} is required for TheRock installation"
        )
    return Path(install_dir_value).expanduser().resolve()


def install_rocm_sdk(script_dir, install_dir):
    build_dir = script_dir / "build"
    build_output_dir = build_dir / "dist/rocm"
    if install_dir == build_output_dir.resolve():
        print(
            "rcb_install.py preserving legacy build/dist/rocm "
            "installation"
        )
        return

    if install_dir.exists():
        raise FileExistsError(
            f"ROCm SDK install directory already exists: {install_dir}. "
            "Rename or delete it before running the install again."
        )

    install_dir.parent.mkdir(parents=True, exist_ok=True)
    install_cmd = [
        "cmake",
        "--install",
        str(build_dir),
        "--component",
        "rocm",
        "--prefix",
        str(install_dir),
    ]
    print(
        "rcb_install.py therock cmake install command: "
        + " ".join(install_cmd)
    )
    result = subprocess.run(install_cmd)
    if result.returncode != 0:
        raise RuntimeError(
            "TheRock installation failed with exit code "
            f"{result.returncode}"
        )


def write_install_marker(install_dir):
    marker_dir = install_dir / ".info"
    marker_dir.mkdir(parents=True, exist_ok=True)
    app_version = os.environ.get("RCB_APP_VERSION", "")
    marker = marker_dir / "rcb_rocm_sdk_src_version"
    marker.write_text(
        f"rockbuilder_therock: {app_version}\n",
        encoding="utf-8",
    )


def main():
    script_dir = Path(__file__).resolve().parent
    install_dir = get_install_dir()
    install_rocm_sdk(script_dir, install_dir)
    write_install_marker(install_dir)
    print(f"rcb_install.py installed ROCm SDK to: {install_dir}")


if __name__ == "__main__":
    main()
