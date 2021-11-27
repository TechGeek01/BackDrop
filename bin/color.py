import re

class Color:
    BLACK = '#000000'
    WHITE = '#ececec'
    BLUE = '#0093c4'
    GREEN = '#6db500'
    GOLD = '#ebb300'
    RED = '#cc0000'
    GRAY = '#666666'

    NORMAL = BLACK

    INFO = '#bbe6ff'
    TOOLTIP = '#008cbb'
    INFOTEXT = '#0095c7'
    INFOTEXTDARK = '#0095c7'
    WARNING = '#ffe69d'
    ERROR = '#ffd0d0'

    COLORACCENT = GREEN

    def combine_hex_color(self, rgb1, rgb2, ratio2: float):
        """Combine two hex colors with a ratio of the second.

        Args:
            rgb1 (String): The first hex color.
            rgb2 (String): The second hex color.
            ratio2 (float): The ratio of the second color.

        Returns:
            String: The new hex color.
        """

        color1 = re.search(r'([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})', rgb1).group(1, 2, 3)
        color2 = re.search(r'([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})', rgb2).group(1, 2, 3)

        # Convert hex string to int
        color1 = [int(x, 16) for x in color1]
        color2 = [int(x, 16) for x in color2]

        # Fancy math
        red = (color1[0] * (255 - ratio2 * 255) + color2[0] * ratio2 * 255) / 255
        green = (color1[1] * (255 - ratio2 * 255) + color2[1] * ratio2 * 255) / 255
        blue = (color1[2] * (255 - ratio2 * 255) + color2[2] * ratio2 * 255) / 255

        # Convert back to hex
        return '#' + hex(int(red))[-2:] + hex(int(green))[-2:] + hex(int(blue))[-2:]

    def __init__(self, root, dark_mode: bool = False):
        """Set the UI colors for the GUI.

        Args:
            root (Tk): The root tkinter window.
            dark_mode (bool): Whether or not the UI should be set to dark mode.
        """

        self.dark_mode = dark_mode

        Color.DEFAULT_BG = root.cget('background')

        if not dark_mode:
            Color.BG = root.winfo_rgb(root.cget('background'))
            r, g, b = [x >> 8 for x in Color.BG]
            Color.BG = '#{:02x}{:02x}{:02x}'.format(r, g, b)

            Color.FG = Color.BLACK
            Color.NORMAL = Color.BLACK

            Color.BGACCENT = self.combine_hex_color(Color.BG, Color.FG, 0.1)
            Color.BGACCENT2 = Color.WHITE
            Color.BGACCENT3 = self.combine_hex_color(Color.BG, Color.FG, 0.65)
        else:
            Color.BG = '#333333'
            Color.FG = Color.WHITE
            Color.NORMAL = Color.WHITE

            Color.BGACCENT = self.combine_hex_color(Color.BG, Color.FG, 0.1)
            Color.BGACCENT2 = self.combine_hex_color(Color.BG, Color.BLACK, 0.4)
            Color.BGACCENT3 = self.combine_hex_color(Color.BG, Color.FG, 0.65)

        Color.FADED = self.combine_hex_color(Color.BG, Color.FG, 0.45)

        Color.STATUS_BAR = self.combine_hex_color(Color.BG, Color.FG, 0.125)

        if dark_mode:
            Color.RED = '#f53'

            Color.INFO = '#3bceff'
            Color.TOOLTIP = '#3bceff'
            Color.INFOTEXT = '#00b2ee'

        Color.ENABLED = Color.GREEN
        Color.DISABLED = Color.RED

        Color.SUCCESS = Color.GREEN
        Color.FAILED = Color.RED

        Color.DANGER = Color.RED

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
