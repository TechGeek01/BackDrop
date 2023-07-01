import wx
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sys
import os
import ctypes
import clipboard
import time

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

    BACKGROUND = wx.Colour(0x33, 0x33, 0x33)
    STATUS_BAR = wx.Colour(0x4a, 0x4a, 0x4a)

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""

    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class RootWindow(wx.Frame):
    def __init__(self, parent = None, title: str = None, size: wx.Size = wx.Size(400, 200), name: str = None, *args, **kwargs):
        """Create a window.

        Args:
            parent: The parent of the resulting frame.
            title (String): The title of the window.
            size (wx.Size): The size of the window.
            name (String): The name to give the frame.
        """

        self.parent = parent

        wx.Frame.__init__(
            self,
            parent=parent,
            title=title,
            size=size,
            name=name,
            *args,
            **kwargs
        )

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
    def __init__(self, parent = None, title: str = None, size: wx.Size = wx.Size(400, 200), name: str = None, *args, **kwargs):
        """Create a modal window.

        Args:
            parent: The parent of the resulting frame.
            title (String): The title of the window.
            size (wx.Size): The size of the window.
            name (String): The name to give the frame.
        """

        RootWindow.__init__(
            self,
            parent=parent,
            title=title,
            size=size,
            name=name,
            *args,
            **kwargs
        )

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

class ScrollableFrame(tk.Frame):
    def __init__(self, parent, scrollbar=None, *args, **kwargs):
        """Create a scrollable frame widget.

        Args:
            parent (tk.*): The parent widget of the resulting frame.
            scrollbar (tk.Scrollbar): An existing scrollbar to bind
                (default: None). If not specified, a scrollbar to the right
                of the frame will be created.
        """

        tk.Frame.__init__(self, parent)
        self.pack_propagate(0)

        self.canvas = tk.Canvas(self, *args, **kwargs)
        if scrollbar is None:
            self.vsb = tk.Scrollbar(self, orient='vertical', command=self.yview)
        else:
            self.vsb = scrollbar
            self.vsb.configure(command=self.yview)

        self.frame = ttk.Frame(self.canvas)
        self.frame.bind('<Configure>', lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox('all')
        ))

        self.canvas.create_window((0, 0), window=self.frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side='left', fill='both', expand=1)
        if scrollbar is None:
            self.vsb.pack(side='left', fill='y')

        self.canvas.bind('<Enter>', self._bind_on_enter)
        self.canvas.bind('<Leave>', self._unbind_on_leave)

    def yview(self, *args):
        if self.canvas.yview() == (0.0, 1.0):
            return
        self.canvas.yview(*args)

    def _on_mousewheel(self, event):
        if self.canvas.yview() == (0.0, 1.0):
            return
        self.canvas.yview_scroll(int(-1 * event.delta / 120), 'units')

    def _bind_on_enter(self, event):
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)

    def _unbind_on_leave(self, event):
        # HACK: ScrollableFrame unbind_all will cause problems if mousewheel is bound to anything else
        self.unbind_all('<MouseWheel>')

    def configure(self, *args, **kwargs):
        self.frame.configure(*args, **kwargs)

    def show_items(self, limit=None):
        """Scroll to the bottom of the frame, and truncate items.

        Args:
            limit (int): If specified, the number of items to truncate to (default: None).
        """

        if limit is not None and isinstance(limit, int):
            [widget.destroy() for widget in self.frame.winfo_children()[:-limit]]

        time.sleep(0.01)
        self.canvas.yview_moveto(1)

    def empty(self):
        self.canvas.yview_moveto(0)
        [widget.destroy() for widget in self.frame.winfo_children()]

    def winfo_height(self):
        self.canvas.update_idletasks()
        return self.canvas.winfo_height()

    def winfo_width(self):
        self.canvas.update_idletasks()
        return self.canvas.winfo_width()

