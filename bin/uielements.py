import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sys
import os
import ctypes
import clipboard
import time

from bin.color import Color

WINDOW_ELEMENT_PADDING = 16

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""

    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class RootWindow(tk.Tk):
    def __init__(self, title, width: int, height: int, center: bool = False, resizable=(True, True), status_bar: bool = False, dark_mode: bool = False, *args, **kwargs):
        # TODO: Get icons working to be passed into RootWindow class
        # TODO: Add option to give RootWindow a scrollbar
        # TODO: Add option to give RootWindow status bar

        """Create a root window.

        Args:
            title (String): The window title.
            width (int): The window width.
            height (int): The window height.
            center (bool): Whether to center the window on the parent
                (optional).
            resizable (tuple): Whether to let the window be resized in
                width or height.
            status_bar (bool): Whether to add a status bar to the window
                (optional).
            dark_mode (bool): Whether to use dark mode (optional).
        """

        (resize_width, resize_height) = resizable

        tk.Tk.__init__(self, *args, **kwargs)
        self.title(title)
        self.minsize(width, height)
        self.geometry(f'{width}x{height}')
        self.resizable(resize_width, resize_height)

        if center:
            self.center()

        # Create and set uicolor instance for application windows
        self.uicolor = Color(self, dark_mode)
        if self.uicolor.is_dark_mode():
            self.tk_setPalette(background=self.uicolor.BG)

        self.dark_mode = self.uicolor.is_dark_mode()

        # Set up window frame
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.main_frame = tk.Frame(self)
        self.main_frame.grid(row=0, column=0, sticky='nsew', padx=(WINDOW_ELEMENT_PADDING, 0), pady=(0, WINDOW_ELEMENT_PADDING))

        # Set up status bar
        if status_bar:
            self.status_bar_frame = tk.Frame(self, bg=self.uicolor.STATUS_BAR)
            self.status_bar_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=0)
            self.status_bar_frame.columnconfigure(50, weight=1)  # Let column 51 fill width, used like a spacer to have both left- and right-aligned text

    def center(self):
        """Center the root window on a screen.
        """

        self.update_idletasks()
        WIDTH = self.winfo_width()
        FRAME_WIDTH = self.winfo_rootx() - self.winfo_x()
        WIN_WIDTH = WIDTH + 2 * FRAME_WIDTH
        HEIGHT = self.winfo_height()
        TITLEBAR_HEIGHT = self.winfo_rooty() - self.winfo_y()
        WIN_HEIGHT = HEIGHT + TITLEBAR_HEIGHT + FRAME_WIDTH

        # Set position and center on screen
        x = self.winfo_screenwidth() // 2 - WIN_WIDTH // 2
        y = self.winfo_screenheight() // 2 - WIN_HEIGHT // 2

        self.geometry('{}x{}+{}+{}'.format(WIDTH, HEIGHT, x, y))
        self.deiconify()

class AppWindow(tk.Toplevel):
    def __init__(self, root, title, width: int, height: int, center: bool = False, center_content: bool = False, resizable=(True, True), status_bar: bool = False, modal: bool = False, *args, **kwargs):
        # TODO: Get icons working to be passed into AppWindow class
        # TODO: Add option to give AppWindow a scrollbar
        # TODO: Add option to give AppWindow status bar

        """Create an app window.

        Args:
            root (tkinter.Tk): The root window to make AppWindow a child of.
            title (String): The window title.
            width (int): The window width.
            height (int): The window height.
            center (bool): Whether to center the window on the parent
                (optional).
            center_content (bool): Whether to center the content in the window
                (optional).
            resizable (tuple): Whether to let the window be resized in
                width or height.
            status_bar (bool): Whether to add a status bar to the window
                (optional).
            modal (bool): Whether or not the window is a modal window (optional).
        """

        (resize_width, resize_height) = resizable

        tk.Toplevel.__init__(self, root, *args, **kwargs)
        self.title(title)
        self.minsize(width, height)
        self.geometry(f'{width}x{height}')
        self.resizable(resize_width, resize_height)

        if center:
            self.center(root)

        # Set up window frame
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.main_frame = tk.Frame(self)
        if not center_content:
            self.main_frame.grid(row=0, column=0, sticky='nsew', padx=WINDOW_ELEMENT_PADDING, pady=(0, WINDOW_ELEMENT_PADDING))
        else:
            self.main_frame.grid(row=0, column=0, sticky='')

        # Set up status bar
        if status_bar:
            self.status_bar_frame = tk.Frame(self, bg=root.uicolor.STATUS_BAR)
            self.status_bar_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=0)
            self.status_bar_frame.columnconfigure(50, weight=1)  # Let column 51 fill width, used like a spacer to have both left- and right-aligned text

        # If window is a modal window, disable parent window until AppWindow
        # is closed.
        if modal:
            def on_close():
                self.destroy()
                root.wm_attributes('-disabled', False)

                ctypes.windll.user32.SetForegroundWindow(root.winfo_id())
                root.focus_set()

            self.protocol('WM_DELETE_WINDOW', on_close)

    def center(self, center_to_window):
        """Center the window on the root window.

        Args:
            center_to_window (tkinter.Tk): The window to center the child window on.
        """

        self.update_idletasks()
        WIDTH = self.winfo_width()
        FRAME_WIDTH = self.winfo_rootx() - self.winfo_x()
        WIN_WIDTH = WIDTH + 2 * FRAME_WIDTH
        HEIGHT = self.winfo_height()
        TITLEBAR_HEIGHT = self.winfo_rooty() - self.winfo_y()
        WIN_HEIGHT = HEIGHT + TITLEBAR_HEIGHT + FRAME_WIDTH

        # Center element provided, so use its position for reference
        ROOT_FRAME_WIDTH = center_to_window.winfo_rootx() - center_to_window.winfo_x()
        ROOT_WIN_WIDTH = center_to_window.winfo_width() + 2 * ROOT_FRAME_WIDTH
        ROOT_TITLEBAR_HEIGHT = center_to_window.winfo_rooty() - center_to_window.winfo_y()
        ROOT_WIN_HEIGHT = center_to_window.winfo_height() + ROOT_TITLEBAR_HEIGHT + ROOT_FRAME_WIDTH

        x = center_to_window.winfo_x() + ROOT_WIN_WIDTH // 2 - WIN_WIDTH // 2
        y = center_to_window.winfo_y() + ROOT_WIN_HEIGHT // 2 - WIN_HEIGHT // 2

        self.geometry('{}x{}+{}+{}'.format(WIDTH, HEIGHT, x, y))
        self.deiconify()

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
            for widget in self.frame.winfo_children()[:-limit]:
                widget.destroy()

        time.sleep(0.01)
        self.canvas.yview_moveto(1)

    def empty(self):
        self.canvas.yview_moveto(0)
        for widget in self.frame.winfo_children():
            widget.destroy()

    def winfo_height(self):
        self.canvas.update_idletasks()
        return self.canvas.winfo_height()

    def winfo_width(self):
        self.canvas.update_idletasks()
        return self.canvas.winfo_width()

