import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib_python.rcb_constants as rcb_const
import rockbuilder


class SdkVerificationTest(unittest.TestCase):
    def write_app_config(self, root, name, uses_sdk):
        apps_dir = root / "apps"
        apps_dir.mkdir(exist_ok=True)
        config_path = apps_dir / f"{name}.cfg"
        lines = [
            "[app_info]",
            f"APP_NAME={name}",
        ]
        if uses_sdk is not None:
            value = "YES" if uses_sdk else "NO"
            lines.append(f"PROP_IS_ROCM_SDK_USED={value}")
        config_path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        ret = config_path
        return ret

    def test_direct_therock_build_does_not_require_sdk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = self.write_app_config(
                root,
                "therock_dev",
                False,
            )

            ret = rockbuilder.is_rocm_sdk_required(
                root,
                [config_path],
            )

        self.assertFalse(ret)

    def test_missing_sdk_property_defaults_to_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_app_config(root, "example", None)

            ret = rockbuilder.is_rocm_sdk_required(
                root,
                ["example"],
            )

        self.assertTrue(ret)

    def test_mixed_application_list_requires_sdk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_app_config(root, "sdk_builder", False)
            self.write_app_config(root, "sdk_consumer", True)

            ret = rockbuilder.is_rocm_sdk_required(
                root,
                ["sdk_builder", "sdk_consumer"],
            )

        self.assertTrue(ret)

    def test_direct_therock_build_uses_configured_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = self.write_app_config(
                root,
                "therock_dev",
                False,
            )
            config_reader = mock.Mock()
            config_reader.get_therock_sanitizer.return_value = "NONE"
            config_reader.get_configured_gpu_list_str.return_value = (
                "gfx90a:xnack+;gfx1100"
            )
            app_manager = mock.Mock()
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(
                    rockbuilder,
                    "_check_distro_specific_environment_variables",
                ),
                mock.patch.object(
                    rockbuilder,
                    "_check_cpu_count_env_variable",
                ),
                mock.patch.object(
                    rockbuilder,
                    "verify_rocm_sdk_install",
                ) as verify_sdk,
            ):
                rockbuilder.prepare_build_environment(
                    config_reader,
                    app_manager,
                    root,
                    [config_path],
                )
                targets = os.environ[
                    rcb_const.RCB__ENV_VAR__AMDGPU_TARGETS
                ]
                base_targets = os.environ[
                    rcb_const.RCB__ENV_VAR__AMDGPU_BASE_TARGETS
                ]
                sanitizer = os.environ[
                    rcb_const.RCB__ENV_VAR__THEROCK_SANITIZER
                ]

        verify_sdk.assert_not_called()
        self.assertEqual(targets, "gfx90a:xnack+;gfx1100")
        self.assertEqual(base_targets, "gfx90a;gfx1100")
        self.assertEqual(sanitizer, "NONE")

    def test_sdk_consumer_verifies_sdk_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = self.write_app_config(
                root,
                "sdk_consumer",
                True,
            )
            config_reader = mock.Mock()
            config_reader.get_therock_sanitizer.return_value = "NONE"
            app_manager = mock.Mock()

            def set_verified_targets(*unused_arguments):
                os.environ[
                    rcb_const.RCB__ENV_VAR__AMDGPU_TARGETS
                ] = "gfx1100"

            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(
                    rockbuilder,
                    "_check_distro_specific_environment_variables",
                ),
                mock.patch.object(
                    rockbuilder,
                    "_check_cpu_count_env_variable",
                ),
                mock.patch.object(
                    rockbuilder,
                    "verify_rocm_sdk_install",
                    side_effect=set_verified_targets,
                ) as verify_sdk,
            ):
                rockbuilder.prepare_build_environment(
                    config_reader,
                    app_manager,
                    root,
                    [config_path],
                )
                base_targets = os.environ[
                    rcb_const.RCB__ENV_VAR__AMDGPU_BASE_TARGETS
                ]

        verify_sdk.assert_called_once_with(
            config_reader,
            app_manager,
            root,
        )
        self.assertEqual(base_targets, "gfx1100")


if __name__ == "__main__":
    unittest.main()
