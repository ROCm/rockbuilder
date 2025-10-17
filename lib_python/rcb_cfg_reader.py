import ast
import configparser
import os
import platform
import sys
import ast
import subprocess
import lib_python.rcb_constants as rcb_const
from lib_python.utils import get_python_wheel_rocm_sdk_home
from lib_python.utils import get_config_value_from_one_element_list
from lib_python.utils import get_python_wheel_rocm_sdk_gpu_list_str
from lib_python.repo_management import RockProjectRepo
from pathlib import Path, PurePosixPath

class RCBConfigReader(configparser.ConfigParser):
    def __init__(self, rcb_root_dir: Path, rcb_build_dir: Path):
        super(RCBConfigReader, self).__init__(allow_no_value=True)
        self.rcb_root_dir = rcb_root_dir
        self.rcb_build_dir = rcb_build_dir
        self.fname = rcb_const.get_rock_builder_config_file()

        self.last_mod_time = 0
        self.gpu_target_list = None
        # python wheel server url from where to install the wheels
        # if install from python wheels is selected
        self.rock_sdk_whl_url = None
        # location where the therock build will install
        self.rock_sdk_home_therock_build_dir = None
        # location from where the existing rocm sdk install was found
        self.rock_sdk_home_existing_install_dir = None

        if self.fname.exists():
            try:
                # get last modified date
                f_stats = self.fname.stat()
                self.last_mod_time = f_stats.st_mtime
                # print("self.last_mod_time:" + str(self.last_mod_time))
                # read the config values
                self.read(self.fname)
                
                self.gpu_target_list = self.get_as_list(
                                          rcb_const.RCB__CFG__SECTION__BUILD_TARGETS,
			                              rcb_const.RCB__CFG__KEY__GPUS)
                if self.has_option(rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_PYTHON_WHEELS):
                    self.rock_sdk_whl_url = get_config_value_from_one_element_list(self,
                                   rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_PYTHON_WHEELS)
                if self.has_option(rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_BUILD):			    
                    self.rock_sdk_home_therock_build_dir = get_config_value_from_one_element_list(self,
                                   rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_BUILD)
                if self.has_option(rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME):
                    self.rock_sdk_home_existing_install_dir = get_config_value_from_one_element_list(self,
                                   rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                   rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME)
            except PermissionError:
                print("No permission to read configuration file:")
                print("    " + str(self.fname))
                sys.exit(1)
            except:
                print("Failed to read configuration file:")
                print("    " + str(self.fname))
                sys.exit(1)
        else:
            raise FileNotFoundError("File " + str(self.fname) + " not found.")


    def _replace_env_variables(self, cmd_str):
        ret = os.path.expandvars(cmd_str)
        return ret

    def _exec_subprocess_cmd(self, exec_cmd, exec_dir):
        ret = True
        if exec_cmd is not None:
            exec_dir = self._replace_env_variables(exec_dir)
            print("exec_cmd: " + exec_cmd)
            # capture_output=True --> can print output after process exist, not possible to see the output during the build time
            # capture_output=False --> can print output only during build time
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

    def _is_rocm_sdk_python_wheel_update_needed(self,
                                                python_home_dir, time_sec):
        ret = True
        try:
            config = configparser.ConfigParser()
            # compare time stamps to check whether rocm sdk python wheels needs to
            # be upgraded even if old install exist
            stamp_fname = rcb_const.RCB__CFG__STAMP_FILE_NAME
            if stamp_fname.exists():
                config.read(stamp_fname)
                if config.has_option("timestamps", python_home_dir):
                    time_read_str = config["timestamps"][python_home_dir]
                    if time_read_str == str(time_sec):
                        print(
                            f"Timestamp matches for "
                            + python_home_dir
                            + ": "
                            + str(time_sec)
                        )
                        ret = False
        except FileExistsError:
            print(f"Directory '{directory_name}' already exists.")
        except OSError as e:
            print(f"Error creating directory '{directory_name}': {e}")
        except IOError as e:
            print(f"Error writing to file: {e}")
        return ret

    def get_as_list(self, section_name, key_name):
        ret = None
        if self.has_option(section_name, key_name):
            # we get values as a string reporesenting a list of strings
            ret = self.get(section_name, key_name)
            # convert it to real python list object
            ret = ast.literal_eval(ret)
            # ret = ret.split(", ")
        return ret


    def get_configured_gpu_list(self):
        return self.gpu_target_list


    def get_locally_build_rocm_sdk_home(self):
        ret = None

        if self.rock_sdk_home_therock_build_dir and self.gpu_target_list:
            ret = self.rock_sdk_home_therock_build_dir
        return ret


    def get_python_wheel_rocm_sdk_server_url(self):
        ret = None

        # rocm sdk from the pip wheel option
        if self.rock_sdk_whl_url and self.gpu_target_list:
             ret = self.rock_sdk_whl_url
        return ret


    def is_python_wheel_rocm_sdk_install_needed(self):
        ret = False
        sdk_update_needed = self._is_rocm_sdk_python_wheel_update_needed(sys.prefix,
                                          self.last_mod_time)
        rocm_home = get_python_wheel_rocm_sdk_home("root")
        if sdk_update_needed or (not rocm_home):
            ret = True
        return ret


    def get_configured_and_existing_rocm_sdk_home(self):
        ret = None
		
        # use rocm sdk from the existing directory specified in the rockbuilder.cfg file
        if self.rock_sdk_home_existing_install_dir and self.gpu_target_list:
            ret = self.rock_sdk_home_existing_install_dir
        return ret


    # get target gpus in str which each one separated with semicolon
    def get_configured_gpu_list_str(self):
        ret = None
        if self.gpu_target_list:
            for ii, gpu_target in enumerate(self.gpu_target_list):
                if ii == 0:
                    ret = self.gpu_target_list[0]
                else:
                    ret = ret + ";" + self.gpu_target_list[ii]
        return ret
