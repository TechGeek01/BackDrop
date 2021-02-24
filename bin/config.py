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
            pathStub = self.filename[0:self.filename.rindex('/')]
        else:
            pathStub = self.filename
        if not os.path.exists(pathStub):
            os.makedirs(pathStub)

        self.config.read(filename)

    def get(self, sectionName, prefName, default=None, verifyData=None, dataType=None):
        """Get a preference value from the dict.

        Args:
            sectionName (String): The name of the section to read.
            prefName (String): The name of the preference to select.
            default (*): The default value to set if preference can't be read.
            verifyData (*[], optional): A list of data to verify the read setting against. Defaults to None.
                If the setting is able to be read from the given file, and this list is
                defined, the default value will be used if the read setting isn't contained
                in the verifyData list.\
            dataType (String): The type of data to convert to if not using a string.

        Returns:
            *: The value of the selected preference, if it exists.
            *: The specified default if the preference doesn't exist. (default: None)
        """

        if sectionName in self.config:
            if prefName in self.config[sectionName]:

                # Convert data type if requested
                if dataType == Config.BOOLEAN:
                    setting = self.config[sectionName].getboolean(prefName)
                elif dataType == Config.INTEGER:
                    setting = int(self.config[sectionName][prefName])
                elif dataType == Config.FLOAT:
                    setting = float(self.config[sectionName][prefName])
                elif dataType == Config.HEXADECIMAL:
                    setting = hex(int(self.config[sectionName][prefName]))
                else:
                    setting = self.config[sectionName][prefName]

                if type(verifyData) is list and setting not in verifyData:
                    setting = default if default in verifyData else None

                    # Setting has been changed from read value, so write changes
                    self.config.set(sectionName, prefName, str(setting))

                return setting

        # If preference not found, return default
        return default

    def set(self, sectionName, prefName, prefVal):
        """Set a preference to a specific value.

        Args:
            sectionName (String): The name of the section to set.
            prefName (String): The name of the preference to set.
            prefVal (*): The value to set the preference to.
        """

        # Create section if it doesn't exist
        if sectionName not in self.config:
            self.config.add_section(sectionName)

        self.config.set(sectionName, prefName, str(prefVal))

        # Write changes to file
        with open(self.filename, 'w') as configFile:
            self.config.write(configFile)

    def show(self):
        """Show config."""

        return self.config
