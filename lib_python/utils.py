import sys
import os
import platform
import ast
import subprocess
import configparser
import lib_python.rcb_constants as rcb_const
from pathlib import Path, PurePosixPath

def truncate_string(s, max_b_cnt):
    if s:
        if len(s) > max_b_cnt:
            return s[:max_b_cnt]
        else:
            return s
    else:
        return None

def _replace_env_variables(cmd_str):
    ret = os.path.expandvars(cmd_str)
    return ret

def get_rocm_sdk_wheel_install_stamp_key():
    ret = Path(sys.prefix).resolve().as_posix()
    # ":" in "c:/mypath" type of string causes problem when
    # string tried to save for a second time
    ret = ret.replace(":", "/")
    return ret

# write stamp file used to verify whether the pip install has been done
def _write_rocm_sdk_wheel_install_stamp_key(stamp_fname,
                         time_sec):
    ret = False
    try:
        dir_path = stamp_fname.parent
        if not dir_path.is_dir():
            dir_path.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if stamp_fname.exists():
            config.read(stamp_fname)
        if "timestamps" not in config:
            config["timestamps"] = {}
        stamp_key = get_rocm_sdk_wheel_install_stamp_key()
        config["timestamps"][stamp_key] = str(time_sec)
        with open(stamp_fname, "w") as configfile:
            config.write(configfile)
        print(
            f"Timestamp "
            + str(time_sec)
            + " written to file: "
            + str(stamp_fname)
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
        print("Error, RCB_AMDGPU_TARGETS must be set on Windows to select the target GPUs")
        print("Target GPU must match with the GPU selected on TheRock core build")
        print("Example for building for AMD Strix Halo and RX 9070:")
        print("  set RCB_AMDGPU_TARGETS=gfx1151;gfx1201")

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
        print("List is allowed to have only one value in " + rcb_const.RCB__CFG__BASE_FILE_NAME)
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
            print("Error, python environment not initialized for the rockbuilder.")
            print("Initialize python virtual env with command:")
            if is_posix:
                print("    source ./init_rcb_env.sh")
            else:
                print("    init_rcb_env.bat")
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
    # workaround until fixed: https://github.com/ROCm/TheRock/issues/1906
    # need to be called while after pip install on windows
    if not dir_str:
        dir_str = _capture(
            [sys.executable, "-m", "rocm_sdk", "path", f"--{path_name}"],
            cwd=Path.cwd(),
        )
    # end of workaround
    if dir_str and len(dir_str) > 0:
        dir_str.strip()
        ret = Path(dir_str)
        version_file = ret / ".info/version"
        if not version_file.exists():
            # workaround for rocm sdk wheel install on windows
            # where the rocm_sdk_devel wheels currently have empty dirs
            # without symlinks on _rocm_sdk_devel directories
            # beacause of the lack symlink support on windows
            if dir_str.endswith("_rocm_sdk_devel"):
                alternative_home = ret.parent
                alternative_home = alternative_home / "_rocm_sdk_core"
                version_file = alternative_home / ".info/version"
                if version_file.exists():
                    ret = alternative_home
                    print("Workaround applied to detect rocm sdk python_wheel ROCM_HOME: " + str(ret))
                else:
                    print("Could not find: " + str(version_file))
                    print("Failed to apply a workaround to detect the ROCM_HOME from rocm sdk python_wheel install")
            else:
               print("Could not fine _rocm_sdk_devel directory from python venv")
               print("Failed to apply a workaround to detect a ROCM_HOME from rocm sdk python_wheel install")
    else:
        print("rocm_sdk path --root command failed, could not get a ROCM_HOME from rocm_sdk python wheel install")
    return ret


# return path to rocm-sdk home if success
# on failure return None
def install_rocm_sdk_from_python_wheels(rcb_cfg) -> str:
    ret = None
    res = True

    rocm_sdk_CMD_UNINSTALL = (sys.executable +
                  " -m pip cache remove rocm_sdk --cache-dir " +
                  (rcb_const.RCB__ROOT_DIR / "pip").as_posix())
    install_deps_cmd = (
        sys.executable +
        " -m pip install setuptools --cache-dir " +
        (rcb_const.RCB__ROOT_DIR / "pip").as_posix()
    )
    rocm_sdk_CMD_INSTALL_base = (
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
        rocm_sdk_CMD_INSTALL_SDK = rocm_sdk_CMD_INSTALL_base + " --index-url " + whl_server_url_full
        print("install_deps_cmd: " + install_deps_cmd)
        exec_subprocess_cmd(install_deps_cmd, rcb_const.RCB__ROOT_DIR.as_posix())
        # uninstall old
        print("rocm_sdk_CMD_UNINSTALL: " + rocm_sdk_CMD_UNINSTALL)
        exec_subprocess_cmd(rocm_sdk_CMD_UNINSTALL, rcb_const.RCB__ROOT_DIR.as_posix())
        # install rocm sdk and pytorch
        print("rocm_sdk_CMD_INSTALL_SDK: " + rocm_sdk_CMD_INSTALL_SDK)
        exec_subprocess_cmd(rocm_sdk_CMD_INSTALL_SDK, rcb_const.RCB__ROOT_DIR.as_posix())
        print("python wheel install commands done")
    except Exception as ex:
        print("ROCM SDK python wheel install error with the rockbuilder.cfg:")
        print("    " + str(ex))
        res = False
    except:
        print("ROCM SDK python wheel install failed")
        res = False
    if res:
        stamp_mod_time = get_last_rcb_config_file_mod_time()
        stamp_fname = rcb_const.RCB__CFG__STAMP_FILE_NAME
        res = _write_rocm_sdk_wheel_install_stamp_key(stamp_fname,
                                                      stamp_mod_time)
        if not res:
            print("Failed to update rocm sdk-python wheel install stamp file: " + str(stamp_fname))
    if res:
        ret = get_python_wheel_rocm_sdk_home("root")
        if ret:
            print("ROCM_SDK python wheel install ROCM_HOME: " + str(ret))
        else:
            print("Error, could not find ROCM_HOME from ROCM_SDK python wheel install.")
    return ret

# check_rcb_rocm_sdk_version_file is checked if we want to use rocm_sdk
# build by therock itself, which will create this file to ensure that everything has been build.
# Otherwise we will assume that rocm_sdk is fully installed.
def get_rocm_sdk_env_variables(rocm_home_root_path:Path,
                               check_rcb_rocm_sdk_version_file: bool,
                               exit_on_error:bool):
    ret = []
    err_happened = False

    is_posix = _is_posix()
    # set the ENV_VARIABLE_NAME__LIB to be either LD_LIBRARY_PATH or LIBPATH depending
    # whether code is executed on Linux or Windows (it is later used to set env-variables)
    NEW_PATH_ENV_DIRS = None
    if is_posix:
        ENV_VARIABLE_NAME__LIB = "LD_LIBRARY_PATH"
    else:
        ENV_VARIABLE_NAME__LIB = "LIBPATH"

    if rocm_home_root_path.exists():
        rcb_rocm_sdk_src_version_fname = rocm_home_root_path / ".info/rcb_rocm_sdk_src_version"
        if rcb_rocm_sdk_src_version_fname.exists() or not check_rcb_rocm_sdk_version_file:
            rocm_home_bin_path = rocm_home_root_path / "bin"
            rocm_home_lib_path = rocm_home_root_path / "lib"
            rocm_home_bin_path = rocm_home_bin_path.resolve()
            rocm_home_lib_path = rocm_home_lib_path.resolve()
            
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
                rocm_home_llvm_path = rocm_home_root_path / "lib" / "llvm" / "bin"
                rocm_home_llvm_path = rocm_home_llvm_path.resolve()
                if rocm_home_bin_path.exists() and not _is_directory_in_env_variable_path("PATH", rocm_home_llvm_path.as_posix()):
                    # print("Adding " + rocm_home_llvm_path.as_posix() + " to PATH")
                    NEW_PATH_ENV_DIRS=NEW_PATH_ENV_DIRS + os.pathsep + rocm_home_llvm_path.as_posix()
                if not _is_directory_in_env_variable_path(ENV_VARIABLE_NAME__LIB, rocm_home_lib_path.as_posix()):
                    # print("Adding " + rocm_home_lib_path.as_posix() + " to " + ENV_VARIABLE_NAME__LIB)
                    ret.append(ENV_VARIABLE_NAME__LIB + "=" + (
                        rocm_home_lib_path.as_posix()
                        + os.pathsep
                        + os.environ.get(ENV_VARIABLE_NAME__LIB, "")))
                # find bitcode and put it to path
                folder_path = None
                for folder_path in Path(rocm_home_root_path).glob("**/bitcode"):
                    folder_path = folder_path.resolve()
                    ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_BITCODE_HOME_DIR + "=" + folder_path.as_posix())
                    print(rcb_const.RCB__ENV_VAR__ROCM_SDK_BITCODE_HOME_DIR + "=" + str(folder_path))
                    break
                if not folder_path:
                    err_happened = True
                    print("")
                    print("Error, could not find bitcode directory from ROCM_SDK:")
                    print("    " + str(rocm_home_root_path))
                    print("")
                    if exit_on_error:
                        sys.exit(1)
                # find hipcc
                if is_posix:
                    hipcc_exec_name = "hipcc"
                else:
                    hipcc_exec_name = "hipcc.bat"
                for folder_path in Path(rocm_home_root_path).glob("**/" + hipcc_exec_name):
                    hipcc_home = folder_path.parent
                    # make sure that we found bin/clang and not clang folder
                    if hipcc_home.name.lower() == "bin":
                        ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_HIPCC_BIN_DIR + "=" + hipcc_home.as_posix())
                        ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_HIPCC_APP + "=" + folder_path.as_posix())
                        print(rcb_const.RCB__ENV_VAR__ROCM_SDK_HIPCC_BIN_DIR + "=" + hipcc_home.as_posix())
                        print(rcb_const.RCB__ENV_VAR__ROCM_SDK_HIPCC_APP + "=" + folder_path.as_posix())
                        hipcc_home = hipcc_home.parent
                        if hipcc_home.is_dir():
                            hipcc_home = hipcc_home.resolve()
                            ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_HIPCC_HOME_DIR + "=" + hipcc_home.as_posix())
                            print(rcb_const.RCB__ENV_VAR__ROCM_SDK_HIPCC_HOME_DIR + "=" + hipcc_home.as_posix())
                            break
                # find clang
                if is_posix:
                    clang_exec_name = "clang"
                else:
                    clang_exec_name = "clang.exe"
                res = False
                for folder_path in Path(rocm_home_root_path).glob("**/" + clang_exec_name):
                    clang_home = folder_path.parent
                    # make sure that we found bin/clang and not clang folder
                    if clang_home.name.lower() == "bin":
                        ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_CLANG_BIN_DIR + "=" + clang_home.as_posix())
                        ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_CLANG_APP + "=" + folder_path.as_posix())
                        print(rcb_const.RCB__ENV_VAR__ROCM_SDK_CLANG_BIN_DIR + "=" + clang_home.as_posix())
                        print(rcb_const.RCB__ENV_VAR__ROCM_SDK_CLANG_APP + "=" + folder_path.as_posix())
                        clang_home = clang_home.parent
                        if clang_home.is_dir():
                            res = True
                            clang_home = clang_home.resolve()
                            ret.append(rcb_const.RCB__ENV_VAR__ROCM_SDK_CLANG_HOME_DIR + "=" + clang_home.as_posix())
                            print(rcb_const.RCB__ENV_VAR__ROCM_SDK_CLANG_HOME_DIR + "=" + str(clang_home))
                            break
                if not res:
                    err_happened = True
                    print("")
                    print("Error, could not find clang from ROCM_SDK directory:")
                    print("    " + str(rocm_home_root_path))
                    print("")
                    if exit_on_error:
                        sys.exit(1)
                # check that RCB_AMDGPU_TARGETS environment variable is set.
                # If not:
                #   - Linux: check the gpus available and assign them to RCB_AMDGPU_TARGETS
                #   - Windows: exit on error, because it can not be queried automatically
                if not "RCB_AMDGPU_TARGETS" in os.environ:
                    gpu_targets = get_installed_gpu_list_str(rocm_home_bin_path)
                    if gpu_targets:
                        ret.append(rcb_const.RCB__ENV_VAR__AMDGPU_TARGETS + "=" + gpu_targets)
                        print(rcb_const.RCB__ENV_VAR__AMDGPU_TARGETS + "=" + gpu_targets)
                    else:
                        print("Could not get the list of GPU's installed to the system")
                        err_happened = True
                        if exit_on_error:
                            sys.exit(1)
            else:
                err_happened = True
                print("")
                print("Error, could not find ROCM_HOME/bin or lib directory:")
                print("    " + rocm_home_bin_path.as_posix())
                print("    " + rocm_home_lib_path.as_posix())
                if exit_on_error:
                    sys.exit(1)
        else:
            err_happened = True
            print("")
            print("Error, could not find ROCM_SDK source version file:")
            print("    " + rcb_rocm_sdk_src_version_fname.as_posix())
            if exit_on_error:
                sys.exit(1)
    else:
        err_happened = True
        print("")
        print("Error, " + rcb_const.RCB__APP_CFG__KEY__PROP_IS_ROCM_SDK_USED +
              " is not set to FALSE in application config file")
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
