import configparser
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib_python.rcb_constants as rcb_const
import rockbuilder
import rockbuilder_cfg
from lib_python.app_builder import RockProjectBuilder
from lib_python.config_ui.build_options import SanitizerMode
from lib_python.config_ui.build_options import normalize_gpu_targets
from lib_python.rcb_cfg_reader import RCBConfigReader


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCRIPT_PATH = (
    REPOSITORY_ROOT
    / "changes/files/therock/common/therock/rcb_config.py"
)
ROCKBUILDER_HASH = "1" * 40
THEROCK_CHECKOUT_HASH = "2" * 40
THEROCK_BUILD_HASH = "3" * 40


class BuildOptionConfigTest(unittest.TestCase):
    def test_torch_config_files_use_torch_prefix(self):
        apps_dir = REPOSITORY_ROOT / "apps"
        old_config_paths = sorted(apps_dir.glob("pytorch*"))
        self.assertEqual(old_config_paths, [])
        old_amd_paths = sorted(apps_dir.glob("torch*amd*"))
        self.assertEqual(old_amd_paths, [])
        misplaced_rocm_paths = sorted(apps_dir.glob("torch_*_rocm*"))
        self.assertEqual(misplaced_rocm_paths, [])
        legacy_package_paths = [
            *apps_dir.glob("torch_vision*"),
            *apps_dir.glob("torch_audio*"),
            *apps_dir.glob("torch_torchcodec*"),
            *apps_dir.glob("torch_aotriton*"),
        ]
        self.assertEqual(legacy_package_paths, [])

        for app_list_path in apps_dir.glob("*.apps"):
            with self.subTest(app_list_path=app_list_path):
                app_list = app_list_path.read_text(encoding="utf-8")
                self.assertNotIn("pytorch_", app_list)
                self.assertNotIn("torch_vision", app_list)
                self.assertNotIn("torch_audio", app_list)
                self.assertNotIn("torch_torchcodec", app_list)
                self.assertNotIn("torch_aotriton", app_list)
                for app_name in app_list.split():
                    if app_name.startswith("torch"):
                        self.assertNotIn("_amd", app_name)
                        if "_rocm" in app_name:
                            self.assertTrue(
                                app_name.startswith("torch_rocm_")
                            )

    def test_full_asan_name_describes_selected_device_targets(self):
        display_name = SanitizerMode.ASAN.get_display_name(
            ["gfx906", "gfx90a"]
        )
        unavailable_name = SanitizerMode.ASAN.get_display_name([])

        self.assertEqual(
            display_name,
            "Host ASAN for all selected GPUs and device ASAN for "
            "gfx906, gfx90a",
        )
        self.assertEqual(
            unavailable_name,
            "Host ASAN for all selected GPUs; no selected GPU "
            "supports device ASAN",
        )

    def test_reader_loads_therock_sanitizer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "rockbuilder.cfg"
            config_path.write_text(
                "[rocm_sdk]\n"
                "rocm_sdk_build_config = ['therock_dev']\n"
                "\n"
                "[build_targets]\n"
                "gpus = ['gfx942:xnack+']\n"
                "\n"
                "[build_options]\n"
                "therock_sanitizer = ['ASAN']\n",
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
            config_reader.get_therock_sanitizer(),
            "ASAN",
        )
        self.assertEqual(
            config_reader.get_configured_gpu_list(),
            ["gfx942:xnack+"],
        )

    def test_reader_defaults_therock_sanitizer_to_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "rockbuilder.cfg"
            config_path.write_text(
                "[build_targets]\n"
                "gpus = ['gfx1100']\n",
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
            config_reader.get_therock_sanitizer(),
            "NONE",
        )

    def test_full_asan_normalizes_only_device_asan_targets(self):
        targets = normalize_gpu_targets(
            [
                "gfx906",
                "gfx908:xnack-",
                "gfx90a",
                "gfx942",
                "gfx1100",
            ],
            "ASAN",
        )

        self.assertEqual(
            targets,
            [
                "gfx906:xnack+",
                "gfx908:xnack-",
                "gfx90a:xnack+",
                "gfx942:xnack+",
                "gfx1100",
            ],
        )

    def test_conflicting_xnack_forms_are_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Conflicting XNACK target forms",
        ):
            normalize_gpu_targets(
                ["gfx90a", "gfx90a:xnack+"],
                "NONE",
            )

    def test_xnack_is_rejected_for_unsupported_target(self):
        with self.assertRaisesRegex(
            ValueError,
            "XNACK mode is not supported",
        ):
            normalize_gpu_targets(
                ["gfx1100:xnack+"],
                "NONE",
            )

    def test_saved_sanitizer_is_exported_for_direct_build(self):
        config = configparser.ConfigParser()
        config.read_string(
            "[build_options]\n"
            "therock_sanitizer = ['HOST_ASAN']\n"
        )
        sanitizer_env = (
            rcb_const.RCB__ENV_VAR__THEROCK_SANITIZER
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            rockbuilder_cfg.configure_sanitizer_environment(config)
            sanitizer = os.environ[sanitizer_env]

        self.assertEqual(sanitizer, "HOST_ASAN")

    def test_missing_sanitizer_selection_exports_none(self):
        config = configparser.ConfigParser()
        sanitizer_env = (
            rcb_const.RCB__ENV_VAR__THEROCK_SANITIZER
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            rockbuilder_cfg.configure_sanitizer_environment(config)
            sanitizer = os.environ[sanitizer_env]

        self.assertEqual(sanitizer, "NONE")

    def test_base_target_environment_removes_xnack_qualifiers(self):
        environment = {
            "RCB_AMDGPU_TARGETS": (
                "gfx90a:xnack-;gfx90a:xnack+;gfx1100"
            )
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            rockbuilder.set_amdgpu_base_targets_environment()
            base_targets = os.environ[
                rcb_const.RCB__ENV_VAR__AMDGPU_BASE_TARGETS
            ]

        self.assertEqual(base_targets, "gfx90a;gfx1100")

    def test_rockbuilder_hash_is_exported(self):
        result = subprocess.CompletedProcess(
            [],
            0,
            stdout=f"{ROCKBUILDER_HASH}\n",
            stderr="",
        )
        hash_env = rcb_const.RCB__ENV_VAR__ROCKBUILDER_HASH
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                rockbuilder.subprocess,
                "run",
                return_value=result,
            ),
        ):
            rockbuilder.configure_rockbuilder_hash_environment(
                REPOSITORY_ROOT
            )
            exported_hash = os.environ[hash_env]

        self.assertEqual(exported_hash, ROCKBUILDER_HASH)

    def test_rockbuilder_dirty_state_is_exported(self):
        result = subprocess.CompletedProcess(
            [],
            0,
            stdout=" M rockbuilder.py\n",
            stderr="",
        )
        dirty_env = rcb_const.RCB__ENV_VAR__ROCKBUILDER_DIRTY
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                rockbuilder.subprocess,
                "run",
                return_value=result,
            ),
        ):
            rockbuilder.configure_rockbuilder_dirty_environment(
                REPOSITORY_ROOT
            )
            exported_dirty = os.environ[dirty_env]

        self.assertEqual(exported_dirty, "true")

    def test_aotriton_uses_base_gpu_target_environment(self):
        config_names = [
            "aotriton_0_11b.cfg",
            "aotriton_0_13b.cfg",
            "aotriton_main.cfg",
        ]

        for config_name in config_names:
            with self.subTest(config_name=config_name):
                config = configparser.ConfigParser()
                config.read(REPOSITORY_ROOT / "apps" / config_name)
                command = config.get(
                    rcb_const.RCB__APP_CFG__SECTION_APP_INFO,
                    rcb_const.RCB__APP_CFG__KEY__CMD_CMAKE_CONFIG,
                )
                self.assertIn(
                    "${RCB_AMDGPU_BASE_TARGETS}",
                    command,
                )
                self.assertNotIn(
                    "${RCB_AMDGPU_TARGETS}",
                    command,
                )
                self.assertIn(
                    "-DAOTRITON_GPU_BUILD_TIMEOUT=0",
                    command,
                )

    def test_therock_passes_sanitizer_as_config_parameter(self):
        config_names = [
            "therock_10_0.cfg",
            "therock_dev.cfg",
        ]

        for config_name in config_names:
            with self.subTest(config_name=config_name):
                config = configparser.ConfigParser()
                config.read(REPOSITORY_ROOT / "apps" / config_name)
                command = config.get(
                    rcb_const.RCB__APP_CFG__SECTION_APP_INFO,
                    rcb_const.RCB__APP_CFG__KEY__CMD_CONFIG,
                )
                self.assertEqual(
                    command,
                    "./rcb_config.py -s ${RCB_THEROCK_SANITIZER} "
                    "-r ${RCB_ROCKBUILDER_HASH} "
                    "-d ${RCB_ROCKBUILDER_DIRTY}",
                )

    def test_therock_patches_register_gfx906_xnack_and_asan(self):
        patch_paths = [
            REPOSITORY_ROOT
            / "changes/patches/therock/main/therock/base"
            / "0002-enable-gfx90a-xnack-and-asan-build-options.patch",
            REPOSITORY_ROOT
            / "changes/patches/therock/release/therock/base"
            / "0003-enable-gfx90a-xnack-and-asan-build-options.patch",
        ]

        for patch_path in patch_paths:
            with self.subTest(patch_path=patch_path):
                patch_text = patch_path.read_text(encoding="utf-8")
                self.assertIn(
                    "therock_add_amdgpu_target(gfx906:xnack-",
                    patch_text,
                )
                self.assertIn(
                    "therock_add_amdgpu_target(gfx906:xnack+",
                    patch_text,
                )
                self.assertIn(
                    "^(gfx906|gfx90a|gfx942|gfx950)$",
                    patch_text,
                )


