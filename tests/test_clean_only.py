import unittest
from types import SimpleNamespace
from unittest import mock

from rockbuilder import do_therock
from rockbuilder import is_clean_only


class CleanOnlyTest(unittest.TestCase):
    def make_args(self, **overrides):
        values = {
            "clean": False,
            "init": False,
            "checkout": False,
            "hipify": False,
            "pre_config": False,
            "config": False,
            "post_config": False,
            "build": False,
            "install": False,
            "post_install": False,
            "cmd_init_force_exec": False,
            "cmd_any_force_exec": True,
        }
        values.update(overrides)
        ret = SimpleNamespace(**values)
        return ret

    def test_detects_clean_only_action(self):
        self.assertTrue(is_clean_only(self.make_args(clean=True)))
        self.assertFalse(
            is_clean_only(self.make_args(clean=True, build=True))
        )
        self.assertFalse(is_clean_only(self.make_args()))

    def test_clean_only_skips_sdk_environment_setup(self):
        builder = mock.Mock()
        builder.is_build_enabled_on_current_os.return_value = True
        builder.app_cfg_base_name = "torch_2_14"
        args = self.make_args(clean=True)

        ret = do_therock(builder, args)

        self.assertTrue(ret)
        builder.init.assert_not_called()
        builder.clean.assert_called_once_with(False, True)
        builder.do_env_setup.assert_not_called()
        builder.undo_env_setup.assert_not_called()

    def test_combined_action_uses_sdk_environment_setup(self):
        builder = mock.Mock()
        builder.is_build_enabled_on_current_os.return_value = True
        builder.app_cfg_base_name = "torch_2_14"
        args = self.make_args(clean=True, build=True)

        ret = do_therock(builder, args)

        self.assertTrue(ret)
        builder.do_env_setup.assert_called_once_with()
        builder.undo_env_setup.assert_called_once_with()
        builder.build.assert_called_once_with(False, True)


if __name__ == "__main__":
    unittest.main()
