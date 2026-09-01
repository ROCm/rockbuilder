"""ROCm SDK selection page for the configuration wizard."""

from lib_python.config_ui.page import WizardPage


class SdkSelectionPage(WizardPage):
    """Select one ROCm SDK and prepare GPU choices for the next page."""

    def __init__(self, selection_list, prepare_gpu_list):
        """Initialize the SDK page and its GPU-list preparation callback.

        Example:
            SdkSelectionPage(sdk_list, configure_gpus) creates the page
            and returns no value.
        """
        super().__init__(selection_list.title, selection_list)
        self.prepare_gpu_list = prepare_gpu_list

    def validate(self):
        """Return an error unless exactly one SDK is selected.

        Example:
            With TheRock 10.0 selected, validate() returns None.
        """
        ret = None
        if self.selection_list.get_selected_item() is None:
            ret = "Select one ROCm SDK before moving forward."
        return ret

    def before_forward(self):
        """Configure compatible GPU choices before opening the GPU page.

        Example:
            With a wheel SDK selected, before_forward() enables the wheel
            GPU list and returns None.
        """
        selected_item = self.selection_list.get_selected_item()
        self.prepare_gpu_list(selected_item)
        ret = None
        return ret
