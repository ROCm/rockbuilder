import configparser
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib_python.rcb_constants as rcb_const
from lib_python.rcb_cfg_reader import RCBConfigReader
import rockbuilder_cfg


class FakeScreen:
    def clear(self):
        pass


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

        self.assertEqual(install_dir, preferred_parent / "rocm_10_0")

    def test_uses_home_when_opt_parent_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            install_dir = rcb_const.get_therock_rocm_sdk_install_dir(
                temp_path / "missing/opt/rcb",
                temp_path / "home",
            )

        self.assertEqual(
            install_dir,
            temp_path / "home/rcb/rocm_10_0",
        )

    def test_uses_home_when_opt_destination_is_not_writable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            preferred_parent = temp_path / "opt/rcb"
            preferred_dir = preferred_parent / "rocm_10_0"
            preferred_dir.mkdir(parents=True)
            home_dir = temp_path / "home"

            with mock.patch.object(os, "access", return_value=False):
                install_dir = (
                    rcb_const.get_therock_rocm_sdk_install_dir(
                        preferred_parent,
                        home_dir,
                    )
                )

        self.assertEqual(install_dir, home_dir / "rcb/rocm_10_0")

    def test_discovers_all_valid_sdk_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            install_parent = temp_path / "opt/rcb"
            expected_installs = [
                install_parent / "rocm_10_0",
                install_parent / "rocm_dev_10_1_a1b2c3d",
                temp_path / "home/rcb/rocm_dev_10_0_d4e5f6a",
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


if __name__ == "__main__":
    unittest.main()
