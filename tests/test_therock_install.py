import configparser
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib_python.rcb_constants as rcb_const
from lib_python.app_builder import RockProjectBuilder
from lib_python.repo_management import RockProjectRepo
from lib_python.repo_management import TAG_CHECKOUT


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT_PATH = (
    REPOSITORY_ROOT
    / "changes/files/therock/common/therock/rcb_install.py"
)


def run_git(repo_path, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class TheRockInstallScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.therock_dir = Path(cls.temp_dir.name)
        spec = importlib.util.spec_from_file_location(
            "rcb_install_under_test",
            INSTALL_SCRIPT_PATH,
        )
        cls.install_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.install_module)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_requires_install_directory_environment_variable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "RCB_ROCM_SDK_INSTALL_DIR is required",
            ):
                self.install_module.get_install_dir()

    def test_rejects_existing_install_directory(self):
        install_dir = self.therock_dir / "existing-rocm"
        install_dir.mkdir()

        with self.assertRaisesRegex(
            FileExistsError,
            "Rename or delete it",
        ):
            self.install_module.install_rocm_sdk(
                self.therock_dir,
                install_dir,
            )

    def test_installs_component_and_writes_marker(self):
        install_dir = self.therock_dir / "install-root/rocm"
        config_record = self.therock_dir / "build/rcb_therock.txt"
        config_record.parent.mkdir(parents=True, exist_ok=True)
        config_record.write_text(
            "cmake -B build -DTHEROCK_AMDGPU_FAMILIES=gfx90a .\n",
            encoding="utf-8",
        )
        environment = {
            "RCB_ROCM_SDK_INSTALL_DIR": str(install_dir),
            "RCB_APP_VERSION": "release-test",
        }
        completed_process = subprocess.CompletedProcess([], 0)

        def run_install(_command):
            install_dir.mkdir(parents=True)
            return completed_process

        with mock.patch.dict(os.environ, environment, clear=True):
            with mock.patch.object(
                self.install_module,
                "__file__",
                str(self.therock_dir / "rcb_install.py"),
            ):
                with mock.patch.object(
                    self.install_module.subprocess,
                    "run",
                    side_effect=run_install,
                ) as run:
                    self.install_module.main()

        run.assert_called_once_with(
            [
                "cmake",
                "--install",
                str(self.therock_dir / "build"),
                "--component",
                "rocm",
                "--prefix",
                str(install_dir),
            ]
        )
        marker = install_dir / ".info/rcb_rocm_sdk_src_version"
        self.assertEqual(
            marker.read_text(encoding="utf-8"),
            "rockbuilder_therock: release-test\n",
        )
        installed_config = install_dir / "rcb_therock.txt"
        self.assertEqual(
            installed_config.read_text(encoding="utf-8"),
            config_record.read_text(encoding="utf-8"),
        )
        self.assertFalse((install_dir / "rcb_config.txt").exists())

    def test_requires_configuration_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            install_dir = temp_path / "install"
            install_dir.mkdir()

            with self.assertRaisesRegex(
                FileNotFoundError,
                "configuration record was not found",
            ):
                self.install_module.install_config_record(
                    temp_path,
                    install_dir,
                )


