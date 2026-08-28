#!/usr/bin/env python3

import os
import platform
import subprocess
import sys

IS_WINDOWS = (platform.system() == "Windows")

# do not use sys.executable because that would run the parent process python
# instead of the one we added to PATH
def get_python_executable_name():
    if IS_WINDOWS:
        return "python"
    else:
        return "python3"

def run_cmd(cmd, description=None, check=True):
    if description:
        print(f"rcb_pre_config.py {description}")
    result = subprocess.run(cmd)
    if check and result.returncode != 0:
        print(f"rcb_pre_config.py command failed (res: {result.returncode}): {cmd}")
        sys.exit(result.returncode)
    return result.returncode

def run_git_command(args, cwd=None):
    """Helper to run git commands and return output/success."""
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        return result
    except FileNotFoundError:
        print("Error: 'git' command not found.")
        return None

def create_and_activate_venv(venv_name):
    venv_path = os.path.abspath(venv_name)
    if IS_WINDOWS:
        bin_dir = os.path.join(venv_path, "Scripts")
    else:
        bin_dir = os.path.join(venv_path, "bin")
    venv_exists = os.path.isdir(bin_dir)
    if not venv_exists:
        print(f"rcb_pre_config.py creating python virtual environment: {venv_name}")
        python_cmd = "python" if IS_WINDOWS else "python3"
        run_cmd([python_cmd, "-m", "venv", venv_name])
    os.environ["VIRTUAL_ENV"] = venv_path
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ.pop("PYTHONHOME", None)
    print(f"rcb_pre_config.py python virtual environment activated: {venv_path}")
    return venv_exists

def install_packages(venv_already_existed):
    python_exec = get_python_executable_name()
    if not venv_already_existed:
        run_cmd([python_exec, "-m", "pip", "install", "--upgrade", "pip"],
                "upgrading pip")
        run_cmd([python_exec, "-m", "pip", "install", "-r", "requirements.txt"],
                "installing requirements.txt")
        run_cmd([python_exec, "-m", "pip", "install", "dvc[s3]"],
                "installing dvc[s3]")
        run_cmd([python_exec, "-m", "pip", "install", "cmake>=3.28.0,<4.0.0"],
                "installing cmake")
        if IS_WINDOWS:
            run_cmd([python_exec, "-m", "pip", "install", "windows-curses"],
                    "installing windows-curses")

def check_and_abort_old_ongoing_am(repo_path="."):
    """Checks for active am session and aborts if found."""
    # check_status_for_am implementation via git status parsing
    res = run_git_command(['status'], cwd=repo_path)
    if res and "You are in the middle of an am session" in res.stdout:
        print(f"Detected active 'am' session in: {os.path.abspath(repo_path)}")
        abort_res = run_git_command(['am', '--abort'], cwd=repo_path)
        if abort_res.returncode == 0:
            print(f"Successfully aborted 'am' in {repo_path}")
        else:
            print(f"Failed to abort 'am' in {repo_path}: {abort_res.stderr}")
        return True
    return True

def fetch_sources():
    python_exec = get_python_executable_name()
    print("rcb_pre_config.py therock source fetch started")
    res = run_cmd([python_exec, "./build_tools/fetch_sources.py"], check=False)
    if res != 0:
        print(f"rcb_pre_config.py first attempt for submodule source code fetch failed: {res}")
        print("rcb_pre_config.py resetting submodules and trying refresh again")

        # first check if the error happens because submodules have "unfinished git am commands from previous attempt
        check_and_abort_old_ongoing_am(".")
        cmd = ['submodule', 'foreach', '--recursive', 'pwd']
        res = run_git_command(cmd)
        if res and res.returncode == 0:
            # Each line of output typically starts with "Entering '<path>'"
            # We extract the paths to check each one
            paths = [line.split("'")[1] for line in res.stdout.splitlines() if "Entering" in line]
            for path in paths:
                check_and_abort_old_ongoing_am(path)
        res = run_cmd([python_exec, "./build_tools/fetch_sources.py"], check=False)
        # if it failed again, then try to reset submodules and then try to fetch sources one more time
        if res != 0:
            run_cmd(["git", "submodule", "foreach", "git", "reset", "--hard"], check=False)
            res = run_cmd([python_exec, "./build_tools/fetch_sources.py"], check=False)
    return res


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"rcb_pre_config.py current directory: {os.getcwd()}")

    venv_already_existed = create_and_activate_venv(".venv")
    install_packages(venv_already_existed)

    result = subprocess.run(["cmake", "--version"], capture_output=True, text=True)
    cmake_version = result.stdout.strip()
    print(f"rcb_pre_config.py CMAKE_VERSION: {cmake_version}")

    res = fetch_sources()
    print(f"rcb_pre_config.py done, res: {res}")
    sys.exit(res)


if __name__ == "__main__":
    main()
