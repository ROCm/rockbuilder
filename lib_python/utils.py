import sys
import os
import platform
import ast
import subprocess
import configparser
import lib_python.rcb_constants as rcb_const
from pathlib import Path, PurePosixPath

def _replace_env_variables(cmd_str):
    ret = os.path.expandvars(cmd_str)
    return ret

# write stamp file used to verify whether the pip install has been done
def _write_pip_install_stamp(fname_pip_done, python_home_dir, time_sec):
    ret = False
    try:
        dir_path = fname_pip_done.parent
        if not dir_path.is_dir():
            dir_path.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if fname_pip_done.exists():
            config.read(fname_pip_done)
        if "timestamps" not in config:
            config["timestamps"] = {}
        config["timestamps"][python_home_dir] = str(time_sec)
        with open(fname_pip_done, "w") as configfile:
            config.write(configfile)
        print(
            f"Timestamp "
            + str(time_sec)
            + " written to file: "
            + str(fname_pip_done)
        )
        ret = True
    except FileExistsError:
        print(f"Directory '{directory_name}' already exists.")
    except OSError as e:
        print(f"Error creating directory '{directory_name}': {e}")
    except IOError as e:
        print(f"Error writing to file: {e}")
    return ret

# check whether specified directory is included in the specified environment variable
def _is_directory_in_env_variable_path(env_variable, directory):
    """
    Checks if a directory is in the env_variable specified as a parameter.
    (path, libpath, etc)

    Args:
      env_variable: Environment variable used to check the path
      directory: The path searched from the environment variable

    Returns:
      True if the directory is in PATH, False otherwise.
    """
    path_env = os.environ.get(env_variable, "")
    path_directories = path_env.split(os.pathsep)
    return directory in path_directories


def exec_subprocess_cmd(exec_cmd, exec_dir):
    ret = True
    if exec_cmd is not None:
        exec_dir = _replace_env_variables(exec_dir)
        print("exec_cmd: " + exec_cmd)
        # - capture_output=True --> print messages to output only after the process exits.
        # - capture_output=False --> print messages to output only while building
        # result = subprocess.run(exec_cmd, shell=True, capture_output=True, text=True)
        result = subprocess.run(
            exec_cmd, cwd=exec_dir, shell=True, capture_output=False, text=True
        )
        if result.returncode == 0:
            if result.stdout:
                print(result.stdout)
        else:
            ret = False
            print(result.stdout)
            print(f"Error: {result.stderr}")
    return ret

def printout_list_items(item_list):
    print("-----------------")
    for item in item_list:
        print(item)
    print("-----------------")


# Get the semicolon separated list of gpus that are supported by the
# python wheels based rocm sdk. This one has 'rocm-sdk' command
# to query the gpu-list that are supported by the sdk
def get_python_wheel_rocm_sdk_gpu_list_str() -> str:
    # Run `rocm-sdk targets` to get the default architecture
    targets = _capture(
        [sys.executable, "-m", "rocm_sdk", "targets"], cwd=Path.cwd()
    )
    if not targets:
        print("Warning: Failed to get a list of supported GPU's")
        print("from python wheel install based rocm-sdk with command:")
        print("    rocm-sdk targets")
        return ""
    # convert space-separated targets to semicolon separated list
    # that can be used for most of the apps as a -DAMD_GPU_TARGETS parameter
    return targets.replace(" ", ";")


# get list of GPU's that have been physically installed to computer
def get_installed_gpu_list_str(exec_dir: Path) -> str:
    ret = None

    is_posix = _is_posix()
    if is_posix:
        if exec_dir is not None:
            exec_cmd = "rocm_agent_enumerator"
            #print("exec_dir: " + str(exec_dir))
            #print("exec_cmd: " + exec_cmd)
            result = subprocess.run(
                exec_cmd, cwd=exec_dir, shell=False, capture_output=True, text=True
            )
            if result.returncode == 0:
                if result.stdout:
                    print(result.stdout)
                    gpu_list = result.stdout.splitlines()
                    # remove duplicates in case there are multiple instances of same gpu
                    gpu_list = list(set(gpu_list))
                    for ii, val in enumerate(gpu_list):
                        if ii == 0:
                            ret = val
                        else:
                            ret = ret + ";" + val
            else:
                ret = False
                print(result.stdout)
                print(f"Failed use to rocm_agent_enumerator to get the gpu list: {result.stderr}")
                sys.exit(1)
    else:
        print("Error, THEROCK_AMDGPU_TARGETS must be set on Windows to select the target GPUs")
        print("Target GPU must match with the GPU selected on TheRock core build")
        print("Example for building for AMD Strix Halo and RX 9070:")
        print("  set THEROCK_AMDGPU_TARGETS=gfx1151;gfx1201")

    return ret


