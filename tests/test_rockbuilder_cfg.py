import configparser
import curses
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib_python.rcb_constants as rcb_const
from lib_python.rcb_cfg_reader import RCBConfigReader
from lib_python.config_ui.config_store import ConfigStore
from lib_python.config_ui.page import NavigationAction
import rockbuilder_cfg


class FakeScreen:
    def __init__(self, keys=None, height=24, width=120):
        """Initialize a fake screen with queued input and dimensions.

        Example:
            FakeScreen([ord("c")], 24, 80) returns a screen that sends
            the Cancel shortcut on its first input read.
        """
        self.keys = list(keys or [])
        self.height = height
        self.width = width
        self.lines = {}
        self.frames = []

    def clear(self):
        """Clear the current frame and return no value.

        Example:
            clear() removes all text previously written to the frame.
        """
        self.lines = {}

    def getmaxyx(self):
        """Return configured terminal height and width.

        Example:
            A 24 by 80 fake screen returns (24, 80).
        """
        ret = (self.height, self.width)
        return ret

    def addstr(self, row, column, text):
        """Record text written at a screen coordinate.

        Example:
            addstr(0, 0, "Title") records "Title" at row zero and
            returns no value.
        """
        self.lines[(row, column)] = text

    def refresh(self):
        """Record the completed frame and return no value.

        Example:
            refresh() appends the current text mapping to frames.
        """
        self.frames.append(dict(self.lines))

    def getch(self):
        """Return the next queued key code.

        Example:
            With [ord("c")] queued, getch() returns ord("c").
        """
        ret = self.keys.pop(0)
        return ret


def make_config(contents):
    config = configparser.ConfigParser()
    config.read_string(contents)
    return config


def selected_values(selection_list):
    return [
        item.get_value()
        for item in selection_list.item_list
        if item.is_selected()
    ]


class TheRockInstallPathTest(unittest.TestCase):
    def test_uses_existing_writable_opt_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            preferred_parent = temp_path / "opt/rcb"
            preferred_parent.mkdir(parents=True)
            home_dir = temp_path / "home"

            with mock.patch.object(os, "access", return_value=True):
                install_dir = (
                    rcb_const.get_therock_rocm_sdk_install_dir(
                        preferred_parent,
                        home_dir,
                    )
                )

        self.assertEqual(install_dir, preferred_parent / "rocm_10_0_0")

    def test_uses_home_when_opt_parent_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            install_dir = rcb_const.get_therock_rocm_sdk_install_dir(
                temp_path / "missing/opt/rcb",
                temp_path / "home",
            )

        self.assertEqual(
            install_dir,
            temp_path / "home/rcb/rocm_10_0_0",
        )

    def test_uses_home_when_opt_destination_is_not_writable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            preferred_parent = temp_path / "opt/rcb"
            preferred_dir = preferred_parent / "rocm_10_0_0"
            preferred_dir.mkdir(parents=True)
            home_dir = temp_path / "home"

            with mock.patch.object(os, "access", return_value=False):
                install_dir = (
                    rcb_const.get_therock_rocm_sdk_install_dir(
                        preferred_parent,
                        home_dir,
                    )
                )

        self.assertEqual(install_dir, home_dir / "rcb/rocm_10_0_0")

    def test_discovers_all_valid_sdk_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            install_parent = temp_path / "opt/rcb"
            expected_installs = [
                install_parent / "rocm_10_0_0",
                install_parent / "rocm_dev_10_1_0_a1b2c3d",
                temp_path / "home/rcb/rocm_dev_10_0_0_d4e5f6a",
            ]
            for install_dir in expected_installs:
                (install_dir / "bin").mkdir(parents=True)
                (install_dir / "lib").mkdir()
            other_sdk = install_parent / "custom_sdk_name"
            (other_sdk / "bin").mkdir(parents=True)
            (other_sdk / "lib").mkdir()
            expected_installs.append(other_sdk)
            invalid_install = install_parent / "not_an_sdk"
            invalid_install.mkdir(parents=True)

            with mock.patch.object(
                rcb_const,
                "THEROCK_SDK__ROCM_HOME_INSTALL_PARENT",
                install_parent,
            ):
                installs = (
                    rockbuilder_cfg.discover_rocm_sdk_installs(
                        temp_path / "home"
                    )
                )

            self.assertCountEqual(installs, expected_installs)


