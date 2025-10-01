import os
from pathlib import Path

RCB__VERSION                               = "2025-10-01_01"

RCB__ROOT_DIR                              = Path(os.path.dirname(os.path.abspath(__file__))).parent.resolve()
RCB__PROJECT_SRC_BASE_DIR                  = RCB__ROOT_DIR / "src_projects"
RCB__PROJECT_BUILD_BASE_DIR                = RCB__ROOT_DIR / "builddir"


RCB__APP_CFG_FILE_SUFFIX                   = ".cfg"
RCB__APP_LIST_CFG_FILE_SUFFIX              = ".pcfg"

RCB__CFG__FILE_NAME                        = RCB__ROOT_DIR / "rockbuilder.ini"
RCB__CFG__STAMP_FILE_NAME                  = RCB__ROOT_DIR / "rocm_sdk_wheels.done"

RCB__CFG__SECTION__ROCM_SDK                = "rocm_sdk"
RCB__CFG__SECTION__BUILD_TARGETS           = "build_targets"

RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME     = "rocm_sdk_home"
RCB__CFG__KEY__ROCM_SDK_FROM_BUILD         = "rocm_sdk_build"
RCB__CFG__KEY__ROCM_SDK_FROM_PYTHON_WHEELS = "rocm_sdk_whl"
RCB__CFG__KEY__GPUS                        = "gpus"

RCB__PRJ_CFG__KEY__CMD_INIT            = "init_cmd"
RCB__PRJ_CFG__KEY__CMD_CLEAN           = "clean_cmd"
RCB__PRJ_CFG__KEY__CMD_CHECKOUT        = "checkout_cmd"
RCB__PRJ_CFG__KEY__CMD_HIPIFY          = "hipify_cmd"
RCB__PRJ_CFG__KEY__CMD_PRECONFIG       = "config_pre_cmd"
RCB__PRJ_CFG__KEY__CMD_CONFIG          = "config_cmd"
RCB__PRJ_CFG__KEY__CMD_POSTCONFIG      = "config_post_cmd"
RCB__PRJ_CFG__KEY__CMD_CMAKE_CONFIG    = "config_cmake_cmd"
RCB__PRJ_CFG__KEY__CMD_CMAKE_BUILD     = "build_cmake_cmd"
RCB__PRJ_CFG__KEY__CMD_BUILD           = "build_cmd"
RCB__PRJ_CFG__KEY__CMD_CMAKE_INSTALL   = "install_cmake_cmd"
RCB__PRJ_CFG__KEY__CMD_INSTALL         = "install_cmd"
RCB__PRJ_CFG__KEY__CMD_POSTINSTALL     = "install_post_cmd"

THEROCK_SDK__ROOT_DIR                   = RCB__ROOT_DIR / "src_projects/therock"
THEROCK_SDK__ROCM_HOME_BUILD_DIR        = THEROCK_SDK__ROOT_DIR / "build/dist/rocm"

THEROCK_SDK__PYTHON_WHEEL_SERVER_URL    = "https://rocm.nightlies.amd.com/v2/"

def get_rock_builder_root_dir():
	return RCB__ROOT_DIR
	
def get_project_src_base_dir():
	return RCB__PROJECT_SRC_BASE_DIR
	
def get_project_build_base_dir():
	return RCB__PROJECT_BUILD_BASE_DIR

def get_rock_builder_config_file():
	return RCB__CFG__FILE_NAME
