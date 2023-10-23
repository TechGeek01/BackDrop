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
    LIGHT_RED = wx.Colour(0xff, 0x55, 0x33)
    RED = wx.Colour(0xcc, 0x00, 0x00)
    GRAY = wx.Colour(0x66, 0x66, 0x66)

    BRAND_COLOR = wx.Colour(0x9e, 0xcf, 0x00)
    COLORACCENT = GREEN

    TEXT_DEFAULT = WHITE
    FADED = wx.Colour(0x8e, 0x8e, 0x8e)
    INFO = wx.Colour(0x00, 0xb4, 0xd8)
    TOOLTIP = INFO
    WARNING = GOLD
    ERROR = LIGHT_RED

    ENABLED = GREEN
    DISABLED = LIGHT_RED

    SUCCESS = GREEN
    FAILED = LIGHT_RED

    DANGER = LIGHT_RED
    FINISHED = GREEN
    RUNNING = BLUE
    STOPPED = LIGHT_RED
    PENDING = FADED

    BACKGROUND = wx.Colour(0x2d, 0x2d, 0x2a)
    WIDGET_COLOR = wx.Colour(0x39, 0x39, 0x37)
    PROGRESS_BAR_BG_COLOR = wx.Colour(0x44, 0x44, 0x42)
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
    def __init__(self, parent=None, title: str = None, size: wx.Size = wx.Size(400, 200), min_size: wx.Size = None, name: str = None, icon: wx.Icon = None, *args, **kwargs):
        """Create a window.

        Args:
            parent: The parent of the resulting frame.
            title (String): The title of the window.
            size (wx.Size): The size of the window.
            min_size (wx.Size): The minimum size of the window (optional).
            name (String): The name to give the frame (optonal).
            icon (wx.Icon): The icon to apply to the window (optional).
        """

        if min_size is None:
            min_size = size
        if name is None:
            name = 'RootWindow'

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
        self.SetMinSize(min_size)

        if icon is not None:
            self.SetIcon(icon)

    def Panel(self, name: str = None, background: wx.Colour = None, foreground: wx.Colour = None):
        """Create the base wx.Panel for the Frame.

        Args:
            name (String): The name of the panel (optional).
            background (wx.Colour): The background color of the panel (optional).
            foreground (wx.Colour): The foreground color of the panel (optional).
        """

        if name is None:
            name = 'Panel'

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
            parent: The parent widget.
            title (String): The title of the window.
            size (wx.Size): The size of the window.
            name (String): The name to give the frame.
            icon (wx.Icon): The icon to apply to the window (optional).
        """

        if name is None:
            name = 'ModalWindow'

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


class StatusBar(wx.Panel):
    SELECTION = 1
    ACTION = 2
    ERROR = 4
    PORTABLE_MODE = 8
    UPDATES = 16

    ALL = SELECTION | ACTION | ERROR | UPDATES

    def __init__(self, parent=None, height: int = None, padding: int = None, flags: int = None, name: str = None, *args, **kwargs):
        """Create a status bar.

        Args:
            parent: The parent widget.
            height (int): The height of the progress bar (default: 20).
            padding (int): The padding between items (default: 8).
            flags (int): The flags for styling the status bar (default: all).
            name (str): The name to give the widgets (optional).
        """

        if height is None:
            height = 20
        if padding is None:
            padding = 8
        if flags is None:
            flags = StatusBar.ALL
        if name is None:
            name = 'StatusBar'

        self.parent = parent
        self.height = height
        self.padding = padding
        self.flags = flags
        self.name = name

        wx.Panel.__init__(self, parent, size=(-1, self.height), name=self.name, *args, **kwargs)
        self.SetForegroundColour(parent.GetForegroundColour())
        self.SetBackgroundColour(parent.GetBackgroundColour())

        self._box = wx.BoxSizer()

        if self.flags & StatusBar.SELECTION:
            self._selection_label = wx.StaticText(self, -1, label='', name=f'{self.name} selection')
            self._box.Add(self._selection_label, 0, wx.LEFT | wx.RIGHT, self.padding)
        if self.flags & StatusBar.ACTION:
            self._action_label = wx.StaticText(self, -1, label='', name=f'{self.name} action')
            self._box.Add(self._action_label, 0, wx.LEFT | wx.RIGHT, self.padding)
        if self.flags & StatusBar.ERROR:
            self._error_counter_label = wx.StaticText(self, -1, label='', name=f'{self.name} error count')
            self._box.Add(self._error_counter_label, 0, wx.LEFT | wx.RIGHT, self.padding)

        self._box.Add((-1, -1), 1, wx.EXPAND)

        if self.flags & StatusBar.PORTABLE_MODE:
            self._portable_mode_label = wx.StaticText(self, -1, label='Portable mode')
            self._box.Add(self._portable_mode_label, 0, wx.LEFT | wx.RIGHT, self.padding)
        if self.flags & StatusBar.UPDATES:
            self._update_label = wx.StaticText(self, -1, label='Up to date', name=f'{self.name} update indicator')
            self._box.Add(self._update_label, 0, wx.LEFT | wx.RIGHT, self.padding)

        self._outer_box = wx.BoxSizer(wx.VERTICAL)
        self._outer_box.Add((-1, -1), 1, wx.EXPAND)
        self._outer_box.Add(self._box, 0, wx.EXPAND)
        self._outer_box.Add((-1, -1), 1, wx.EXPAND)
        self.SetSizer(self._outer_box)

    def SetSelectionLabel(self, label: str):
        """Set the label for the selection.

        Args:
            label (str): The label to set.
        """

        if self.flags & StatusBar.SELECTION:
            self._selection_label.SetLabel(label=label)
            self._selection_label.Layout()
            self.Layout()

    def SetSelectionForegroundColour(self, color: wx.Colour):
        """Set the label for the selection.

        Args:
            color (wx.Colour): The color to set the text to.
        """

        if self.flags & StatusBar.SELECTION:
            self._selection_label.SetForegroundColour(color)
            self._selection_label.Layout()

    def SetActionLabel(self, label: str):
        """Set the label for the action.

        Args:
            label (str): The label to set.
        """

        if self.flags & StatusBar.ACTION:
            self._action_label.SetLabel(label=label)
            self._action_label.Layout()
            self.Layout()

    def SetActionForegroundColour(self, color: wx.Colour):
        """Set the label for the action.

        Args:
            color (wx.Colour): The color to set the text to.
        """

        if self.flags & StatusBar.ACTION:
            self._action_label.SetForegroundColour(color)
            self._action_label.Layout()

    def SetErrorCount(self, count: int = None):
        """Set the label for the error counter.

        Args:
            count (int): The error count to set.
        """

        if count is None:
            count = 0

        if self.flags & StatusBar.ERROR:
            self._error_counter_label.SetLabel(label=f'{count} failed')
            if count > 0:
                self._error_counter_label.SetForegroundColour(Color.DANGER)
            else:
                self._error_counter_label.SetForegroundColour(Color.FADED)
            self._error_counter_label.Layout()
            self.Layout()

    def SetUpdateLabel(self, label: str):
        """Set the label for the update indicator.

        Args:
            label (str): The label to set.
        """

        if self.flags & StatusBar.UPDATES:
            self._update_label.SetLabel(label=label)
            self._update_label.Layout()
            self.Layout()

    def SetUpdateForegroundColour(self, color: wx.Colour):
        """Set the label for the update indicator.

        Args:
            color (wx.Colour): The color to set the text to.
        """

        if self.flags & StatusBar.UPDATES:
            self._update_label.SetForegroundColour(color)
            self._update_label.Layout()


class FancyProgressBar(wx.Panel):
    def __init__(self, parent=None, value: int = None, max_val: int = None, height: int = None, color: wx.Colour = None, name: str = None, *args, **kwargs):
        """Create a progress bar.

        Args:
            parent: The parent widget.
            value (int): The value to set the progress to (optional).
            max_val (int): The max value of the progress bar (optional).
            height (int): The height of the progress bar (optional).
            color (wx.Colour): The color of the progress bar (optional).
            name (String): The name of the widget (optional).
        """

        if value is None:
            value = 0
        if max_val is None:
            max_val = 10000
        if height is None:
            height = 6
        if color is None:
            color = Color.BRAND_COLOR
        if name is None:
            name = 'FancyProgressBar'

        self.parent = parent
        self.value = value
        self.range = max_val
        self.height = height
        self.color = color
        self._indeterminate = False
        self._indeterminate_width = 100
        self._indeterminate_pos = 0
        self._indeterminate_step = 4

        self._progress_threads = 0

        wx.Panel.__init__(self, parent, size=(-1, self.height), name=name, *args, **kwargs)

        self.SetBackgroundColour(Color.PROGRESS_BAR_BG_COLOR)

        self._timer = wx.Timer(self)

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_TIMER, self.update_indeterminate)

    def on_paint(self, event):
        dc = wx.BufferedPaintDC(self)
        self.draw(dc)

    def draw(self, dc):
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()

        if not self._indeterminate:
            if self.range > 0:
                progress_width = int(self.GetSize().GetWidth() * self.value / self.range)
            else:
                progress_width = 0

            if progress_width > 0:
                dc.SetBrush(wx.Brush(self.color))
                dc.DrawRectangle(0, 0, progress_width, self.height)
        else:
            dc.SetBrush(wx.Brush(self.color))
            dc.DrawRectangle(self._indeterminate_pos, 0, self._indeterminate_width, self.height)

    def update_indeterminate(self, event):
        self._indeterminate_pos += self._indeterminate_step

        # If bar is all the way to the right, change direction
        if self._indeterminate_pos + self._indeterminate_width >= self.GetSize().GetWidth():
            self._indeterminate_pos = self.GetSize().GetWidth() - self._indeterminate_width
            self._indeterminate_step = -4

        # If bar is all the way to the left, change direction
        if self._indeterminate_pos <= 0:
            self._indeterminate_pos = 0
            self._indeterminate_step = 4

        self.Refresh()

    def StartIndeterminate(self):
        """Start indeterminate mode."""

        self._progress_threads += 1

        # No need to start if this isn't the first progress thread
        if self._progress_threads > 1:
            return

        # If progress bar is already in indeterminate mode, no need to set it
        if self._indeterminate:
            return

        self._timer.Start(1)
        self._indeterminate = True

    def StopIndeterminate(self):
        """Stop indeterminate mode."""

        self._progress_threads -= 1

        # No need to stop if this isn't the only progress thread
        if self._progress_threads > 1:
            return

        # If progress bar is already in determinate mode, no need to set it
        if not self._indeterminate:
            return

        self._indeterminate = False
        self._timer.Stop()
        self.Refresh()

    def SetRange(self, value):
        """Set the max value of the progress bar.

        Args:
            value (int): The maximum value to use.
        """

        self.range = value
        self.Refresh()

    def SetValue(self, value):
        """Set the current value of the progress bar.

        Args:
            value (int): The value to use.
        """

        self.value = value
        self.Refresh()

    def SetForegroundColour(self, value):
        """Set the color of the progress bar.

        Args:
            value (int): The value to use.
        """

        self.color = value


class ProgressBar(wx.Gauge):
    MAX_RANGE = 10000

    def __init__(self, parent, name: str = None, *args, **kwargs):
        """Create a progress bar.

        Args:
            parent: The parent widget.
            name (String): The name of the widget (optional).
        """

        if name is None:
            name = 'ProgressBar'

        self.value = 0
        self.range = None
        self.is_indeterminate = False

        self._progress_threads = 0

        wx.Gauge.__init__(self, parent, name=name, *args, **kwargs)

    def StartIndeterminate(self):
        """Start indeterminate mode."""

        self._progress_threads += 1

        # No need to start if this isn't the first progress thread
        if self._progress_threads > 1:
            return

        # If progress bar is already in indeterminate mode, no need to set it
        if self.is_indeterminate:
            return

        self.value = self.GetValue()
        self.Pulse()
        self.is_indeterminate = True

    def StopIndeterminate(self):
        """Stop indeterminate mode."""

        self._progress_threads -= 1

        # No need to stop if this isn't the only progress thread
        if self._progress_threads > 1:
            return

        # If progress bar is already in determinate mode, no need to set it
        if not self.is_indeterminate:
            return

        self.is_indeterminate = False
        self.SetValue(self.value)

    def SetRange(self, value):
        """Set the max value of the progress bar.

        Args:
            value (int): The maximum value to use.
        """

        self.range = value

        wx.Gauge.SetRange(self, ProgressBar.MAX_RANGE)

    def SetValue(self, value):
        """Set the current value of the progress bar.

        Args:
            value (int): The value to use.
        """

        self.value = value
        wx.Gauge.SetValue(self, int(ProgressBar.MAX_RANGE * value / self.range))


class WarningPanel(wx.Panel):
    def __init__(self, parent, name: str = None, *args, **kwargs):
        """Create an alert-like panel for warnings and errors.

        Args:
            parent: The parent widget.
            name (String): The name of the widget (optional).
        """

        if name is None:
            name = 'WarningPanel'

        wx.Panel.__init__(self, parent, name=name, *args, **kwargs)

        self.parent = parent

        # Set up box sizer for panel
        self.box = wx.BoxSizer()
        self.SetSizer(self.box)

        # Set up main sizer
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.box.Add((-1, -1), 1)
        self.box.Add(self.sizer, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 10)
        self.box.Add((-1, -1), 1)


class InlineLabel(wx.BoxSizer):
    def __init__(self, parent, label: str, value: str, color=None, value_color=None, name: str = None, *args, **kwargs):
        """Create an inline label with both a label and content.

        Args:
            parent: The parent widget.
            label (String): The label text to display.
            value (String): The value text for the label.
            color (wx.Colour): The color for the label (optional).
            value_color (wx.Colour): The color for the value (optional).
            name (String): The name to use for the StaticText items (optional).
        """

        if color is None:
            color = Color.TEXT_DEFAULT
        if value_color is None:
            value_color = Color.TEXT_DEFAULT
        if name is None:
            name = 'InlineLabel'

        wx.BoxSizer.__init__(self, *args, **kwargs)

        self.parent = parent

        self.color = color
        self.value_color = value_color

        self.label = wx.StaticText(self.parent, -1, label=f'{label}: ', name=f'{name} label')
        self.value = wx.StaticText(self.parent, -1, label=value, name=f'{name} value')
        self.Add(self.label, 0, wx.ALIGN_CENTER_VERTICAL)
        self.Add(self.value, 0, wx.ALIGN_CENTER_VERTICAL)
        self.label.SetForegroundColour(self.color)
        self.value.SetForegroundColour(self.value_color)

    def SetLabel(self, label: str):
        """Set the label for the value of the InlineLabel.

        Args:
            label (String): The label to set.
        """

        self.value.SetLabel(label=label)
        self.value.Layout()
        self.Layout()
        self.parent.Layout()

    def SetForegroundColour(self, color: str):
        """Set the color for the value of the InlineLabel.

        Args:
            color (String): The color to set.
        """

        self.value.SetForegroundColour(color)


class Counter(wx.BoxSizer):
    def __init__(self, parent, value: int = None, name: str = None, *args, **kwargs):
        """Create a counter to track numbers.

        Args:
            parent: The parent widget.
            value (int): The iniitial value to set (optional).
            name (String): The name to use for the StaticText items (optional).
        """

        if value is None:
            value = 0
        if name is None:
            name = 'Counter'

        wx.BoxSizer.__init__(self, *args, **kwargs)

        self.parent = parent

        self._value = value
        self._label = wx.StaticText(self.parent, -1, label=str(value), name=f'{name} label')
        self.Add(self._label, 0)

    def SetLabel(self, text):
        """Set the label of the counter.

        Args:
            text (str): The label to set.
        """

        self._label.SetLabel(text)

        self._label.Layout()
        self.Layout()

    def AddCount(self, count):
        """Add a count to the value of the counter.

        Args:
            count (int): The count to add to the value.
        """

        self._value += count
        self.SetLabel(str(self._value))

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.SetLabel(str(value))

    def SetFont(self, *args, **kwargs):
        self._label.SetFont(*args, **kwargs)
        self._label.Layout()
        self.Layout()

    def SetForegroundColour(self, *args, **kwargs):
        self._label.SetForegroundColour(*args, **kwargs)

    def Bind(self, *args, **kwargs):
        self._label.Bind(*args, **kwargs)


class SelectionListCtrl(wx.ListCtrl):
    def __init__(self, parent, id, load_fn, name: str = None, *args, **kwargs):
        """Create a ListCtrl for file selection.

        Args:
            id (int): The ID for the ListCtrl widget.
            load_fn (def): The function to call when loading data.
            name (String): The name of the ListCtrl (optional).
        """

        if name is None:
            name = 'SelectionListCtrl'

        wx.ListCtrl.__init__(self, parent, id, name=name, *args, **kwargs)

        self._load_fn = load_fn

        self.loading = False
        self.locked = False

        self.SetBackgroundColour(Color.WIDGET_COLOR)
        self.SetTextColour(Color.WHITE)

    def load(self, *args, **kwargs):
        """Load data to populate the SelectionListCtrl."""

        # Don't load if already loading
        if self.loading:
            return

        self.loading = True
        self._load_fn(*args, **kwargs)
        self.loading = False

    def Lock(self):
        """Lock the ListCtrl from being changed."""

        self.locked = True

    def Unlock(self):
        """Unlock the ListCtrl to allow changes."""

        self.locked = False


class CopyListPanel(wx.Panel):
    def __init__(self, parent, label, name: str = None, *args, **kwargs):
        """Create a scrollable list block with a header and click-to-copy.

        Args:
            label (str): The label for the header.
            name (str): The name for the CopyListBlock item (optional).
        """

        if name is None:
            name = 'CopyListPanel'

        wx.Panel.__init__(self, parent, *args, **kwargs)

        self.parent = parent
        self.list = []

        # Set up box sizer for panel
        self._box = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self._box)
        self.SetForegroundColour(self.parent.GetForegroundColour())

        self._header_sizer = wx.BoxSizer()
        self._header_text = wx.StaticText(self, -1, label=f'{label} ', name=f'{name} header')
        self._header_copy_text = wx.StaticText(self, -1, label='(click to copy)', name=f'{name} click to copy text')
        self._header_copy_text.SetForegroundColour(Color.FADED)
        self._counter = Counter(self, name=f'{name} counter')
        self._header_sizer.Add(self._header_text, 0, wx.ALIGN_BOTTOM)
        self._header_sizer.Add(self._header_copy_text, 0, wx.ALIGN_BOTTOM | wx.BOTTOM, 1)
        self._header_sizer.Add((-1, -1), 1, wx.EXPAND)
        self._header_sizer.Add(self._counter, 0, wx.ALIGN_BOTTOM)

        self._list_panel = wx.ScrolledWindow(self, -1, style=wx.VSCROLL, name=f'{name} scrollable panel')
        self._list_panel.SetScrollbars(20, 20, 50, 50)
        self._list_panel.SetForegroundColour(Color.TEXT_DEFAULT)

        self._list_panel_box = wx.BoxSizer(wx.VERTICAL)
        self._list_panel.SetSizer(self._list_panel_box)

        self._box.Add(self._header_sizer, 0, wx.EXPAND)
        self._box.Add(self._list_panel, 1, wx.EXPAND)

        # Mouse click bindings
        self._header_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join(self.list)))
        self._header_copy_text.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join(self.list)))
        self._counter.Bind(wx.EVT_LEFT_DOWN, lambda event: clipboard.copy('\n'.join(self.list)))

    def AddItems(self, items, color=None, *args, **kwargs):
        """Add one or more items to the panel.

        Args:
            items (list): The items to add.
            color (wx.Colour): The text color to use (optional).
        """

        self.list.append(items)

        file_label = wx.StaticText(self._list_panel, -1, label='\n'.join(items))
        if color is not None:
            file_label.SetForegroundColour(color)

        self._list_panel_box.Add(file_label, 0)
        self._list_panel.Layout()

        self._counter.AddCount(len(items))
        self.Layout()

    @property
    def count(self):
        return self._counter.value

    def SetLabel(self, label, *args, **kwargs):
        """Set the label for the header."""

        self._header_text.SetLabel(label=label, *args, **kwargs)
        self._header_text.Layout()
        self.Layout()

    def SetHeaderFont(self, font, *args, **kwargs):
        """Set the font for the header lines."""

        self._header_text.SetFont(font, *args, **kwargs)
        self._header_text.Layout()
        self._counter.SetFont(font, *args, **kwargs)
        self.Layout()

    def Clear(self, *args, **kwargs):
        """Clear the panel."""

        self.list = []
        self._counter.value = 0
        self._list_panel_box.Clear(True)
        self.Layout()


class DetailBlock(wx.BoxSizer):
    TITLE = 'title'
    CONTENT = 'content'

    def __init__(self, parent, title: str, text_font: wx.Font, bold_font: wx.Font, enabled: bool = True, name: str = None):
        """Create an expandable detail block to display info.

        Args:
            parent: The parent widget.
            title (String): The bold title to display.
            text_font (wx.Font): The font to use for the text.
            bold_font (wx.Font): The font to use for the headings.
            enabled (bool): Whether or not this block is enabled.
            name (String): The name of the widget (optional).
        """

        if name is None:
            name = 'DetailBlock'

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
        self.header_sizer.Add(self.arrow, 0, wx.TOP, 2)
        self.header = wx.StaticText(self.parent, -1, label=title, name=f'{name} header text')
        self.header.SetFont(self.BOLD_FONT)
        self.header.SetForegroundColour(Color.TEXT_DEFAULT if self.enabled else Color.FADED)
        self.header_sizer.Add(self.header, 0, wx.LEFT, 5)
        self.Add(self.header_sizer, 0)

        self.content = wx.Panel(self.parent, name=f'{name} content panel')
        self.content.Hide()
        self.content.SetForegroundColour(Color.TEXT_DEFAULT if self.enabled else Color.FADED)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        self.content.SetSizer(self.content_sizer)
        self.Add(self.content, 1, wx.EXPAND | wx.LEFT, 15)

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
            self.content_sizer.Layout()
            self.Layout()

    def SetLabel(self, line_name: str, label: str):
        """Set the label text of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.lines[line_name].SetLabel(label=label)
            self.content_sizer.Layout()
            self.Layout()

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
            self.content.SetForegroundColour(*args, **kwargs)

        def SetFont(self, *args, **kwargs):
            """Set the font of the line."""

            self.title.SetFont(*args, **kwargs)
            self.title.Layout()
            self.Layout()

        def SetLabel(self, label: str):
            """Set the content label text of the line."""

            self.content.SetLabel(label=label)
            self.content.Layout()
            self.Layout()


class BackupDetailBlock(DetailBlock):
    def __init__(self, parent, title: str, text_font: wx.Font, bold_font: wx.Font, name: str = None, enabled: bool = True):
        """Create an expandable detail block to display info.

        Args:
            parent: The parent widget.
            title (String): The bold title to display.
            text_font (wx.Font): The font to use for the text.
            bold_font (wx.Font): The font to use for the headings.
            name (String): The name of the widget (optional).
            enabled (bool): Whether or not this block is enabled (optional).
        """

        if name is None:
            name = 'BackupDetailBlock'

        # FIXME: Clicking on the state doesn't toggle the content. Rewriting the toggle function should fix this.
        DetailBlock.__init__(self, parent, title, text_font, bold_font, enabled, name=name)

        self.state = wx.StaticText(self.parent, -1, label='Pending' if self.enabled else 'Skipped', name=f'{name} state text')
        self.state.SetForegroundColour(Color.PENDING if self.enabled else Color.FADED)
        self.header_sizer.Add(self.state, 0, wx.LEFT, 5)
