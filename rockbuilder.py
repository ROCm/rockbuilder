#!/usr/bin/env python3

import argparse
import configparser
import sys
import os
import time
import platform
import subprocess
import lib_python.app_builder as app_builder
import rockbuilder_cfg as rcb_cfg_writer
import lib_python.rcb_cfg_reader as rcb_cfg_reader
import lib_python.rcb_constants as rcb_const
from lib_python.utils import get_python_wheel_rocm_sdk_home
from lib_python.utils import install_rocm_sdk_from_python_wheels
from lib_python.utils import get_rocm_sdk_env_variables
from lib_python.utils import verify_env__python
from lib_python.utils import get_python_wheel_rocm_sdk_gpu_list_str
from pathlib import Path, PurePosixPath


def printout_rock_builder_info():
    print("RockBuilder " + rcb_const.RCB__VERSION)
    print("")
    print("RCB_HOME_DIR: " + os.environ["RCB_HOME_DIR"])
    print("RCB_SRC_DIR: " + os.environ["RCB_SRC_DIR"])
    print("RCB_BUILD_DIR: " + os.environ["RCB_BUILD_DIR"])


def printout_build_env_info():
    printout_rock_builder_info()
    print("Build environment:")
    print("-----------------------------")
    if "ROCM_HOME" in os.environ:
        print("ROCM_HOME: " + os.environ["ROCM_HOME"])
    else:
        print("ROCK_HOME: not defined")
    if "ROCM_HOME" in os.environ:
        print("RCB_PYTHON_PATH: " + os.environ["RCB_PYTHON_PATH"])
    else:
        print("RCB_PYTHON_PATH: not defined")
    print("PATH: " + os.environ["PATH"])
    print("-----------------------------")
    time.sleep(1)


# if the app_name is full path to cfg file, return it
# othetwise assume that project name is "apps/app_name.cfg"
def get_app_cfg_path(rock_builder_home_dir: Path, fname: str):
    ret = None
    if fname:
        if fname.endswith(rcb_const.RCB__APP_CFG_FILE_SUFFIX):
            ret = Path(fname)
        else:
            fname_base = f"{fname}" + rcb_const.RCB__APP_CFG_FILE_SUFFIX
            ret = (
                Path(rock_builder_home_dir) /
                     rcb_const.RCB__APP_CFG_DEFAULT_BASE_DIR /
                     fname_base
            )
        ret = ret.resolve()
    return ret


# if the fname is full path to cfg file, return it
# othetwise assume that project name is "apps/fname.cfg"
def get_app_list_cfg_path(rock_builder_home_dir: Path, fname: str):
    ret = None
    if fname:
        if fname.endswith(rcb_const.RCB__APP_LIST_CFG_FILE_SUFFIX):
            ret = Path(fname)
        else:
            fname_base = f"{fname}" + rcb_const.RCB__APP_LIST_CFG_FILE_SUFFIX
            ret = (
                Path(rock_builder_home_dir) /
                     rcb_const.RCB__APP_CFG_DEFAULT_BASE_DIR /
                     fname_base
            )
        ret = ret.resolve()
    return ret


def get_app_or_app_list_config(rock_builder_home_dir: Path, fname: str):
    ret = None

    cfg_path = get_app_cfg_path(rock_builder_home_dir, fname)
    if not cfg_path or not cfg_path.exists():
        cfg_path = get_app_list_cfg_path(rock_builder_home_dir, fname)
    if cfg_path:
        ret = app_builder.ConfigReader(cfg_path)
    return ret

