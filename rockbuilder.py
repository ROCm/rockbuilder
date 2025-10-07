#!/usr/bin/env python

import argparse
import configparser
import sys
import os
import time
import platform
import subprocess
import lib_python.project_builder as project_builder
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


# This argument parser is used to parse the project list.
# This is needed to do first before parsing other arguments
# because we need to add the --<project-name>-version arguments for the second parser that
# is used to parse all possible parameters.
def get_project_list_manager(rock_builder_home_dir: Path):
    parser = argparse.ArgumentParser(description="Project and Project List Parser")

    # Add arguments
    parser.add_argument(
        "--project_list",
        type=str,
        help="specify project list for the actions, for example: projects/pytorch_apps" + rcb_const.RCB__APP_LIST_CFG_FILE_SUFFIX,
        default=None,
    )
    parser.add_argument(
        "--project",
        type=str,
        help="specify target for the action, for example: pytorch or projects/pytorch" + rcb_const.RCB__APP_CFG_FILE_SUFFIX,
        default=None,
    )
    prj = None
    prj_list = None
    args, unknown = parser.parse_known_args()
    prj_cfg_file = get_project_cfg_file_path(rock_builder_home_dir, args.project)
    ret = project_builder.RockExternalProjectListManager(
        rock_builder_home_dir, args.project_list, prj_cfg_file
    )
    return ret

def get_project_cfg_base_name_without_extension(project_name: str):
    ret = os.path.basename(project_name)
    ret = os.path.splitext(ret)[0]
    return ret

# create user parameter parser
def create_build_argument_parser(
    rock_builder_home_dir, default_src_base_dir: Path, project_list
):
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(description="ROCK Project Builders")

    # Add arguments
    parser.add_argument(
        "--project_list",
        type=str,
        help="specify project list for the actions, for example: projects/pytorch_apps.pcfg",
        default=None,
    )
    parser.add_argument(
        "--project",
        type=str,
        help="specify project for the action, for example: pytorch or projects/pytorch" + rcb_const.RCB__APP_CFG_FILE_SUFFIX,
        default=None,
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="init build environment by installing dependencies",
        default=False,
    )
    parser.add_argument(
        "--clean", action="store_true", help="clean build files", default=False
    )
    parser.add_argument(
        "--checkout",
        action="store_true",
        help="checkout source code for the project",
        default=False,
    )
    parser.add_argument(
        "--hipify",
        action="store_true",
        help="hipify command for project",
        default=False,
    )
    parser.add_argument(
        "--pre_config",
        action="store_true",
        help="pre-config command for project",
        default=False,
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="config command for project",
        default=False,
    )
    parser.add_argument(
        "--post_config",
        action="store_true",
        help="post-config command for project",
        default=False,
    )
    parser.add_argument(
        "--build", action="store_true", help="build project", default=False
    )
    parser.add_argument(
        "--install", action="store_true", help="install build project", default=False
    )
    parser.add_argument(
        "--post_install",
        action="store_true",
        help="post-install command for project",
        default=False,
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        help="Directory where to checkout single project source code. Can only be used with the --project parameter.",
        default=None,
    )
    parser.add_argument(
        "--src-base-dir",
        type=Path,
        help="Base directory where each projects source code is checked out. Default is src_apps.",
        default=default_src_base_dir,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to copy built wheels to",
        default=rock_builder_home_dir / "packages" / "wheels",
    )
    for ii, prj_item in enumerate(project_list):
        base_name = get_project_cfg_base_name_without_extension(prj_item)
        arg_name = "--" + base_name + "-version"
        print("arg_name: " + arg_name)
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
		# if cmd_phase argument is specified, we will execute the command even if the stamp file exist
        args.cmd_force_exec = True
        print("checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install argument specified")
    else:
        args.cmd_force_exec = False
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
    print("    clean:       ", args.clean)
    print("    init:        ", args.init)
    print("    checkout:    ", args.checkout)
    print("    hipify:      ", args.hipify)
    print("    pre_config:  ", args.pre_config)
    print("    config:      ", args.config)
    print("    post_config: ", args.post_config)
    print("    build:       ", args.build)
    print("    install:     ", args.install)
    print("    post_install:", args.post_install)
    print("Projects:", args.project)


