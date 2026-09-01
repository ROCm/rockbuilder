"""Common page, button, rendering, and input handling for the wizard."""

import curses
from dataclasses import dataclass
from enum import Enum


class NavigationAction(Enum):
    """Actions which can be returned by a configuration wizard page."""

    NONE = "none"
    BACK = "back"
    CANCEL = "cancel"
    FORWARD = "forward"
    SAVE = "save"


@dataclass(frozen=True)
class NavigationButton:
    """Describe one consistently rendered wizard navigation button."""

    label: str
    shortcut: str
    action: NavigationAction


class WizardPage:
    """Provide common selection, navigation, and rendering behavior."""

    def __init__(self, title, selection_list):
        """Initialize a page with its title and selection list.

        Example:
            WizardPage("Select GPUs", gpu_list) creates a page and returns
            no value.
        """
        self.title = title
        self.selection_list = selection_list
        self.item_cursor = 0
        self.first_visible_item = 0
        self.button_cursor = 0
        self.buttons_focused = False
        self.status_message = ""

    def get_buttons(self, page_index, page_count):
        """Return buttons appropriate for a page's wizard position.

        Example:
            get_buttons(0, 2) returns Cancel and Forward buttons.
        """
        ret_arr = []
        if page_index > 0:
            ret_arr.append(
                NavigationButton(
                    "Back",
                    "b",
                    NavigationAction.BACK,
                )
            )
        ret_arr.append(
            NavigationButton(
                "Cancel",
                "c",
                NavigationAction.CANCEL,
            )
        )
        if page_index == page_count - 1:
            ret_arr.append(
                NavigationButton(
                    "Save",
                    "s",
                    NavigationAction.SAVE,
                )
            )
        else:
            ret_arr.append(
                NavigationButton(
                    "Forward",
                    "f",
                    NavigationAction.FORWARD,
                )
            )
        return ret_arr

    def validate(self):
        """Return an error message, or None when this page is valid.

        Example:
            validate() returns None for a page with valid selections.
        """
        ret = None
        return ret

    def before_forward(self):
        """Prepare dependent state immediately before moving forward.

        Example:
            before_forward() may update the GPU list and returns None.
        """
        ret = None
        return ret

    def set_status_message(self, message):
        """Set the validation or navigation message shown on this page.

        Example:
            set_status_message("Select one GPU") displays that text and
            returns None.
        """
        self.status_message = message

    def handle_key(self, key, page_index, page_count):
        """Handle one key and return the requested navigation action.

        Example:
            handle_key(ord("f"), 0, 2) returns FORWARD.
        """
        ret = NavigationAction.NONE
        buttons = self.get_buttons(page_index, page_count)
        shortcut_action = self._get_shortcut_action(key, buttons)
        enter_keys = [curses.KEY_ENTER, 10, 13]
        back_tab = getattr(curses, "KEY_BTAB", 353)

        if shortcut_action is not NavigationAction.NONE:
            ret = shortcut_action
        elif key == 27:
            ret = NavigationAction.CANCEL
        elif key in [9, back_tab]:
            self.buttons_focused = not self.buttons_focused
        elif key == curses.KEY_UP:
            self._move_item_cursor(-1)
        elif key == curses.KEY_DOWN:
            self._move_item_cursor(1)
        elif key == curses.KEY_LEFT:
            self._move_button_cursor(-1, len(buttons))
        elif key == curses.KEY_RIGHT:
            self._move_button_cursor(1, len(buttons))
        elif key == ord(" "):
            if self.buttons_focused:
                ret = buttons[self.button_cursor].action
            else:
                self._toggle_current_item()
        elif key in enter_keys:
            if self.buttons_focused:
                ret = buttons[self.button_cursor].action
            else:
                self._focus_primary_button(buttons)
        return ret

    def render(self, screen, page_index, page_count):
        """Render this page, its viewport, buttons, and help text.

        Example:
            render(screen, 0, 2) draws page one of two and returns None.
        """
        screen.clear()
        height, width = screen.getmaxyx()
        buttons = self.get_buttons(page_index, page_count)
        self._normalize_cursors(len(buttons))
        visible_count = max(0, height - 5)
        self._adjust_viewport(visible_count)

        title = f"{self.title} ({page_index + 1}/{page_count})"
        self._safe_addstr(screen, 0, 0, title, width)
        self._render_items(screen, 2, visible_count, width)
        status_row = max(0, height - 3)
        button_row = max(0, height - 2)
        help_row = max(0, height - 1)
        self._safe_addstr(
            screen,
            status_row,
            0,
            self.status_message,
            width,
        )
        self._render_buttons(screen, button_row, width, buttons)
        help_text = (
            "Up/Down: select  Space: toggle  Enter: primary/activate  "
            "Tab: focus  Left/Right: button  C/F/B/S: action"
        )
        self._safe_addstr(screen, help_row, 0, help_text, width)
        screen.refresh()

    def _normalize_cursors(self, button_count):
        """Keep item and button cursors inside their current ranges.

        Example:
            With two items and item_cursor=5, this changes it to 1 and
            returns None.
        """
        item_count = self.selection_list.get_item_cnt()
        if item_count > 0:
            self.item_cursor = min(self.item_cursor, item_count - 1)
        else:
            self.item_cursor = 0
        if button_count > 0:
            self.button_cursor = min(
                self.button_cursor,
                button_count - 1,
            )
        else:
            self.button_cursor = 0

    def _move_item_cursor(self, direction):
        """Move the item cursor by a signed amount with wraparound.

        Example:
            _move_item_cursor(1) moves from item 0 to item 1 and returns
            None.
        """
        item_count = self.selection_list.get_item_cnt()
        self.buttons_focused = False
        if item_count > 0:
            self.item_cursor = (
                self.item_cursor + direction
            ) % item_count

    def _move_button_cursor(self, direction, button_count):
        """Focus buttons and move between them with wraparound.

        Example:
            _move_button_cursor(1, 2) moves to the next button and
            returns None.
        """
        self.buttons_focused = True
        if button_count > 0:
            self.button_cursor = (
                self.button_cursor + direction
            ) % button_count

    def _focus_primary_button(self, buttons):
        """Focus Forward or Save without changing the selected item.

        Example:
            On the first page, _focus_primary_button(buttons) focuses
            Forward and returns None.
        """
        primary_actions = [
            NavigationAction.FORWARD,
            NavigationAction.SAVE,
        ]
        self.buttons_focused = True
        for button_index, button in enumerate(buttons):
            if button.action in primary_actions:
                self.button_cursor = button_index
                break

    def _toggle_current_item(self):
        """Toggle or select the item at the current item cursor.

        Example:
            With item_cursor=0, _toggle_current_item() selects item zero
            and returns None.
        """
        item_count = self.selection_list.get_item_cnt()
        if item_count > 0:
            self.selection_list.toggle_item_selection(
                self.item_cursor
            )

    def _get_shortcut_action(self, key, buttons):
        """Return the action matching a button's letter shortcut.

        Example:
            With a Save button, _get_shortcut_action(ord("s"), buttons)
            returns SAVE.
        """
        ret = NavigationAction.NONE
        if 0 <= key <= 255:
            key_text = chr(key).lower()
            for button in buttons:
                if key_text == button.shortcut:
                    ret = button.action
                    break
        return ret

    def _adjust_viewport(self, visible_count):
        """Adjust the first visible item so the cursor remains visible.

        Example:
            With cursor 8 and five rows, the first visible item becomes
            4 and the method returns None.
        """
        if visible_count <= 0:
            self.first_visible_item = self.item_cursor
        elif self.item_cursor < self.first_visible_item:
            self.first_visible_item = self.item_cursor
        elif self.item_cursor >= (
            self.first_visible_item + visible_count
        ):
            self.first_visible_item = (
                self.item_cursor - visible_count + 1
            )

    def _render_items(self, screen, first_row, row_count, width):
        """Render the visible portion of this page's selection list.

        Example:
            _render_items(screen, 2, 5, 80) draws at most five items and
            returns None.
        """
        item_count = self.selection_list.get_item_cnt()
        last_item = min(
            item_count,
            self.first_visible_item + row_count,
        )
        for item_index in range(
            self.first_visible_item,
            last_item,
        ):
            item = self.selection_list.get_item(item_index)
            cursor_text = ">"
            if self.buttons_focused or item_index != self.item_cursor:
                cursor_text = " "
            selected_text = "X" if item.is_selected() else " "
            item_text = (
                f"{cursor_text} [{selected_text}] {item.get_name()}"
            )
            row = first_row + item_index - self.first_visible_item
            self._safe_addstr(screen, row, 0, item_text, width)

    def _render_buttons(self, screen, row, width, buttons):
        """Render all navigation buttons using one consistent style.

        Example:
            _render_buttons(screen, 20, 80, buttons) draws the buttons
            on row 20 and returns None.
        """
        button_text_arr = []
        for button_index, button in enumerate(buttons):
            button_text = f"[ {button.label} ]"
            if (
                self.buttons_focused
                and button_index == self.button_cursor
            ):
                button_text = f"> {button_text} <"
            button_text_arr.append(button_text)
        self._safe_addstr(
            screen,
            row,
            0,
            "  ".join(button_text_arr),
            width,
        )

    def _safe_addstr(self, screen, row, column, text, width):
        """Write clipped text while tolerating a very small terminal.

        Example:
            _safe_addstr(screen, 0, 0, "Title", 80) writes "Title" and
            returns None.
        """
        if width > column:
            clipped_text = text[:width - column]
            try:
                screen.addstr(row, column, clipped_text)
            except curses.error:
                pass