def create_argument_parser_with_basic_options(rock_builder_home_dir,
                                              default_src_base_dir: Path):
    # create an argument parser object
    parser = argparse.ArgumentParser(description="ROCKBuilder")

    # add non-positional arguments requiring a "--flag"
    parser.add_argument(
        "--init",
        action="store_true",
        help="Execute applications init command to initialize the project. Executed by default always",
        default=False,
    )
    parser.add_argument(
        "--clean", action="store_true", help="Execute applications clean command to remove build files", default=False
    )
    parser.add_argument(
        "--checkout",
        action="store_true",
        help="Execute applications checkout command to get source files",
        default=False,
    )
    parser.add_argument(
        "--hipify",
        action="store_true",
        help="Execute applications hipify command to modify source files after checkout",
        default=False,
    )
    parser.add_argument(
        "--pre_config",
        action="store_true",
        help="Execute applications pre-config command",
        default=False,
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Execute applications config command",
        default=False,
    )
    parser.add_argument(
        "--post_config",
        action="store_true",
        help="Execute applications post-config command",
        default=False,
    )
    parser.add_argument(
        "--build", action="store_true", help="Execute applications build command", default=False
    )
    parser.add_argument(
        "--install", action="store_true", help="Execute applications install command", default=False
    )
    parser.add_argument(
        "--post_install",
        action="store_true",
        help="Execute applications post-install command",
        default=False,
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        help="Specify exact directory where to checkout source code for app config is specified instead of application list.",
        default=None,
    )
    parser.add_argument(
        "--src-base-dir",
        type=Path,
        help="Specify base directory where each application source code is checked out. Default is src_apps.",
        default=default_src_base_dir,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to copy built wheels to",
        default=rock_builder_home_dir / "packages" / "wheels",
    )
    # add positional arguments not requiring a "--flag"
    parser.add_argument("config_file", type=str, help="Specify path to a app or app_list config file that specify which apps are build. For example: apps/pytorch.apps ")
    return parser


# This argument parser is used to parse the project list.
# This is needed to do first before parsing other arguments
# because we need to add the --<project-name>-version arguments for the second parser that
# is used to parse all possible parameters.
def get_app_list_manager(rock_builder_home_dir: Path, default_src_base_dir: Path):
    ret = None

    parser = create_argument_parser_with_basic_options(rock_builder_home_dir, default_src_base_dir)
    args, unknown = parser.parse_known_args()
    if not args.config_file:
	    args.config_file = rcb_const.RCB__APP_CFG_DEFAULT_BASE_DIR / "core.apps"
    cfg_info = get_app_or_app_list_config(rock_builder_home_dir, args.config_file)
    ret = app_builder.RockExternalProjectListManager(rock_builder_home_dir,
                                                     cfg_info)
    return ret

def get_app_cfg_base_name_without_extension(fname: str):
    ret = os.path.basename(fname)
    ret = os.path.splitext(ret)[0]
    return ret

# create user parameter parser
def create_build_argument_parser(
    rock_builder_home_dir, default_src_base_dir: Path, app_list
):
    parser = create_argument_parser_with_basic_options(rock_builder_home_dir, default_src_base_dir)
    # add application version arguments 
    for ii, prj_item in enumerate(app_list):
        base_name = get_app_cfg_base_name_without_extension(prj_item)
        arg_name = "--" + base_name + "-version"
        # print("arg_name: " + arg_name)
        parser.add_argument(
            "--" + base_name + "-version",
            help = base_name + " version used for the operations",
            default=None,
        )
    return parser


def parse_build_arguments(parser):
    # parse command line parameters
    args = parser.parse_args()
    if (
        ("--checkout" in sys.argv)
        or ("--clean" in sys.argv)
        or ("--init" in sys.argv)
        or ("--hipify" in sys.argv)
        or ("--pre_config" in sys.argv)
        or ("--config" in sys.argv)
        or ("--post_config" in sys.argv)
        or ("--build" in sys.argv)
        or ("--install" in sys.argv)
        or ("--post_install" in sys.argv)
    ):
        # If cmd_phase argument is specified:
        #
        # 1) we will execute the command even if the stamp file exist.
        # 2) we will clean all cmd-phase stamps remaining that phase.
        #    Because init function is always called, we need to have
        #    separate flag to indicate whether "--init" was given as a parameter.
        if ("--init" in sys.argv):
            args.cmd_init_force_exec = True
        else:
            args.cmd_init_force_exec = False
        args.cmd_any_force_exec = True
        print("checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install argument specified")
    else:
        args.cmd_init_force_exec = False
        args.cmd_any_force_exec = False
        # print("Action not specified.(checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install)")
        # print("Using default values")
        # enable everything except clean
        args.clean = False
        args.init = True
        args.checkout = True
        args.hipify = True
        args.pre_config = True
        args.config = True
        args.post_config = True
        args.build = True
        args.install = True
        args.post_install = True
    # force the hipify step always as a part of the checkout
    if args.checkout:
        args.hipify = True

    return args


