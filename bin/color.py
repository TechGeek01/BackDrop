import platform

class Color:
    BLACK = '#000'
    WHITE = '#ececec'
    BLUE = '#0093c4'
    GREEN = '#6db500'
    GOLD = '#ebb300'
    RED = '#c00'
    GRAY = '#666'

    NORMAL = BLACK

    INFO = '#bbe6ff'
    INFOTEXT = '#0095c7'
    INFOTEXTDARK = '#0095c7'
    WARNING = '#ffe69d'
    ERROR = '#ffd0d0'

    BG = None
    FG = BLACK

    if platform.system() == 'Windows':
        FADED = '#999'
        STATUS_BAR = '#d4d4d4'
    elif platform.system() == 'Linux':
        FADED = '#888'
        STATUS_BAR = '#c4c4c4'

    BGACCENT = '#e9e9e9'
    BGACCENT2 = '#fff'
    BGACCENT3 = '#888'
    COLORACCENT = GREEN

    def __init__(self, root, dark_mode=False):
        """Set the UI colors for the GUI.

        Args:
            root (Tk): The root tkinter window.
            dark_mode (bool): Whether or not the UI should be set to dark mode.
        """

        self.dark_mode = dark_mode

        Color.BG = root.cget('background')

        if dark_mode:
            Color.BG = '#333'
            Color.FG = Color.WHITE
            Color.NORMAL = Color.WHITE

            Color.STATUS_BAR = '#4a4a4a'

            Color.BGACCENT = '#444'
            Color.BGACCENT2 = '#222'
            Color.BGACCENT3 = '#aaa'

            Color.RED = '#f53'

            Color.INFO = '#3bceff'
            Color.INFOTEXT = '#00b2ee'

        Color.ENABLED = Color.GREEN
        Color.DISABLED = Color.RED

        Color.FINISHED = Color.GREEN
        Color.RUNNING = Color.BLUE
        Color.STOPPED = Color.RED
        Color.PENDING = Color.FADED

    def is_dark_mode(self):
        """Check whether the color pallete is set to dark mode or not.

        Returns:
            bool: Whether the pallete is set to dark mode.
        """

        return self.dark_mode

class bcolor:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
