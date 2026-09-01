#!/usr/bin/env python

# curses works both on linux and windows
#   linux: pip3 install curses
#   windows: pip3 install windows-curses
import ast
import curses
import os
import subprocess
import sys
from lib_python.config_ui.config_store import ConfigStore
from lib_python.config_ui.pages.gpu_page import GpuSelectionPage
from lib_python.config_ui.pages.sdk_page import SdkSelectionPage
from lib_python.config_ui.wizard import Wizard
from lib_python.utils import verify_env__python
from lib_python.utils import install_rocm_sdk_from_python_wheels
import lib_python.rcb_constants as rcb_const
from pathlib import Path

# Basic heuristic vefication to check whether rocm_sdk directory looks valid
#
# return True if path is valid
def is_valid_rocm_home_path(rocm_home_path):
    rocm_home_bin = rocm_home_path / "bin"
    rocm_home_lib = rocm_home_path / "lib"
    ret = rocm_home_bin.is_dir() and rocm_home_lib.is_dir()
    return ret


def get_rocm_home_path_if_available():
    if "ROCM_HOME" not in os.environ:
        return None
    rocm_home = Path(os.environ["ROCM_HOME"]).resolve()
    if is_valid_rocm_home_path(rocm_home):
        return rocm_home
    return None


def get_rocm_sdk_install_search_parents(home_dir=None):
    if home_dir is None:
        home_dir = Path.home()
    parents = [
        rcb_const.THEROCK_SDK__ROCM_HOME_INSTALL_PARENT,
        Path(home_dir) / "rcb",
    ]
    return list(dict.fromkeys(parent.resolve() for parent in parents))


def discover_rocm_sdk_installs(home_dir=None):
    installs = []
    for parent in get_rocm_sdk_install_search_parents(home_dir):
        if not parent.is_dir():
            continue
        for install_dir in sorted(parent.iterdir()):
            if is_valid_rocm_home_path(install_dir):
                installs.append(install_dir.resolve())
    return installs


def parse_config_values(raw_value):
    """Parse a scalar or Python-style sequence from rockbuilder.cfg."""
    try:
        parsed_value = ast.literal_eval(raw_value)
    except (SyntaxError, ValueError):
        parsed_value = raw_value

    if isinstance(parsed_value, (list, tuple, set)):
        return [str(value) for value in parsed_value]
    return [str(parsed_value)]


def load_existing_config(config_file=None):
    """Load rockbuilder.cfg or return an empty configuration.

    Example:
        load_existing_config(Path("rockbuilder.cfg")) returns a
        ConfigParser containing that file's sections.
    """
    config_store = ConfigStore(config_file)
    ret = config_store.load()
    return ret


def invalidate_therock_phase_stamps(build_root_dir=None):
    """Invalidate TheRock checkout and all later build phases."""
    if build_root_dir is None:
        build_root_dir = rcb_const.RCB__APP_BUILD_ROOT_DIR
    phase_names = [
        rcb_const.RCB__APP_CFG__KEY__CMD_CHECKOUT,
        rcb_const.RCB__APP_CFG__KEY__CMD_HIPIFY,
        rcb_const.RCB__APP_CFG__KEY__CMD_PRE_CONFIG,
        rcb_const.RCB__APP_CFG__KEY__CMD_CONFIG,
        rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_CONFIG,
        rcb_const.RCB__APP_CFG__KEY__CMD_POST_CONFIG,
        rcb_const.RCB__APP_CFG__KEY__CMD_BUILD,
        rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_BUILD,
        rcb_const.RCB__APP_CFG__KEY__CMD_INSTALL,
        rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_INSTALL,
        rcb_const.RCB__APP_CFG__KEY__CMD_POST_INSTALL,
    ]
    for config_name in rcb_const.RCB__THEROCK_CONFIGS:
        therock_build_dir = Path(build_root_dir) / config_name
        for phase_name in phase_names:
            stamp_path = therock_build_dir / f"{phase_name}.done"
            stamp_path.unlink(missing_ok=True)