def printout_build_arguments(args):
    # printout arguments enabled
    print("Actions Enabled: ")
    print("    clean:        ", args.clean)
    print("    init:         ", args.init)
    print("    checkout:     ", args.checkout)
    print("    hipify:       ", args.hipify)
    print("    pre_config:   ", args.pre_config)
    print("    config:       ", args.config)
    print("    post_config:  ", args.post_config)
    print("    build:        ", args.build)
    print("    install:      ", args.install)
    print("    post_install: ", args.post_install)
    print("Application: ", args.config_file)


def get_config_reader(rock_builder_home_dir: Path,
                     rock_builder_build_dir: Path):
    # read and set up env based on to rockbuilder.cfg file if it exist
    ret = None
    try:
        ret = rcb_cfg_reader.RCBConfigReader(rock_builder_home_dir,
                                             rock_builder_build_dir)
    except:
        # it's ok to not to find the config
        pass
    return ret


# do all build steps for given process
def do_therock(prj_builder, args):
    ret = False
    if prj_builder is not None:
        if prj_builder.is_build_enabled_on_current_os():
            # setup first the project specific environment variables
            prj_builder.printout("start")
            prj_builder.do_env_setup()
            exec_next_phase = False
            # print("do_env_setup done")

            # then do all possible commands requested for the project
            # multiple steps possible, so do not use else's here

            # init command differs from others
            # and will be executed always even if not arg flag is specified
            # It can be used to execute a script that can be used for example
            # to set an environment variable for the revision to be checked out
            prj_builder.printout("init")
            prj_builder.init(args.cmd_init_force_exec, args.cmd_any_force_exec)
            if args.cmd_init_force_exec: exec_next_phase = True
            if args.clean:
                prj_builder.printout("clean")
                prj_builder.clean(args.cmd_init_force_exec, args.cmd_any_force_exec)
            if args.checkout or exec_next_phase:
                prj_builder.printout("checkout")
                prj_builder.checkout(args.cmd_init_force_exec, args.cmd_any_force_exec)
                # enable hipify always when doing the code checkout
                # even if it is not requested explicitly to be it's own command
                args.hipify = True
                #if args.cmd_any_force_exec: exec_next_phase = True
            if args.hipify or exec_next_phase:
                prj_builder.printout("hipify")
                prj_builder.hipify(args.cmd_init_force_exec, args.cmd_any_force_exec)
                #if args.cmd_any_force_exec: exec_next_phase = True
            if args.pre_config or exec_next_phase:
                prj_builder.printout("pre_config")
                prj_builder.pre_config(args.cmd_init_force_exec, args.cmd_any_force_exec)
                if args.cmd_any_force_exec: exec_next_phase = True
            if args.config or exec_next_phase:
                prj_builder.printout("config")
                prj_builder.config(args.cmd_init_force_exec, args.cmd_any_force_exec)
                if args.cmd_any_force_exec: exec_next_phase = True
            if args.post_config or exec_next_phase:
                prj_builder.printout("post_config")
                prj_builder.post_config(args.cmd_init_force_exec, args.cmd_any_force_exec)
                if args.cmd_any_force_exec: exec_next_phase = True
            if args.build or exec_next_phase:
                prj_builder.printout("build")
                prj_builder.build(args.cmd_init_force_exec, args.cmd_any_force_exec)
                if args.cmd_any_force_exec: exec_next_phase = True
            if args.install or exec_next_phase:
                prj_builder.printout("install")
                prj_builder.install(args.cmd_init_force_exec, args.cmd_any_force_exec)
                if args.cmd_any_force_exec: exec_next_phase = True
            if args.post_install or exec_next_phase:
                prj_builder.printout("post_install")
                prj_builder.post_install(args.cmd_init_force_exec, args.cmd_any_force_exec)
                if args.cmd_any_force_exec: exec_next_phase = True
            # in the end restore original environment variables
            # so that they do not cause problem for next possible project handled
            prj_builder.undo_env_setup()
            #prj_builder.printout("done")
            print("Success: " + prj_builder.app_cfg_base_name)
            ret = True
        else:
            print("Builing of project disabled in applications config file")
            print("by one of the following properties:")
            print("    " + rcb_const.RCB__APP_CFG__KEY__PROP_IS_BUILD_ENABLED)
            print("    " + rcb_const.RCB__APP_CFG__KEY__PROP_IS_BUILD_ENABLED_LINUX)
            print("    " + rcb_const.RCB__APP_CFG__KEY__PROP_IS_BUILD_ENABLED_WINDOWS)
            prj_builder.printout("skip")
            ret = True
    return ret


