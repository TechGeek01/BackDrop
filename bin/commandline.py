import os
import sys

from bin.color import bcolor

class CommandLine:
    def __init__(self, option_info_list: tuple):
        """Configure and parse the command line options.

        Args:
            option_info_list (list): A list of parameters to configure.
            option_info_list.item (String): An information string to show in the
                help menu.
            option_info_list.item (tuple): A tuple containing the short and long
                parameters names, and the description for the help menu.
        """

        self.option_info_list = option_info_list
        self.option_list = [item for item in self.option_info_list if type(item) is tuple]

        self.CONSOLE_WIDTH = os.get_terminal_size().columns

        param_list_long = [param[1] for param in self.option_list]
        param_list_short = [param[0] for param in self.option_list]

        self.user_params = {}
        param_name = False
        for arg in sys.argv[1:]:
            if arg in param_list_long or arg in param_list_short:
                if arg in param_list_long:
                    arg_index = param_list_long.index(arg)
                else:
                    arg_index = param_list_short.index(arg)

                param_name = param_list_long[arg_index][2:]
                self.user_params[param_name] = []
            elif param_name:
                self.user_params[param_name].append(arg)

    def show_help(self):
        """Show the help menu."""

        length_long = len(max([item[1] for item in self.option_list], key=len))
        length_short = 3

        def parse_string(help_string, indent_size: int):
            """Convert a help string into a line-broken message for console output.

            Args:
                help_string (String): The string to parse.
                indent_size (int): The size of the indent for the column.

            Returns:
                (String): The broken string.
            """

            string_length = self.CONSOLE_WIDTH - 1 - indent_size

            remaining_string = help_string
            string_parts = []
            while len(remaining_string) > 0:
                working_string = remaining_string[:string_length]

                if len(remaining_string) > string_length:
                    if remaining_string[string_length:string_length + 1] == ' ':
                        # If string_length breaks at space, remove space from next string
                        string_parts.append(working_string)
                        remaining_string = remaining_string[string_length + 1:]
                    else:
                        # string_length doesn't break on space, so break at last space before it
                        string_space = working_string.rindex(' ')
                        working_string = remaining_string[:string_space]

                        string_parts.append(working_string)
                        remaining_string = remaining_string[string_space + 1:]
                else:
                    string_parts.append(working_string)
                    remaining_string = remaining_string[string_length:]

            return f"\n{' ' * indent_size}".join(string_parts)

        for param in self.option_info_list:
            if type(param) is tuple:
                display_short_option = param[0] + ',' if type(param[0]) is str else ''
                print(f"{display_short_option: <{length_short}} {param[1]: <{length_long}}    {parse_string(param[3], length_long + length_short + 5)}")
            else:
                print(param)

    def validate_yes_no(self, message, default: bool) -> bool:
        """Validate a yes/no answer input.

        Args:
            message (String): The message to display.
            default (bool): Whether the default should be yes.

        Returns:
            bool: Whether or not yes has been selected.
        """

        default_string = '(Y/n)' if default else '(y/N)'

        user_input = False

        while user_input not in ['y', 'n', 'yes', 'no', '']:
            user_input = input(f"{bcolor.OKCYAN}{message} {default_string}{bcolor.ENDC} ").lower()

            if user_input not in ['y', 'n', 'yes', 'no', '']:
                print('Please enter either Yes or No')

        if user_input in ['y', 'n', 'yes', 'no']:
            return user_input in ['y', 'yes']
        else:
            return default

    def validate_choice(self, message, choices: list, default, case_sensitive: bool = False, chars_required: int = None):
        """Validate a yes/no answer input.

        Args:
            message (String): The message to display.
            choices (String[]): The list of options to verify against.
            default (String): The option to default to.
            case_sensitive (bool): Whether or not the input is case sensitive (default False).
            chars_required (int): How many characters required if not requiring an exact
                    match (Defaults to None).

        Returns:
            String: The selected option.
        """

        default_string = f" ({default})" if default is not None else ''

        if type(chars_required) is int:
            full_choices = [choice[:chars_required] for choice in choices]
        else:
            full_choices = [choice for choice in choices]

        if not case_sensitive:
            full_choices = [choice.lower() for choice in full_choices]

        full_choices.append('')
        user_input = False
        while user_input not in full_choices:
            user_input = input(f"{bcolor.OKCYAN}{message}{default_string}{bcolor.ENDC} ")
            if not case_sensitive:
                user_input = user_input.lower()
            if type(chars_required) is int:
                user_input = user_input[:chars_required]

            if user_input not in full_choices:
                print('Please choose an option from the list')

        if user_input in full_choices and user_input != '':
            return choices[full_choices.index(user_input)]
        else:
            return default

    def validate_choice_list(self, message, choices: list, default, case_sensitive: bool = False, chars_required: int = None):
        """Validate a yes/no answer input.

        Args:
            message (String): The message to display.
            choices (String[]): The list of options to verify against.
            default (String): The option to default to.
            case_sensitive (bool): Whether or not the input is case sensitive (default False).
            chars_required (int): How many characters required if not requiring an exact
                    match (Defaults to None).

        Returns:
            String: The selected option.
        """

        default_string = f" ({default})" if default is not None else ''

        if type(chars_required) is int:
            full_choices = [choice[:chars_required] for choice in choices]
        else:
            full_choices = [choice for choice in choices]

        if not case_sensitive:
            full_choices = [choice.lower() for choice in full_choices]

        input_valid = False
        while not input_valid:
            user_input = input(f"{bcolor.OKCYAN}{message}{default_string}{bcolor.ENDC} ")
            if not case_sensitive:
                user_input = user_input.lower()

            user_input = user_input.split(' ')
            if type(chars_required) is int:
                user_input = [entry[:chars_required] for entry in user_input]

            input_valid = False not in [option in full_choices for option in user_input]
            if not input_valid:
                print('Please choose options from the list')

        return [choices[full_choices.index(option)] for option in user_input]

    def has_param(self, param) -> bool:
        """Check if a param is specified in the command line.

        Args:
            param (String): The param to check.

        Returns:
            bool: Whether or not the param is specified.
        """

        return param in self.user_params.keys()

    def get_param(self, param) -> list:
        """Get the value of a specific parameter.

        Args:
            param (String): The param to get.

        Returns:
            list: The list of values for the parameter.
        """

        if param in self.user_params.keys():
            return self.user_params[param]
        else:
            return False
