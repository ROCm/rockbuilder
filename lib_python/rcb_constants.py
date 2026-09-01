import os
from pathlib import Path

RCB__VERSION                                 = "2026-04-13_01"
RCB__CFG__DEF__ROCM_SDK_PYTHON_WHEEL_VERSION = "7.13.0a20260501"

RCB__ENV_VAR__ROCM_SDK_DEVICE_LIB_PATH       = "DEVICE_LIB_PATH"
RCB__ENV_VAR__ROCM_SDK_HIP_DEVICE_LIB_PATH   = "HIP_DEVICE_LIB_PATH"
RCB__ENV_VAR_DISABLE_ROCM_SDK_CHECK          = "RCB_DISABLE_ROCM_SDK_CHECK"
RCB__ENV_VAR__ROCM_SDK_INSTALL_DIR           = "RCB_ROCM_SDK_INSTALL_DIR"

RCB__ENV_VAR__ROCM_SDK_ROCM_HOME_DIR         = "ROCM_HOME"
RCB__ENV_VAR__ROCM_SDK_ROCM_HOME_BIN_DIR     = "ROCM_HOME_BIN_DIR"
RCB__ENV_VAR__ROCM_SDK_ROCM_HOME_LIB_DIR     = "ROCM_HOME_LIB_DIR"
RCB__ENV_VAR__ROCM_SDK_ROCM_PATH_DIR         = "ROCM_PATH"

RCB__ENV_VAR__ROCM_SDK_HIPCC_HOME_DIR        = "HIPCC_HOME"
RCB__ENV_VAR__ROCM_SDK_HIPCC_BIN_DIR         = "HIPCC_BIN_DIR"
RCB__ENV_VAR__ROCM_SDK_HIPCC_LIB_DIR         = "HIPCC_LIB_DIR"
RCB__ENV_VAR__ROCM_SDK_HIPCC_EXEC            = "HIPCC_EXEC"

RCB__ENV_VAR__ROCM_SDK_CLANG_HOME_DIR        = "CLANG_HOME"
RCB__ENV_VAR__ROCM_SDK_CLANG_BIN_DIR         = "CLANG_BIN_DIR"
RCB__ENV_VAR__ROCM_SDK_CLANG_LIB_DIR         = "CLANG_LIB_DIR"
RCB__ENV_VAR__ROCM_SDK_CLANG_CC_EXEC         = "CLANG_CC_EXEC"
RCB__ENV_VAR__ROCM_SDK_CLANG_CXX_EXEC        = "CLANG_CXX_EXEC"
# clang_cl is windows only clang wrapper binary to microsoft's own msvc compiler
RCB__ENV_VAR__ROCM_SDK_CLANG_CL_EXEC         = "CLANG_CL_EXEC"
RCB__ENV_VAR__AMDGPU_TARGETS                 = "RCB_AMDGPU_TARGETS"
RCB__ENV_VAR__AMDGPU_BASE_TARGETS            = "RCB_AMDGPU_BASE_TARGETS"
RCB__ENV_VAR__THEROCK_SANITIZER              = "RCB_THEROCK_SANITIZER"

RCB__ENV_VAR__APP_SRC_DIR                    = "RCB_APP_SRC_DIR"
RCB__ENV_VAR__APP_BUILD_DIR                  = "RCB_APP_BUILD_DIR"
RCB__ENV_VAR__APP_VERSION                    = "RCB_APP_VERSION"
RCB__ENV_VAR__USER_CHANGES_ROOT_DIR          = "RCB__USER_CHANGES_ROOT_DIR"

RCB__ENV_VAR__MODERATE_CPU_JOB_COUNT_COMPILE = "RCB_MODERATE_CPU_JOB_COUNT_COMPILE"
RCB__ENV_VAR__MODERATE_CPU_JOB_COUNT_LINK    = "RCB_MODERATE_CPU_JOB_COUNT_LINK"
RCB__ENV_VAR__SAFE_CPU_JOB_COUNT_COMPILE     = "RCB_SAFE_CPU_JOB_COUNT_COMPILE"
RCB__ENV_VAR__SAFE_CPU_JOB_COUNT_LINK        = "RCB_SAFE_CPU_JOB_COUNT_LINK"