def get_config_value_as_list(rcb_cfg, section_name, key_name):
    # we get values as a string reporesenting a list of strings
    ret = rcb_cfg.get(section_name, key_name)
    # convert it to real python list object
    ret = ast.literal_eval(ret)
    # ret = ret.split(", ")
    return ret


def get_config_value_from_one_element_list(rcb_cfg, section_name, key_name):
    res_list = get_config_value_as_list(rcb_cfg, section_name, key_name)
    if len(res_list) == 1:
        ret = res_list[0]
    else:
        print("List is allowed to have only one value in rockbuilder.ini")
        print("    section: " + section_name)
        print("    key: " + key_name)
        sys.exit(1)
    return ret
    
def _is_posix():
    return not any(platform.win32_ver())

def verify_env__python():
    is_posix = _is_posix()
    # check the python used. It needs to be by default an virtual env but
    # this can be overriden to real python version by setting up ENV variable
    # RCB_PYTHON_PATH
    python_home_dir = os.path.dirname(sys.executable)
    if "VIRTUAL_ENV" in os.environ:
        os.environ["RCB_PYTHON_PATH"] = python_home_dir
    else:
        if "RCB_PYTHON_PATH" in os.environ:
            if not os.path.abspath(python_home_dir) == os.path.abspath(os.environ["RCB_PYTHON_PATH"]):
                print("Error, virtual python environment is not active and")
                print("PYTHON location is different than specified by the RCB_PYTHON_PATH")
                print("    PYTHON location: " + python_home_dir)
                print("    RCB_PYTHON_PATH: " + os.environ["RCB_PYTHON_PATH"])
                print("If you want use this python location instead of using a virtual python env, define RCB_PYTHON_PATH:")
                if is_posix:
                    print("    export RCB_PYTHON_PATH=" + python_home_dir)
                else:
                    print("    set RCB_PYTHON_PATH=" + python_home_dir)
                print("Alternatively activate the virtual python environment")
                sys.exit(1)
            else:
                print("Using python from location: " + python_home_dir)
        else:
            print("Error, init python virtual env with command:")
            print("    source ./init_rcb_env.sh")
            print("Or define RCB_PYTHON_PATH with command: (not recommended)")
            if is_posix:
                print("    export RCB_PYTHON_PATH=" + python_home_dir)
            else:
                print("    set RCB_PYTHON_PATH=" + python_home_dir)
            print("")
            sys.exit(1)

def get_last_rcb_config_file_mod_time():
    ret = 0
    fname_cfg = rcb_const.get_rock_builder_config_file()
    if fname_cfg.exists():
        f_stats = fname_cfg.stat()
        ret = f_stats.st_mtime
    return ret


def _capture(args: list[str | Path], cwd: Path) -> str:
    args = [str(arg) for arg in args]
    try:
        return subprocess.check_output(args, cwd=str(cwd)).decode().strip()
    except subprocess.CalledProcessError as e:
        print(f"Error capturing output: {e}")
        return ""


# this works only for rocm sdk's installed as a pip wheel which have rocm_sdk tool
def get_python_wheel_rocm_sdk_home(path_name: str) -> Path:
    ret = None
    dir_str = _capture(
        [sys.executable, "-m", "rocm_sdk", "path", f"--{path_name}"],
        cwd=Path.cwd(),
    )
    if len(dir_str) > 0:
        print("python_wheel_rocm_sdk_home: " + str(dir_str))
        dir_str.strip()
        ret = Path(dir_str)
    return ret


