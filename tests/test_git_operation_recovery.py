import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib_python.repo_management import RockProjectRepo


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRE_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "changes/files/therock/common/therock/rcb_pre_config.py"
)
PRE_CONFIG_SPEC = importlib.util.spec_from_file_location(
    "therock_rcb_pre_config",
    PRE_CONFIG_PATH,
)
PRE_CONFIG = importlib.util.module_from_spec(PRE_CONFIG_SPEC)
PRE_CONFIG_SPEC.loader.exec_module(PRE_CONFIG)


def run_git(repo_path, *args):
    ret = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return ret


class GitOperationRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name) / "repository"
        self.repo_path.mkdir()
        run_git(self.repo_path, "init", "-q")
        self.repo = object.__new__(RockProjectRepo)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detects_git_am_from_rebase_apply_metadata(self):
        state_path = self.repo_path / ".git/rebase-apply"
        state_path.mkdir()
        (state_path / "applying").touch()

        operation, detected_path = (
            self.repo._get_in_progress_git_operation(self.repo_path)
        )

        self.assertEqual(operation, "am")
        self.assertEqual(detected_path, state_path.resolve())

    def test_detects_apply_based_rebase(self):
        state_path = self.repo_path / ".git/rebase-apply"
        state_path.mkdir()
        (state_path / "rebasing").touch()

        operation, detected_path = (
            self.repo._get_in_progress_git_operation(self.repo_path)
        )

        self.assertEqual(operation, "rebase")
        self.assertEqual(detected_path, state_path.resolve())

    def test_reports_when_no_operation_was_resolved(self):
        ret = self.repo.check_and_resolve_in_progress_git_operation(
            self.repo_path
        )

        self.assertFalse(ret)

    def test_noninteractive_build_fails_with_abort_command(self):
        state_path = self.repo_path / ".git/rebase-apply"
        operation_info = ("am", state_path)
        with (
            mock.patch.object(
                self.repo,
                "_get_in_progress_git_operation",
                return_value=operation_info,
            ),
            mock.patch("sys.stdin.isatty", return_value=False),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "git -C .* am --abort",
            ):
                self.repo.check_and_resolve_in_progress_git_operation(
                    self.repo_path
                )

    def test_interactive_build_aborts_after_confirmation(self):
        state_path = self.repo_path / ".git/rebase-apply"
        operation_info = ("am", state_path)
        abort_result = subprocess.CompletedProcess(
            ["git", "am", "--abort"],
            0,
            "",
            "",
        )
        with (
            mock.patch.object(
                self.repo,
                "_get_in_progress_git_operation",
                side_effect=[operation_info, None],
            ),
            mock.patch.object(
                self.repo,
                "run_git_command",
                return_value=abort_result,
            ) as run_command,
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", return_value="yes"),
        ):
            ret = (
                self.repo.check_and_resolve_in_progress_git_operation(
                    self.repo_path
                )
            )

        self.assertTrue(ret)
        run_command.assert_called_once_with(
            ["am", "--abort"],
            cwd=self.repo_path.resolve(),
        )

    def test_interactive_build_preserves_declined_operation(self):
        state_path = self.repo_path / ".git/rebase-merge"
        operation_info = ("rebase", state_path)
        with (
            mock.patch.object(
                self.repo,
                "_get_in_progress_git_operation",
                return_value=operation_info,
            ),
            mock.patch.object(
                self.repo,
                "run_git_command",
            ) as run_command,
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", return_value="no"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "was not aborted",
            ):
                self.repo.check_and_resolve_in_progress_git_operation(
                    self.repo_path
                )

        run_command.assert_not_called()

    def test_therock_recovery_fails_safely_without_terminal(self):
        state_path = self.repo_path / ".git/rebase-apply"
        operation_info = ("am", state_path)
        with (
            mock.patch.object(
                PRE_CONFIG,
                "get_in_progress_git_operation",
                return_value=operation_info,
            ),
            mock.patch.object(
                PRE_CONFIG.sys.stdin,
                "isatty",
                return_value=False,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "git -C .* am --abort",
            ):
                PRE_CONFIG.check_and_resolve_in_progress_git_operation(
                    self.repo_path
                )

    def test_therock_does_not_retry_failed_patch_series(self):
        with (
            mock.patch.object(
                PRE_CONFIG,
                "get_python_executable_name",
                return_value="python3",
            ),
            mock.patch.object(
                PRE_CONFIG,
                "check_repo_and_submodule_git_operations",
                side_effect=[False, True],
            ),
            mock.patch.object(
                PRE_CONFIG,
                "run_cmd",
                return_value=1,
            ) as run_cmd,
        ):
            ret = PRE_CONFIG.fetch_sources()

        self.assertEqual(ret, 1)
        self.assertEqual(run_cmd.call_count, 1)

    def test_therock_retries_failure_without_git_operation(self):
        with (
            mock.patch.object(
                PRE_CONFIG,
                "get_python_executable_name",
                return_value="python3",
            ),
            mock.patch.object(
                PRE_CONFIG,
                "check_repo_and_submodule_git_operations",
                return_value=False,
            ),
            mock.patch.object(
                PRE_CONFIG,
                "run_cmd",
                side_effect=[1, 0, 0],
            ) as run_cmd,
        ):
            ret = PRE_CONFIG.fetch_sources()

        self.assertEqual(ret, 0)
        self.assertEqual(run_cmd.call_count, 3)


if __name__ == "__main__":
    unittest.main()
