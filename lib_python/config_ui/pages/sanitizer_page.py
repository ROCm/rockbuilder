"""TheRock sanitizer build-mode selection page."""

from lib_python.config_ui.build_options import SanitizerMode
from lib_python.config_ui.build_options import XnackMode
from lib_python.config_ui.page import WizardPage


class SanitizerSelectionPage(WizardPage):
    """Select and validate normal, host ASAN, or combined ASAN builds."""

    def __init__(self, selection_list, gpu_list, is_enabled):
        """Initialize the sanitizer page and its applicability callback.

        Example:
            SanitizerSelectionPage(options, gpus, callback) creates the
            page and returns no value.
        """
        super().__init__(selection_list.title, selection_list)
        self.gpu_list = gpu_list
        self.is_enabled = is_enabled

    def is_applicable(self):
        """Return whether the selected SDK will be built by RockBuilder.

        Example:
            For the therock_dev SDK option, is_applicable() returns True.
        """
        ret = self.is_enabled()
        return ret

    def get_sanitizer_mode(self):
        """Return the sanitizer mode currently selected by the user.

        Example:
            When Host ASAN is selected, this returns HOST_ASAN.
        """
        selected_item = self.selection_list.get_selected_item()
        ret = SanitizerMode.NONE
        if selected_item is not None:
            ret = SanitizerMode(selected_item.get_value())
        return ret

    def validate(self):
        """Return an error when device ASAN conflicts with GPU targets.

        Example:
            Combined ASAN with only gfx1100 returns a capability error.
        """
        ret = None
        if self.get_sanitizer_mode() is SanitizerMode.ASAN:
            capable_targets = (
                self.gpu_list.get_selected_asan_targets()
            )
            incompatible_targets = []
            for base_target in capable_targets:
                mode = self.gpu_list.get_xnack_mode(base_target)
                if mode in [XnackMode.MINUS, XnackMode.BOTH]:
                    incompatible_targets.append(base_target)
            if not capable_targets:
                ret = (
                    "Device ASAN requires gfx906, gfx90a, gfx942, "
                    "or gfx950. Use Host ASAN for other GPUs."
                )
            elif incompatible_targets:
                target_names = ", ".join(incompatible_targets)
                ret = (
                    "Device ASAN requires Plain or XNACK+ for: "
                    + target_names
                )
        return ret
