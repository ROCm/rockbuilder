import configparser
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib_python.rcb_constants as rcb_const
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

        self.assertEqual(install_dir, preferred_parent / "rocm")

    def test_uses_home_when_opt_parent_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            install_dir = rcb_const.get_therock_rocm_sdk_install_dir(
                temp_path / "missing/opt/rcb",
                temp_path / "home",
            )

        self.assertEqual(install_dir, temp_path / "home/rcb/rocm")

    def test_uses_home_when_opt_destination_is_not_writable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            preferred_parent = temp_path / "opt/rcb"
            preferred_dir = preferred_parent / "rocm"
            preferred_dir.mkdir(parents=True)
            home_dir = temp_path / "home"

            with mock.patch.object(os, "access", return_value=False):
                install_dir = (
                    rcb_const.get_therock_rocm_sdk_install_dir(
                        preferred_parent,
                        home_dir,
                    )
                )

        self.assertEqual(install_dir, home_dir / "rcb/rocm")


class ConfigSelectionTest(unittest.TestCase):
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


class UiManagerRestoreTest(unittest.TestCase):
    @mock.patch(
        "rockbuilder_cfg.get_local_rocm_sdk_path_if_available",
        return_value=None,
    )
    @mock.patch(
        "rockbuilder_cfg.get_rocm_home_path_if_available",
        return_value=None,
    )
    def test_restores_build_sdk_and_multiple_gpus(
        self,
        unused_rocm_home,
        unused_local_sdk,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            sdk_path = Path(temp_dir) / "not-built/rocm"
            config = make_config(
                "[rocm_sdk]\n"
                f"rocm_sdk_build = ['{sdk_path.as_posix()}']\n"
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
            rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_BUILD,
        )
        self.assertEqual(
            selected_values(ui_manager.gpu_list),
            ["gfx90a", "gfx1100"],
        )

    @mock.patch(
        "rockbuilder_cfg.get_local_rocm_sdk_path_if_available",
        return_value=None,
    )
    @mock.patch(
        "rockbuilder_cfg.get_rocm_home_path_if_available",
        return_value=None,
    )
    def test_restores_configured_sdk_without_rocm_home(
        self,
        unused_rocm_home,
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
                "Previously configured ROCm SDK",
                selected_sdk.get_name(),
            )
            self.assertIs(ui_manager.sdk_list.get_item(0), selected_sdk)

    @mock.patch(
        "rockbuilder_cfg.get_local_rocm_sdk_path_if_available",
        return_value=None,
    )
    @mock.patch(
        "rockbuilder_cfg.get_rocm_home_path_if_available",
        return_value=None,
    )
    def test_ignores_configured_sdk_when_directory_is_invalid(
        self,
        unused_rocm_home,
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
            rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_BUILD,
        )

    @mock.patch(
        "rockbuilder_cfg.get_local_rocm_sdk_path_if_available"
    )
    @mock.patch(
        "rockbuilder_cfg.get_rocm_home_path_if_available",
        return_value=None,
    )
    def test_existing_build_is_feasible_for_saved_build_selection(
        self,
        unused_rocm_home,
        local_sdk,
    ):
        sdk_path = rcb_const.THEROCK_SDK__ROCM_HOME_BUILD_DIR
        local_sdk.return_value = sdk_path
        config = make_config(
            "[rocm_sdk]\n"
            f"rocm_sdk_build = ['{sdk_path.as_posix()}']\n"
        )

        ui_manager = rockbuilder_cfg.UiManager(FakeScreen(), config)

        selected_sdk = ui_manager.sdk_list.get_selected_item()
        self.assertEqual(
            selected_sdk.get_key(),
            rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME,
        )
        self.assertEqual(selected_sdk.get_value(), sdk_path.as_posix())

    @mock.patch(
        "rockbuilder_cfg.get_local_rocm_sdk_path_if_available",
        return_value=None,
    )
    @mock.patch(
        "rockbuilder_cfg.get_rocm_home_path_if_available",
        return_value=None,
    )
    def test_restores_saved_build_when_default_path_changes(
        self,
        unused_rocm_home,
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
        "rockbuilder_cfg.get_local_rocm_sdk_path_if_available",
        return_value=None,
    )
    @mock.patch(
        "rockbuilder_cfg.get_rocm_home_path_if_available",
        return_value=None,
    )
    def test_restores_wheel_sdk_gpu_and_version(
        self,
        unused_rocm_home,
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