# return path to rocm-sdk home if success
# on failure return None
def install_rocm_sdk_from_python_wheels(rcb_cfg) -> str:
    ret = None
    res = True

    rocm_sdk_uninstall_cmd = (sys.executable +
                  " -m pip cache remove rocm_sdk --cache-dir " +
                  (rcb_const.RCB__ROOT_DIR / "pip").as_posix())
    install_deps_cmd = (
        sys.executable +
        " -m pip install setuptools --cache-dir " +
        (rcb_const.RCB__ROOT_DIR / "pip").as_posix()
    )
    rocm_sdk_install_cmd_base = (
        sys.executable +
        " -m pip install rocm[libraries,devel] --force-reinstall --cache-dir " +
        (rcb_const.RCB__ROOT_DIR / "pip").as_posix()
    )
    
    try:
        gpu_target = get_config_value_from_one_element_list(rcb_cfg,
                                   rcb_const.RCB__CFG__SECTION__BUILD_TARGETS,
                                   rcb_const.RCB__CFG__KEY__GPUS)
        whl_server_url_base = get_config_value_from_one_element_list(rcb_cfg,
                                   rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_PYTHON_WHEELS)
        whl_server_url_full = whl_server_url_base + gpu_target
        rocm_sdk_install_cmd_full = rocm_sdk_install_cmd_base + " --index-url " + whl_server_url_full
        exec_subprocess_cmd(install_deps_cmd, rcb_const.RCB__ROOT_DIR.as_posix())
        # uninstall old
        exec_subprocess_cmd(rocm_sdk_uninstall_cmd, rcb_const.RCB__ROOT_DIR.as_posix())
        # install rocm sdk and pytorch
        exec_subprocess_cmd(rocm_sdk_install_cmd_full, rcb_const.RCB__ROOT_DIR.as_posix())        
    except  Exception as ex:
        print("ROCM SDK python wheel install error with the therock.cfg:")
        print("    " + str(ex))
        res = False
    if res:
        cfg_file_mod_time = get_last_rcb_config_file_mod_time()
        cfg_stamp_fname = rcb_const.RCB__CFG__STAMP_FILE_NAME
        res = _write_pip_install_stamp(cfg_stamp_fname,
                                       sys.prefix,
                                       cfg_file_mod_time)
        if not res:
            print("Failed to write to config stamp file: " + str(fname_pip_done))
    if res:
        ret = get_python_wheel_rocm_sdk_home("root")
        if not ret:
            print("Error, could not find ROCM_HOME from ROCM_SDK python wheel install.")
    return ret