def handle_config_change():
    """Report a saved change and invalidate dependent TheRock phases.

    Example:
        handle_config_change() removes checkout-and-later stamps and
        returns None.
    """
    print("RockBuilder configuration changed.")
    print("Restarting TheRock from the checkout phase.")
    invalidate_therock_phase_stamps()


class SelectionItem:
    def __init__(self,
                 name,
                 key,
                 value,
                 selected,
                 extra_key=None,
                 extra_val=None):
        self.name = name
        self.key = key
        self.value = value
        self.selected = selected
        self.extra_key=extra_key
        self.extra_val=extra_val

    def is_selected(self):
        return self.selected

    def set_selected(self, selection):
        self.selected = selection

    def toggle_selected(self):
        self.selected = not self.selected

    def get_name(self):
        return self.name

    def get_key(self):
        return self.key

    def get_value(self):
        return self.value


class ConfigSelection:
    def __init__(self, header, selection_dict):
        self.header = header
        self.selection_dict = selection_dict


class BaseSelectionList:
    def __init__(self, stdscr, config_header, title, multi_selection):
        # todo, find out how to generate the list of supported GPUs
        self.title = title
        self.config_header = config_header
        self.stdscr = stdscr
        # whether to allow selecting multiple items
        self.multi_selection = multi_selection
        self.item_list = []
        self.item_selection_listeners = []

    def add_item_selection_listener(self, new_listener):
        self.item_selection_listeners.append(new_listener)

    def set_item_list(self, new_item_list):
        self.item_list.clear()
        self.item_list.extend(new_item_list)

    def get_item_cnt(self):
        return len(self.item_list)

    def get_config_header(self):
        return self.config_header

    def get_item(self, indx):
        return self.item_list[indx]

    def get_selected_item(self):
        for item in self.item_list:
            if item.is_selected():
                return item
        return None

    def restore_selection(self, config):
        """Restore selections which are still available in this list."""
        section = self.get_config_header()
        if not config.has_section(section):
            return []

        matched_items = []
        for item in self.item_list:
            if not config.has_option(section, item.get_key()):
                continue
            configured_values = parse_config_values(
                config.get(section, item.get_key())
            )
            if str(item.get_value()) in configured_values:
                matched_items.append(item)
                if not self.multi_selection:
                    break

        if not matched_items:
            return []

        for item in self.item_list:
            item.set_selected(item in matched_items)

        for item in matched_items:
            if item.extra_key and config.has_option(section, item.extra_key):
                item.extra_val = config.get(section, item.extra_key)
        return matched_items

    def fire_item_selection_event(self, item, selected):
        for listener in self.item_selection_listeners:
            listener.handle_item_selected(self, item, selected)

    def set_multi_selection(self, enable):
        """Set selection mode while preserving feasible selections.

        Example:
            set_multi_selection(False) keeps the first selected GPU,
            clears later selections, and returns None.
        """
        if self.multi_selection != enable:
            self.multi_selection = enable
            if not enable:
                selected_item_found = False
                for item in self.item_list:
                    if item.is_selected() and selected_item_found:
                        item.set_selected(False)
                    elif item.is_selected():
                        selected_item_found = True

    # handle the item selection logic
    def toggle_item_selection(self, indx):
        if self.multi_selection:
            # allow selecting 0-n items simultaneously
            item = self.item_list[indx]
            item.toggle_selected()
            new_state = item.is_selected()
            self.fire_item_selection_event(item, new_state)
        else:
            # allow selecting only one item at a time
            for ii, item in enumerate(self.item_list):
                if ii == indx:
                    item.set_selected(True)
                    # notify in this case only from the item selected
                    self.fire_item_selection_event(item, True)
                else:
                    item.set_selected(False)

    def show(self, indx_cursor, indx_first_item, indx_first_row):
        index_base = indx_first_row
        try:
            self.stdscr.addstr(index_base, 0, self.title)
            # display the list of item_list for the user to choose from
            index_base = index_base + 2
            for ii, gpu_item in enumerate(self.item_list):
                if indx_first_item + ii == indx_cursor:
                    if gpu_item.is_selected():
                        self.stdscr.addstr(
                            index_base + ii, 0, f"> [X] {gpu_item.name}"
                        )  # cursor + selected
                    else:
                        self.stdscr.addstr(
                            index_base + ii, 0, f"> [ ] {gpu_item.name}"
                        )  # cursor + not selected
                else:
                    if gpu_item.is_selected():
                        self.stdscr.addstr(
                            index_base + ii, 0, f"  [X] {gpu_item.name}"
                        )  # selected
                    else:
                        self.stdscr.addstr(
                            index_base + ii, 0, f"  [ ] {gpu_item.name}"
                        )  # not selected
        except curses.error:
            print("Terminal is too small. Please increase the size that all text will fit.")

    # get config selections
    #
    # - hrd contains the title for the selections. (section name in ini-file)
    # - selection_dict contains key-value pairs for the user selections
    # - each value stored to dictionary is itself actually an array of values
    #
    def get_config_selections(self):
        selection_dict = {}
        for ii, item in enumerate(self.item_list):
            if item.is_selected():
                val_arr = selection_dict.get(item.get_key())
                if not val_arr:
                    val_arr = []
                val_arr.append(item.get_value())
                selection_dict[item.get_key()] = val_arr
                if item.extra_key and item.extra_val:
                    selection_dict[item.extra_key] = item.extra_val
        section = self.get_config_header()
        return ConfigSelection(section, selection_dict)


