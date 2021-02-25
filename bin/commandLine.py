import os
import sys

from bin.color import bcolor

class CommandLine:
    def __init__(self, optionInfoList):
        self.optionInfoList = optionInfoList

        self.CONSOLE_WIDTH = os.get_terminal_size().columns

        longParamList = [param[1] for param in self.optionList]
        shortParamList = [param[0] for param in self.optionList]

        self.consoleWidth = os.get_terminal_size().columns

        self.userParams = {}
        paramName = False
        for arg in sys.argv[1:]:
            if arg in longParamList or arg in shortParamList:
                if arg in longParamList:
                    argIndex = longParamList.index(arg)
                else:
                    argIndex = shortParamList.index(arg)

                param_name = param_list_long[argIndex][2:]
                self.__user_params[param_name] = []
            elif param_name:
                self.__user_params[param_name].append(arg)

    def showHelp(self):
        """Show the help menu."""

        length_long = len(max([item[1] for item in self.__option_list], key=len))
        length_short = 3

        def parseString(helpString, indentSize):
            """Convert a help string into a line-broken message for console output.

            Args:
                helpString (String): The string to parse.
                indentSize (int): The size of the indent for the column.

            Returns:
                (String): The broken string.
            """

            stringLength = self.CONSOLE_WIDTH - 1 - indentSize

            remainingString = helpString
            stringParts = []
            while len(remainingString) > 0:
                workingString = remainingString[:stringLength]

                if len(remainingString) > stringLength:
                    if remainingString[stringLength:stringLength + 1] == ' ':
                        # If stringLength breaks at space, remove space from next string
                        stringParts.append(workingString)
                        remainingString = remainingString[stringLength + 1:]
                    else:
                        # stringLength doesn't break on space, so break at last space before it
                        stringSpace = workingString.rindex(' ')
                        workingString = remainingString[:stringSpace]

                        stringParts.append(workingString)
                        remainingString = remainingString[stringSpace + 1:]
                else:
                    stringParts.append(workingString)
                    remainingString = remainingString[stringLength:]

            return f"\n{' ' * indentSize}".join(stringParts)

        for param in self.optionInfoList:
            if type(param) is tuple:
                displayShortOption = param[0] + ',' if type(param[0]) is str else ''
                print(f"{displayShortOption: <{shortLength}} {param[1]: <{longLength}}    {parseString(param[3], longLength + shortLength + 5)}")
            else:
                print(param)

    def validateYesNo(self, message, default):
        """Validate a yes/no answer input.

        Args:
            message (String): The message to display.
            default (bool): Whether the default should be yes.

        Returns:
            bool: Whether or not yes has been selected.
        """

        defaultString = '(Y/n)' if default else '(y/N)'

        userInput = False

        while userInput not in ['y', 'n', 'yes', 'no', '']:
            userInput = input(f"{bcolor.OKCYAN}{message} {defaultString}{bcolor.ENDC} ").lower()

            if userInput not in ['y', 'n', 'yes', 'no', '']:
                print('Please enter either Yes or No')

        if userInput in ['y', 'n', 'yes', 'no']:
            return userInput in ['y', 'yes']
        else:
            return default

    def validateChoice(self, message, choices, default, caseSensitive=False, charsRequired=None):
        """Validate a yes/no answer input.

        Args:
            message (String): The message to display.
            choices (String[]): The list of options to verify against.
            default (String): The option to default to.
            caseSenstive (bool): Whether or not the input is case sensitive (default False).
            charsRequired (int): How many characters required if not requiring an exact
                    match (Defaults to None).

        Returns:
            String: The selected option.
        """

        defaultString = f" ({default})" if default is not None else ''

        if type(charsRequired) is int:
            fullChoices = [choice[:charsRequired] for choice in choices]
        else:
            fullChoices = [choice for choice in choices]

        if not caseSensitive:
            fullChoices = [choice.lower() for choice in fullChoices]

        fullChoices.append('')
        userInput = False
        while userInput not in fullChoices:
            userInput = input(f"{bcolor.OKCYAN}{message}{defaultString}{bcolor.ENDC} ")
            if not caseSensitive:
                userInput = userInput.lower()
            if type(charsRequired) is int:
                userInput = userInput[:charsRequired]

            if userInput not in fullChoices:
                print('Please choose an option from the list')

        if userInput in fullChoices and userInput != '':
            return choices[fullChoices.index(userInput)]
        else:
            return default

    def validateChoiceList(self, message, choices, default, caseSensitive=False, charsRequired=None):
        """Validate a yes/no answer input.

        Args:
            message (String): The message to display.
            choices (String[]): The list of options to verify against.
            default (String): The option to default to.
            caseSensitive (bool): Whether or not the input is case sensitive (default False).
            charsRequired (int): How many characters required if not requiring an exact
                    match (Defaults to None).

        Returns:
            String: The selected option.
        """

        defaultString = f" ({default})" if default is not None else ''

        if type(charsRequired) is int:
            fullChoices = [choice[:charsRequired] for choice in choices]
        else:
            fullChoices = [choice for choice in choices]

        if not caseSensitive:
            fullChoices = [choice.lower() for choice in fullChoices]

        inputValid = False
        while not inputValid:
            userInput = input(f"{bcolor.OKCYAN}{message}{defaultString}{bcolor.ENDC} ")
            if not caseSensitive:
                userInput = userInput.lower()

            userInput = userInput.split(' ')
            if type(charsRequired) is int:
                userInput = [entry[:charsRequired] for entry in userInput]

            inputValid = False not in [option in fullChoices for option in userInput]
            if not inputValid:
                print('Please choose options from the list')

        return [choices[fullChoices.index(option)] for option in userInput]

    def hasParam(self, param):
        """Check if a param is specified in the command line.

        Args:
            param (String): The param to check.

        Returns:
            bool: Whether or not the param is specified.
        """

        return param in self.userParams.keys()

    def getParam(self, param):
        """Get the value of a specific parameter.

        Args:
            param (String): The param to get.

        Returns:
            list: The list of values for the parameter.
        """

        if param in self.userParams.keys():
            return self.userParams[param]
        else:
            return False
