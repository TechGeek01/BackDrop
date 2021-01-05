class Color:
    BLACK = '#000'
    WHITE = '#ececec'
    FADED = '#999'
    BLUE = '#0093c4'
    GREEN = '#6db500'
    GOLD = '#ebb300'
    RED = '#c00'
    GRAY = '#666'

    NORMAL = BLACK

    INFO = '#bbe6ff'
    WARNING = '#ffe69d'
    ERROR = '#ffd0d0'

    BG = None
    FG = BLACK

    BGACCENT = '#e9e9e9'
    BGACCENT2 = '#fff'
    BGACCENT3 = '#888'
    COLORACCENT = GREEN

    def __init__(self, root, darkMode=False):
        self.darkMode = darkMode

        Color.BG = root.cget('background')

        if darkMode:
            Color.BG = '#282822'
            Color.BG = '#333'
            Color.FG = Color.WHITE
            Color.NORMAL = Color.WHITE

            Color.BGACCENT = '#282828'
            Color.BGACCENT = '#444'
            Color.BGACCENT2 = '#222'
            Color.BGACCENT3 = '#aaa'

            Color.RED = '#f53'

            Color.INFO = '#a2f4ff'

        Color.ENABLED = Color.GREEN
        Color.DISABLED = Color.RED

        Color.FINISHED = Color.GREEN
        Color.RUNNING = Color.BLUE
        Color.STOPPED = Color.RED
        Color.PENDING = Color.FADED

    def isDarkMode(self):
        """Check whether the color pallete is set to dark mode or not.

        Returns:
            bool: Whether the pallete is set to dark mode.
        """
        return self.darkMode

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