def get_config_reader(rock_builder_home_dir: Path,
                     rock_builder_build_dir: Path):
    # read and set up env based on to rockbuilder.ini file if it exist
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
            # print("do_env_setup done")

            # then do all possible commands requested for the project
            # multiple steps possible, so do not use else's here

            # init command differs from others
            # and will be executed always even if not arg flag is specified
            # It can be used to execute a script that can be used for example
            # to set an environment variable for the revision to be checked out
            prj_builder.printout("init")
            prj_builder.init(args.cmd_force_exec)
            if args.clean:
                prj_builder.printout("clean")
                prj_builder.clean(args.cmd_force_exec)
            if args.checkout:
                prj_builder.printout("checkout")
                prj_builder.checkout(args.cmd_force_exec)
                # enable hipify always when doing the code checkout
                # even if it is not requested explicitly to be it's own command
                args.hipify = True
            if args.hipify:
                prj_builder.printout("hipify")
                prj_builder.hipify(args.cmd_force_exec)
            if args.pre_config:
                prj_builder.printout("pre_config")
                prj_builder.pre_config(args.cmd_force_exec)
            if args.config:
                prj_builder.printout("config")
                prj_builder.config(args.cmd_force_exec)
            if args.post_config:
                prj_builder.printout("post_config")
                prj_builder.post_config(args.cmd_force_exec)
            if args.build:
                prj_builder.printout("build")
                prj_builder.build(args.cmd_force_exec)
            if args.install:
                prj_builder.printout("install")
                prj_builder.install(args.cmd_force_exec)
            if args.post_install:
                prj_builder.printout("post_install")
                prj_builder.post_install(args.cmd_force_exec)
            # in the end restore original environment variables
            # so that they do not cause problem for next possible project handled
            prj_builder.undo_env_setup()
            #prj_builder.printout("done")
            print("Operations finished ok: " +prj_builder.project_cfg_base_name)
            ret = True
        else:
            print("PROP_IS_BUILD_ENABLED_WINDOWS or PROP_IS_BUILD_ENABLED_LINUX enabled for project")
            prj_builder.printout("skip")
            ret = True
    return ret


# if the project_name is full path to cfg file, return it
# othetwise assume that project name is "projects/project_name.cfg"
def get_project_cfg_file_path(rock_builder_home_dir: Path, project_name: str):
    if project_name:
        if project_name.endswith(rcb_const.RCB__APP_CFG_FILE_SUFFIX):
            ret = Path(project_name)
        else:
            fname_base = f"{project_name}" + rcb_const.RCB__APP_CFG_FILE_SUFFIX
            ret = (
                Path(rock_builder_home_dir) / "projects" / fname_base
            )
        ret = ret.resolve()
    else:
        ret = project_name
    return ret

def verify_rockbuilder_config(rcb_cfg_reader):
    if rcb_cfg_reader:
        gpu_list = rcb_cfg_reader.get_configured_gpu_list()
    if not rcb_cfg_reader or not gpu_list:
        print("Rockbuilder is not yet configured, launching config UI")
        time.sleep(1)
        saved_cfg = rcb_cfg_writer.show_and_process_selections()
        if saved_cfg:
            print("ROCM SDK and target GPU configured ok.")
        else:
            print("ROCM SDK and target GPU configure failed.")
            sys.exit(1)

# Ensures that rocm_sdk install exist or will be installed by using
# the method that has been saved to rockbuilder.ini config file.
# (by using the rockbuilder_cfg.py)
#
# Check is disabled if env-variable 'RCB_DISABLE_ROCM_SDK_CHECK' has been defined.
# Otherwise following cases are checked depending on from the rockbuilder configuration:
# - rocm_sdk from from the python wheels provied by therock
# - rocm_sdk from the therock sources
# - rocm sdk from other location (by specifiying ROCM_HOME before opening rockbuilder_cfg.py)
def verify_rocm_sdk_install(rcb_cfg_reader, project_manager, rock_builder_home_dir):
    if rcb_const.RCB__ENV_VAR_DISABLE_ROCM_SDK_CHECK in os.environ:
        return
    default_src_base_dir = rcb_const.get_project_src_base_dir()
    rocm_home = rcb_cfg_reader.get_locally_build_rocm_sdk_home()
    if rocm_home:
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
			# use rocm sdk from location where the rock has been build
            os.environ["ROCM_HOME"] = rocm_home
        else:
            # environment variables not returned
            # --> sdk not found
            # --> build rocm_sdk by using therock
            rocm_sdk_local_build_needed = True
            prj_cfg_file = get_project_cfg_file_path(rock_builder_home_dir, "therock")
            prj_cfg_base_name = get_project_cfg_base_name_without_extension(prj_cfg_file)
            version_override = None
            prj_builder = project_manager.get_rock_project_builder(
                    rcb_const.RCB__PROJECT_SRC_ROOT_DIR / "therock",
                    prj_cfg_base_name,
                    prj_cfg_file,
                    rcb_const.RCB__PROJECT_BUILD_ROOT_DIR,
                    version_override
                )
            if prj_builder:
                project_list = ["therock"]
                arg_parser = create_build_argument_parser(rock_builder_home_dir,
                                    default_src_base_dir,
                                    project_list)
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
			# use installed rocm sdk from the location specified by the rockbuilder.ini
            env_var_arr = None
            rocm_home = rcb_cfg_reader.get_configured_and_existing_rocm_sdk_home()
            if rocm_home:
                # check whether the rocm sdk has been configured ok in this location
                env_var_arr = get_rocm_sdk_env_variables(Path(rocm_home), True, False)
            if env_var_arr:
                os.environ["ROCM_HOME"] = rocm_home
            else:
                print("Failed to use ROCM_SDK from location configured in rockbuilder.ini")
                print("   ROCM_SDK location searched: " + rocm_home)
                sys.exit(1)


