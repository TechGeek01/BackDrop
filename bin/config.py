from configparser import ConfigParser
import os
import re

class Config:
    BOOLEAN = 'boolean'
    INTEGER = 'integer'
    FLOAT = 'float'
    HEXADECIMAL = 'hexadecimal'
    STRING = 'string'

    TYPES = [BOOLEAN, INTEGER, FLOAT, HEXADECIMAL, STRING]

    def __init__(self, filename):
        """Initialize a preference object.

        Args:
            filename: The filename and location of the preference file.
        """

        self.filename = re.sub(r'\\', '/', filename)
        self.config = ConfigParser()

        # Make sure destination path exists before copying
        if self.filename.find('/') > -1:
            path_stub = self.filename[0:self.filename.rindex('/')]
        else:
            path_stub = self.filename
        if not os.path.exists(path_stub):
            os.makedirs(path_stub)

        self.config.read(filename)

    def get(self, section_name, pref_name, default=None, verify_data=None, data_type=None):
        """Get a preference value from the dict.

        Args:
            section_name (String): The name of the section to read.
            pref_name (String): The name of the preference to select.
            default (*): The default value to set if preference can't be read.
            verify_data (*[], optional): A list of data to verify the read setting against. Defaults to None.
                If the setting is able to be read from the given file, and this list is
                defined, the default value will be used if the read setting isn't contained
                in the verify_data list.\
            data_type (String): The type of data to convert to if not using a string.

        Returns:
            *: The value of the selected preference, if it exists.
            *: The specified default if the preference doesn't exist. (default: None)
        """

        if section_name in self.config:
            if pref_name in self.config[section_name]:

                # Convert data type if requested
                if data_type == Config.BOOLEAN:
                    setting = self.config[section_name].getboolean(pref_name)
                elif data_type == Config.INTEGER:
                    setting = int(self.config[section_name][pref_name])
                elif data_type == Config.FLOAT:
                    setting = float(self.config[section_name][pref_name])
                elif data_type == Config.HEXADECIMAL:
                    setting = hex(int(self.config[section_name][pref_name]))
                else:
                    setting = self.config[section_name][pref_name]

                if type(verify_data) is list and setting not in verify_data:
                    setting = default if default in verify_data else None

                    # Setting has been changed from read value, so write changes
                    self.config.set(section_name, pref_name, str(setting))

                return setting

        # If preference not found, return default
        return default

    def set(self, section_name, pref_name, pref_val):
        """Set a preference to a specific value.

        Args:
            section_name (String): The name of the section to set.
            pref_name (String): The name of the preference to set.
            pref_val (*): The value to set the preference to.
        """

        # Create section if it doesn't exist
        if section_name not in self.config:
            self.config.add_section(section_name)

        self.config.set(section_name, pref_name, str(pref_val))

        # Write changes to file
        with open(self.filename, 'w') as config_file:
            self.config.write(config_file)

    def show(self):
        """Show config."""

        return self.config
