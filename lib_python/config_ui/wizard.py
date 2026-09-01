"""Ordered page execution for the RockBuilder configuration wizard."""

from lib_python.config_ui.page import NavigationAction


class Wizard:
    """Run registered pages and coordinate navigation and final saving."""

    def __init__(self, screen, pages, save_callback):
        """Initialize a wizard with its screen, pages, and save callback.

        Example:
            Wizard(screen, [sdk_page, gpu_page], save_config) creates a
            two-page wizard and returns no value.
        """
        self.screen = screen
        self.pages = pages
        self.save_callback = save_callback

    def run(self):
        """Run pages in registration order and return saved configuration.

        Example:
            run() returns a ConfigParser after Save, or None after
            Cancel.
        """
        ret = None
        page_index = 0
        running = bool(self.pages)

        while running:
            page_count = len(self.pages)
            page = self.pages[page_index]
            page.render(self.screen, page_index, page_count)
            key = self.screen.getch()
            page.set_status_message("")
            action = page.handle_key(key, page_index, page_count)

            if action is NavigationAction.BACK:
                page_index = max(0, page_index - 1)
            elif action is NavigationAction.CANCEL:
                running = False
            elif action is NavigationAction.FORWARD:
                error_message = page.validate()
                if error_message:
                    page.set_status_message(error_message)
                else:
                    page.before_forward()
                    page_index = min(
                        page_count - 1,
                        page_index + 1,
                    )
            elif action is NavigationAction.SAVE:
                invalid_page_index = self._get_invalid_page_index()
                if invalid_page_index is None:
                    ret = self.save_callback()
                    running = False
                else:
                    page_index = invalid_page_index
                    invalid_page = self.pages[page_index]
                    error_message = invalid_page.validate()
                    invalid_page.set_status_message(error_message)
        return ret

    def _get_invalid_page_index(self):
        """Return the first invalid page index, or None when all are valid.

        Example:
            With a valid SDK page and invalid GPU page, this returns 1.
        """
        ret = None
        for page_index, page in enumerate(self.pages):
            if page.validate():
                ret = page_index
                break
        return ret
