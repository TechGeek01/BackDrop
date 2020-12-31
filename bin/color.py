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

    def __init__(self, darkMode=False):
        self.darkMode = darkMode

        if darkMode:
            Color.BG = '#282822'
            Color.FG = Color.WHITE
            Color.NORMAL = Color.WHITE

            Color.RED = '#f53'

            Color.INFO = '#a2f4ff'#'#12c4ff'

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
