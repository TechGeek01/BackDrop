import sys
import os
import wx
import clipboard

WINDOW_ELEMENT_PADDING = 16


class Color:
    BLACK = wx.Colour(0x00, 0x00, 0x00)
    WHITE = wx.Colour(0xec, 0xec, 0xec)
    BLUE = wx.Colour(0x00, 0x93, 0xc4)
    GREEN = wx.Colour(0x6d, 0xb5, 0x00)
    GOLD = wx.Colour(0xeb, 0xb3, 0x00)
    RED = wx.Colour(0xff, 0x55, 0x33)
    GRAY = wx.Colour(0x66, 0x66, 0x66)

    COLORACCENT = GREEN

    TEXT_DEFAULT = WHITE
    FADED = wx.Colour(0x8e, 0x8e, 0x8e)
    INFO = wx.Colour(0x3b, 0xce, 0xff)
    TOOLTIP = INFO
    WARNING = GOLD
    ERROR = RED

    ENABLED = GREEN
    DISABLED = RED

    SUCCESS = GREEN
    FAILED = RED

    DANGER = RED
    FINISHED = GREEN
    RUNNING = BLUE
    STOPPED = RED
    PENDING = FADED

    BACKGROUND = wx.Colour(0x2d, 0x2d, 0x2a)
    WIDGET_COLOR = wx.Colour(0x39, 0x39, 0x37)
    STATUS_BAR = wx.Colour(0x48, 0x48, 0x43)


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""

    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class RootWindow(wx.Frame):
    def __init__(self, parent=None, title: str = None, size: wx.Size = wx.Size(400, 200), name: str = None, icon: wx.Icon = None, *args, **kwargs):
        """Create a window.

        Args:
            parent: The parent of the resulting frame.
            title (String): The title of the window.
            size (wx.Size): The size of the window.
            name (String): The name to give the frame.
            icon (wx.Icon): The icon to apply to the window (optional).
        """

        self.parent = parent
        self.icon = icon

        wx.Frame.__init__(
            self,
            parent=parent,
            title=title,
            size=size,
            name=name,
            *args,
            **kwargs
        )

        if icon is not None:
            self.SetIcon(icon)

    def Panel(self, name: str = None, background: wx.Colour = None, foreground: wx.Colour = None):
        """Create the base wx.Panel for the Frame.

        Args:
            name (String): The name of the panel (optional).
            background (wx.Colour): The background color of the panel (optional).
            foreground (wx.Colour): The foreground color of the panel (optional).
        """

        self.root_panel = wx.Panel(self, name=name)

        if background is not None:
            self.root_panel.SetBackgroundColour(background)

        if foreground is not None:
            self.root_panel.SetForegroundColour(foreground)

        self.root_panel.Fit()
        self.SendSizeEvent()


class ModalWindow(RootWindow):
    def __init__(self, parent=None, title: str = None, size: wx.Size = wx.Size(400, 200), name: str = None, icon: wx.Icon = None, *args, **kwargs):
        """Create a modal window.

        Args:
            parent: The parent of the resulting frame.
            title (String): The title of the window.
            size (wx.Size): The size of the window.
            name (String): The name to give the frame.
            icon (wx.Icon): The icon to apply to the window (optional).
        """

        self.icon = icon

        RootWindow.__init__(
            self,
            parent=parent,
            title=title,
            size=size,
            name=name,
            icon=icon,
            *args,
            **kwargs
        )

        if icon is not None:
            self.SetIcon(icon)
        elif parent is not None and parent.icon is not None:  # If no icon is specified, inherit from parent if the parent has an icon
            self.SetIcon(parent.icon)

        self.Bind(wx.EVT_CLOSE, self.on_close)

    def on_close(self, event):
        self.parent.Enable()
        self.parent.Show()

        if event.CanVeto():
            event.Veto()
            self.Hide()
        else:
            self.Destroy()

    def ShowModal(self):
        """Show the modal."""

        self.parent.Disable()
        self.Show()