class GpuSelectionList(BaseSelectionList):
    def __init__(self, stdscr):
        super().__init__(
            stdscr,
            rcb_const.RCB__CFG__SECTION__BUILD_TARGETS,
            f"Select AMD GPUs Used (Each of the selected GPU will increase build time)", True
        )

    # Override the default selection logic because selection logic depends from the SDK selected
    #
    # - If we have selected PIP wheel install, we can not at the moment support multiple GPU-families at a same time
    # - If we select the local SDK, we can have multiple GPU's selected.
    # def toggle_item_selection(self, indx):
    #    for ii, item in enumerate(self.item_list):
    #        if ii == indx:
    #            item.set_selected(True)
    #        else:
    #            item.set_selected(False)


# Show list of possible ROCM_SDK's from which user can use for the build
#
# Existing SDKs are shown alongside available local build configurations.
class SDKSelectionList(BaseSelectionList):
    def __init__(self, stdscr):
        super().__init__(
            stdscr,
            rcb_const.RCB__CFG__SECTION__ROCM_SDK,
            f"Select ROCM SDK Used by the RockBuilder", False
        )

        def_sel = True
        whl_server_base_url = rcb_const.THEROCK_SDK__PYTHON_WHEEL_SERVER_URL
        rocm_home = get_rocm_home_path_if_available()
        if rocm_home:
            self.item_list.append(
                SelectionItem(
                    "ROCm SDK Specified by ROCM_HOME: "
                    + rocm_home.as_posix(),
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME,
                    rocm_home.as_posix(),
                    def_sel,
                )
            )
            def_sel = False

        existing_paths = set()
        if rocm_home:
            existing_paths.add(rocm_home.resolve())
        for install_dir in discover_rocm_sdk_installs():
            if install_dir in existing_paths:
                continue
            self.item_list.append(
                SelectionItem(
                    "Existing ROCm SDK: "
                    + install_dir.as_posix(),
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME,
                    install_dir.as_posix(),
                    def_sel,
                )
            )
            def_sel = False
            existing_paths.add(install_dir)

        build_config_key = (
            rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG
        )
        release_install_dir = (
            rcb_const.get_therock_rocm_sdk_install_dir(
                install_dir_basename="rocm_10_0_0"
            )
        )
        self.item_list.append(
            SelectionItem(
                "Build TheRock 10.0: " + release_install_dir.as_posix(),
                build_config_key,
                "therock_10_0",
                def_sel,
            )
        )
        def_sel = False
        self.item_list.append(
            SelectionItem(
                "Build TheRock development main branch",
                build_config_key,
                "therock_dev",
                def_sel,
            )
        )
        # add an option/selection to use the rocm sdk that will be installed from the python wheel
        self.item_list.append(
            SelectionItem(
                "ROCm SDK from Python Wheels Install: " + whl_server_base_url,
                rcb_const.RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER,
                whl_server_base_url,
                def_sel,
                rcb_const.RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_VERSION,
                rcb_const.RCB__CFG__DEF__ROCM_SDK_PYTHON_WHEEL_VERSION
            )
        )

    def restore_selection(self, config):
        restored_items = super().restore_selection(config)
        if restored_items:
            return restored_items

        section = self.get_config_header()
        build_key = rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_BUILD
        home_key = rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME
        if not config.has_option(section, build_key):
            return []

        configured_paths = parse_config_values(config.get(section, build_key))
        for item in self.item_list:
            is_existing_build = item.get_key() == home_key
            if is_existing_build and str(item.get_value()) in configured_paths:
                for candidate in self.item_list:
                    candidate.set_selected(candidate is item)
                return [item]
        return []

    # Override the default selection logic because we should only allow
    # one SDK to be selected at a time.
    # When one SDK location is selected, previous selections are disabled.
    # def toggle_item_selection(self, indx):
    #    for ii, item in enumerate(self.item_list):
    #        if ii == indx:
    #            item.set_selected(True)
    #        else:
    #            item.set_selected(False)


