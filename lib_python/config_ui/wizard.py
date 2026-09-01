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
        active_pages = self._get_active_pages()
        current_page = active_pages[0] if active_pages else None
        running = current_page is not None

        while running:
            active_pages = self._get_active_pages()
            if current_page not in active_pages:
                current_page = active_pages[0]
            page_index = active_pages.index(current_page)
            page_count = len(active_pages)
            page = current_page
            page.render(self.screen, page_index, page_count)
            key = self.screen.getch()
            page.set_status_message("")
            action = page.handle_key(key, page_index, page_count)

            if action is NavigationAction.BACK:
                current_page = active_pages[
                    max(0, page_index - 1)
                ]
            elif action is NavigationAction.CANCEL:
                running = False
            elif action is NavigationAction.FORWARD:
                error_message = page.validate()
                if error_message:
                    page.set_status_message(error_message)
                else:
                    page.before_forward()
                    active_pages = self._get_active_pages()
                    page_index = active_pages.index(page)
                    current_page = active_pages[
                        min(len(active_pages) - 1, page_index + 1)
                    ]
            elif action is NavigationAction.SAVE:
                invalid_page = self._get_invalid_page(active_pages)
                if invalid_page is None:
                    ret = self.save_callback()
                    running = False
                else:
                    current_page = invalid_page
                    error_message = invalid_page.validate()
                    invalid_page.set_status_message(error_message)
        return ret

    def _get_active_pages(self):
        """Return registered pages applicable to the current selections.

        Example:
            When XNACK is not selected, this omits the XNACK page.
        """
        ret_arr = [
            page
            for page in self.pages
            if page.is_applicable()
        ]
        return ret_arr

    def _get_invalid_page(self, pages):
        """Return the first invalid active page, or None when all are valid.

        Example:
            With an invalid GPU page, this returns that page object.
        """
        ret = None
        for page in pages:
            if page.validate():
                ret = page
                break
        return ret