class ConfigSelectionTest(unittest.TestCase):
    def test_therock_variants_share_name_and_use_separate_patches(self):
        expected_values = {
            "therock_10_0": ("release/therock-10.0", "release"),
            "therock_dev": ("main", "main"),
        }
        for config_name, expected in expected_values.items():
            config = configparser.ConfigParser()
            config.read(
                rcb_const.RCB__ROOT_DIR
                / "apps"
                / f"{config_name}.cfg"
            )
            section = rcb_const.RCB__APP_CFG__SECTION_APP_INFO
            self.assertEqual(config.get(section, "APP_NAME"), "therock")
            self.assertEqual(
                (
                    config.get(section, "APP_VERSION"),
                    config.get(section, "PATCH_DIR"),
                ),
                expected,
            )

    def test_parse_config_values_accepts_sequences_and_scalars(self):
        self.assertEqual(
            rockbuilder_cfg.parse_config_values("['gfx90a', 'gfx1100']"),
            ["gfx90a", "gfx1100"],
        )
        self.assertEqual(
            rockbuilder_cfg.parse_config_values("gfx90a"),
            ["gfx90a"],
        )

    def test_load_existing_config_reads_available_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "rockbuilder.cfg"
            config_path.write_text(
                "[build_targets]\ngpus = ['gfx90a']\n",
                encoding="utf-8",
            )

            config = rockbuilder_cfg.load_existing_config(config_path)

        self.assertEqual(
            config.get("build_targets", "gpus"),
            "['gfx90a']",
        )

    def test_config_reader_loads_therock_build_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "rockbuilder.cfg"
            config_path.write_text(
                "[rocm_sdk]\n"
                "rocm_sdk_build_config = ['therock_dev']\n"
                "\n"
                "[build_targets]\n"
                "gpus = ['gfx90a']\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                rcb_const,
                "get_rock_builder_config_file",
                return_value=config_path,
            ):
                config_reader = RCBConfigReader(
                    temp_path,
                    temp_path / "build",
                )

            self.assertEqual(
                config_reader.get_rocm_sdk_build_config(),
                "therock_dev",
            )

    def test_processes_selected_therock_build_variant(self):
        config = make_config(
            "[rocm_sdk]\n"
            "rocm_sdk_build_config = ['therock_dev']\n"
        )
        with mock.patch.object(
            rockbuilder_cfg,
            "process_therock_rocm_sdk_build",
            return_value=True,
        ) as process_build:
            rockbuilder_cfg.process_config_selections(config)

        process_build.assert_called_once_with("therock_dev")

    def test_restore_selection_ignores_unavailable_values(self):
        selection_list = rockbuilder_cfg.BaseSelectionList(
            None,
            "build_targets",
            "GPUs",
            True,
        )
        selection_list.set_item_list(
            [
                rockbuilder_cfg.SelectionItem(
                    "Default",
                    "gpus",
                    "gfx1201",
                    True,
                ),
                rockbuilder_cfg.SelectionItem(
                    "MI210",
                    "gpus",
                    "gfx90a",
                    False,
                ),
            ]
        )
        config = make_config(
            "[build_targets]\n"
            "gpus = ['gfx90a', 'unsupported-gpu']\n"
        )

        selection_list.restore_selection(config)

        self.assertEqual(selected_values(selection_list), ["gfx90a"])

    def test_unavailable_selection_keeps_default(self):
        selection_list = rockbuilder_cfg.BaseSelectionList(
            None,
            "build_targets",
            "GPUs",
            True,
        )
        selection_list.set_item_list(
            [
                rockbuilder_cfg.SelectionItem(
                    "Default",
                    "gpus",
                    "gfx1201",
                    True,
                )
            ]
        )
        config = make_config(
            "[build_targets]\ngpus = ['unsupported-gpu']\n"
        )

        selection_list.restore_selection(config)

        self.assertEqual(selected_values(selection_list), ["gfx1201"])