class SelectionListManager:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.selection_list_arr = []

    def add_selection_list(self, new_list):
        self.selection_list_arr.append(new_list)

    def get_total_selection_list_item_cnt(self):
        ret = 0
        for ii, selection_list in enumerate(self.selection_list_arr):
            ret = ret + selection_list.get_item_cnt()
        return ret

    def get_last_row_indx(self):
        ret = 0
        for ii, selection_list in enumerate(self.selection_list_arr):
            ret = ret + selection_list.get_item_cnt() + 3
        return ret

    def show(self, indx_cursor):
        cnt_items_viewed = 0
        indx_first_row = 0
        for ii, selection_list in enumerate(self.selection_list_arr):
            selection_list.show(indx_cursor, cnt_items_viewed, indx_first_row)
            cnt_items_viewed = cnt_items_viewed + selection_list.get_item_cnt()
            indx_first_row = indx_first_row + selection_list.get_item_cnt() + 3

    def on_selection_key_pressed(self, indx_cursor):
        indx_first_item = 0
        indx_last_item = 0
        for ii, selection_list in enumerate(self.selection_list_arr):
            indx_last_item = indx_last_item + selection_list.get_item_cnt()
            if (indx_cursor >= indx_first_item) and (indx_cursor < indx_last_item):
                selection_list.toggle_item_selection(indx_cursor - indx_first_item)
            indx_first_item = indx_last_item

    def save_selection(self):
        """Save all managed lists and return the resulting configuration.

        Example:
            With SDK and GPU lists registered, save_selection() writes
            both sections and returns a ConfigParser.
        """
        fname = rcb_const.get_rock_builder_config_file()
        config_store = ConfigStore(
            fname,
            handle_config_change,
        )
        ret = config_store.save(self.selection_list_arr)
        return ret