def get_rocm_sdk_env_variables(rocm_home_root_path:Path, use_rocm_sdk:bool, exit_on_error:bool):
    ret = []
    err_happened = False

    if use_rocm_sdk:
        is_posix = _is_posix()
        # set the ENV_VARIABLE_NAME__LIB to be either LD_LIBRARY_PATH or LIBPATH depending
        # whether code is executed on Linux or Windows (it is later used to set env-variables)
        NEW_PATH_ENV_DIRS = None
        if is_posix:
            ENV_VARIABLE_NAME__LIB = "LD_LIBRARY_PATH"
        else:
            ENV_VARIABLE_NAME__LIB = "LIBPATH"
        
        if rocm_home_root_path.exists():
            rocm_home_bin_path = rocm_home_root_path / "bin"
            rocm_home_lib_path = rocm_home_root_path / "lib"
            rocm_home_bin_path = rocm_home_bin_path.resolve()
            rocm_home_lib_path = rocm_home_lib_path.resolve()
            rocm_home_llvm_path = rocm_home_root_path / "lib" / "llvm" / "bin"
            rocm_home_llvm_path = rocm_home_llvm_path.resolve()
            
            if rocm_home_bin_path.exists() and rocm_home_lib_path.exists():
                # set ROCM_HOME if not yet set
                if not "ROCM_HOME" in os.environ:
                    # print("ROCM_HOME: " + rocm_home_root_path.as_posix())
                    ret.append("ROCM_HOME=" + rocm_home_root_path.as_posix())
                # set ROCM_PATH to always point to same location than ROCM_HOME
                # ROCM_PATH is used by some ROCM applications instead of ROCM_HOME
                ret.append("ROCM_PATH=" + rocm_home_root_path.as_posix())
                if not _is_directory_in_env_variable_path("PATH", rocm_home_bin_path.as_posix()):
                    NEW_PATH_ENV_DIRS=rocm_home_bin_path.as_posix()
                    # print("Adding " + rocm_home_bin_path.as_posix() + " to PATH")
                if not _is_directory_in_env_variable_path("PATH", rocm_home_llvm_path.as_posix()):
                    # print("Adding " + rocm_home_llvm_path.as_posix() + " to PATH")
                    NEW_PATH_ENV_DIRS=NEW_PATH_ENV_DIRS + os.pathsep + rocm_home_llvm_path.as_posix()
                if not _is_directory_in_env_variable_path(ENV_VARIABLE_NAME__LIB, rocm_home_lib_path.as_posix()):
                    # print("Adding " + rocm_home_lib_path.as_posix() + " to " + ENV_VARIABLE_NAME__LIB)
                    ret.append(ENV_VARIABLE_NAME__LIB + "=" + (
                        rocm_home_lib_path.as_posix()
                        + os.pathsep
                        + os.environ.get(ENV_VARIABLE_NAME__LIB, "")))
                # find bitcode and put it to path
                for folder_path in Path(rocm_home_root_path).glob("**/bitcode"):
                    folder_path = folder_path.resolve()
                    ret.append("ROCK_BUILDER_BITCODE_HOME=" + folder_path.as_posix())
                    break
                # find hipcc
                if is_posix:
                    hipcc_exec_name = "hipcc"
                else:
                    hipcc_exec_name = "hipcc.bat"
                for folder_path in Path(rocm_home_root_path).glob("**/" + hipcc_exec_name):
                    hipcc_home = folder_path.parent
                    # make sure that we found bin/clang and not clang folder
                    if hipcc_home.name.lower() == "bin":
                        ret.append("ROCK_BUILDER_COMPILER_HIPCC=" + folder_path.as_posix())
                        hipcc_home = hipcc_home.parent
                        if hipcc_home.is_dir():
                            hipcc_home = hipcc_home.resolve()
                            ret.append("ROCK_BUILDER_HIPCC_HOME=" + hipcc_home.as_posix())
                            break
                # find clang
                if is_posix:
                    clang_exec_name = "clang"
                else:
                    clang_exec_name = "clang.exe"
                for folder_path in Path(rocm_home_root_path).glob("**/" + clang_exec_name):
                    clang_home = folder_path.parent
                    # make sure that we found bin/clang and not clang folder
                    if clang_home.name.lower() == "bin":
                        ret.append("ROCK_BUILDER_COMPILER_CLANG=" + folder_path.as_posix())
                        clang_home = clang_home.parent
                        if clang_home.is_dir():
                            clang_home = clang_home.resolve()
                            ret.append("ROCK_BUILDER_CLANG_HOME=" + clang_home.as_posix())
                            break
                # check that THEROCK_AMDGPU_TARGETS environment variable is set.
                # If not:
                #   - Linux: check the gpus available and assign them to THEROCK_AMDGPU_TARGETS
                #   - Windows: exit on error, because it can not be queried automatically
                if not "THEROCK_AMDGPU_TARGETS" in os.environ:
                    gpu_targets = get_installed_gpu_list_str(rocm_home_bin_path)
                    if gpu_targets:
                        ret.append("THEROCK_AMDGPU_TARGETS=" + gpu_targets)
                        print("THEROCK_AMDGPU_TARGETS: " + gpu_targets)
                    else:
                        print("Could not get the list of GPU's installed to the system")
                        err_happened = True
                        if exit_on_error:
                            sys.exit(1)
            else:
                err_happened = True
                print("")
                print("Error, could not find directory ROCM_HOME/lib: ")
                print("    " + rocm_home_lib_path.as_posix())
                if exit_on_error:
                    sys.exit(1)
        else:
            err_happened = True
            print("")
            print("Error, use_rocm_sdk is not set to false in project config file")
            print("   or ROCM_HOME is not defined")
            print("   or existing ROCM SDK build is not detected in directory:")
            print(rocm_home_root_path.as_posix())
            print("")
            if exit_on_error:
                sys.exit(1)
        if (not err_happened) and NEW_PATH_ENV_DIRS:
            ret.append("PATH=" + (
                     NEW_PATH_ENV_DIRS
                     + os.pathsep
                     + os.environ.get("PATH", "")))
        if err_happened:
            ret = None
    return ret
