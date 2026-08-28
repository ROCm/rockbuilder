import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = (
    REPOSITORY_ROOT
    / "patches/therock/release/therock/base"
    / "0001-therock-patches-to-python-scripts-config-and-build.patch"
)


class TheRockInstallScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.therock_dir = Path(cls.temp_dir.name)
        subprocess.run(
            ["git", "init", "-q", str(cls.therock_dir)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(cls.therock_dir),
                "apply",
                str(PATCH_PATH),
            ],
            check=True,
        )
        module_path = cls.therock_dir / "rcb_install.py"
        spec = importlib.util.spec_from_file_location(
            "rcb_install_under_test",
            module_path,
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
        environment = {
            "RCB_ROCM_SDK_INSTALL_DIR": str(install_dir),
            "RCB_APP_VERSION": "release-test",
        }
        completed_process = subprocess.CompletedProcess([], 0)

        with mock.patch.dict(os.environ, environment, clear=True):
            with mock.patch.object(
                self.install_module.subprocess,
                "run",
                return_value=completed_process,
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


if __name__ == "__main__":
    unittest.main()