class TheRockInstallPathResolutionTest(unittest.TestCase):
    def test_dev_path_uses_checkout_tag_version_and_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo_path = temp_path / "therock_dev"
            repo_path.mkdir()
            run_git(repo_path, "init", "-q")
            (repo_path / "version.json").write_text(
                '{"rocm-version": "10.1.0"}\n',
                encoding="utf-8",
            )
            run_git(repo_path, "add", "version.json")
            run_git(
                repo_path,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "Checkout",
            )
            run_git(repo_path, "tag", TAG_CHECKOUT)
            checkout_revision = run_git(repo_path, "rev-parse", TAG_CHECKOUT)
            (repo_path / "patched.txt").write_text(
                "patched\n",
                encoding="utf-8",
            )
            run_git(repo_path, "add", "patched.txt")
            run_git(
                repo_path,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "Patch",
            )
            head_revision = run_git(repo_path, "rev-parse", "HEAD")

            builder = object.__new__(RockProjectBuilder)
            builder.app_src_dir_path = repo_path
            builder.app_repo = object.__new__(RockProjectRepo)
            builder.rocm_sdk_install_dir_basename = (
                "rocm_dev_{rocm_version}_{git_hash}"
            )
            builder.resolved_rocm_sdk_install_dir = None
            install_parent = temp_path / "install"
            install_parent.mkdir()
            with mock.patch.object(
                rcb_const,
                "get_therock_rocm_sdk_install_dir",
                side_effect=lambda **kwargs: (
                    install_parent / kwargs["install_dir_basename"]
                ),
            ), mock.patch.object(Path, "symlink_to") as create_symlink:
                install_dir = builder._resolve_rocm_sdk_install_dir()

            self.assertEqual(
                install_dir.name,
                f"rocm_dev_10_1_0_{checkout_revision[:7]}",
            )
            self.assertNotIn(head_revision[:7], install_dir.name)
            create_symlink.assert_not_called()

    def test_resolved_install_path_is_persisted_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "rockbuilder.cfg"
            config_path.write_text(
                "[rocm_sdk]\n"
                "rocm_sdk_home = ['/opt/other-rocm']\n"
                "\n"
                "[build_targets]\n"
                "gpus = ['gfx90a']\n",
                encoding="utf-8",
            )
            builder = object.__new__(RockProjectBuilder)
            builder.app_cfg_base_name = "therock_dev"
            builder.resolved_rocm_sdk_install_dir = (
                temp_path / "rocm_dev_10_1_0_a1b2c3d"
            )

            with mock.patch.object(
                rcb_const,
                "get_rock_builder_config_file",
                return_value=config_path,
            ):
                builder._save_rocm_sdk_build_config()

            config = configparser.ConfigParser()
            config.read(config_path)
            section = rcb_const.RCB__CFG__SECTION__ROCM_SDK
            self.assertEqual(
                config.get(
                    section,
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_BUILD,
                ),
                str([builder.resolved_rocm_sdk_install_dir.as_posix()]),
            )
            self.assertEqual(
                config.get(
                    section,
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_BUILD_CONFIG,
                ),
                "['therock_dev']",
            )
            self.assertFalse(
                config.has_option(
                    section,
                    rcb_const.RCB__CFG__KEY__ROCM_SDK_FROM_ROCM_HOME,
                )
            )
            self.assertFalse(config_path.with_suffix(".tmp").exists())


class CleanCommandTest(unittest.TestCase):
    def test_failed_clean_command_terminates_build(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = object.__new__(RockProjectBuilder)
            builder.app_build_dir_path = Path(temp_dir) / "build"
            builder.app_build_dir_path.mkdir()
            builder.app_repo = mock.Mock()
            builder.app_repo.do_clean.return_value = False
            builder.CMD_CLEAN = "failing clean command"
            builder.printout_error_and_terminate = mock.Mock(
                side_effect=SystemExit(1)
            )

            with self.assertRaises(SystemExit):
                builder.clean(False, False)

            builder.printout_error_and_terminate.assert_called_once_with(
                rcb_const.RCB__APP_CFG__KEY__CMD_CLEAN
            )

    def test_current_pytorch_clean_commands_do_not_use_setup_py(self):
        config_names = (
            "pytorch_2_14.cfg",
            "pytorch_nightly.cfg",
            "pytorch_torchcodec_nightly.cfg",
            "pytorch_vision_nightly.cfg",
            "triton_nightly.cfg",
        )
        for config_name in config_names:
            with self.subTest(config_name=config_name):
                config = configparser.ConfigParser()
                config.read(REPOSITORY_ROOT / "apps" / config_name)

                clean_command = config.get("app_info", "CMD_CLEAN")
                self.assertNotIn("setup.py", clean_command)
                self.assertEqual(
                    clean_command,
                    "RCB_CALLBACK__DELETE_APP_SRC_SUBDIR build dist",
                )

    def test_pytorch_nightly_enables_nvshmem(self):
        config = configparser.ConfigParser()
        config.read(REPOSITORY_ROOT / "apps/pytorch_nightly.cfg")

        environment = config.get("app_info", "ENV_VAR")
        self.assertIn("USE_NVSHMEM=1", environment.splitlines())


if __name__ == "__main__":
    unittest.main()
