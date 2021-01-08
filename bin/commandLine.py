import os
import sys
from bin.color import bcolor

class CommandLine:
    def __init__(self, optionInfoList):
        self.optionInfoList = optionInfoList

        self.optionList = [item for item in self.optionInfoList if type(item) is tuple]

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

                paramName = longParamList[argIndex][2:]
                self.userParams[paramName] = []
            elif paramName:
                self.userParams[paramName].append(arg)

    def showHelp(self):
        """Show the help menu."""
        longLength = len(max([item[1] for item in self.optionList], key=len))
        shortLength = 3

        def parseString(helpString, indentSize):
            """Convert a help string into a line-broken message for console output.

            Args:
                helpString (String): The string to parse.
                indentSize (int): The size of the indent for the column.

            Returns:
                (String): The broken string.
            """

            stringLength = self.consoleWidth - 1 - indentSize

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
            message (String): The message to display
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

    def hasParam(self, param):
        """Check if a param is specified in the command line.

        Returns:
            bool: Whether or not the param is specified.
        """

        return param in self.userParams.keys()

    def getParam(self, param):
        """Get the value of a specific parameter.

        Returns:
            list: The list of values for the parameter.
        """

        if param in self.userParams.keys():
            return self.userParams[param]
        else:
            return False