def verify_rockbuilder_config(rcb_cfg_reader):
    if rcb_cfg_reader:
        gpu_list = rcb_cfg_reader.get_configured_gpu_list()
    if not rcb_cfg_reader or not gpu_list:
        if rcb_const.RCB__ENV_VAR_DISABLE_ROCM_SDK_CHECK in os.environ:
            return
        print("Rockbuilder is not yet configured, launching config UI")
        time.sleep(1)
        saved_cfg = rcb_cfg_writer.show_and_process_selections()
        if saved_cfg:
            print("ROCM SDK and target GPU configured ok.")
        else:
            print("ROCM SDK and target GPU configure failed.")
            sys.exit(1)

# Ensures that rocm_sdk install exist or will be installed by using
# the method that has been saved to rockbuilder.cfg config file.
# (by using the rockbuilder_cfg.py)
#
# Check is disabled if env-variable 'RCB_DISABLE_ROCM_SDK_CHECK' has been defined.
# Otherwise following cases are checked depending on from the rockbuilder configuration:
# - rocm_sdk from from the python wheels provied by therock
# - rocm_sdk from the therock sources
# - rocm sdk from other location (by specifiying ROCM_HOME before opening rockbuilder_cfg.py)
def verify_rocm_sdk_install(rcb_cfg_reader, app_manager, rock_builder_home_dir):
    if rcb_const.RCB__ENV_VAR_DISABLE_ROCM_SDK_CHECK in os.environ:
        return
    default_src_base_dir = rcb_const.get_app_src_base_dir()
    rocm_home = rcb_cfg_reader.get_locally_build_rocm_sdk_home()
    if rocm_home:
        print("Rockbuilder is configured to use ROCM_SDK build by the rockbuilder itself")
        # rocm sdk is wanted to be used from locally build therock dir
        # if none is returned, SDK is not yet build
        if not "RCB_AMDGPU_TARGETS" in os.environ:
            gpu_list_str = rcb_cfg_reader.get_configured_gpu_list_str()
            if gpu_list_str:
                os.environ["RCB_AMDGPU_TARGETS"] = gpu_list_str
            else:
                print("Could not get a list of configured target GPUs")
                sys.exit(1)
        env_var_arr = get_rocm_sdk_env_variables(Path(rocm_home), True, False)
        if env_var_arr:
            print("setting rocm_home")
			# use rocm sdk from location where the rock has been build
            os.environ["ROCM_HOME"] = rocm_home
        else:
            print("")
            print("ROCM_SDK build by rockbuilder not found")
            print("...building it first... This gonna take a while ...")
            time.sleep(2)
            # environment variables not returned
            # --> sdk not found
            # --> build rocm_sdk by using therock
            rocm_sdk_local_build_needed = True
            prj_cfg_file = get_app_cfg_path(rock_builder_home_dir, "therock")
            prj_cfg_base_name = get_app_cfg_base_name_without_extension(prj_cfg_file)
            version_override = None
            prj_builder = app_manager.get_rock_app_builder(
                    rcb_const.RCB__APP_SRC_ROOT_DIR / "therock",
                    prj_cfg_base_name,
                    prj_cfg_file,
                    rcb_const.RCB__APP_BUILD_ROOT_DIR,
                    version_override,
                    True
                )
            if prj_builder:
                app_list = ["therock"]
                arg_parser = create_build_argument_parser(rock_builder_home_dir,
                                    default_src_base_dir,
                                    app_list)
                args = parse_build_arguments(arg_parser)
                do_therock(prj_builder, args)
                os.environ["ROCM_HOME"] = rocm_home
    else:
        rocm_sdk_wheel_server_url = rcb_cfg_reader.get_python_wheel_rocm_sdk_server_url()
        if rocm_sdk_wheel_server_url:
            inst_wheels = rcb_cfg_reader.is_python_wheel_rocm_sdk_install_needed()
            if inst_wheels:
                rocm_home = install_rocm_sdk_from_python_wheels(rcb_cfg_reader)
            else:
                rocm_home = get_python_wheel_rocm_sdk_home("root")
            if rocm_home:
                print("rocm_home: " + rocm_home.as_posix())
                os.environ["ROCM_HOME"] = rocm_home.as_posix()
                # set target GPUs to environment variable if not set earlier
                if not "RCB_AMDGPU_TARGETS" in os.environ:
                    # get list of gpus that are supported by the currently installed
                    # python wheel based rocm sdk
                    gpu_list_str = get_python_wheel_rocm_sdk_gpu_list_str()
                    if gpu_list_str:
                        print("python wheel rocm-sdk RCB_AMDGPU_TARGETS: " + gpu_list_str)
                        os.environ["RCB_AMDGPU_TARGETS"] = gpu_list_str
                    else:
                        print("Python wheel based ROCM SDK install failed")
                        print("Could not get a list of configured target GPUs.")
                        print("   Python wheel server url: " + rocm_sdk_wheel_server_url)
                        sys.exit(1)
                else:
                    print("Failed to install ROCM_SDK from python wheels")
                    print("   Python wheel server url: " + rocm_sdk_wheel_server_url)
                    sys.exit(1)
        else:
            if not "RCB_AMDGPU_TARGETS" in os.environ:
                gpu_list_str = rcb_cfg_reader.get_configured_gpu_list_str()
                if gpu_list_str:
                    os.environ["RCB_AMDGPU_TARGETS"] = gpu_list_str
			# use installed rocm sdk from the location specified by the rockbuilder.cfg
            env_var_arr = None
            rocm_home = rcb_cfg_reader.get_configured_and_existing_rocm_sdk_home()
            if rocm_home:
                # check whether the rocm sdk has been configured ok in this location
                env_var_arr = get_rocm_sdk_env_variables(Path(rocm_home), False, False)
            if env_var_arr:
                os.environ["ROCM_HOME"] = rocm_home
            else:
                print("Failed to use ROCM_SDK from location configured in " + rcb_const.RCB__CFG__BASE_FILE_NAME)
                print("   ROCM_SDK location searched: " + rocm_home)
                sys.exit(1)