class UiManager:
    def __init__(self, stdscr, existing_config=None):
        """Initialize selection models and register wizard pages in order.

        Example:
            UiManager(screen, config) creates SDK and GPU pages and
            returns no value.
        """
        key_name_gpus = rcb_const.RCB__CFG__KEY__GPUS
        self.stdscr = stdscr
        # init curses based display to show text based ui
        self.stdscr.clear()

        self.gpu_pip_wheel_list = []
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx101X-dgpu", key_name_gpus, "gfx101X-dgpu", False)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx103X-dgpu", key_name_gpus, "gfx103X-dgpu", False)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx110X-all", key_name_gpus, "gfx110X-all", False)
        )
        self.gpu_pip_wheel_list.append(SelectionItem("gfx1150", key_name_gpus, "gfx1150", False))
        self.gpu_pip_wheel_list.append(SelectionItem("gfx1151", key_name_gpus, "gfx1151", False))
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx120X-all", key_name_gpus, "gfx120X-all", True)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx906", key_name_gpus, "gfx906", False)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx908", key_name_gpus, "gfx908", False)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx90a", key_name_gpus, "gfx90a", False)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx94X-dcgpu", key_name_gpus, "gfx94X-dcgpu", False)
        )
        self.gpu_pip_wheel_list.append(
            SelectionItem("gfx950-dcgpu", key_name_gpus, "gfx950-dcgpu", False)
        )

        self.gpu_build_target_list = []
        self.gpu_build_target_list.append(SelectionItem("Radeon VII/MI50/Vega20 (gfx906)", key_name_gpus, "gfx906", False))
        self.gpu_build_target_list.append(SelectionItem("MI100 (gfx908)", key_name_gpus, "gfx908", False))
        self.gpu_build_target_list.append(SelectionItem("MI210 (gfx90a)", key_name_gpus, "gfx90a", False))
        self.gpu_build_target_list.append(SelectionItem("MI350 (gfx942)", key_name_gpus, "gfx942", False))
        self.gpu_build_target_list.append(SelectionItem("MI355X gfx950", key_name_gpus, "gfx950", False))
        self.gpu_build_target_list.append(SelectionItem("RX 5600/5700 (gfx1010)", key_name_gpus, "gfx1010", False))
        self.gpu_build_target_list.append(SelectionItem("RX 5500 (gfx1012)", key_name_gpus, "gfx1012", False))
        self.gpu_build_target_list.append(SelectionItem("RX 6800/6900 (gfx1030)", key_name_gpus, "gfx1030", False))
        self.gpu_build_target_list.append(SelectionItem("RX 6700 (gfx1031)", key_name_gpus, "gfx1031", False))
        self.gpu_build_target_list.append(SelectionItem("RX 6600 (gfx1032)", key_name_gpus, "gfx1032", False))
        self.gpu_build_target_list.append(SelectionItem("680M iGPU (gfx1035)", key_name_gpus, "gfx1035", False))
        self.gpu_build_target_list.append(SelectionItem("RX 7800/7900 (gfx1100)", key_name_gpus, "gfx1100", False))
        self.gpu_build_target_list.append(SelectionItem("RX 7700 (gfx1101)", key_name_gpus, "gfx1101", False))
        self.gpu_build_target_list.append(SelectionItem("RX 7500/7600 (gfx1102)", key_name_gpus, "gfx1102", False))
        self.gpu_build_target_list.append(SelectionItem("780M iGPU (gfx1103)", key_name_gpus, "gfx1103", False))
        self.gpu_build_target_list.append(SelectionItem("890M iGPU/Strix Point (gfx1150)", key_name_gpus, "gfx1150", False))
        self.gpu_build_target_list.append(SelectionItem("8040S/8050S/8060S iGPU/Strix Halo (gfx1151)", key_name_gpus, "gfx1151", False))
        self.gpu_build_target_list.append(SelectionItem("RX 9060/RX 9060 XT (gfx1200)", key_name_gpus, "gfx1200", False))
        self.gpu_build_target_list.append(SelectionItem("RX 9070/RX 9070 XT (gfx1201)", key_name_gpus, "gfx1201", False))

        self.sdk_list = SDKSelectionList(stdscr)
        self.gpu_list = GpuSelectionList(stdscr)
        self.gpu_list.set_item_list(self.gpu_build_target_list)

        if existing_config is None:
            existing_config = load_existing_config()
        self.restore_selections(existing_config)
        self.sdk_list.add_item_selection_listener(self)

        self.selection_list_manager = SelectionListManager(self.stdscr)
        self.selection_list_manager.add_selection_list(self.sdk_list)
        self.selection_list_manager.add_selection_list(self.gpu_list)
        self.pages = [
            SdkSelectionPage(
                self.sdk_list,
                self.prepare_gpu_list,
            ),
            GpuSelectionPage(self.gpu_list),
        ]

    def configure_gpu_list(self, sdk_item, clear_display):
        """Choose the compatible GPU list for the selected SDK.

        Example:
            configure_gpu_list(wheel_sdk, False) selects wheel GPU
            families and returns None.
        """
        if sdk_item is None:
            ret = None
        else:
            wheel_server_key = (
                rcb_const.RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER
            )
            if sdk_item.get_key() == wheel_server_key:
                self.gpu_list.set_item_list(
                    self.gpu_pip_wheel_list
                )
                self.gpu_list.set_multi_selection(False)
            else:
                self.gpu_list.set_item_list(
                    self.gpu_build_target_list
                )
                self.gpu_list.set_multi_selection(True)
            if clear_display:
                self.stdscr.clear()
            ret = None
        return ret

    def prepare_gpu_list(self, sdk_item):
        """Prepare GPU choices before advancing from the SDK page.

        Example:
            prepare_gpu_list(local_sdk) enables build GPU targets and
            returns None.
        """
        self.configure_gpu_list(sdk_item, False)
        ret = None
        return ret

    def restore_selections(self, config):
        """Restore feasible SDK and GPU values from existing config.

        Example:
            restore_selections(config_with_gfx90a) selects gfx90a and
            returns None.
        """
        restored_sdk_items = self.sdk_list.restore_selection(config)
        if restored_sdk_items:
            selected_sdk_item = restored_sdk_items[0]
        else:
            selected_sdk_item = self.sdk_list.get_selected_item()

        self.configure_gpu_list(selected_sdk_item, False)
        self.gpu_list.restore_selection(config)

    def show(self):
        """Run registered pages and return saved config or None.

        Example:
            show() returns a ConfigParser after Save or None after
            Cancel.
        """
        wizard = Wizard(
            self.stdscr,
            self.pages,
            self.selection_list_manager.save_selection,
        )
        ret = wizard.run()
        return ret

    def handle_item_selected(self, sender, item, selected):
        """Update GPU compatibility when the SDK selection changes.

        Example:
            handle_item_selected(sdk_list, wheel_sdk, True) selects
            wheel GPU families and returns None.
        """
        self.configure_gpu_list(item, False)