class ProgressBar(wx.Gauge):
    def __init__(self, parent, *args, **kwargs):
        """Create a progress bar.

        Args:
            parent: The parent of the progress bar.
        """

        self.value = 0
        self.max = None
        self.is_indeterminate = False

        wx.Gauge.__init__(self, parent, *args, **kwargs)

    def BindThreadManager(self, thread_manager):
        """Bind a ThreadManager instance to the progress bar.

        Args:
            thread_manager (ThreadManager): The ThreadManager to bind to.
        """

        self.__thread_manager = thread_manager

    def StartIndeterminate(self):
        """Start indeterminate mode."""

        # No need to start if this isn't the first progress thread
        if len(self.__thread_manager.get_progress_threads()) > 1:
            return

        # If progress bar is already in indeterminate mode, no need to set it
        if self.is_indeterminate:
            return

        self.value = self.GetValue()
        self.Pulse()
        self.is_indeterminate = True

    def StopIndeterminate(self):
        """Stop indeterminate mode."""

        # No need to stop if this isn't the only progress thread
        if len(self.__thread_manager.get_progress_threads()) > 1:
            return

        # If progress bar is already in determinate mode, no need to set it
        if not self.is_indeterminate:
            return

        self.is_indeterminate = False
        self.SetValue(self.value)


class WarningPanel(wx.Panel):
    def __init__(self, parent, *args, **kwargs):
        """Create an alert-like panel for warnings and errors."""

        wx.Panel.__init__(self, parent, *args, **kwargs)

        self.parent = parent

        # Set up box sizer for panel
        self.box = wx.BoxSizer()
        self.SetSizer(self.box)

        # Set up main sizer
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.box.Add((-1, -1), 1)
        self.box.Add(self.sizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 10)
        self.box.Add((-1, -1), 1)