class ConfigStampInvalidationTest(unittest.TestCase):
    def save_gpu_selection(self, config_path, build_root, gpu):
        selection_list = mock.Mock()
        selection_list.get_config_selections.return_value = (
            rockbuilder_cfg.ConfigSelection(
                rcb_const.RCB__CFG__SECTION__BUILD_TARGETS,
                {rcb_const.RCB__CFG__KEY__GPUS: [gpu]},
            )
        )
        manager = rockbuilder_cfg.SelectionListManager(None)
        manager.add_selection_list(selection_list)
        with (
            mock.patch.object(
                rcb_const,
                "get_rock_builder_config_file",
                return_value=config_path,
            ),
            mock.patch.object(
                rcb_const,
                "RCB__APP_BUILD_ROOT_DIR",
                build_root,
            ),
        ):
            manager.save_selection()

    def test_changed_config_invalidates_therock_phases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "rockbuilder.cfg"
            config_path.write_text(
                "[build_targets]\ngpus = ['gfx90a']\n",
                encoding="utf-8",
            )
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
            phase_stamps = []
            init_stamps = []
            for config_name in rcb_const.RCB__THEROCK_CONFIGS:
                build_dir = temp_path / "build" / config_name
                build_dir.mkdir(parents=True)
                phase_stamps.extend(
                    build_dir / f"{phase_name}.done"
                    for phase_name in phase_names
                )
                init_stamps.append(
                    build_dir
                    / f"{rcb_const.RCB__APP_CFG__KEY__CMD_INIT}.done"
                )
            for stamp_path in [*init_stamps, *phase_stamps]:
                stamp_path.touch()

            self.save_gpu_selection(
                config_path,
                temp_path / "build",
                "gfx1100",
            )

            self.assertTrue(all(path.exists() for path in init_stamps))
            self.assertFalse(any(path.exists() for path in phase_stamps))

    def test_unchanged_config_preserves_therock_phases(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "rockbuilder.cfg"
            config_path.write_text(
                "[build_targets]\ngpus = ['gfx90a']\n",
                encoding="utf-8",
            )
            checkout_stamp = (
                temp_path
                / "build/therock_10_0"
                / f"{rcb_const.RCB__APP_CFG__KEY__CMD_CHECKOUT}.done"
            )
            checkout_stamp.parent.mkdir(parents=True)
            checkout_stamp.touch()

            self.save_gpu_selection(
                config_path,
                temp_path / "build",
                "gfx90a",
            )

            self.assertTrue(checkout_stamp.exists())


class UiManagerRestoreTest(unittest.TestCase):
    def setUp(self):
        self.saved_rocm_home = os.environ.pop("ROCM_HOME", None)

    def tearDown(self):
        if self.saved_rocm_home is not None:
            os.environ["ROCM_HOME"] = self.saved_rocm_home

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_offers_release_and_development_builds(
        self,
        unused_installs,
    ):
        ui_manager = rockbuilder_cfg.UiManager(FakeScreen(), make_config(""))
        build_items = [
            (item.get_key(), item.get_value())
            for item in ui_manager.sdk_list.item_list
            if item.get_key()
            == rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG
        ]

        self.assertEqual(
            build_items,
            [
                (
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG,
                    "therock_10_0",
                ),
                (
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG,
                    "therock_dev",
                ),
            ],
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_offers_sdk_from_rocm_home(
        self,
        unused_installs,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            sdk_path = Path(temp_dir) / "rocm"
            (sdk_path / "bin").mkdir(parents=True)
            (sdk_path / "lib").mkdir()
            with mock.patch.dict(
                os.environ,
                {"ROCM_HOME": sdk_path.as_posix()},
            ):
                ui_manager = rockbuilder_cfg.UiManager(
                    FakeScreen(),
                    make_config(""),
                )

        selected_values = {
            item.get_value()
            for item in ui_manager.sdk_list.item_list
        }
        self.assertIn(sdk_path.as_posix(), selected_values)

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_restores_build_sdk_and_multiple_gpus(
        self,
        unused_local_sdk,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            sdk_path = Path(temp_dir) / "not-built/rocm"
            config = make_config(
                "[rocm_sdk]\n"
                "rocm_sdk_build_config = ['therock_dev']\n"
                "\n"
                "[build_targets]\n"
                "gpus = ['gfx90a', 'gfx1100']\n"
            )

            with mock.patch(
                "rockbuilder_cfg.rcb_const."
                "get_therock_rocm_sdk_install_dir",
                return_value=sdk_path,
            ):
                ui_manager = rockbuilder_cfg.UiManager(
                    FakeScreen(),
                    config,
                )

        self.assertEqual(
            ui_manager.sdk_list.get_selected_item().get_key(),
            rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG,
        )
        self.assertEqual(
            ui_manager.sdk_list.get_selected_item().get_value(),
            "therock_dev",
        )
        self.assertEqual(
            selected_values(ui_manager.gpu_list),
            ["gfx90a", "gfx1100"],
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_restores_configured_sdk_without_rocm_home(
        self,
        unused_local_sdk,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            sdk_path = Path(temp_dir) / "rocm"
            (sdk_path / "bin").mkdir(parents=True)
            (sdk_path / "lib").mkdir()
            config = make_config(
                "[rocm_sdk]\n"
                f"rocm_sdk_home = ['{sdk_path.as_posix()}']\n"
            )
            unused_local_sdk.return_value = [sdk_path.resolve()]

            ui_manager = rockbuilder_cfg.UiManager(
                FakeScreen(),
                config,
            )

            selected_sdk = ui_manager.sdk_list.get_selected_item()
            self.assertEqual(
                selected_sdk.get_key(),
                rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME,
            )
            self.assertEqual(
                selected_sdk.get_value(),
                sdk_path.resolve().as_posix(),
            )
            self.assertIn(
                "Existing ROCm SDK",
                selected_sdk.get_name(),
            )
            self.assertIs(ui_manager.sdk_list.get_item(0), selected_sdk)

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_ignores_configured_sdk_when_directory_is_invalid(
        self,
        unused_local_sdk,
    ):
        config = make_config(
            "[rocm_sdk]\n"
            "rocm_sdk_home = ['/missing/rocm-sdk']\n"
        )

        ui_manager = rockbuilder_cfg.UiManager(FakeScreen(), config)

        selected_sdk = ui_manager.sdk_list.get_selected_item()
        self.assertEqual(
            selected_sdk.get_key(),
            rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG,
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_existing_build_is_feasible_for_saved_build_selection(
        self,
        local_sdk,
    ):
        config = make_config(
            "[rocm_sdk]\n"
            "rocm_sdk_build_config = ['therock_10_0']\n"
        )

        ui_manager = rockbuilder_cfg.UiManager(FakeScreen(), config)

        selected_sdk = ui_manager.sdk_list.get_selected_item()
        self.assertEqual(
            selected_sdk.get_key(),
            rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG,
        )
        self.assertEqual(selected_sdk.get_value(), "therock_10_0")

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_restores_saved_build_when_default_path_changes(
        self,
        unused_local_sdk,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            sdk_path = Path(temp_dir) / "rocm"
            (sdk_path / "bin").mkdir(parents=True)
            (sdk_path / "lib").mkdir()
            config = make_config(
                "[rocm_sdk]\n"
                f"rocm_sdk_build = ['{sdk_path.as_posix()}']\n"
            )
            unused_local_sdk.return_value = [sdk_path.resolve()]

            ui_manager = rockbuilder_cfg.UiManager(
                FakeScreen(),
                config,
            )

            selected_sdk = ui_manager.sdk_list.get_selected_item()
            self.assertEqual(
                selected_sdk.get_key(),
                rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME,
            )
            self.assertEqual(
                selected_sdk.get_value(),
                sdk_path.resolve().as_posix(),
            )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_restores_wheel_sdk_gpu_and_version(
        self,
        unused_local_sdk,
    ):
        server = rcb_const.THEROCK_SDK__PYTHON_WHEEL_SERVER_URL
        config = make_config(
            "[rocm_sdk]\n"
            f"rocm_sdk_whl_server = ['{server}']\n"
            "rocm_sdk_whl_version = saved-version\n"
            "\n"
            "[build_targets]\n"
            "gpus = ['gfx90a']\n"
        )

        ui_manager = rockbuilder_cfg.UiManager(FakeScreen(), config)

        selected_sdk = ui_manager.sdk_list.get_selected_item()
        self.assertEqual(
            selected_sdk.get_key(),
            rcb_const.RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER,
        )
        self.assertEqual(selected_sdk.extra_val, "saved-version")
        self.assertEqual(selected_values(ui_manager.gpu_list), ["gfx90a"])
        self.assertFalse(ui_manager.gpu_list.multi_selection)


class WizardNavigationTest(unittest.TestCase):
    def setUp(self):
        self.saved_rocm_home = os.environ.pop("ROCM_HOME", None)

    def tearDown(self):
        if self.saved_rocm_home is not None:
            os.environ["ROCM_HOME"] = self.saved_rocm_home

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_registers_pages_and_position_specific_buttons(
        self,
        unused_installs,
    ):
        ui_manager = rockbuilder_cfg.UiManager(
            FakeScreen(),
            make_config(""),
        )

        first_buttons = ui_manager.pages[0].get_buttons(0, 2)
        last_buttons = ui_manager.pages[1].get_buttons(1, 2)

        self.assertEqual(
            [button.action for button in first_buttons],
            [
                NavigationAction.CANCEL,
                NavigationAction.FORWARD,
            ],
        )
        self.assertEqual(
            [button.action for button in last_buttons],
            [
                NavigationAction.BACK,
                NavigationAction.CANCEL,
                NavigationAction.SAVE,
            ],
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_shortcuts_move_forward_and_save(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                ord("f"),
                ord(" "),
                ord("s"),
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        saved_config = make_config(
            "[build_targets]\ngpus = ['gfx906']\n"
        )
        save_selection = mock.Mock(return_value=saved_config)
        ui_manager.selection_list_manager.save_selection = (
            save_selection
        )

        result = ui_manager.show()

        self.assertIs(result, saved_config)
        save_selection.assert_called_once_with()
        first_frame = "\n".join(screen.frames[0].values())
        second_frame = "\n".join(screen.frames[1].values())
        self.assertIn("Select ROCM SDK", first_frame)
        self.assertNotIn("Select AMD GPUs", first_frame)
        self.assertIn("Select AMD GPUs", second_frame)

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_focused_buttons_activate_with_enter(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                9,
                curses.KEY_RIGHT,
                10,
                ord(" "),
                9,
                curses.KEY_RIGHT,
                curses.KEY_RIGHT,
                10,
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        saved_config = make_config(
            "[build_targets]\ngpus = ['gfx906']\n"
        )
        save_selection = mock.Mock(return_value=saved_config)
        ui_manager.selection_list_manager.save_selection = (
            save_selection
        )

        result = ui_manager.show()

        self.assertIs(result, saved_config)
        save_selection.assert_called_once_with()

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_enter_focuses_primary_button_without_selecting_item(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                curses.KEY_DOWN,
                10,
                10,
                ord(" "),
                10,
                10,
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        initial_sdk = ui_manager.sdk_list.get_selected_item()
        saved_config = make_config(
            "[build_targets]\ngpus = ['gfx906']\n"
        )
        save_selection = mock.Mock(return_value=saved_config)
        ui_manager.selection_list_manager.save_selection = (
            save_selection
        )

        result = ui_manager.show()

        self.assertIs(result, saved_config)
        self.assertIs(
            ui_manager.sdk_list.get_selected_item(),
            initial_sdk,
        )
        save_selection.assert_called_once_with()

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_back_returns_to_sdk_page_and_cancel_does_not_save(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                ord("f"),
                ord("b"),
                ord("c"),
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        save_selection = mock.Mock()
        ui_manager.selection_list_manager.save_selection = (
            save_selection
        )

        result = ui_manager.show()

        self.assertIsNone(result)
        save_selection.assert_not_called()
        frame_titles = [
            frame.get((0, 0), "")
            for frame in screen.frames
        ]
        self.assertIn("Select ROCM SDK", frame_titles[0])
        self.assertIn("Select AMD GPUs", frame_titles[1])
        self.assertIn("Select ROCM SDK", frame_titles[2])

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_back_and_forward_preserve_gpu_selection(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                ord("f"),
                ord(" "),
                ord("b"),
                ord("f"),
                ord("s"),
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        saved_config = make_config(
            "[build_targets]\ngpus = ['gfx906']\n"
        )
        save_selection = mock.Mock(return_value=saved_config)
        ui_manager.selection_list_manager.save_selection = (
            save_selection
        )

        result = ui_manager.show()

        self.assertIs(result, saved_config)
        self.assertEqual(
            selected_values(ui_manager.gpu_list),
            ["gfx906"],
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_save_shows_validation_message_for_empty_gpu_list(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                ord("f"),
                ord("s"),
                ord("c"),
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        save_selection = mock.Mock()
        ui_manager.selection_list_manager.save_selection = (
            save_selection
        )

        result = ui_manager.show()

        self.assertIsNone(result)
        save_selection.assert_not_called()
        validation_frame = "\n".join(screen.frames[2].values())
        self.assertIn(
            "Select at least one GPU target",
            validation_frame,
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_runtime_wheel_sdk_selection_uses_single_gpu_mode(
        self,
        unused_installs,
    ):
        screen = FakeScreen(
            [
                curses.KEY_DOWN,
                curses.KEY_DOWN,
                ord(" "),
                ord("f"),
                ord("c"),
            ]
        )
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )

        ui_manager.show()

        selected_sdk = ui_manager.sdk_list.get_selected_item()
        self.assertEqual(
            selected_sdk.get_key(),
            rcb_const.RCB__CFG__KEY__ROCM_SDK_PYTHON_WHEEL_SERVER,
        )
        self.assertFalse(ui_manager.gpu_list.multi_selection)
        self.assertEqual(
            ui_manager.gpu_list.get_item(0).get_value(),
            "gfx101X-dgpu",
        )

    @mock.patch(
        "rockbuilder_cfg.discover_rocm_sdk_installs",
        return_value=[],
    )
    def test_page_scrolls_to_keep_cursor_visible(
        self,
        unused_installs,
    ):
        screen = FakeScreen(height=8)
        ui_manager = rockbuilder_cfg.UiManager(
            screen,
            make_config(""),
        )
        gpu_page = ui_manager.pages[1]
        gpu_page.item_cursor = 10

        gpu_page.render(screen, 1, 2)

        self.assertEqual(gpu_page.first_visible_item, 8)
        rendered_text = "\n".join(screen.frames[-1].values())
        first_gpu_name = (
            ui_manager.gpu_list.get_item(0).get_name()
        )
        current_gpu_name = (
            ui_manager.gpu_list.get_item(10).get_name()
        )
        self.assertNotIn(first_gpu_name, rendered_text)
        self.assertIn(current_gpu_name, rendered_text)


class ConfigStoreTest(unittest.TestCase):
    def test_save_replaces_owned_sections_and_preserves_other_sections(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "rockbuilder.cfg"
            config_path.write_text(
                "[custom]\n"
                "keep = yes\n"
                "\n"
                "[rocm_sdk]\n"
                "stale = value\n",
                encoding="utf-8",
            )
            sdk_list = mock.Mock()
            sdk_list.get_config_selections.return_value = (
                rockbuilder_cfg.ConfigSelection(
                    "rocm_sdk",
                    {"rocm_sdk_build_config": ["therock_dev"]},
                )
            )
            gpu_list = mock.Mock()
            gpu_list.get_config_selections.return_value = (
                rockbuilder_cfg.ConfigSelection(
                    "build_targets",
                    {"gpus": ["gfx90a"]},
                )
            )
            on_change = mock.Mock()
            config_store = ConfigStore(config_path, on_change)

            saved_config = config_store.save(
                [sdk_list, gpu_list]
            )

        self.assertEqual(saved_config.get("custom", "keep"), "yes")
        self.assertFalse(saved_config.has_option("rocm_sdk", "stale"))
        self.assertEqual(
            saved_config.get("rocm_sdk", "rocm_sdk_build_config"),
            "['therock_dev']",
        )
        self.assertEqual(
            saved_config.get("build_targets", "gpus"),
            "['gfx90a']",
        )
        on_change.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