def main():
    is_posix = not any(platform.win32_ver())
    rocm_sdk_local_build_needed = False
    
    rock_builder_home_dir = rcb_const.get_rock_builder_root_dir()
    rock_builder_build_dir = rcb_const.get_app_build_base_dir()
    default_src_base_dir = rcb_const.get_app_src_base_dir()
    os.environ["RCB_HOME_DIR"] = rock_builder_home_dir.as_posix()
    os.environ["RCB_BUILD_DIR"] = rock_builder_build_dir.as_posix()
    
    verify_env__python()

    rcb_cfg_reader = get_config_reader(rock_builder_home_dir,
                              rock_builder_build_dir)
    verify_rockbuilder_config(rcb_cfg_reader)
    if not rcb_cfg_reader:
		# read the configure again if the configuration was only done above
        rcb_cfg_reader = get_config_reader(rock_builder_home_dir,
                                           rock_builder_build_dir)
    app_manager = get_app_list_manager(rock_builder_home_dir, default_src_base_dir)
    verify_rocm_sdk_install(rcb_cfg_reader, app_manager, rock_builder_home_dir)    

    app_list = app_manager.get_external_app_list()
    print(app_list)

    arg_parser = create_build_argument_parser(rock_builder_home_dir,
                                    default_src_base_dir,
                                    app_list)
    args = parse_build_arguments(arg_parser)

    # add output dir to environment variables
    if args.src_dir:
        # single project case with optional src_dir specified
        parent_dir = args.src_dir.parent
        if parent_dir == args.src_dir:
            print("Error, --src-dir parameter is not allowed to be a root-directory")
            sys.exit(1)
        os.environ["RCB_SRC_DIR"] = parent_dir.as_posix()
    else:
        # directory where each apps source code is checked out
        os.environ["RCB_SRC_DIR"] = args.src_base_dir.as_posix()
    os.environ["RCB_ARTIFACT_EXPORT_DIR"] = args.output_dir.as_posix()

    # store the arguments to dictionary to make it easier to get "app_name"-version parameters
    args_dict = args.__dict__
    printout_build_arguments(args)
    #verify_build_env(args, is_posix, rock_builder_home_dir, rock_builder_build_dir)
    printout_build_env_info()

    for ii, prj_item in enumerate(app_list):
        print(f"    Project [{ii}]: {prj_item}")

    # small delay to allow user to see env variable printouts before the build starts
    time.sleep(1)

    if not app_manager.config_info.is_app_config():
        # process all apps specified in the core_project.pcfg
        if args.src_dir:
            print('\nError, "--src-dir" parameter requires also to specify a single app.cfg file')
            print('Alternatively you could use the "--src-base-dir" parameter.')
            print("")
            sys.exit(1)
        for ii, prj_item in enumerate(app_list):
            print(f"[{ii}]: {prj_item}")
            # argparser --> Keyword for parameter "--my-project-version=xyz" = "my_app_version"
            prj_cfg_file = get_app_cfg_path(rock_builder_home_dir, app_list[ii])
            prj_cfg_base_name = get_app_cfg_base_name_without_extension(prj_cfg_file)
            prj_version_keyword = prj_cfg_base_name + "_version"
            prj_version_keyword = prj_version_keyword.replace("-", "_")
            version_override = args_dict[prj_version_keyword]
            # when issuing a command for all apps, we assume that the src_base_dir
            # is the base source directory under each project specific directory is checked out.
            prj_builder = app_manager.get_rock_app_builder(
                args.src_base_dir / prj_cfg_base_name,
                prj_cfg_base_name,
                prj_cfg_file,
                args.output_dir,
                version_override,
                True
            )
            if prj_builder is None:
                print("Error, could not get a project builder")
                sys.exit(1)
            else:
                do_therock(prj_builder, args)
    else:
        # process only a single project cfg file
        # argparser --> Keyword for parameter "--my-project-version=xyz" = "my_app_version"
        prj_cfg_file = get_app_cfg_path(rock_builder_home_dir, args.config_file)
        prj_cfg_base_name = get_app_cfg_base_name_without_extension(prj_cfg_file)
        prj_version_keyword = prj_cfg_base_name + "_version"
        prj_version_keyword = prj_version_keyword.replace("-", "_")
        version_override = args_dict[prj_version_keyword]
        if args.src_dir:
            # source checkout dir = "--src-dir"
            prj_builder = app_manager.get_rock_app_builder(
                args.src_dir,
                prj_cfg_base_name,
                prj_cfg_file,
                args.output_dir,
                version_override,
                True
            )
        else:
            # source checkout dir = "--src-base-dir" / app_name
            prj_builder = app_manager.get_rock_app_builder(
                args.src_base_dir / prj_cfg_base_name,
                prj_cfg_base_name,
                prj_cfg_file,
                args.output_dir,
                version_override,
                True
            )
        if prj_builder:
            do_therock(prj_builder, args)
        else:
            print("Error, failed to find the target project.")
            sys.exit(1)

if __name__ == "__main__":
    main()
