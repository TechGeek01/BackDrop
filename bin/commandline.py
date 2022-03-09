from bin.color import bcolor

class CommandLine:
    def __init__(self):
        """Configure and parse the command line options.
        """
        pass

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