class TabbedFrame(tk.Frame):
    def __init__(self, parent, tabs=None, *args, **kwargs):
        """Create a tabbed frame widget.

        Args:
            parent (tk.*): The parent widget of the resulting frame.
            tabs (dict): A list of display names for tabs to show (optional).
                key (String): The internal name for the tab.
                value (String): The display name for the tab.
        """

        if tabs is None:
            tabs = {}

        tk.Frame.__init__(self, parent)
        self.pack_propagate(0)

        self.tab = {}

        self.tab_frame = tk.Frame(self)
        self.gutter = tk.Frame(self)
        self.frame = tk.Frame(self)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.tab_frame.grid(row=0, column=0)
        self.gutter.grid(row=0, column=1, sticky='ew')
        self.frame.grid(row=1, column=0, columnspan=2, sticky='nsew')

        first_tab_name = list(tabs.keys())[0]
        for tab_name, tab_label in tabs.items():
            tab_style = 'active.tab.TButton' if tab_name == first_tab_name else 'tab.TButton'

            self.tab[tab_name] = {
                'tab': ttk.Button(self.tab_frame, text=tab_label, width=0, command=lambda tn=tab_name: self.change_tab(tn), style=tab_style),
                'content': None
            }
            self.tab[tab_name]['tab'].pack(side='left', ipadx=3, ipady=2, padx=2)

    def change_tab(self, tab_name):
        """Change to a given tab in the tab list.

        Args:
            tab_name (String): The tab to change to.
        """

        self.focus_set()

        [widget.pack_forget() for widget in self.frame.winfo_children()]

        # Change styling of tabs to show active tab
        for tab in self.tab:
            tab_style = 'active.tab.TButton' if tab == tab_name else 'tab.TButton'
            self.tab[tab]['tab'].configure(style=tab_style)

        self.tab[tab_name]['content'].pack(fill='both', expand=True)

    def configure(self, *args, **kwargs):
        self.frame.configure(*args, **kwargs)

class BackupDetailBlock(tk.Frame):
    HEADER_FONT = (None, 9, 'bold')
    TEXT_FONT = (None, 9)

    TITLE = 'title'
    CONTENT = 'content'

    def __init__(self, parent, title, uicolor, backup, enabled: bool = None):
        """Create an expandable detail block to display info.

        Args:
            parent (tk.*): The parent widget.
            title (String): The bold title to display.
            uicolor (Color): The UI pallete instance.
            backup (Backup): The backup instance to reference.
            enabled (bool): Whether or not this block is enabled.
        """

        if enabled is None:
            enabled = True

        self.enabled = enabled
        self.backup = backup
        self.uicolor = uicolor
        self.dark_mode = True
        self.right_arrow = ImageTk.PhotoImage(Image.open(resource_path(f"media/right_nav{'_light' if self.dark_mode else ''}.png")))
        self.down_arrow = ImageTk.PhotoImage(Image.open(resource_path(f"media/down_nav{'_light' if self.dark_mode else ''}.png")))

        self.lines = {}

        tk.Frame.__init__(self, parent)
        self.pack_propagate(0)
        self.grid_columnconfigure(1, weight=1)

        self.arrow = tk.Label(self, image=self.right_arrow)
        self.header_frame = tk.Frame(self)
        self.header = tk.Label(self.header_frame, text=title, font=BackupDetailBlock.HEADER_FONT, fg=self.uicolor.NORMAL if self.enabled else self.uicolor.FADED)
        self.state = tk.Label(self.header_frame, text='Pending' if self.enabled else 'Skipped', font=BackupDetailBlock.TEXT_FONT, fg=self.uicolor.PENDING if self.enabled else self.uicolor.FADED)

        self.content = tk.Frame(self)

        self.arrow.grid(row=0, column=0)
        self.header_frame.grid(row=0, column=1, sticky='w')
        self.header.pack(side='left')
        self.state.pack(side='left')

        # Bind click for expanding and collapsing
        self.arrow.bind('<Button-1>', lambda e: self.toggle())
        self.header.bind('<Button-1>', lambda e: self.toggle())

    def toggle(self):
        """Toggle expanding content of a block."""

        # Don't toggle when backup analysis is still running
        if self.backup.analysis_running:
            return

        # Check if arrow needs to be expanded
        if not self.content.grid_info():
            # Collapsed turns into expanded
            self.arrow.configure(image=self.down_arrow)
            self.content.grid(row=1, column=1, sticky='w')
        else:
            # Expanded turns into collapsed
            self.arrow.configure(image=self.right_arrow)
            self.content.grid_forget()

    def add_line(self, line_name, title, content, *args, **kwargs):
        """Add a line to the block content.

        Args:
            line_name (String): The name of the line for later reference.
            title (String): The line title.
            content (String): The content to display.
        """

        self.lines[line_name] = self.InfoLine(self.content, title, content, self.uicolor, *args, **kwargs)
        self.lines[line_name].pack(anchor='w')

    def add_copy_line(self, line_name, title, content, clipboard_data, *args, **kwargs):
        """Add a line to the block content.

        Args:
            line_name (String): The name of the line for later reference.
            title (String): The line title.
            content (String): The content to display.
        """

        self.lines[line_name] = self.InfoLine(self.content, title, content, self.uicolor, clipboard_data, *args, **kwargs)
        self.lines[line_name].pack(anchor='w')

    def configure(self, line_name, *args, **kwargs):
        if line_name in self.lines.keys():
            self.lines[line_name].configure(*args, **kwargs)

    class InfoLine(tk.Frame):
        def __init__(self, parent, title, content, uicolor, clipboard_data=None, *args, **kwargs):
            """Create an info line for use in DisplayBlock classes.

            Args:
                parent (tk.*): The parent widget).
                title (String): The line title.
                content (String): The content to display.
                uicolor (Color): The UI pallete instance.
                clipboard_data (String): The data to copy to clipboard if line
                    is a copy line (default: None).
            """

            tk.Frame.__init__(self, parent)

            self.uicolor = uicolor

            self.title = tk.Label(self, text=f"{title}:", font=BackupDetailBlock.HEADER_FONT)
            if clipboard_data is not None and clipboard_data:
                self.tooltip = tk.Label(self, text='(Click to copy)', font=BackupDetailBlock.TEXT_FONT, fg=self.uicolor.FADED)
                self.clipboard_data = clipboard_data
            self.content = tk.Label(self, text=content, font=BackupDetailBlock.TEXT_FONT, *args, **kwargs)

            self.title.pack(side='left')
            if clipboard_data is not None and clipboard_data:
                self.tooltip.pack(side='left')
            self.content.pack(side='left')

            # Set up keyboard binding for copies
            if clipboard_data is not None and clipboard_data:
                self.title.bind('<Button-1>', lambda e: clipboard.copy(self.clipboard_data))
                self.tooltip.bind('<Button-1>', lambda e: clipboard.copy(self.clipboard_data))
                self.content.bind('<Button-1>', lambda e: clipboard.copy(self.clipboard_data))

        def configure(self, *args, **kwargs):
            self.content.configure(*args, **kwargs)

