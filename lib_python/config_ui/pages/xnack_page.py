"""XNACK mode selection page for capable GPU architectures."""

from lib_python.config_ui.page import WizardPage


class XnackDisplayItem:
    """Expose one GPU's XNACK mode through the common page renderer."""

    def __init__(self, gpu_list, base_target):
        """Initialize a display item for one selected base target.

        Example:
            XnackDisplayItem(gpu_list, "gfx90a") creates a mode row and
            returns no value.
        """
        self.gpu_list = gpu_list
        self.base_target = base_target

    def get_name(self):
        """Return the base target and currently selected XNACK mode.

        Example:
            For plain gfx90a, get_name() returns "gfx90a: Plain".
        """
        mode = self.gpu_list.get_xnack_mode(self.base_target)
        ret = (
            f"{self.base_target}: {mode.get_display_name()}"
        )
        return ret

    def is_selected(self):
        """Return True because every row represents a selected GPU.

        Example:
            is_selected() returns True for a visible gfx90a mode row.
        """
        ret = True
        return ret


class XnackModeSelectionList:
    """Adapt selected XNACK-capable GPUs to the common list interface."""

    def __init__(self, gpu_list):
        """Initialize the adapter around the main GPU selection list.

        Example:
            XnackModeSelectionList(gpu_list) creates a live mode list and
            returns no value.
        """
        self.title = "Select XNACK Mode for Capable GPUs"
        self.gpu_list = gpu_list

    def get_item_cnt(self):
        """Return the number of selected XNACK-capable targets.

        Example:
            With gfx90a and gfx942 selected, get_item_cnt() returns 2.
        """
        ret = len(self.gpu_list.get_selected_xnack_targets())
        return ret

    def get_item(self, item_index):
        """Return a display item for one selected capable target.

        Example:
            get_item(0) returns the display item for the first target.
        """
        base_targets = self.gpu_list.get_selected_xnack_targets()
        ret = XnackDisplayItem(
            self.gpu_list,
            base_targets[item_index],
        )
        return ret

    def toggle_item_selection(self, item_index):
        """Advance one target to its next XNACK mode.

        Example:
            For plain gfx90a, toggle_item_selection(0) selects XNACK-
            and returns None.
        """
        base_targets = self.gpu_list.get_selected_xnack_targets()
        self.gpu_list.cycle_xnack_mode(
            base_targets[item_index]
        )


class XnackSelectionPage(WizardPage):
    """Configure XNACK modes independently for all capable targets."""

    def __init__(self, gpu_list, is_enabled):
        """Initialize the XNACK page and its applicability callback.

        Example:
            XnackSelectionPage(gpu_list, callback) creates the page and
            returns no value.
        """
        selection_list = XnackModeSelectionList(gpu_list)
        super().__init__(selection_list.title, selection_list)
        self.gpu_list = gpu_list
        self.is_enabled = is_enabled

    def is_applicable(self):
        """Return whether XNACK choices apply to current GPU selections.

        Example:
            With local gfx90a selected, is_applicable() returns True.
        """
        ret = (
            self.is_enabled()
            and bool(self.gpu_list.get_selected_xnack_targets())
        )
        return ret

    def validate(self):
        """Return an error for an infeasible restored target combination.

        Example:
            A restored plain-plus-XNACK+ combination returns an error.
        """
        ret = None
        invalid_targets = self.gpu_list.get_invalid_xnack_targets()
        if invalid_targets:
            target_names = ", ".join(invalid_targets)
            ret = (
                "Choose one XNACK mode for: "
                + target_names
            )
        return ret

    def get_help_text(self):
        """Return keyboard instructions for cycling XNACK modes.

        Example:
            get_help_text() describes Space as the mode-cycle key.
        """
        ret = (
            "Up/Down: target  Space: next mode  "
            "Enter: primary/activate  Tab: focus  "
            "Left/Right: button  C/F/B/S: action"
        )
        return ret
