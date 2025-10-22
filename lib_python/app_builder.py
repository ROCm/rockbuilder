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

class ConfigReader(configparser.ConfigParser):
    def __init__(
        self,
        cfg_path: Path
    ):
        super(ConfigReader, self).__init__(allow_no_value=True)

        self._is_app_config = False
        self._is_app_list_config = False
        self.cfg_path = cfg_path
        if self.cfg_path.exists():
            try:
                self.read(self.cfg_path)
            except:
                raise ValueError(
                    "Could not read the configuration file: "
                    + self.cfg_path.as_posix()
                )
        else:
            raise ValueError(
                "Could not find the app configuration file: "
                + self.cfg_path.as_posix()
            )
        if self.has_section(rcb_const.RCB__APP_CFG__SECTION_APP_INFO):
            self._is_app_config = True
        else:
            if (self.has_section(rcb_const.RCB__APPS_CFG__SECTION_APPS) and
                self.has_option(rcb_const.RCB__APPS_CFG__SECTION_APPS, rcb_const.RCB__APPS_CFG__KEY__APP_LIST)):
               self._is_app_list_config = True


    def is_app_config(self):
        return self._is_app_config


    def is_app_list_config(self):
        return self._is_app_list_config


        # app_info section is mandatory but the
        # name, repo_url and version information is not
        # (project could want to run pip install command for example)
        if not self.has_section(rcb_const.RCB__APP_CFG__SECTION_APP_INFO):
            raise ValueError(
                "Could not find the app_info from configuration file: "
                + self.cfg_path.as_posix()
            )


