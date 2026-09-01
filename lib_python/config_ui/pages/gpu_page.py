"""GPU target selection page for the configuration wizard."""

from lib_python.config_ui.page import WizardPage


class GpuSelectionPage(WizardPage):
    """Select one or more GPU targets supported by the chosen SDK."""

    def __init__(self, selection_list):
        """Initialize the GPU page with its compatible target list.

        Example:
            GpuSelectionPage(gpu_list) creates the page and returns no
            value.
        """
        super().__init__(selection_list.title, selection_list)

    def validate(self):
        """Return an error unless at least one GPU target is selected.

        Example:
            With gfx90a selected, validate() returns None.
        """
        ret = None
        if self.selection_list.get_selected_item() is None:
            ret = "Select at least one GPU target before saving."
        return ret