def main():
    is_posix = not any(platform.win32_ver())
    rocm_sdk_local_build_needed = False
    
    rock_builder_home_dir = rcb_const.get_rock_builder_root_dir()
    rock_builder_build_dir = rcb_const.get_project_build_base_dir()
    default_src_base_dir = rcb_const.get_project_src_base_dir()
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
    project_manager = get_project_list_manager(rock_builder_home_dir)
    verify_rocm_sdk_install(rcb_cfg_reader, project_manager, rock_builder_home_dir)    

    project_list = project_manager.get_external_project_list()
    print(project_list)

    arg_parser = create_build_argument_parser(rock_builder_home_dir,
                                    default_src_base_dir,
                                    project_list)
    args = parse_build_arguments(arg_parser)

    # add output dir to environment variables
    if args.project and args.src_dir:
        # single project case with optional src_dir specified
        parent_dir = args.src_dir.parent
        if parent_dir == args.src_dir:
            print("Error, --src-dir parameter is not allowed to be a root-directory")
            sys.exit(1)
        os.environ["RCB_SRC_DIR"] = parent_dir.as_posix()
    else:
        # directory where each projects source code is checked out
        os.environ["RCB_SRC_DIR"] = args.src_base_dir.as_posix()
    os.environ["RCB_ARTIFACT_EXPORT_DIR"] = args.output_dir.as_posix()

    # store the arguments to dictionary to make it easier to get "project_name"-version parameters
    args_dict = args.__dict__
    printout_build_arguments(args)
    #verify_build_env(args, is_posix, rock_builder_home_dir, rock_builder_build_dir)
    printout_build_env_info()

    for ii, prj_item in enumerate(project_list):
        print(f"    Project [{ii}]: {prj_item}")

    # small delay to allow user to see env variable printouts before the build starts
    time.sleep(1)

    if not args.project:
        # process all projects specified in the core_project.pcfg
        if args.src_dir:
            print('\nError, "--src-dir" parameter requires also to specify the project with the "--project"-parameter')
            print('Alternatively you could use the "--src-base-dir" parameter.')
            print("")
            sys.exit(1)
        for ii, prj_item in enumerate(project_list):
            print(f"[{ii}]: {prj_item}")
            # argparser --> Keyword for parameter "--my-project-version=xyz" = "my_project_version"
            prj_cfg_file = get_project_cfg_file_path(rock_builder_home_dir, project_list[ii])
            prj_cfg_base_name = get_project_cfg_base_name_without_extension(prj_cfg_file)
            prj_version_keyword = prj_cfg_base_name + "_version"
            prj_version_keyword = prj_version_keyword.replace("-", "_")
            version_override = args_dict[prj_version_keyword]
            # when issuing a command for all projects, we assume that the src_base_dir
            # is the base source directory under each project specific directory is checked out.
            prj_builder = project_manager.get_rock_project_builder(
                args.src_base_dir / prj_cfg_base_name,
                prj_cfg_base_name,
                prj_cfg_file,
                args.output_dir,
                version_override,
            )
            if prj_builder is None:
                print("Error, could not get a project builder")
                sys.exit(1)
            else:
                do_therock(prj_builder, args)
    else:
        # process only a single project specified with the "--project" parameter
        # argparser --> Keyword for parameter "--my-project-version=xyz" = "my_project_version"
        prj_cfg_file = get_project_cfg_file_path(rock_builder_home_dir, args.project)
        prj_cfg_base_name = get_project_cfg_base_name_without_extension(prj_cfg_file)
        prj_version_keyword = prj_cfg_base_name + "_version"
        prj_version_keyword = prj_version_keyword.replace("-", "_")
        version_override = args_dict[prj_version_keyword]
        if args.src_dir:
            # source checkout dir = "--src-dir"
            prj_builder = project_manager.get_rock_project_builder(
                args.src_dir,
                prj_cfg_base_name,
                prj_cfg_file,
                args.output_dir,
                version_override
            )
        else:
            # source checkout dir = "--src-base-dir" / project_name
            prj_builder = project_manager.get_rock_project_builder(
                args.src_base_dir / prj_cfg_base_name,
                prj_cfg_base_name,
                prj_cfg_file,
                args.output_dir,
                version_override,
            )
        if prj_builder:
            do_therock(prj_builder, args)
        else:
            print("Error, failed to find the target project.")
            sys.exit(1)

if __name__ == "__main__":
    main()
