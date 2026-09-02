import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib_python.repo_management import RockProjectRepo
from lib_python.repo_management import get_gpu_artifact_id
from lib_python.repo_management import get_rocm_sdk_artifact_id
from lib_python.repo_management import get_wheel_install_base_dir


class WheelArtifactPathTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_rocm_home(
        self,
        version="10.1.0",
        name="rocm_dev_10_1_0_4144ab3",
    ):
        rocm_home = self.temp_path / name
        version_file = rocm_home / ".info" / "version"
        version_file.parent.mkdir(parents=True)
        version_file.write_text(version + "\n", encoding="utf-8")
        return rocm_home

    def test_sdk_id_matches_resolved_install_directory_name(self):
        rocm_home = self.create_rocm_home()

        self.assertEqual(
            get_rocm_sdk_artifact_id(rocm_home),
            "rocm_dev_10_1_0_4144ab3",
        )

    def test_sdk_id_does_not_require_installed_version_metadata(self):
        rocm_home = self.temp_path / "rocm_10_0_0"
        rocm_home.mkdir()

        self.assertEqual(
            get_rocm_sdk_artifact_id(rocm_home),
            "rocm_10_0_0",
        )

    def test_sdk_id_sanitizes_install_directory_name(self):
        rocm_home = self.create_rocm_home(
            name="rocm dev 10_2_0+abc",
        )

        self.assertEqual(
            get_rocm_sdk_artifact_id(rocm_home),
            "rocm_dev_10_2_0plusabc",
        )

    def test_sdk_id_supports_builds_without_rocm(self):
        self.assertEqual(
            get_rocm_sdk_artifact_id(None),
            "no_rocm_sdk",
        )

    def test_gpu_id_is_sorted_unique_and_filesystem_safe(self):
        gpu_targets = (
            "gfx942;gfx90a:xnack+;gfx90a:xnack-;gfx942"
        )

        self.assertEqual(
            get_gpu_artifact_id(gpu_targets),
            "gfx90a_xnackminus_gfx90a_xnackplus_gfx942",
        )

    def test_gpu_id_handles_missing_targets(self):
        self.assertEqual(get_gpu_artifact_id(None), "cpu")
        self.assertEqual(get_gpu_artifact_id(""), "cpu")

    def test_custom_output_dir_is_contextual_base(self):
        rocm_home = self.create_rocm_home(
            "10.2.0-dev",
            "rocm_dev_10_2_0_abcdef0",
        )
        sdk_id = get_rocm_sdk_artifact_id(rocm_home)

        output_dir = get_wheel_install_base_dir(
            self.temp_path / "custom",
            rocm_home,
            ["gfx950", "gfx942"],
        )

        self.assertEqual(
            output_dir,
            self.temp_path
            / "custom"
            / sdk_id
            / "gfx942_gfx950",
        )


class WheelArtifactCopyTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_dir = self.temp_path / "dist"
        self.source_dir.mkdir()
        self.wheel = self.source_dir / "torch-1.0-py3-none-any.whl"
        self.wheel.write_bytes(b"wheel")

        self.repo = object.__new__(RockProjectRepo)
        self.repo.wheel_install_base_dir = (
            self.temp_path
            / "packages"
            / "whl"
            / "rocm_dev_10_1_0_4144ab3"
            / "gfx90a"
        )
        self.repo.app_name = "torch"
        self.repo.app_cfg_name = "torch_nightly"
        self.repo.app_exec_dir = self.temp_path

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_callback_copies_to_context_and_app_directory(self):
        command = f"RCB_CALLBACK__INSTALL_PYTHON_WHEEL {self.source_dir}"

        with mock.patch.object(
            self.repo,
            "_exec_subprocess_cmd",
            return_value=True,
        ) as execute:
            result = (
                self.repo
                ._handle_RCB_CALLBACK__INSTALL_PYTHON_WHEEL(command)
            )

        destination = (
            self.repo.wheel_install_base_dir
            / "torch"
            / self.wheel.name
        )
        self.assertTrue(result)
        self.assertEqual(destination.read_bytes(), b"wheel")
        self.assertEqual(execute.call_count, 2)
        self.assertIn(str(self.wheel), execute.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
