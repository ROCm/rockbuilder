import os
from pathlib import Path

RCB__VERSION                                 = "2025-10-31_01"

RCB__ENV_VAR__ROCM_SDK_DEVICE_LIB_PATH       = "DEVICE_LIB_PATH"
RCB__ENV_VAR__ROCM_SDK_HIP_DEVICE_LIB_PATH   = "HIP_DEVICE_LIB_PATH"
RCB__ENV_VAR_DISABLE_ROCM_SDK_CHECK          = "RCB_DISABLE_ROCM_SDK_CHECK"

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
RCB__ENV_VAR__ROCM_SDK_CLANG_EXEC            = "CLANG_EXEC"
RCB__ENV_VAR__AMDGPU_TARGETS                 = "RCB_AMDGPU_TARGETS"

RCB__ENV_VAR__APP_SRC_DIR                    = "RCB_APP_SRC_DIR"
RCB__ENV_VAR__APP_BUILD_DIR                  = "RCB_APP_BUILD_DIR"
RCB__ENV_VAR__APP_VERSION                    = "RCB_APP_VERSION"

RCB__APP_CFG_DEFAULT_BASE_DIR                = "apps"
RCB__APP_SRC_BASE_DIR                        = "src_apps"
RCB__APP_BUILD_BASE_DIR                      = "build"
RCB__APP_PATCHES_BASE_DIR                    = "patches"

RCB__ROOT_DIR                                = Path(os.path.dirname(os.path.abspath(__file__))).parent.resolve()
RCB__APP_SRC_ROOT_DIR                        = RCB__ROOT_DIR / RCB__APP_SRC_BASE_DIR
RCB__APP_BUILD_ROOT_DIR                      = RCB__ROOT_DIR / RCB__APP_BUILD_BASE_DIR
RCB__APP_PATCHES_ROOT_DIR                    = RCB__ROOT_DIR / RCB__APP_PATCHES_BASE_DIR

RCB__APP_CFG_FILE_SUFFIX                     = ".cfg"
RCB__APP_LIST_CFG_FILE_SUFFIX                = ".apps"

RCB__CFG__BASE_FILE_NAME                     = "rockbuilder.cfg"
RCB__CFG__FILE_NAME                          = RCB__ROOT_DIR / RCB__CFG__BASE_FILE_NAME
RCB__CFG__STAMP_FILE_NAME                    = RCB__ROOT_DIR / "rocm_sdk_wheels.done"

RCB__CFG__SECTION__ROCM_SDK                  = "rocm_sdk"
RCB__CFG__SECTION__BUILD_TARGETS             = "build_targets"

RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME       = "rocm_sdk_home"
RCB__CFG__KEY__ROCM_SDK_FROM_BUILD           = "rocm_sdk_build"
RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER  = "rocm_sdk_whl_server"
RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER_DEPRECATED  = "rocm_sdk_whl"
RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_VERSION = "rocm_sdk_whl_version"
RCB__CFG__DEF__ROCM_SDK_PYTHON_WHEEL_VERSION = "7.11.0a20251201"
RCB__CFG__KEY__GPUS                          = "gpus"

RCB__APPS_CFG__SECTION_APPS                  = "apps"
RCB__APPS_CFG__KEY__APP_LIST                 = "app_list"

RCB__THEROCK_CFG_NAME                        = "therock.cfg"


RCB__APP_CFG__SECTION_APP_INFO               = "app_info"
RCB__APP_CFG__KEY__APP_NAME                  = "APP_NAME"
RCB__APP_CFG__KEY__APP_VERSION               = "APP_VERSION"
RCB__APP_CFG__KEY__REPO_URL                  = "REPO_URL"
RCB__APP_CFG__KEY__PROP_FETCH_REPO_TAGS      = "PROP_FETCH_REPO_TAGS"
RCB__APP_CFG__KEY__PATCH_DIR                 = "PATCH_DIR"

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
RCB_CALLBACK__DELETE_FROM_APP_SRC_DIR            = "RCB_CALLBACK__DELETE_FROM_APP_SRC_DIR"

THEROCK_SDK_SRC__ROOT_DIR                        = RCB__APP_SRC_ROOT_DIR / "therock"
THEROCK_SDK_SRC__PATCHES_ROOT_DIR                = THEROCK_SDK_SRC__ROOT_DIR / "external-builds/pytorch/patches"
# can be different location in future if we later deploy the sdk from source dir after build
THEROCK_SDK__ROCM_HOME_BUILD_DIR                 = THEROCK_SDK_SRC__ROOT_DIR / "build/dist/rocm"
THEROCK_SDK__PYTHON_WHEEL_SERVER_URL             = "https://rocm.nightlies.amd.com/v2/"

def get_rock_builder_root_dir():
	return RCB__ROOT_DIR
	
def get_app_src_base_dir():
	return RCB__APP_SRC_ROOT_DIR
	
def get_app_build_base_dir():
	return RCB__APP_BUILD_ROOT_DIR

def get_rock_builder_config_file():
	return RCB__CFG__FILE_NAME
