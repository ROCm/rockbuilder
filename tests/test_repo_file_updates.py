import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lib_python.rcb_constants as rcb_const
from lib_python.app_builder import RockProjectBuilder
from lib_python.repo_management import RockProjectRepo
from lib_python.repo_management import TAG_CHECKOUT
from lib_python.repo_management import TAG_FILE_COPY


def run_git(repo_path, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class RepoFileUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.repo_path = self.temp_path / "source"
        self.changes_root = self.temp_path / "changes"
        self.files_root = self.changes_root / "files"
        self.repo_path.mkdir()
        run_git(self.repo_path, "init", "-q")
        (self.repo_path / "upstream.txt").write_text(
            "upstream\n",
            encoding="utf-8",
        )
        run_git(self.repo_path, "add", "upstream.txt")
        run_git(
            self.repo_path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "-m",
            "Upstream",
        )

        self.repo = object.__new__(RockProjectRepo)
        self.repo.app_src_dir = self.repo_path
        self.repo.app_name = "demo"
        self.repo.app_patch_dir_base_name = "1.0"
        self.repo.change_dir_root_arr = [self.changes_root]

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_update_file(self, version, relative_path, contents):
        update_path = (
            self.files_root
            / "demo"
            / version
            / "demo"
            / relative_path
        )
        update_path.parent.mkdir(parents=True, exist_ok=True)
        update_path.write_text(contents, encoding="utf-8")
        return update_path

    def test_version_files_override_common_files(self):
        self.write_update_file("common", "shared.txt", "common\n")
        executable = self.write_update_file(
            "common",
            "tools/common.py",
            "common\n",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        self.write_update_file("1.0", "shared.txt", "version\n")

        checkout_commit = run_git(self.repo_path, "rev-parse", "HEAD")
        self.repo.force_tag(self.repo_path, TAG_CHECKOUT)
        copied_count = self.repo.copy_repo_files(self.repo_path)

        self.assertEqual(copied_count, 2)
        self.assertEqual(
            (self.repo_path / "shared.txt").read_text(encoding="utf-8"),
            "version\n",
        )
        copied_mode = (self.repo_path / "tools/common.py").stat().st_mode
        self.assertTrue(copied_mode & stat.S_IXUSR)
        self.assertEqual(
            run_git(self.repo_path, "rev-parse", "HEAD^"),
            checkout_commit,
        )
        self.assertEqual(
            run_git(self.repo_path, "rev-parse", TAG_CHECKOUT),
            checkout_commit,
        )
        self.assertEqual(
            run_git(self.repo_path, "rev-parse", TAG_FILE_COPY),
            run_git(self.repo_path, "rev-parse", "HEAD"),
        )
        self.assertEqual(run_git(self.repo_path, "status", "--porcelain"), "")

    def test_environment_changes_root_has_highest_precedence(self):
        env_root = self.temp_path / "alternative-changes"
        env_name = rcb_const.RCB__ENV_VAR__USER_CHANGES_ROOT_DIR
        with patch.dict(
            "os.environ",
            {env_name: str(env_root)},
        ):
            change_dir_roots = (
                RockProjectBuilder._get_change_dir_root_arr()
            )

        self.assertEqual(change_dir_roots[0], env_root.resolve())
        self.assertEqual(len(change_dir_roots), 2)
        self.assertEqual(
            change_dir_roots[1],
            rcb_const.RCB__CHANGES_ROOT_DIR.resolve(),
        )
        patch_dir = self.repo.get_app_patch_dir_root(
            change_dir_roots[0],
            "demo",
            "1.0",
        )
        self.assertEqual(
            patch_dir,
            env_root / "patches/demo/1.0",
        )

    def test_multiline_cmake_config_runs_as_one_command(self):
        self.repo.app_build_dir = self.temp_path / "build"
        cmake_config = """
            -DCMAKE_PREFIX_PATH=/opt/rocm
            "-DAOTRITON_TARGET_ARCH=gfx90a;gfx1100"
            /source/aotriton
        """
        with patch.object(
            self.repo,
            "_handle_command_exec",
            return_value=True,
        ) as command_exec:
            result = self.repo.do_CMD_CMAKE_CONFIG(cmake_config)

        self.assertTrue(result)
        command_exec.assert_called_once_with(
            "CMD_CMAKE_CONFIG",
            "cmake -GNinja -DCMAKE_PREFIX_PATH=/opt/rocm "
            '"-DAOTRITON_TARGET_ARCH=gfx90a;gfx1100" '
            "/source/aotriton",
            self.repo.app_build_dir,
        )

    @unittest.skipUnless(Path("/bin/bash").is_file(), "requires Bash")
    def test_multiline_command_stops_after_failure(self):
        self.repo.is_posix = True
        marker_path = self.temp_path / "continued"
        command = f'false\nprintf continued > "{marker_path}"'

        with patch("lib_python.repo_management.time.sleep"):
            result = self.repo._handle_command_exec(
                "build",
                command,
                self.temp_path,
            )

        self.assertFalse(result)
        self.assertFalse(marker_path.exists())

    @unittest.skipUnless(Path("/bin/bash").is_file(), "requires Bash")
    def test_multiline_command_detects_pipeline_failure(self):
        self.repo.is_posix = True
        marker_path = self.temp_path / "continued"
        command = (
            "false | true\n"
            f'printf continued > "{marker_path}"'
        )

        with patch("lib_python.repo_management.time.sleep"):
            result = self.repo._handle_command_exec(
                "build",
                command,
                self.temp_path,
            )

        self.assertFalse(result)
        self.assertFalse(marker_path.exists())

    @unittest.skipUnless(Path("/bin/bash").is_file(), "requires Bash")
    def test_multiline_command_preserves_shell_state(self):
        self.repo.is_posix = True
        child_path = self.temp_path / "child"
        child_path.mkdir()
        marker_path = self.temp_path / "working-directory"
        command = f'cd "{child_path}"\npwd > "{marker_path}"'

        with patch("lib_python.repo_management.time.sleep"):
            result = self.repo._handle_command_exec(
                "build",
                command,
                self.temp_path,
            )

        self.assertTrue(result)
        self.assertEqual(
            marker_path.read_text(encoding="utf-8").strip(),
            str(child_path),
        )

    def test_windows_multiline_command_adds_failure_checks(self):
        self.repo.app_build_dir = self.temp_path / "build"
        command = "mkdir output\ncd output\necho done > result.txt"
        with (
            patch(
                "lib_python.repo_management.platform.win32_ver",
                return_value=("10", "", "", ""),
            ),
            patch.object(
                self.repo,
                "_exec_subprocess_batch_file",
                return_value=True,
            ),
        ):
            result = self.repo._handle_command_exec(
                "install",
                command,
                self.temp_path,
            )

        batch_path = self.repo.app_build_dir / "install.bat"
        self.assertTrue(result)
        self.assertEqual(
            batch_path.read_text(encoding="utf-8"),
            "@echo off\n"
            "mkdir output\n"
            "if errorlevel 1 exit /b %errorlevel%\n"
            "cd output\n"
            "if errorlevel 1 exit /b %errorlevel%\n"
            "echo done > result.txt\n"
            "if errorlevel 1 exit /b %errorlevel%\n",
        )

    def test_batch_failure_returns_false(self):
        completed_process = subprocess.CompletedProcess(
            args=["failed.bat"],
            returncode=1,
        )
        with patch(
            "lib_python.repo_management.subprocess.run",
            return_value=completed_process,
        ):
            result = self.repo._exec_subprocess_batch_file("failed.bat")

        self.assertFalse(result)

    def test_no_files_points_both_tags_to_checkout(self):
        checkout_commit = run_git(self.repo_path, "rev-parse", "HEAD")

        self.repo.force_tag(self.repo_path, TAG_CHECKOUT)
        copied_count = self.repo.copy_repo_files(self.repo_path)

        self.assertEqual(copied_count, 0)
        self.assertEqual(
            run_git(self.repo_path, "rev-parse", TAG_CHECKOUT),
            checkout_commit,
        )
        self.assertEqual(
            run_git(self.repo_path, "rev-parse", TAG_FILE_COPY),
            checkout_commit,
        )

    def test_python_cache_files_are_not_copied(self):
        self.write_update_file(
            "common",
            "__pycache__/helper.cpython-312.pyc",
            "cache\n",
        )
        self.repo.force_tag(self.repo_path, TAG_CHECKOUT)

        copied_count = self.repo.copy_repo_files(self.repo_path)

        self.assertEqual(copied_count, 0)
        self.assertFalse((self.repo_path / "__pycache__").exists())

    def test_existing_destination_fails_before_copy(self):
        self.write_update_file("common", "upstream.txt", "replacement\n")
        self.write_update_file("common", "not-copied.txt", "new\n")

        self.repo.force_tag(self.repo_path, TAG_CHECKOUT)
        with self.assertRaisesRegex(
            FileExistsError,
            "upstream.txt",
        ):
            self.repo.copy_repo_files(self.repo_path)

        self.assertFalse((self.repo_path / "not-copied.txt").exists())
        self.assertEqual(
            (self.repo_path / "upstream.txt").read_text(encoding="utf-8"),
            "upstream\n",
        )

    def test_saved_patches_exclude_file_copy_commit(self):
        self.write_update_file("common", "copied.txt", "copied\n")
        self.repo.force_tag(self.repo_path, TAG_CHECKOUT)
        self.repo.copy_repo_files(self.repo_path)
        (self.repo_path / "copied.txt").write_text(
            "updated\n",
            encoding="utf-8",
        )
        run_git(self.repo_path, "add", "copied.txt")
        run_git(
            self.repo_path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "-m",
            "Update copied file",
        )
        patches_path = self.temp_path / "saved-patches"

        self.repo.save_repo_patches(self.repo_path, patches_path)

        patch_files = list((patches_path / "base").glob("*.patch"))
        self.assertEqual(len(patch_files), 1)
        patch_text = patch_files[0].read_text(encoding="utf-8")
        self.assertIn("Subject: [PATCH] Update copied file", patch_text)
        self.assertNotIn("ROCKBUILDER FILE COPY", patch_text)

    def test_repeated_checkout_moves_tags(self):
        origin_path = self.temp_path / "origin"
        checkout_path = self.temp_path / "checkout"
        origin_path.mkdir()
        run_git(origin_path, "init", "-q")
        (origin_path / "upstream.txt").write_text(
            "first\n",
            encoding="utf-8",
        )
        run_git(origin_path, "add", "upstream.txt")
        run_git(
            origin_path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "-m",
            "First upstream",
        )
        run_git(origin_path, "tag", "v1")
        self.write_update_file("common", "copied.txt", "copied\n")
        checkout_repo = object.__new__(RockProjectRepo)
        checkout_repo.app_src_dir = checkout_path
        checkout_repo.app_name = "demo"
        checkout_repo.app_patch_dir_base_name = "1.0"
        checkout_repo.change_dir_root_arr = [self.changes_root]
        checkout_repo.app_version_hashtag = "v1"
        checkout_repo.app_repo_url = str(origin_path)

        checkout_repo.do_checkout(repo_fetch_depth=0)
        first_checkout = run_git(
            checkout_path,
            "rev-parse",
            TAG_CHECKOUT,
        )
        first_file_copy = run_git(
            checkout_path,
            "rev-parse",
            TAG_FILE_COPY,
        )

        (origin_path / "upstream.txt").write_text(
            "second\n",
            encoding="utf-8",
        )
        run_git(origin_path, "add", "upstream.txt")
        run_git(
            origin_path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "-m",
            "Second upstream",
        )
        run_git(origin_path, "tag", "-f", "v1")

        checkout_repo.do_checkout(repo_fetch_depth=0)
        second_checkout = run_git(
            checkout_path,
            "rev-parse",
            TAG_CHECKOUT,
        )
        second_file_copy = run_git(
            checkout_path,
            "rev-parse",
            TAG_FILE_COPY,
        )

        self.assertNotEqual(first_checkout, second_checkout)
        self.assertNotEqual(first_file_copy, second_file_copy)
        self.assertEqual(
            run_git(checkout_path, "rev-parse", "HEAD^"),
            second_checkout,
        )


if __name__ == "__main__":
    unittest.main()
