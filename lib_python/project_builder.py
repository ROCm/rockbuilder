import ast
import configparser
import os
import platform
import shutil
import sys
from lib_python.repo_management import RockProjectRepo
from lib_python.utils import get_rocm_sdk_env_variables
from lib_python.utils import printout_list_items
from pathlib import Path, PurePosixPath
import lib_python.rcb_constants as rcb_const

class RockProjectBuilder(configparser.ConfigParser):

    # Read the value from the config-file's "project_info" section.
    #
    # Return value if it exist, otherwise return None
    def _get_project_info_config_value(self, config_key):
        try:
            ret = self.get("project_info", config_key)
        except:
            # just catch what ever exception is thrown by current python
            # env-version in case that the config-key/value is not specified
            # in the configuration file. (key/value pairs can be optional)
            ret = None
        return ret

    def to_boolean(self, value):
        if isinstance(value, bool):
            return value
        elif isinstance(value, (int, float)):
            return bool(value)  # 0 and 0.0 are False, others are True
        elif isinstance(value, str):
            lower_value = value.lower().strip()
            if lower_value in ("true", "yes", "1"):
                return True
            elif lower_value in ("false", "no", "0"):
                return False
            else:
                raise ValueError(f"Cannot convert '{value}' to boolean.")
        else:
            raise TypeError(f"Unsupported type: {type(value)}")

    def __init__(
        self,
        rock_builder_root_dir,
        project_src_dir: Path,
        project_cfg_base_name: str,
        project_cfg_file_path: Path,
        package_output_dir,
        version_override,
    ):
        super(RockProjectBuilder, self).__init__(allow_no_value=True)

        self.is_posix = not any(platform.win32_ver())
        self.rock_builder_root_dir = rock_builder_root_dir
        self.project_cfg_base_name = project_cfg_base_name
        self.project_cfg_file_path = project_cfg_file_path
        self.package_output_dir = package_output_dir
        if self.project_cfg_file_path.exists():
            self.read(self.project_cfg_file_path)
        else:
            raise ValueError(
                "Could not find the configuration file: "
                + self.project_cfg_file_path.as_posix()
            )
        # name, repo_url and version are not mandatory
        # (project could want to run pip install command for example)
        if self.has_option("project_info", "name"):
            self.project_name = self.get("project_info", "name")
        else:
            self.project_name = project_cfg_base_name
        if self.has_option("project_info", "repo_url"):
            self.repo_url = self.get("project_info", "repo_url")
        else:
            self.repo_url = None

        if self.has_option("project_info", "repo_tags"):
            self.repo_tags = self._get_project_info_config_value("repo_tags")
            self.repo_tags = self.to_boolean(self.repo_tags)
            if self.repo_tags:
                self.repo_depth = 0
            else:
                self.repo_depth = 1
        else:
            self.repo_depth = 1
            self.repo_tags = None

        if self.has_option("project_info", "use_rocm_sdk"):
            self.use_rocm_sdk = self._get_project_info_config_value("use_rocm_sdk")
            self.use_rocm_sdk = self.to_boolean(self.use_rocm_sdk)
        else:
            self.use_rocm_sdk = True
        print("use_rocm_sdk: " + str(self.use_rocm_sdk))

        # If the project's version_override parameter has been set, then use that version
        # instead of using the version specified in the project.cfg file
        env_version_name = "--" + self.project_name + "-version"
        if version_override:
            self.project_version = version_override
            print("Overriding project version with the value given as a parameter")
            print("    " + env_version_name + ": " + self.project_version)
        else:
            # check the version from the project.cfg file
            if self.has_option("project_info", "version"):
                self.project_version = self.get("project_info", "version")
            else:
                self.project_version = None
        if self.has_option("project_info", "patch_dir"):
            self.project_patch_dir_base_name = self.get("project_info", "patch_dir")
        else:
            self.project_patch_dir_base_name = self.project_version

        # environment setup can have common and os-specific sections that needs to be appended together
        if self.is_posix:
            self.skip_on_os = self._get_project_info_config_value("skip_linux")
        else:
            self.skip_on_os = self._get_project_info_config_value("skip_windows")
        self.env_setup_cmd = None
        value = self._get_project_info_config_value("env_common")
        if value:
            self.env_setup_cmd = list(
                filter(None, (x.strip() for x in value.splitlines()))
            )
        if self.is_posix:
            value = self._get_project_info_config_value("env_linux")
            if value:
                temp_env_list = list(
                    filter(None, (x.strip() for x in value.splitlines()))
                )
                if self.env_setup_cmd:
                    self.env_setup_cmd.extend(temp_env_list)
                else:
                    self.env_setup_cmd = temp_env_list
        else:
            value = self._get_project_info_config_value("env_windows")
            if value:
                temp_env_list = list(
                    filter(None, (x.strip() for x in value.splitlines()))
                )
                if self.env_setup_cmd:
                    self.env_setup_cmd.extend(temp_env_list)
                else:
                    self.env_setup_cmd = temp_env_list
        self.init_cmd = self._get_project_info_config_value("init_cmd")
        self.clean_cmd = self._get_project_info_config_value("clean_cmd")
        self.hipify_cmd = self._get_project_info_config_value("hipify_cmd")
        self.pre_config_cmd = self._get_project_info_config_value("pre_config_cmd")
        self.config_cmd = self._get_project_info_config_value("config_cmd")
        self.post_config_cmd = self._get_project_info_config_value("post_config_cmd")

        is_windows = any(platform.win32_ver())
        # here we want to check if window option is set
        # otherwise we use generic "build_cmd" option also on windows
        if is_windows and self.has_option("project_info", "build_cmd_windows"):
            self.build_cmd = self._get_project_info_config_value("build_cmd_windows")
        else:
            self.build_cmd = self._get_project_info_config_value("build_cmd")
        self.cmake_config = self._get_project_info_config_value("cmake_config")
        self.install_cmd = self._get_project_info_config_value("install_cmd")
        self.post_install_cmd = self._get_project_info_config_value("post_install_cmd")

        self.project_root_dir_path = Path(rock_builder_root_dir)
        self.project_src_dir_path = project_src_dir
        self.project_build_dir_path = (
            Path(rock_builder_root_dir) / "builddir" / self.project_cfg_base_name
        )

        self.cmd_execution_dir = self._get_project_info_config_value("cmd_exec_dir")
        if self.cmd_execution_dir is None:
            # default value if not specified in the config-file
            self.cmd_execution_dir = self.project_src_dir_path
        self.patch_dir_root_arr = []
        self.patch_dir_root_arr.append(Path(rock_builder_root_dir)
                      / "patches")
        self.patch_dir_root_arr.append(Path(rock_builder_root_dir)
                      / "sdk/therock/external-builds/pytorch/patches")
        for ii, element in enumerate(self.patch_dir_root_arr):
            self.patch_dir_root_arr[ii] = self.patch_dir_root_arr[ii].resolve()
        self.project_repo = RockProjectRepo(
            self.package_output_dir,
            self.project_name,
            self.project_cfg_base_name,
            self.project_root_dir_path,
            self.project_src_dir_path,
            self.project_build_dir_path,
            self.cmd_execution_dir,
            self.repo_url,
            self.project_version,
            self.project_patch_dir_base_name,
            self.patch_dir_root_arr,
        )

    # printout project builder specific info for logging and debug purposes
    def printout(self, phase):
        print("Project build phase " + phase + ": -----")
        print("    Project_name:     " + self.project_name)
        print("    Project cfg name: " + self.project_cfg_base_name)
        print("    Project cfg file: " + self.project_cfg_file_path.as_posix())
        if self.project_version:
            print("    Version:          " + self.project_version)
        print("    Source dir:       " + self.project_src_dir_path.as_posix())
        for ii, cur_patch_dir_root in enumerate(self.patch_dir_root_arr):
            if self.project_name:
                if self.project_patch_dir_base_name:
                    print("    Patch dir[" + str(ii) + "]:     " + str(cur_patch_dir_root / self.project_name / self.project_patch_dir_base_name))
                else:
                    print("    Patch dir[" + str(ii) + "]:     " + str(cur_patch_dir_root / self.project_name))
            else:
                print("    Patch dir[" + str(ii) + "]:     " + str(cur_patch_dir_root / self.project_name))
                sys.exit(1)
        print("    Build dir:        " + self.project_build_dir_path.as_posix())
        print("------------------------")

    def printout_error_and_terminate(self, phase):
        self.printout(phase)
        print(phase + " failed")
        sys.exit(1)

    # check whether operations should be skipped on current operating system
    def check_skip_on_os(self):
        ret = True
        if (self.skip_on_os is None) or (
            (self.skip_on_os != "1")
            and (str(self.skip_on_os).casefold() != str("y").casefold())
            and (str(self.skip_on_os).casefold() != str("yes").casefold())
            and (str(self.skip_on_os).casefold() != str("on").casefold())
        ):
            ret = False
        return ret

    def _get_cmd_phase_stamp_filename(self, operation_phase_name:str):
        fname = operation_phase_name + ".done"
        ret = Path(self.project_build_dir_path) / fname
        return ret

    def _add_stamp_filename_to_list_if_phase_equal_or_forced(self,
                          phase_stamp_fname_arr,
                          searched_phase_name: str,
                          phase_name: str,
                          force_add: bool):
        if (searched_phase_name == phase_name) or force_add:
            ret = True
            fname = self._get_cmd_phase_stamp_filename(searched_phase_name)
            phase_stamp_fname_arr.append(Path(fname))
        else:
            ret = False
        return ret

    # add stamp filenames for command_phase and all other commands that would be executed after it
    def _get_cmd_phase_stamp_filenames_for_pending_commands(self, cmd_phase_name:str):
        ret = []
        force_add = False
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_CHECKOUT, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_HIPIFY, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_INIT, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_PRECONFIG, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_CONFIG, cmd_phase_name, force_add)
        # add cmake version of phase_cmd after as we do not have specific user arg command for it
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_CMAKE_CONFIG, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_POSTCONFIG, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_BUILD, cmd_phase_name, force_add)
        # add cmake version of phase_cmd after as we do not have specific user arg command for it
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_CMAKE_BUILD, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_INSTALL, cmd_phase_name, force_add)
        # add cmake version of phase_cmd after as we do not have specific user arg command for it
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_CMAKE_INSTALL, cmd_phase_name, force_add)
        force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__PRJ_CFG__KEY__CMD_POSTINSTALL, cmd_phase_name, force_add)
        return ret

    def _clean_pending_cmd_phases_stamp_filenames(self, cmd_phase_name):
        fname_arr = self._get_cmd_phase_stamp_filenames_for_pending_commands(cmd_phase_name)
        for fname in fname_arr:
            try:
                fname.unlink(missing_ok=True)
            except OSError as ex1:
                print("Error, failed to delete phase command stamp file:")
                print("    " + str(fname))
                sys.exit(1)


    def _is_cmd_phase_exec_required(self, cmd_phase_name:str, force_exec: bool):
        if force_exec:
            ret = True
        else:
            # exec needed if stamp filename does not exist
            fname = self._get_cmd_phase_stamp_filename(cmd_phase_name)
            ret = not fname.exists()
            #print("_is_cmd_phase_exec_required, fname: " + str(fname) + ", res: " + str(ret))
        if ret:
            self._clean_pending_cmd_phases_stamp_filenames(cmd_phase_name)
        return ret

    def _set_cmd_phase_done_on_success(self, res: bool, cmd_phase_name: str):
        #print("_set_cmd_phase_done_on_success, phase: " + cmd_phase_name + ", res: " + str(res))
        if res:
            fname = self._get_cmd_phase_stamp_filename(cmd_phase_name)
            fname.touch()
            ret = fname.exists()
            if not res:
                print("Failed to create operation success stamp file: " + str(fname))
                sys.exit(1)
        else:
            if not res:
                self.printout_error_and_terminate(cmd_phase_name)


    def do_env_setup(self):
        rocm_sdk_setup_cmd_list = None
        if self.use_rocm_sdk:
            if "ROCM_HOME" in os.environ:
                rocm_home_root_path = Path(os.environ["ROCM_HOME"])
                rocm_home_root_path = rocm_home_root_path.resolve()
                rocm_sdk_setup_cmd_list = get_rocm_sdk_env_variables(rocm_home_root_path, self.use_rocm_sdk, True)
                printout_list_items(rocm_sdk_setup_cmd_list)
            else:
                print("Failed to setup env for rockbuilder project")
                print("    ROCM_HOME not defined")
                sys.exit(1)
        res = self.project_repo.do_env_setup(rocm_sdk_setup_cmd_list, self.env_setup_cmd)
        if not res:
            self.printout_error_and_terminate("env_setup")

    def undo_env_setup(self):
        res = self.project_repo.undo_env_setup()
        if not res:
            self.printout_error_and_terminate("undo_env_setup")

    def init(self, force_exec: bool):
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_INIT
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_init(self.init_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def clean(self, force_exec: bool):
		# delete build directory
        shutil.rmtree(self.project_build_dir_path)
        # then create it again
        cur_p = Path(self.project_build_dir_path)
        cur_p.mkdir(parents=True, exist_ok=True)
        # and finally run other optional clean commands
        res = self.project_repo.do_clean(self.clean_cmd)

    def checkout(self, force_exec: bool):
        if self.repo_url:
            phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_CHECKOUT
            res = self._is_cmd_phase_exec_required(phase_name, force_exec)
            if res:
                res = self.project_repo.do_checkout(repo_fetch_depth=self.repo_depth, repo_fetch_tags=self.repo_tags)
                self._set_cmd_phase_done_on_success(res, phase_name)

    def hipify(self, force_exec: bool):
        if self.repo_url:
            phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_HIPIFY
            res = self._is_cmd_phase_exec_required(phase_name, force_exec)
            if res:
                res = self.project_repo.do_hipify(self.hipify_cmd)
                self._set_cmd_phase_done_on_success(res, phase_name)

    def pre_config(self, force_exec: bool):
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_PRECONFIG
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_pre_config(self.pre_config_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def config(self, force_exec: bool):
		# cmd_config_cmake
        if self.cmake_config:
            phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_CMAKE_CONFIG
            res = self._is_cmd_phase_exec_required(phase_name, force_exec)
            if res:
                # in case that project has cmake configure/build/install needs
                res = self.project_repo.do_cmake_config(self.cmake_config)
                self._set_cmd_phase_done_on_success(res, phase_name)
        # cmd_config
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_CONFIG
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_config(self.config_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def post_config(self, force_exec: bool):
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_POSTCONFIG
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_post_config(self.post_config_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def build(self, force_exec: bool):
        # cmd_build_cmake is done only if cmake config exist
        if self.cmake_config:
            phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_CMAKE_BUILD
            res = self._is_cmd_phase_exec_required(phase_name, force_exec)
            if res:
                # not all projects have things to build with cmake
                res = self.project_repo.do_cmake_build(self.cmake_config)
                self._set_cmd_phase_done_on_success(res, phase_name)
        # cmd_build
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_BUILD
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_build(self.build_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def install(self, force_exec: bool):
        # do cmd_install_cmake is done only if cmake config exist
        if self.cmake_config:
            phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_CMAKE_INSTALL
            res = self._is_cmd_phase_exec_required(phase_name, force_exec)
            if res:
                res = self.project_repo.do_cmake_install()
                self._set_cmd_phase_done_on_success(res, phase_name)
        # cmd_install
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_INSTALL
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_install(self.install_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)


    def post_install(self, force_exec: bool):
        phase_name = rcb_const.RCB__PRJ_CFG__KEY__CMD_POSTINSTALL
        res = self._is_cmd_phase_exec_required(phase_name, force_exec)
        if res:
            res = self.project_repo.do_post_install(self.post_install_cmd)
            self._set_cmd_phase_done_on_success(res, phase_name)

class RockExternalProjectListManager(configparser.ConfigParser):
    def __init__(self, rock_builder_root_dir: Path, project_list_name, project_cfg_name):
        # default application list to builds
        self.rock_builder_root_dir = rock_builder_root_dir
        super(RockExternalProjectListManager, self).__init__(allow_no_value=True)
        if project_list_name:
            project_list_name = Path(project_list_name)
        if not project_list_name and not project_cfg_name:
            project_list_name = rock_builder_root_dir / "projects" / "core_apps.pcfg"
        if project_list_name:
            if project_list_name.exists():
                self.read(project_list_name)
                value = self.get("projects", "project_list")
                # convert to list of project string names
                self.prj_list = list(
                    filter(None, (x.strip() for x in value.splitlines()))
                )
            else:
                self.prj_list = []
        elif project_cfg_name:
            self.prj_list = [project_cfg_name]
        else:
            self.prj_list = []

    def get_external_project_list(self):
        return self.prj_list

    def get_rock_project_builder(
        self,
        project_src_dir: Path,
        project_cfg_base_name: str,
        project_cfg_file_path: Path,
        package_output_dir: Path,
        version_override,
    ):
        ret = None
        try:
            ret = RockProjectBuilder(
                self.rock_builder_root_dir,
                project_src_dir,
                project_cfg_base_name,
                project_cfg_file_path,
                package_output_dir,
                version_override,
            )
        except ValueError as e:
            print(str(e))
        return ret