class SanitizerInstallIdentityTest(unittest.TestCase):
    def resolve_install_name(self, sanitizer):
        builder = object.__new__(RockProjectBuilder)
        builder.rocm_sdk_install_dir_basename = "rocm_10_0_0"
        builder.resolved_rocm_sdk_install_dir = None
        install_parent = Path("/temporary/install")
        sanitizer_env = (
            rcb_const.RCB__ENV_VAR__THEROCK_SANITIZER
        )
        with (
            mock.patch.dict(
                os.environ,
                {sanitizer_env: sanitizer},
                clear=True,
            ),
            mock.patch.object(
                rcb_const,
                "get_therock_rocm_sdk_install_dir",
                side_effect=lambda **kwargs: (
                    install_parent
                    / kwargs["install_dir_basename"]
                ),
            ),
        ):
            install_dir = builder._resolve_rocm_sdk_install_dir()
        ret = install_dir.name
        return ret

    def test_full_asan_has_distinct_install_identity(self):
        self.assertEqual(
            self.resolve_install_name("ASAN"),
            "rocm_10_0_0_asan",
        )

    def test_host_asan_has_distinct_install_identity(self):
        self.assertEqual(
            self.resolve_install_name("HOST_ASAN"),
            "rocm_10_0_0_host_asan",
        )

    def test_normal_build_keeps_existing_install_identity(self):
        self.assertEqual(
            self.resolve_install_name("NONE"),
            "rocm_10_0_0",
        )


class TheRockSanitizerCommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "rcb_config_build_options_test",
            CONFIG_SCRIPT_PATH,
        )
        cls.config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.config_module)

    def test_sanitizer_parameter_defaults_to_none(self):
        with mock.patch.object(
            self.config_module.sys,
            "argv",
            [
                "rcb_config.py",
                "-r",
                ROCKBUILDER_HASH,
                "-d",
                "false",
            ],
        ):
            arguments = self.config_module.parse_arguments()

        self.assertIsNone(arguments.sanitizer)
        self.assertEqual(
            arguments.rockbuilder_hash,
            ROCKBUILDER_HASH,
        )
        self.assertEqual(arguments.rockbuilder_dirty, "false")

    def test_sanitizer_parameter_accepts_explicit_mode(self):
        with mock.patch.object(
            self.config_module.sys,
            "argv",
            [
                "rcb_config.py",
                "-s",
                "HOST_ASAN",
                "-r",
                ROCKBUILDER_HASH,
                "-d",
                "true",
            ],
        ):
            arguments = self.config_module.parse_arguments()

        self.assertEqual(arguments.sanitizer, "HOST_ASAN")
        self.assertEqual(
            arguments.rockbuilder_hash,
            ROCKBUILDER_HASH,
        )
        self.assertEqual(arguments.rockbuilder_dirty, "true")

    def test_explicit_targets_have_safe_bundle_name(self):
        bundle_name = self.config_module.get_dist_bundle_name(
            "gfx942:xnack-;gfx942:xnack+"
        )

        self.assertEqual(
            bundle_name,
            "gfx942_xnackminus_gfx942_xnackplus",
        )

    def test_missing_git_hash_returns_empty_string(self):
        error = subprocess.CalledProcessError(
            128,
            ["git", "rev-parse", "missing^{commit}"],
            output="fatal: ambiguous argument\n",
        )
        with mock.patch.object(
            self.config_module.subprocess,
            "check_output",
            side_effect=error,
        ):
            git_hash = self.config_module.get_git_hash(
                CONFIG_SCRIPT_PATH.parent,
                "missing",
            )

        self.assertEqual(git_hash, "")

    def test_config_record_uses_therock_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            build_dir = Path(temp_dir)
            cmake_cmd = [
                "cmake",
                "-B",
                "build",
                "-GNinja",
                "-DTHEROCK_AMDGPU_FAMILIES=gfx90a;gfx1100",
                ".",
            ]
            self.config_module.write_config_record(
                build_dir,
                cmake_cmd,
                ROCKBUILDER_HASH,
                "false",
                THEROCK_CHECKOUT_HASH,
                THEROCK_BUILD_HASH,
            )

            config_path = build_dir / "rcb_therock.txt"
            config = configparser.ConfigParser(interpolation=None)
            config.read(config_path)
            self.assertEqual(
                config.get("metadata", "format_version"),
                "1.0",
            )
            self.assertEqual(
                config.get("therock", "config").splitlines(),
                [
                    "cmake -B build -GNinja",
                    "-DTHEROCK_AMDGPU_FAMILIES=gfx90a;gfx1100",
                    ".",
                ],
            )
            self.assertEqual(
                config.get("therock", "checkout_hash"),
                THEROCK_CHECKOUT_HASH,
            )
            self.assertEqual(
                config.get("therock", "build_hash"),
                THEROCK_BUILD_HASH,
            )
            self.assertEqual(
                config.get("rockbuilder", "hash"),
                ROCKBUILDER_HASH,
            )
            self.assertEqual(
                config.get("rockbuilder", "dirty"),
                "false",
            )
            self.assertFalse((build_dir / "rcb_config.txt").exists())

    def run_main(self, sanitizer, gpu_target="gfx942:xnack+"):
        version_result = subprocess.CompletedProcess(
            [],
            0,
            stdout="cmake version 4.1.0\n",
        )
        configure_result = subprocess.CompletedProcess([], 0)
        environment = {
            "RCB_AMDGPU_TARGETS": gpu_target,
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(self.config_module.os, "chdir"),
            mock.patch.object(self.config_module, "activate_venv"),
            mock.patch.object(
                self.config_module.subprocess,
                "run",
                side_effect=[version_result, configure_result],
            ) as run,
            mock.patch.object(
                self.config_module,
                "write_config_record",
            ) as write_config_record,
            mock.patch.object(
                self.config_module,
                "get_git_hash",
                side_effect=[
                    THEROCK_CHECKOUT_HASH,
                    THEROCK_BUILD_HASH,
                ],
            ),
            self.assertRaises(SystemExit) as exit_error,
        ):
            self.config_module.main(
                sanitizer,
                ROCKBUILDER_HASH,
                "true",
            )
        configure_command = run.call_args_list[1].args[0]
        write_config_record.assert_called_once_with(
            CONFIG_SCRIPT_PATH.parent / "build",
            configure_command,
            ROCKBUILDER_HASH,
            "true",
            THEROCK_CHECKOUT_HASH,
            THEROCK_BUILD_HASH,
        )
        ret = (
            configure_command,
            exit_error.exception.code,
        )
        return ret

    def test_normal_mode_disables_sanitizer(self):
        command, exit_code = self.run_main("NONE")

        self.assertNotIn("-DTHEROCK_SANITIZER=ASAN", command)
        self.assertIn("-DTHEROCK_SANITIZER=", command)
        self.assertEqual(exit_code, 0)

    def test_full_asan_is_passed_to_cmake(self):
        command, exit_code = self.run_main("ASAN")

        self.assertIn("-DTHEROCK_SANITIZER=ASAN", command)
        self.assertEqual(exit_code, 0)

    def test_missing_sanitizer_parameter_defaults_to_none(self):
        command, exit_code = self.run_main(None, "gfx906")

        self.assertIn("-DTHEROCK_SANITIZER=", command)
        self.assertEqual(exit_code, 0)

    def test_selected_targets_limit_test_artifacts(self):
        command, exit_code = self.run_main(
            "NONE",
            "gfx90a;gfx1100",
        )

        self.assertIn(
            "-DTHEROCK_AMDGPU_FAMILIES=gfx90a;gfx1100",
            command,
        )
        self.assertIn(
            "-DTHEROCK_TEST_AMDGPU_TARGETS=gfx90a;gfx1100",
            command,
        )
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
