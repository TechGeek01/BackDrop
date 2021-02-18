import os

class Preferences:
    BOOLEAN = 'boolean'
    INTEGER = 'integer'
    FLOAT = 'float'
    HEXADECIMAL = 'hexadecimal'
    STRING = 'string'

    def __init__(self, filename):
        """Initialize a preference object.

        Args:
            filename: The filename and location of the preference file.
        """

        self.file = filename

        self.types = {
            'sourceDrive': Preferences.STRING,
            'darkMode': Preferences.BOOLEAN
        }

        self.prefs = self.__read()

    def __read(self):
        """Load preferences from the preference file.

        Returns:
            dict: The preferences object with parsed settings
        """

        newPrefs = {}

        if os.path.isfile(self.file):
            with open(self.file) as f:
                propList = self.types.keys()
                for line in f:
                    line = line.strip()
                    delim = line.find('=')
                    name = line[:delim]
                    value = line[delim + 1:]

                    if delim != -1 and name in propList and len(value) > 0:
                        newPrefs[name] = self.__convert(value, self.types[name])

        return newPrefs

    def __write(self):
        """Write preferences to the preference file."""

        prefsFile = open(self.file, 'w')

        for pref, value in self.prefs.items():
            prefsFile.write(f"{pref}={value}\n")

        prefsFile.close()

    def __convert(self, convertVal, typeString):
        """Convert a value to a specific type.

        Args:
            convertVal (String): The value to convert.
            typeString (String): The type to convert to.

        Returns:
            *: The converted value. None if not converted.
        """

        if typeString == Preferences.BOOLEAN:
            if type(convertVal) == str:
                falsyVals = ['', 'no', 'false', '0', 'none']
                return convertVal.lower() not in falsyVals
            else:
                return bool(convertVal)
        elif typeString == Preferences.INTEGER:
            return int(convertVal)
        elif typeString == Preferences.FLOAT:
            return float(convertVal)
        elif typeString == Preferences.HEXADECIMAL:
            return hex(int(convertVal))
        elif typeString == Preferences.STRING:
            return str(convertVal)

        return None

    def get(self, prefName, default=None, verifyData=None):
        """Get a preference value from the dict.

        Args:
            prefName (String): The name of the preference to select.
            default (*): The default value to set if preference can't be read.
            verifyData (*[], optional): A list of data to verify the read setting against. Defaults to None.
                If the setting is able to be read from the given file, and this list is
                defined, the default value will be used if the read setting isn't contained
                in the verifyData list.

        Returns:
            *: The value of the selected preference, if it exists.
            *: The specified default if the preference doesn't exist. (default: None)
        """

        if prefName in self.prefs.keys():
            setting = self.prefs[prefName]

            if type(verifyData) is list and setting not in verifyData:
                setting = default if default in verifyData else None

                # Preference has been changed from read value, so write changes
                self.set(prefName, setting)

            return setting
        else:
            # Preference doesn't exist, so write changes
            self.set(prefName, default)
            return default

    def set(self, prefName, prefVal):
        """Set a preference to a specific value.

        Args:
            prefName (String): The name of the preference to set.
            prefVal (*): The value to set the preference to.
        """

        if prefName in self.types.keys():
            self.prefs[prefName] = self.__convert(prefVal, self.types[prefName])

            self.__write()

    def show(self):
        """Show preferences."""
        return self.prefs