def show_config_ui():
    ret = None

    try:
        # Initialize curses
        stdscr = curses.initscr()
        curses.noecho()  # Turn off automatic echoing of typed characters
        curses.cbreak()  # React to keys instantly, without requiring Enter
        stdscr.keypad(True) # Enable special key processing

        ui_manager = UiManager(stdscr)
        ret = ui_manager.show()
    finally:
        # Clean up curses
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
    return ret


def process_therock_rocm_sdk_build(config_name):
    try:
        if config_name not in rcb_const.RCB__THEROCK_CONFIGS:
            raise ValueError(
                f"Unknown TheRock build configuration: {config_name}"
            )
        fname_cfg = str(
            Path(rcb_const.RCB__APP_CFG_DEFAULT_DIR_BASENAME)
            / f"{config_name}.cfg"
        )
        therock_cmd_build = [sys.executable, "rockbuilder.py", fname_cfg]
        result = subprocess.run(therock_cmd_build)
        return result.returncode == 0
    except Exception as ex:
        print(f"ROCM SDK build error with {config_name}.cfg:")
        print("    " + str(ex))
        return False

def process_therock_rocm_sdk_python_wheel_install(saved_cfg):
    return install_rocm_sdk_from_python_wheels(saved_cfg)

def process_config_selections(saved_cfg):
    if saved_cfg:
        if saved_cfg.has_section(rcb_const.RCB__CFG__SECTION__ROCM_SDK):
            section = rcb_const.RCB__CFG__SECTION__ROCM_SDK
            build_config_key = (
                rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG
            )
            if saved_cfg.has_option(section, build_config_key):
                config_names = parse_config_values(
                    saved_cfg.get(section, build_config_key)
                )
                if len(config_names) != 1:
                    raise ValueError(
                        "Exactly one TheRock build configuration is required"
                    )
                res = process_therock_rocm_sdk_build(config_names[0])
                if not res:
                    print("ROCM SDK build failed")
                    sys.exit(1)
            if saved_cfg.has_option(rcb_const.RCB__CFG__SECTION__ROCM_SDK,
                                    rcb_const.RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER):
                res = process_therock_rocm_sdk_python_wheel_install(saved_cfg)
                if not res:
                    print("ROCM SDK install from python wheels failed")
                    sys.exit()

def show_and_process_selections():
    saved_cfg = show_config_ui()
    process_config_selections(saved_cfg)
    return saved_cfg

    
def main():
	verify_env__python()
	show_and_process_selections()


if __name__ == "__main__":
    main()