RCB__APP_CFG_DEFAULT_DIR_BASENAME            = "apps"
RCB__APP_SRC_DIR_BASENAME                    = "src_apps"
RCB__APP_BUILD_DIR_BASENAME                  = "build"
RCB__CHANGES_DIR_BASENAME                    = "changes"
RCB__APP_FILES_DIR_BASENAME                  = "files"
RCB__APP_PATCHES_DIR_BASENAME                = "patches"

RCB__ROOT_DIR                                = Path(os.path.dirname(os.path.abspath(__file__))).parent.resolve()
RCB__APP_SRC_ROOT_DIR = (
    RCB__ROOT_DIR / RCB__APP_SRC_DIR_BASENAME
)
RCB__APP_BUILD_ROOT_DIR = (
    RCB__ROOT_DIR / RCB__APP_BUILD_DIR_BASENAME
)
RCB__CHANGES_ROOT_DIR = (
    RCB__ROOT_DIR / RCB__CHANGES_DIR_BASENAME
)

RCB__APP_CFG_FILE_SUFFIX                     = ".cfg"
RCB__APP_LIST_CFG_FILE_SUFFIX                = ".apps"

RCB__CFG__BASE_FILE_NAME                     = "rockbuilder.cfg"
RCB__CFG__FILE_NAME                          = RCB__ROOT_DIR / RCB__CFG__BASE_FILE_NAME
RCB__CFG__STAMP_FILE_NAME                    = RCB__ROOT_DIR / "rocm_sdk_wheels.done"

RCB__CFG__SECTION__ROCM_SDK                  = "rocm_sdk"
RCB__CFG__SECTION__BUILD_TARGETS             = "build_targets"
RCB__CFG__SECTION__BUILD_OPTIONS             = "build_options"

RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME       = "rocm_sdk_home"
RCB__CFG__KEY__ROCM_SDK_FROM_BUILD           = "rocm_sdk_build"
RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG         = "rocm_sdk_build_config"
RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER  = "rocm_sdk_whl_server"
RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER_DEPRECATED  = "rocm_sdk_whl"
RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_VERSION = "rocm_sdk_whl_version"
RCB__CFG__KEY__GPUS                          = "gpus"
RCB__CFG__KEY__THEROCK_SANITIZER             = "therock_sanitizer"
RCB__CFG__THEROCK_SANITIZER_VALUES = (
    "NONE",
    "HOST_ASAN",
    "ASAN",
)

RCB__APPS_CFG__SECTION_APPS                  = "apps"
RCB__APPS_CFG__KEY__APP_LIST                 = "app_list"

RCB__THEROCK_DEFAULT_CONFIG                  = "therock_10_0"
RCB__THEROCK_CONFIGS = (
    RCB__THEROCK_DEFAULT_CONFIG,
    "therock_dev",
)


RCB__APP_CFG__SECTION_APP_INFO               = "app_info"
RCB__APP_CFG__KEY__APP_NAME                  = "APP_NAME"
RCB__APP_CFG__KEY__APP_VERSION               = "APP_VERSION"
RCB__APP_CFG__KEY__REPO_URL                  = "REPO_URL"
RCB__APP_CFG__KEY__PROP_FETCH_REPO_TAGS      = "PROP_FETCH_REPO_TAGS"
RCB__APP_CFG__KEY__PATCH_DIR                 = "PATCH_DIR"
RCB__APP_CFG__KEY__ROCM_SDK_INSTALL_DIR_BASENAME = (
    "ROCM_SDK_INSTALL_DIR_BASENAME"
)

RCB__APP_CFG__KEY__CMD_EXEC_DIR              = "CMD_EXEC_DIR"

RCB__APP_CFG__CMD_PHASE_EXTENSION_LINUX      = "_LINUX"
RCB__APP_CFG__CMD_PHASE_EXTENSION_WINDOWS    = "_WINDOWS"