class DetailBlock(wx.BoxSizer):
    TITLE = 'title'
    CONTENT = 'content'

    def __init__(self, parent, title: str, text_font: wx.Font, bold_font: wx.Font, enabled: bool = True):
        """Create an expandable detail block to display info.

        Args:
            parent: The parent widget.
            title (String): The bold title to display.
            text_font (wx.Font): The font to use for the text.
            bold_font (wx.Font): The font to use for the headings.
            enabled (bool): Whether or not this block is enabled.
        """

        wx.BoxSizer.__init__(self, orient=wx.VERTICAL)

        self.enabled = enabled
        self.parent = parent
        self.TEXT_FONT = text_font
        self.BOLD_FONT = bold_font
        self.expanded = False
        self.dark_mode = True  # FIXME: Get dark mode working with DetailBlock class
        self.right_arrow = wx.Bitmap(wx.Image(resource_path(f'assets/img/right_nav{"_light" if self.dark_mode else ""}.png'), wx.BITMAP_TYPE_ANY))
        self.down_arrow = wx.Bitmap(wx.Image(resource_path(f'assets/img/down_nav{"_light" if self.dark_mode else ""}.png'), wx.BITMAP_TYPE_ANY))

        self.lines = {}

        self.header_sizer = wx.BoxSizer()
        self.arrow = wx.StaticBitmap(self.parent, -1, self.right_arrow)
        self.header_sizer.Add(self.arrow, 0, wx.TOP, 3)
        self.header = wx.StaticText(self.parent, -1, label=title)
        self.header.SetFont(self.BOLD_FONT)
        self.header.SetForegroundColour(Color.TEXT_DEFAULT if self.enabled else Color.FADED)
        self.header_sizer.Add(self.header, 0, wx.LEFT, 5)
        self.Add(self.header_sizer, 0)

        self.content = wx.Panel(self.parent, name='DetailBlock content panel')
        self.content.Hide()
        self.content.SetForegroundColour(Color.TEXT_DEFAULT if self.enabled else Color.FADED)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        self.content.SetSizer(self.content_sizer)
        self.Add(self.content, 0)

        # Bind click for expanding and collapsing
        self.arrow.Bind(wx.EVT_LEFT_DOWN, lambda e: self.toggle())
        self.header.Bind(wx.EVT_LEFT_DOWN, lambda e: self.toggle())

    def toggle(self):
        """Toggle expanding content of a block."""

        if not self.expanded:
            # Collapsed turns into expanded
            self.expanded = True

            self.arrow.SetBitmap(self.down_arrow)
            self.content.Show()
            self.Layout()
            self.parent.Layout()
            self.parent.GetParent().Layout()
        else:
            # Expanded turns into collapsed
            self.expanded = False

            self.arrow.SetBitmap(self.right_arrow)
            self.content.Hide()
            self.Layout()
            self.parent.Layout()
            self.parent.GetParent().Layout()

    def add_line(self, line_name: str, title: str, content: str, clipboard_data: str = None, *args, **kwargs):
        """Add a line to the block content.

        Args:
            line_name (String): The name of the line for later reference.
            title (String): The line title.
            content (String): The content to display.
            clipboard_data (String): The clipboard data to copy when clicked (optional).
        """

        self.lines[line_name] = self.InfoLine(self.content, title, content, bold_font=self.BOLD_FONT, text_font=self.TEXT_FONT, clipboard_data=clipboard_data, *args, **kwargs)
        self.content_sizer.Add(self.lines[line_name], 0)
        self.lines[line_name].Layout()
        self.content_sizer.Layout()

    def SetForegroundColour(self, line_name: str, *args, **kwargs):
        """Set the foreground color of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.lines[line_name].SetForegroundColour(*args, **kwargs)

    def SetFont(self, line_name: str, *args, **kwargs):
        """Set the font of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.lines[line_name].SetFont(*args, **kwargs)

    def SetLabel(self, line_name: str, *args, **kwargs):
        """Set the label text of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.lines[line_name].SetLabel(*args, **kwargs)

    def Layout(self, line_name: str, *args, **kwargs):
        """Set the font of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.lines[line_name].Layout(*args, **kwargs)

    class InfoLine(wx.BoxSizer):
        def __init__(self, parent, title: str, content: str, bold_font: wx.Font, text_font: wx.Font, clipboard_data: str = None, *args, **kwargs):
            """Create an info line for use in DisplayBlock classes.

            Args:
                parent: The parent widget).
                title (String): The line title.
                content (String): The content to display.
                bold_font (wx.Font): The font to be used for the header.
                text_font (wx.Font): The font to be used for the text.
                clipboard_data (String): The data to copy to clipboard if line
                    is a copy line (default: None).
            """

            wx.BoxSizer.__init__(self)

            self.parent = parent
            self.BOLD_FONT = bold_font
            self.TEXT_FONT = text_font

            self.title = wx.StaticText(self.parent, -1, label=f"{title}:")
            self.title.SetFont(self.BOLD_FONT)
            self.Add(self.title, 0)

            if clipboard_data is not None and clipboard_data:
                self.tooltip = wx.StaticText(self.parent, -1, label='(Click to copy)')
                self.tooltip.SetFont(self.TEXT_FONT)
                self.tooltip.SetForegroundColour(Color.FADED)
                self.clipboard_data = clipboard_data
                self.Add(self.tooltip, 0, wx.LEFT, 5)

            self.content = wx.StaticText(self.parent, -1, label=content)
            self.content.SetFont(self.TEXT_FONT)
            self.Add(self.content, 0, wx.LEFT, 5)

            # Set up keyboard binding for copies
            if clipboard_data is not None and clipboard_data:
                self.title.Bind(wx.EVT_LEFT_DOWN, lambda e: clipboard.copy(self.clipboard_data))
                self.tooltip.Bind(wx.EVT_LEFT_DOWN, lambda e: clipboard.copy(self.clipboard_data))
                self.content.Bind(wx.EVT_LEFT_DOWN, lambda e: clipboard.copy(self.clipboard_data))

            self.Layout()

        def SetForegroundColour(self, *args, **kwargs):
            """Set the foreground color of the line."""

            self.title.SetForegroundColour(*args, **kwargs)

        def SetFont(self, *args, **kwargs):
            """Set the font of the line."""

            self.title.SetFont(*args, **kwargs)

        def SetLabel(self, *args, **kwargs):
            """Set the content label text of the line."""

            self.content.SetLabel(*args, **kwargs)

        def Layout(self, *args, **kwargs):
            """Update the layout of the line."""

            self.title.Layout(*args, **kwargs)
            self.content.Layout(*args, **kwargs)


class BackupDetailBlock(DetailBlock):
    def __init__(self, parent, title: str, text_font: wx.Font, bold_font: wx.Font, enabled: bool = True):
        """Create an expandable detail block to display info.

        Args:
            parent: The parent widget.
            title (String): The bold title to display.
            text_font (wx.Font): The font to use for the text.
            bold_font (wx.Font): The font to use for the headings.
            enabled (bool): Whether or not this block is enabled.
        """

        DetailBlock.__init__(self, parent, title, text_font, bold_font, enabled)

        self.state = wx.StaticText(self.parent, -1, label='Pending' if self.enabled else 'Skipped')
        self.state.SetForegroundColour(Color.PENDING if self.enabled else Color.FADED)
        self.header_sizer.Add(self.state, 0)
