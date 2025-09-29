#!/usr/bin/env python

import argparse
import configparser
import sys
import os
import time
import platform
import subprocess
import lib_python.project_builder as project_builder
import lib_python.rockbuilder_config as RockBuilderConfig
import lib_python.rckb_constants as rckb_constants
from pathlib import Path, PurePosixPath

def printout_rock_builder_info():
    print("RockBuilder " + rckb_constants.RCKB__VERSION)
    print("")
    print("ROCK_BUILDER_HOME_DIR: " + os.environ["ROCK_BUILDER_HOME_DIR"])
    print("ROCK_BUILDER_SRC_DIR: " + os.environ["ROCK_BUILDER_SRC_DIR"])
    print("ROCK_BUILDER_BUILD_DIR: " + os.environ["ROCK_BUILDER_BUILD_DIR"])


def printout_build_env_info():
    printout_rock_builder_info()
    print("Build environment:")
    print("-----------------------------")
    if "ROCM_HOME" in os.environ:
        print("ROCM_HOME: " + os.environ["ROCM_HOME"])
    else:
        print("ROCK_HOME: not defined")
    if "ROCM_HOME" in os.environ:
        print("ROCK_PYTHON_PATH: " + os.environ["ROCK_PYTHON_PATH"])
    else:
        print("ROCK_PYTHON_PATH: not defined")
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
        help="specify project list for the actions, for example: projects/pytorch_apps" + rckb_constants.RCKB__APP_LIST_CFG_FILE_SUFFIX,
        default=None,
    )
    parser.add_argument(
        "--project",
        type=str,
        help="specify target for the action, for example: pytorch or projects/pytorch" + rckb_constants.RCKB__APP_CFG_FILE_SUFFIX,
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
        help="specify project for the action, for example: pytorch or projects/pytorch" + rckb_constants.RCKB__APP_CFG_FILE_SUFFIX,
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
        help="Base directory where each projects source code is checked out. Default is src_projects.",
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
        print(
            "checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install argument specified"
        )
    else:
        args.cmd_force_exec = False
        # print("Action not specified.(checkout/init/clean/hipify/pre_config/config/post_config/build/install/post_install)")
        # print("Using default values")
        # enable everything except clean
        args.checkout = True
        args.init = True
        args.clean = False
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
    print("Actions Enabled:")
    print("    checkout: ", args.checkout)
    print("    init:    ", args.init)
    print("    clean:    ", args.clean)
    print("    hipify:    ", args.hipify)
    print("    pre_config:", args.pre_config)
    print("    config:", args.config)
    print("    post_config:", args.post_config)
    print("    build:    ", args.build)
    print("    install:  ", args.install)
    print("    post_install:  ", args.post_install)
    print("Projects:", args.project)


def verify_build_env__python(self, is_posix: bool):
    # check the python used. It needs to be by default an virtual env but
    # this can be overriden to real python version by setting up ENV variable
    # ROCK_PYTHON_PATH
    python_home_dir = os.path.dirname(sys.executable)
    if "VIRTUAL_ENV" in os.environ:
        os.environ["ROCK_PYTHON_PATH"] = python_home_dir
    else:
        if "ROCK_PYTHON_PATH" in os.environ:
            if not os.path.abspath(python_home_dir) == os.path.abspath(os.environ["ROCK_PYTHON_PATH"]):
                print("Error, virtual python environment is not active and")
                print("PYTHON location is different than specified by the ROCK_PYTHON_PATH")
                print("    PYTHON location: " + python_home_dir)
                print("    ROCK_PYTHON_PATH: " + os.environ["ROCK_PYTHON_PATH"])
                print("If you want use this python location instead of using a virtual python env, define ROCK_PYTHON_PATH:")
                if is_posix:
                    print("    export ROCK_PYTHON_PATH=" + python_home_dir)
                else:
                    print("    set ROCK_PYTHON_PATH=" + python_home_dir)
                print("Alternatively activate the virtual python environment")
                sys.exit(1)
            else:
                print("Using python from location: " + python_home_dir)
        else:
            print("Error, virtual python environment is not active and ROCK_PYTHON_PATH is not defined")
            print("    PYTHON location: " + python_home_dir)
            print("If you want use this python location instead of using a virtual python env, define ROCK_PYTHON_PATH:")
            if is_posix:
                print("    export ROCK_PYTHON_PATH=" + python_home_dir)
            else:
                print("    set ROCK_PYTHON_PATH=" + python_home_dir)
            print("Alternatively activate the virtual python environment")
            sys.exit(1)

def verify_build_env__rockbuilder_config(self,
                     rock_builder_home_dir: Path,
                     rock_builder_build_dir: Path):
    # read and set up env based on to rockbuilder.ini file if it exist
    rcb_config = RockBuilderConfig.RockBuilderConfig(
        rock_builder_home_dir, rock_builder_build_dir
    )
    res = rcb_config.read_cfg()
    if res:
        rcb_config.setup_build_env()


def get_rocm_sdk_targets_on_linux(exec_dir: Path):
    ret = ""
    if exec_dir is not None:
        exec_cmd = "rocm_agent_enumerator"
        print("exec_dir: " + str(exec_dir))
        print("exec_cmd: " + exec_cmd)
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
            print(
                f"Failed use to rocm_agent_enumerator to get gpu list: {result.stderr}"
            )
            sys.exit(1)
    return ret


# do all build steps for given process
def do_therock(prj_builder, args):
    ret = False
    if prj_builder is not None:
        if prj_builder.check_skip_on_os() == False:
            # setup first the project specific environment variables
            prj_builder.printout("start")
            prj_builder.do_env_setup()
            # print("do_env_setup done")

            # then do all possible commands requested for the project
            # multiple steps possible, so do not use else's here
            if args.clean:
                prj_builder.printout("clean")
                prj_builder.clean(args.cmd_force_exec)
            if args.checkout:
                prj_builder.printout("checkout")
                prj_builder.checkout(args.cmd_force_exec)
                # enable hipify always when doing the code checkout
                # even if it is not requested explicitly to be it's own command
                args.hipify = True
            if args.init:
                prj_builder.printout("init")
                prj_builder.init(args.cmd_force_exec)
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
            print("skip_windows or skip_linux enabled for project")
            prj_builder.printout("skip")
            ret = True
    return ret


# if the project_name is full path to cfg file, return it
# othetwise assume that project name is "projects/project_name.cfg"
def get_project_cfg_file_path(rock_builder_home_dir: Path, project_name: str):
    if project_name:
        if project_name.endswith(rckb_constants.RCKB__APP_CFG_FILE_SUFFIX):
            ret = Path(project_name)
        else:
            fname_base = f"{project_name}" + rckb_constants.RCKB__APP_CFG_FILE_SUFFIX
            ret = (
                Path(rock_builder_home_dir) / "projects" / fname_base
            )
        ret = ret.resolve()
    else:
        ret = project_name
    return ret

def main():
    is_posix = not any(platform.win32_ver())

    rock_builder_home_dir = rckb_constants.get_rock_builder_root_dir()
    rock_builder_build_dir = rckb_constants.get_project_build_base_dir()
    default_src_base_dir = rckb_constants.get_project_src_base_dir()

    os.environ["ROCK_BUILDER_HOME_DIR"] = rock_builder_home_dir.as_posix()
    os.environ["ROCK_BUILDER_BUILD_DIR"] = rock_builder_build_dir.as_posix()

    project_manager = get_project_list_manager(rock_builder_home_dir)
    project_list = project_manager.get_external_project_list()
    print(project_list)

    arg_parser = create_build_argument_parser(
        rock_builder_home_dir, default_src_base_dir, project_list
    )
    args = parse_build_arguments(arg_parser)

    # add output dir to environment variables
    if args.project and args.src_dir:
        # single project case with optional src_dir specified
        parent_dir = args.src_dir.parent
        if parent_dir == args.src_dir:
            print("Error, --src-dir parameter is not allowed to be a root-directory")
            sys.exit(1)
        os.environ["ROCK_BUILDER_SRC_DIR"] = parent_dir.as_posix()
    else:
        # directory where each projects source code is checked out
        os.environ["ROCK_BUILDER_SRC_DIR"] = args.src_base_dir.as_posix()
    os.environ["ROCK_BUILDER_PACKAGE_OUTPUT_DIR"] = args.output_dir.as_posix()

    # store the arguments to dictionary to make it easier to get "project_name"-version parameters
    args_dict = args.__dict__
    printout_build_arguments(args)
    verify_build_env__python(args, is_posix)
    verify_build_env__rockbuilder_config(args, rock_builder_home_dir, rock_builder_build_dir)
    #verify_build_env(args, is_posix, rock_builder_home_dir, rock_builder_build_dir)
    printout_build_env_info()

    for ii, prj_item in enumerate(project_list):
        print(f"    Project [{ii}]: {prj_item}")

    # small delay to allow user to see env variable printouts before the build starts
    time.sleep(1)

    if not args.project:
        # process all projects specified in the core_project.pcfg
        if args.src_dir:
            print(
                '\nError, "--src-dir" parameter requires also to specify the project with the "--project"-parameter'
            )
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
        if prj_builder is None:
            print("Error, failed to get the project builder")
            sys.exit(1)
        else:
            do_therock(prj_builder, args)


if __name__ == "__main__":
    main()
