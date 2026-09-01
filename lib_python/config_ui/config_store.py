"""Read and save RockBuilder wizard configuration."""

import configparser
from pathlib import Path

import lib_python.rcb_constants as rcb_const


class ConfigStore:
    """Persist wizard-owned sections while preserving unrelated sections."""

    def __init__(self, config_file=None, on_change=None):
        """Initialize storage with an optional path and change callback.

        Example:
            ConfigStore(Path("rockbuilder.cfg"), callback) creates a
            store and returns no value.
        """
        self.config_file = config_file
        self.on_change = on_change

    def load(self):
        """Load the configured file, or return an empty configuration.

        Example:
            load() reads rockbuilder.cfg and returns a ConfigParser.
        """
        ret = configparser.ConfigParser()
        config_path = self._get_config_path()
        if config_path.is_file():
            ret.read(config_path)
        return ret

    def save(self, selection_lists):
        """Save selected values and return the resulting configuration.

        Existing sections not represented by selection_lists are kept.
        Example:
            save([sdk_list, gpu_list]) writes both sections and returns
            the saved ConfigParser.
        """
        ret = self.load()
        existing_values = self._get_config_value_map(ret)

        for selection_list in selection_lists:
            config_value = selection_list.get_config_selections()
            section = config_value.header
            ret.remove_section(section)
            ret.add_section(section)
            for new_key, new_value in (
                config_value.selection_dict.items()
            ):
                ret[section][new_key] = str(new_value)

        config_path = self._get_config_path()
        with open(
            config_path,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as config_file:
            ret.write(config_file)

        new_values = self._get_config_value_map(ret)
        if existing_values != new_values and self.on_change:
            self.on_change()
        return ret

    def _get_config_path(self):
        """Return the explicit or default RockBuilder config path.

        Example:
            With config_file="custom.cfg", this returns
            Path("custom.cfg").
        """
        ret = self.config_file
        if ret is None:
            ret = rcb_const.get_rock_builder_config_file()
        ret = Path(ret)
        return ret

    def _get_config_value_map(self, config):
        """Return comparable values independent of section ordering.

        Example:
            For [build_targets] gpus=['gfx90a'], this returns a mapping
            containing {"build_targets": {"gpus": "['gfx90a']"}}.
        """
        ret = {
            section: dict(config.items(section))
            for section in config.sections()
        }
        return ret