RCB__APP_CFG__KEY__CMD_INIT                  = "CMD_INIT"
RCB__APP_CFG__KEY__CMD_CLEAN                 = "CMD_CLEAN"
RCB__APP_CFG__KEY__CMD_CHECKOUT              = "CMD_CHECKOUT"
RCB__APP_CFG__KEY__CMD_HIPIFY                = "CMD_HIPIFY"
RCB__APP_CFG__KEY__CMD_PRE_CONFIG            = "CMD_PRE_CONFIG"
RCB__APP_CFG__KEY__CMD_CONFIG                = "CMD_CONFIG"
RCB__APP_CFG__KEY__CMD_POST_CONFIG           = "CMD_POST_CONFIG"
RCB__APP_CFG__KEY__CMD_CMAKE_CONFIG          = "CMD_CMAKE_CONFIG"
RCB__APP_CFG__KEY__CMD_CMAKE_BUILD           = "CMD_CMAKE_BUILD"
RCB__APP_CFG__KEY__CMD_BUILD                 = "CMD_BUILD"
RCB__APP_CFG__KEY__CMD_BUILD_LINUX           = "CMD_BUILD_LINUX"
RCB__APP_CFG__KEY__CMD_BUILD_WINDOWS         = "CMD_BUILD_WINDOWS"
RCB__APP_CFG__KEY__CMD_CMAKE_INSTALL         = "CMD_CMAKE_INSTALL"
RCB__APP_CFG__KEY__CMD_INSTALL               = "CMD_INSTALL"
RCB__APP_CFG__KEY__CMD_POST_INSTALL          = "CMD_POST_INSTALL"

# both windows and linux or only linux or only windows
RCB__APP_CFG__KEY__PROP_BUILD_DISABLE            = "PROP_DISABLE"
RCB__APP_CFG__KEY__PROP_BUILD_DISABLE_LINUX      = "PROP_DISABLE_LINUX"
RCB__APP_CFG__KEY__PROP_BUILD_DISABLE_WINDOWS    = "PROP_DISABLE_WINDOWS"

RCB__APP_CFG__KEY__PROP_IS_ROCM_SDK_USED         = "PROP_IS_ROCM_SDK_USED"

RCB__APP_CFG__KEY__ENV_VAR                       = "ENV_VAR"
RCB__APP_CFG__KEY__ENV_VAR_LINUX                 = "ENV_VAR_LINUX"
RCB__APP_CFG__KEY__ENV_VAR_WINDOWS               = "ENV_VAR_WINDOWS"

RCB_CALLBACK__INSTALL_PYTHON_WHEEL               = "RCB_CALLBACK__INSTALL_PYTHON_WHEEL"
RCB_CALLBACK__DELETE_APP_SRC_SUBDIR              = "RCB_CALLBACK__DELETE_APP_SRC_SUBDIR"
RCB_CALLBACK__RESET_APP_SRC_REPOSITORY           = "RCB_CALLBACK__RESET_APP_SRC_REPOSITORY"

THEROCK_SDK__ROCM_HOME_INSTALL_PARENT            = Path("/opt/rcb")
THEROCK_SDK__PYTHON_WHEEL_SERVER_URL             = "https://rocm.nightlies.amd.com/v2/"

def get_therock_rocm_sdk_install_dir(
    preferred_parent=THEROCK_SDK__ROCM_HOME_INSTALL_PARENT,
    home_dir=None,
    install_dir_basename="rocm_10_0_0",
):
    """Select the system install path when its existing parent is writable."""
    preferred_dir = preferred_parent / install_dir_basename
    if preferred_dir.exists():
        writable_path = preferred_dir
    else:
        writable_path = preferred_parent
    write_mode = os.W_OK | os.X_OK
    use_preferred_dir = (
        os.name != "nt"
        and preferred_parent.is_dir()
        and os.access(writable_path, write_mode)
    )
    if use_preferred_dir:
        return preferred_dir

    if home_dir is None:
        home_dir = Path.home()
    return Path(home_dir) / "rcb" / install_dir_basename


def get_rock_builder_root_dir():
	return RCB__ROOT_DIR
	
def get_app_src_base_dir():
	return RCB__APP_SRC_ROOT_DIR
	
def get_app_build_base_dir():
	return RCB__APP_BUILD_ROOT_DIR

def get_rock_builder_config_file():
	return RCB__CFG__FILE_NAME