class TabbedFrame(tk.Frame):
    def __init__(self, parent, tabs={}, *args, **kwargs):
        """Create a tabbed frame widget.

        Args:
            parent (tk.*): The parent widget of the resulting frame.
            tabs (dict): A list of display names for tabs to show (optional).
                key (String): The internal name for the tab.
                value (String): The display name for the tab.
        """

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

        for widget in self.frame.winfo_children():
            widget.pack_forget()

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

    def __init__(self, parent, title, uicolor, backup, enabled: bool = True):
        """Create an expandable detail block to display info.

        Args:
            parent (tk.*): The parent widget.
            title (String): The bold title to display.
            uicolor (Color): The UI pallete instance.
            backup (Backup): The backup instance to reference.
            enabled (bool): Whether or not this block is enabled.
        """

        self.enabled = enabled
        self.backup = backup
        self.uicolor = uicolor
        self.dark_mode = uicolor.is_dark_mode()
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

        if not self.backup.analysis_running:
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

class DetailBlock(tk.Frame):
    HEADER_FONT = (None, 9, 'bold')
    TEXT_FONT = (None, 9)

    TITLE = 'title'
    CONTENT = 'content'

    def __init__(self, parent, title, uicolor, enabled: bool = True):
        """Create an expandable detail block to display info.

        Args:
            parent (tk.*): The parent widget.
            title (String): The bold title to display.
            uicolor (Color): The UI pallete instance.
            enabled (bool): Whether or not this block is enabled.
        """

        self.enabled = enabled
        self.uicolor = uicolor
        self.dark_mode = uicolor.is_dark_mode()
        self.right_arrow = ImageTk.PhotoImage(Image.open(resource_path(f"media/right_nav{'_light' if self.dark_mode else ''}.png")))
        self.down_arrow = ImageTk.PhotoImage(Image.open(resource_path(f"media/down_nav{'_light' if self.dark_mode else ''}.png")))

        self.lines = {}

        tk.Frame.__init__(self, parent)
        self.pack_propagate(0)
        self.grid_columnconfigure(1, weight=1)

        self.arrow = tk.Label(self, image=self.right_arrow)
        self.header_frame = tk.Frame(self)
        self.header = tk.Label(self.header_frame, text=title, font=DetailBlock.HEADER_FONT, fg=self.uicolor.NORMAL if self.enabled else self.uicolor.FADED)

        self.content = tk.Frame(self)

        self.arrow.grid(row=0, column=0)
        self.header_frame.grid(row=0, column=1, sticky='w')
        self.header.pack(side='left')

        # Bind click for expanding and collapsing
        self.arrow.bind('<Button-1>', lambda e: self.toggle())
        self.header.bind('<Button-1>', lambda e: self.toggle())

    def toggle(self):
        """Toggle expanding content of a block."""

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

            self.title = tk.Label(self, text=f"{title}:", font=DetailBlock.HEADER_FONT)
            if clipboard_data is not None and clipboard_data:
                self.tooltip = tk.Label(self, text='(Click to copy)', font=DetailBlock.TEXT_FONT, fg=self.uicolor.FADED)
                self.clipboard_data = clipboard_data
            self.content = tk.Label(self, text=content, font=DetailBlock.TEXT_FONT, *args, **kwargs)

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
