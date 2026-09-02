#!/usr/bin/env python3

import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

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
        print(
            "rcb_pre_config.py command failed "
            f"(res: {result.returncode}): {cmd}"
        )
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
        print(
            "rcb_pre_config.py creating python virtual environment: "
            f"{venv_name}"
        )
        python_cmd = "python" if IS_WINDOWS else "python3"
        run_cmd([python_cmd, "-m", "venv", venv_name])
    os.environ["VIRTUAL_ENV"] = venv_path
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ.pop("PYTHONHOME", None)
    print(
        "rcb_pre_config.py python virtual environment activated: "
        f"{venv_path}"
    )
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

def get_in_progress_git_operation(repo_path="."):
    """Return the active patch-related Git operation and state path."""
    ret = None
    for state_name in ("rebase-apply", "rebase-merge"):
        res = run_git_command(
            ["rev-parse", "--git-path", state_name],
            cwd=repo_path,
        )
        if res is None or res.returncode != 0:
            raise RuntimeError(
                f"Could not inspect Git state in {repo_path}"
            )
        state_path = Path(res.stdout.strip())
        if not state_path.is_absolute():
            state_path = Path(repo_path) / state_path
        if state_path.is_dir():
            operation = "rebase"
            if (
                state_name == "rebase-apply"
                and not (state_path / "rebasing").exists()
            ):
                operation = "am"
            ret = (operation, state_path.resolve())
            break
    return ret


def check_and_resolve_in_progress_git_operation(repo_path="."):
    """Ask before aborting an operation that blocks patch application."""
    ret = False
    operation_info = get_in_progress_git_operation(repo_path)
    if operation_info is not None:
        ret = True
        operation, state_path = operation_info
        repo_path = Path(repo_path).resolve()
        abort_args = [operation, "--abort"]
        abort_command = (
            f"git -C {shlex.quote(str(repo_path))} "
            f"{operation} --abort"
        )
        print(
            f"Detected unfinished git {operation} operation in "
            f"{repo_path}"
        )
        print(f"Git operation state: {state_path}")
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Cannot apply patches with an unfinished Git operation. "
                f"Review the repository and run `{abort_command}`."
            )
        answer = input(
            f"Abort the operation with `{abort_command}`? [y/N]: "
        )
        if answer.strip().lower() not in ("y", "yes"):
            raise RuntimeError(
                "Patch application cancelled because the unfinished "
                "Git operation was not aborted."
            )
        abort_res = run_git_command(
            abort_args,
            cwd=repo_path,
        )
        if abort_res is None or abort_res.returncode != 0:
            stderr = ""
            if abort_res is not None:
                stderr = abort_res.stderr.strip()
            raise RuntimeError(
                f"Failed to run `{abort_command}`: {stderr}"
            )
        operation_info = get_in_progress_git_operation(repo_path)
        if operation_info is not None:
            raise RuntimeError(
                "Git operation state still exists after running "
                f"`{abort_command}`."
            )
        print(f"Successfully ran `{abort_command}`")
    return ret


def check_repo_and_submodule_git_operations():
    """Check the TheRock repository and each initialized submodule."""
    ret = check_and_resolve_in_progress_git_operation(".")
    cmd = ["submodule", "foreach", "--recursive", "pwd"]
    res = run_git_command(cmd)
    if res is None or res.returncode != 0:
        raise RuntimeError(
            "Could not inspect Git state in TheRock submodules"
        )
    for output_line in res.stdout.splitlines():
        path = output_line.strip()
        if path and not path.startswith("Entering "):
            if check_and_resolve_in_progress_git_operation(path):
                ret = True
    return ret

def fetch_sources():
    python_exec = get_python_executable_name()
    check_repo_and_submodule_git_operations()
    print("rcb_pre_config.py therock source fetch started")
    res = run_cmd([python_exec, "./build_tools/fetch_sources.py"], check=False)
    if res != 0:
        print(
            "rcb_pre_config.py first submodule source fetch failed: "
            f"{res}"
        )
        operation_resolved = check_repo_and_submodule_git_operations()
        if operation_resolved:
            print(
                "rcb_pre_config.py patch application failed; "
                "not retrying the unchanged patch series"
            )
        else:
            print(
                "rcb_pre_config.py resetting submodules and trying "
                "source fetch again"
            )
            run_cmd(
                [
                    "git",
                    "submodule",
                    "foreach",
                    "git",
                    "reset",
                    "--hard",
                ],
                check=False,
            )
            res = run_cmd(
                [python_exec, "./build_tools/fetch_sources.py"],
                check=False,
            )
            if res != 0:
                check_repo_and_submodule_git_operations()
    return res


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"rcb_pre_config.py current directory: {os.getcwd()}")

    venv_already_existed = create_and_activate_venv(".venv")
    install_packages(venv_already_existed)

    result = subprocess.run(
        ["cmake", "--version"],
        capture_output=True,
        text=True,
    )
    cmake_version = result.stdout.strip()
    print(f"rcb_pre_config.py CMAKE_VERSION: {cmake_version}")

    res = fetch_sources()
    print(f"rcb_pre_config.py done, res: {res}")
    sys.exit(res)


if __name__ == "__main__":
    main()
