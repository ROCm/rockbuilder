import os
from pathlib import Path

RCKB__VERSION                           = "2025-09-16_01"

RCKB__ROOT_DIR                          = Path(os.path.dirname(os.path.abspath(__file__))).parent.resolve()
RCKB__PROJECT_SRC_BASE_DIR              = RCKB__ROOT_DIR / "src_projects"
RCKB__PROJECT_BUILD_BASE_DIR            = RCKB__ROOT_DIR / "builddir"


RCKB__APP_CFG_FILE_SUFFIX               = ".cfg"
RCKB__APP_LIST_CFG_FILE_SUFFIX          = ".pcfg"

RCKB__CFG__FILE_NAME                    = RCKB__ROOT_DIR / "rockbuilder.ini"

RCKB__CFG__SECTION__ROCM_SDK            = "rocm_sdk"
RCKB__CFG__SECTION__BUILD_TARGETS       = "build_targets"

RCKB__CFG__KEY__ROCM_SDK_HOME           = "rocm_sdk_home"
RCKB__CFG__KEY__BUILD_ROCM_SDK          = "rocm_sdk_build"
RCKB__CFG__KEY__GPUS                    = "gpus"
RCKB__CFG__KEY__WHEEL_SERVER_URL        = "rocm_sdk_whl_server"


THEROCK_SDK__ROOT_DIR                   = RCKB__ROOT_DIR / "src_projects/therock"
THEROCK_SDK__ROCM_HOME_BUILD_DIR        = THEROCK_SDK__ROOT_DIR / "build/dist/rocm"

THEROCK_SDK__PYTHON_WHEEL_SERVER_URL    = "https://d2awnip2yjpvqn.cloudfront.net/v2/"

def get_rock_builder_root_dir():
	return RCKB__ROOT_DIR
	
def get_project_src_base_dir():
	return RCKB__PROJECT_SRC_BASE_DIR
	
def get_project_build_base_dir():
	return RCKB__PROJECT_BUILD_BASE_DIR

def get_rock_builder_config_file():
	return RCKB__CFG__FILE_NAME