class DetailBlock(wx.BoxSizer):
    TITLE = 'title'
    CONTENT = 'content'

    def __init__(self, parent, title: str, text_font: wx.Font, bold_font: wx.Font, enabled: bool = True):
        """Create an expandable detail block to display info.

        Args:
            parent (tk.*): The parent widget.
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
        self.dark_mode = True
        self.right_arrow = wx.Bitmap(wx.Image(f'media/right_nav{"_light" if self.dark_mode else ""}.png', wx.BITMAP_TYPE_ANY))
        self.down_arrow = wx.Bitmap(wx.Image(f'media/down_nav{"_light" if self.dark_mode else ""}.png', wx.BITMAP_TYPE_ANY))

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

    def SetForegroundColour(self, line_name: str, *args, **kwargs):
        """Set the foreground color of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.header.SetForegroundColour(*args, **kwargs)

    def SetFont(self, line_name: str, *args, **kwargs):
        """Set the font of an info line.

        Args:
            line_name (String): The line name to change.
        """

        if line_name in self.lines.keys():
            self.header.SetFont(*args, **kwargs)

    class InfoLine(wx.BoxSizer):
        def __init__(self, parent, title: str, content: str, bold_font: wx.Font, text_font: wx.Font, clipboard_data: str = None, *args, **kwargs):
            """Create an info line for use in DisplayBlock classes.

            Args:
                parent (tk.*): The parent widget).
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

        def SetForegroundColour(self, *args, **kwargs):
            """Set the foreground color of the line."""

            self.header.SetForegroundColour(*args, **kwargs)

        def SetFont(self, *args, **kwargs):
            """Set the font of the line."""

            self.header.SetFont(*args, **kwargs)