class RockProjectBuilder(configparser.ConfigParser):
    def _to_boolean(self, value):
        if not value:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)  # 0 and 0.0 are False, others are True
        elif isinstance(value, str):
            lower_value = value.lower().strip()
            if lower_value in ("true", "yes", "on", "1"):
                return True
            elif lower_value in ("false", "no", "off", "0"):
                return False
            else:
                raise ValueError(f"Cannot convert '{value}' to boolean.")
        else:
            raise TypeError(f"Unsupported type: {type(value)}")

    # Read the value from the config-file's rcb_const.RCB__APP_CFG__SECTION_APP_INFO section.
    #
    # Return value if it exist, otherwise return None
    def _get_app_info_config_value(self, config_key):
        ret = None
        try:
            if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, config_key):
                ret = self.get(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, config_key)
        except:
            pass
            # just catch what ever exception is thrown by current python
            # env-version in case that the config-key/value is not specified
            # in the configuration file. (key/value pairs can be optional)
        return ret


    def _get_app_info_boolean_value(self, config_key):
        val = self._get_app_info_config_value(config_key)
        ret = self._to_boolean(val)
        return ret


    #return either os specific or generic version of command depending which is available.
    #if both versions of command exist in app-config file, then the os-specific is selected.
    def _get_cmd_phase_allowing_os_override(self, cmd_generic):
        if self.is_posix:
            cmd_os = cmd_generic + rcb_const.RCB__APP_CFG__CMD_PHASE_EXTENSION_LINUX
        else:
            cmd_os = cmd_generic + rcb_const.RCB__APP_CFG__CMD_PHASE_EXTENSION_WINDOWS
        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, cmd_os):
            ret = self._get_app_info_config_value(cmd_os)
        else:
            ret = self._get_app_info_config_value(cmd_generic)
        return ret


    def __init__(
        self,
        rock_builder_root_dir,
        app_src_dir: Path,
        app_cfg_base_name: str,
        app_cfg_path: Path,
        package_output_dir,
        version_override,
    ):
        super(RockProjectBuilder, self).__init__(allow_no_value=True)

        self.is_posix = not any(platform.win32_ver())
        self.rock_builder_root_dir = rock_builder_root_dir
        self.app_cfg_base_name = app_cfg_base_name
        self.app_cfg_path = app_cfg_path
        self.package_output_dir = package_output_dir
        if self.app_cfg_path.exists():
            self.read(self.app_cfg_path)
        else:
            raise ValueError(
                "Could not find the app configuration file: "
                + self.app_cfg_path.as_posix()
            )
        # app_info section is mandatory but the
        # name, repo_url and version information is not
        # (project could want to run pip install command for example)
        if not self.has_section(rcb_const.RCB__APP_CFG__SECTION_APP_INFO):
            raise ValueError(
                "Could not find the app_info from configuration file: "
                + self.app_cfg_path.as_posix()
            )
        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__APP_NAME):
            self.app_name = self.get(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__APP_NAME)
        else:
            self.app_name = app_cfg_base_name
        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__REPO_URL):
            self.repo_url = self.get(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__REPO_URL)
        else:
            self.repo_url = None

        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__PROP_FETCH_REPO_TAGS):
            self.repo_tags = self._get_app_info_boolean_value(rcb_const.RCB__APP_CFG__KEY__PROP_FETCH_REPO_TAGS)
            if self.repo_tags:
                self.repo_depth = 0
            else:
                self.repo_depth = 1
        else:
            self.repo_depth = 1
            self.repo_tags = None

        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__PROP_IS_ROCM_SDK_USED):
            self.use_rocm_sdk = self._get_app_info_boolean_value(rcb_const.RCB__APP_CFG__KEY__PROP_IS_ROCM_SDK_USED)
        else:
            self.use_rocm_sdk = True
        print(rcb_const.RCB__APP_CFG__KEY__PROP_IS_ROCM_SDK_USED + ": " + str(self.use_rocm_sdk))

        # If the project's version_override parameter has been set, then use that version
        # instead of using the version specified in the project.cfg file
        env_version_name = "--" + self.app_name + "-version"
        if version_override:
            self.app_version = version_override
            print("Overriding project version with the value given as a parameter")
            print("    " + env_version_name + ": " + self.app_version)
        else:
            # check the version from the project.cfg file
            if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__APP_VERSION):
                self.app_version = self.get(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__APP_VERSION)
            else:
                self.app_version = None
        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__PATCH_DIR):
            self.app_patch_dir_base_name = self.get(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, rcb_const.RCB__APP_CFG__KEY__PATCH_DIR)
        else:
            self.app_patch_dir_base_name = self.app_version

        # environment setup can have common and os-specific sections that needs to be appended together
        if self.is_posix:
            prop_name = rcb_const.RCB__APP_CFG__KEY__PROP_IS_BUILD_ENABLED_LINUX
        else:
            prop_name = rcb_const.RCB__APP_CFG__KEY__PROP_IS_BUILD_ENABLED_WINDOWS
        if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, prop_name):
            self.enable_on_os = self._get_app_info_boolean_value(prop_name)
        else:
            # check only if OS specific property version is not used
            prop_name = rcb_const.RCB__APP_CFG__KEY__PROP_IS_BUILD_ENABLED
            if self.has_option(rcb_const.RCB__APP_CFG__SECTION_APP_INFO, prop_name):
                self.enable_on_os = self._get_app_info_boolean_value(prop_name)
            else:
                self.enable_on_os = True

        self._get_app_info_boolean_value
        self.env_setup_cmd = None
        value = self._get_app_info_config_value(rcb_const.RCB__APP_CFG__KEY__ENV_VAR)
        if value:
            self.env_setup_cmd = list(
                filter(None, (x.strip() for x in value.splitlines()))
            )
        if self.is_posix:
            value = self._get_app_info_config_value(rcb_const.RCB__APP_CFG__KEY__ENV_VAR_LINUX)
            if value:
                temp_env_list = list(
                    filter(None, (x.strip() for x in value.splitlines()))
                )
                if self.env_setup_cmd:
                    self.env_setup_cmd.extend(temp_env_list)
                else:
                    self.env_setup_cmd = temp_env_list
        else:
            value = self._get_app_info_config_value(rcb_const.RCB__APP_CFG__KEY__ENV_VAR_WINDOWS)
            if value:
                temp_env_list = list(
                    filter(None, (x.strip() for x in value.splitlines()))
                )
                if self.env_setup_cmd:
                    self.env_setup_cmd.extend(temp_env_list)
                else:
                    self.env_setup_cmd = temp_env_list
        # here we want to check if specific CMD_XXX_LINUX or CMD_XXX_WINDOWS option is set
        # otherwise we use generic "CMD_XXX" option
        self.CMD_INIT         = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_INIT)
        self.CMD_CLEAN        = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_CLEAN)
        self.CMD_HIPIFY       = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_HIPIFY)
        self.CMD_PRE_CONFIG   = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_PRE_CONFIG)
        self.CMD_CONFIG       = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_CONFIG)
        self.CMD_POST_CONFIG  = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_POST_CONFIG)
        self.CMD_BUILD        = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_BUILD)
        self.CMD_CMAKE_CONFIG = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_CONFIG)
        self.CMD_INSTALL      = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_INSTALL)
        self.CMD_POST_INSTALL = self._get_cmd_phase_allowing_os_override(rcb_const.RCB__APP_CFG__KEY__CMD_POST_INSTALL)

        self.app_root_dir_path = Path(rock_builder_root_dir)
        self.app_src_dir_path = app_src_dir
        self.app_build_dir_path = (
            rcb_const.RCB__APP_BUILD_ROOT_DIR / self.app_cfg_base_name
        )

        self.cmd_execution_dir = self._get_app_info_config_value(rcb_const.RCB__APP_CFG__KEY__CMD_EXEC_DIR)
        if self.cmd_execution_dir is None:
            # default value if not specified in the config-file
            self.cmd_execution_dir = self.app_src_dir_path
        self.patch_dir_root_arr = []
        self.patch_dir_root_arr.append(rcb_const.RCB__APP_PATCHES_ROOT_DIR)
        self.patch_dir_root_arr.append(rcb_const.THEROCK_SDK_SRC__PATCHES_ROOT_DIR)
        for ii, element in enumerate(self.patch_dir_root_arr):
            self.patch_dir_root_arr[ii] = self.patch_dir_root_arr[ii].resolve()
        self.app_repo = RockProjectRepo(
            self.package_output_dir,
            self.app_name,
            self.app_cfg_base_name,
            self.app_root_dir_path,
            self.app_src_dir_path,
            self.app_build_dir_path,
            self.cmd_execution_dir,
            self.repo_url,
            self.app_version,
            self.app_patch_dir_base_name,
            self.patch_dir_root_arr,
        )

    # printout project builder specific info for logging and debug purposes
    def printout(self, phase):
        print("Project build phase " + phase + ": -----")
        print("    Project_name:     " + self.app_name)
        print("    Project cfg name: " + self.app_cfg_base_name)
        print("    Project cfg file: " + self.app_cfg_path.as_posix())
        if self.app_version:
            print("    Version:          " + self.app_version)
        print("    Source dir:       " + self.app_src_dir_path.as_posix())
        for ii, cur_patch_dir_root in enumerate(self.patch_dir_root_arr):
            if self.app_name:
                if self.app_patch_dir_base_name:
                    print("    Patch dir[" + str(ii) + "]:     " + str(cur_patch_dir_root / self.app_name / self.app_patch_dir_base_name))
                else:
                    print("    Patch dir[" + str(ii) + "]:     " + str(cur_patch_dir_root / self.app_name))
            else:
                print("    Patch dir[" + str(ii) + "]:     " + str(cur_patch_dir_root / self.app_name))
                sys.exit(1)
        print("    Build dir:        " + self.app_build_dir_path.as_posix())
        print("------------------------")

    def printout_error_and_terminate(self, phase):
        self.printout(phase)
        print(phase + " failed")
        sys.exit(1)

    # check whether operations should be skipped on current operating system
    def is_build_enabled_on_current_os(self):
        ret = False
        if self.enable_on_os:
            ret = self.enable_on_os
        return ret

    def _get_cmd_phase_stamp_filename(self, operation_phase_name:str):
        fname = operation_phase_name + ".done"
        ret = Path(self.app_build_dir_path) / fname
        return ret

    def _add_stamp_filename_to_list_if_phase_equal_or_forced(self,
                          phase_stamp_fname_arr,
                          searched_phase_name: str,
                          phase_name: str,
                          force_add: bool):
        #print("searched_phase_name: " + searched_phase_name)
        #print("phase_name: " + phase_name)
        if (searched_phase_name == phase_name) or force_add:
            ret = True
            fname = self._get_cmd_phase_stamp_filename(searched_phase_name)
            phase_stamp_fname_arr.append(Path(fname))
        else:
            ret = False
        return ret

    # add stamp filenames for command_phase and all other commands that would be executed after it
    def _get_cmd_phase_stamp_filenames_for_pending_commands(self,
                        cmd_phase_name:str,
                        cmd_init_force_exec:bool,
                        cmd_any_force_exec:bool):
        ret = []
        force_add = False
        if (((cmd_phase_name == rcb_const.RCB__APP_CFG__KEY__CMD_INIT) and cmd_init_force_exec) or
            ((cmd_phase_name != rcb_const.RCB__APP_CFG__KEY__CMD_INIT) and cmd_any_force_exec)):
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_INIT, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_CHECKOUT, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_HIPIFY, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_PRE_CONFIG, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_CONFIG, cmd_phase_name, force_add)
            # add cmake version of phase_cmd after as we do not have specific user arg command for it
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_CONFIG, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_POST_CONFIG, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_BUILD, cmd_phase_name, force_add)
            # add cmake version of phase_cmd after as we do not have specific user arg command for it
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_BUILD, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_INSTALL, cmd_phase_name, force_add)
            # add cmake version of phase_cmd after as we do not have specific user arg command for it
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_INSTALL, cmd_phase_name, force_add)
            force_add = self._add_stamp_filename_to_list_if_phase_equal_or_forced(ret, rcb_const.RCB__APP_CFG__KEY__CMD_POST_INSTALL, cmd_phase_name, force_add)
        return ret

    def _clean_pending_cmd_phases_stamp_filenames(self,
                           cmd_phase_name:str,
                           cmd_init_force_exec:bool,
                           cmd_any_force_exec:bool):
        fname_arr = self._get_cmd_phase_stamp_filenames_for_pending_commands(cmd_phase_name,
                                           cmd_init_force_exec,
                                           cmd_any_force_exec)
        for fname in fname_arr:
            try:
                fname.unlink(missing_ok=True)
            except OSError as ex1:
                print("Error, failed to delete phase command stamp file:")
                print("    " + str(fname))
                sys.exit(1)


    def _is_cmd_phase_exec_required(self,
                      cmd_phase_name:str,
                      cmd_init_force_exec:bool,
                      cmd_any_force_exec:bool):
        #print("cmd_phase_name: " + cmd_phase_name)
        #print("cmd_init_force_exec: " + str(cmd_init_force_exec))
        #print("cmd_any_force_exec: " + str(cmd_any_force_exec))
        if cmd_init_force_exec or cmd_any_force_exec:
            # exec of command phase needed
            ret = True
        else:
            # exec needed if stamp filename does not exist
            fname = self._get_cmd_phase_stamp_filename(cmd_phase_name)
            ret = not fname.exists()
            #print("_is_cmd_phase_exec_required, fname: " + str(fname) + ", res: " + str(ret))
        if ret:
            self._clean_pending_cmd_phases_stamp_filenames(cmd_phase_name,
                                     cmd_init_force_exec,
                                     cmd_any_force_exec)
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
                rocm_sdk_setup_cmd_list = get_rocm_sdk_env_variables(rocm_home_root_path,
                                                                     False,
                                                                     True)
                printout_list_items(rocm_sdk_setup_cmd_list)
            else:
                print("Failed to setup env for rockbuilder project")
                print("    ROCM_HOME not defined")
                sys.exit(1)
        res = self.app_repo.do_env_setup(rocm_sdk_setup_cmd_list, self.env_setup_cmd)
        if not res:
            self.printout_error_and_terminate("env_setup")

    def undo_env_setup(self):
        res = self.app_repo.undo_env_setup()
        if not res:
            self.printout_error_and_terminate("undo_env_setup")

    def init(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_INIT
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            if self.CMD_INIT:
                res = self.app_repo.do_init(self.CMD_INIT)
            else:
                res = True
            self._set_cmd_phase_done_on_success(res, phase_name)

    def clean(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
		# delete build directory
        shutil.rmtree(self.app_build_dir_path)
        # then create it again
        cur_p = Path(self.app_build_dir_path)
        cur_p.mkdir(parents=True, exist_ok=True)
        # and finally run other optional clean commands
        res = self.app_repo.do_clean(self.CMD_CLEAN)

    def checkout(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        if self.repo_url:
            phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_CHECKOUT
            res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
            if res:
                res = self.app_repo.do_checkout(repo_fetch_depth=self.repo_depth, repo_fetch_tags=self.repo_tags)
                self._set_cmd_phase_done_on_success(res, phase_name)

    def hipify(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        if self.repo_url:
            phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_HIPIFY
            res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
            if res:
                res = self.app_repo.do_hipify(self.CMD_HIPIFY)
                self._set_cmd_phase_done_on_success(res, phase_name)

    def pre_config(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_PRE_CONFIG
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            res = self.app_repo.do_pre_config(self.CMD_PRE_CONFIG)
            # print("res: " + str(res))
            self._set_cmd_phase_done_on_success(res, phase_name)

    def config(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
		# cmd_config_cmake
        if self.CMD_CMAKE_CONFIG:
            phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_CONFIG
            res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
            if res:
                # in case that project has cmake configure/build/install needs
                res = self.app_repo.do_CMD_CMAKE_CONFIG(self.CMD_CMAKE_CONFIG)
                self._set_cmd_phase_done_on_success(res, phase_name)
        # cmd_config
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_CONFIG
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            res = self.app_repo.do_config(self.CMD_CONFIG)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def post_config(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_POST_CONFIG
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            res = self.app_repo.do_post_config(self.CMD_POST_CONFIG)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def build(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        # cmd_build_cmake is done only if cmake config exist
        if self.CMD_CMAKE_CONFIG:
            phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_BUILD
            res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
            if res:
                # not all app have things to build with cmake
                res = self.app_repo.do_cmake_build(self.CMD_CMAKE_CONFIG)
                self._set_cmd_phase_done_on_success(res, phase_name)
        # cmd_build
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_BUILD
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            res = self.app_repo.do_build(self.CMD_BUILD)
            self._set_cmd_phase_done_on_success(res, phase_name)

    def install(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        # do cmd_install_cmake is done only if cmake config exist
        if self.CMD_CMAKE_CONFIG:
            phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_INSTALL
            res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
            if res:
                res = self.app_repo.do_cmake_install()
                self._set_cmd_phase_done_on_success(res, phase_name)
        # cmd_install
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_INSTALL
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            res = self.app_repo.do_install(self.CMD_INSTALL)
            self._set_cmd_phase_done_on_success(res, phase_name)


    def post_install(self, cmd_init_force_exec:bool, cmd_any_force_exec:bool):
        phase_name = rcb_const.RCB__APP_CFG__KEY__CMD_POST_INSTALL
        res = self._is_cmd_phase_exec_required(phase_name, cmd_init_force_exec, cmd_any_force_exec)
        if res:
            res = self.app_repo.do_post_install(self.CMD_POST_INSTALL)
            self._set_cmd_phase_done_on_success(res, phase_name)

class RockExternalProjectListManager(configparser.ConfigParser):
    def __init__(
        self,
        rock_builder_root_dir: Path,
        config_info: ConfigReader
    ):
        # default application list to builds
        self.rock_builder_root_dir = rock_builder_root_dir
        self.config_info = config_info
        super(RockExternalProjectListManager, self).__init__(allow_no_value=True)

        self.prj_list = []
        if config_info:
            if config_info.is_app_config():
                self.prj_list = [config_info.cfg_path]
            elif config_info.is_app_list_config():
                self.read(config_info.cfg_path)
                value = self.get(rcb_const.RCB__APPS_CFG__SECTION_APPS,
                                 rcb_const.RCB__APPS_CFG__KEY__APP_LIST)
                # convert to list of project string names
                self.prj_list = list(
                    filter(None, (x.strip() for x in value.splitlines()))
                )

    def get_external_app_list(self):
        return self.prj_list

    def get_rock_app_builder(
        self,
        app_src_dir: Path,
        app_cfg_base_name: str,
        app_cfg_path: Path,
        package_output_dir: Path,
        version_override,
        printout_err: bool,
    ):
        ret = None
        try:
            ret = RockProjectBuilder(
                self.rock_builder_root_dir,
                app_src_dir,
                app_cfg_base_name,
                app_cfg_path,
                package_output_dir,
                version_override,
            )
        except ValueError as e:
            if printout_err:
                print(str(e))
        return ret
