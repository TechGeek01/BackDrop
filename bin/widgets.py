import tkinter as tk
from tkinter import ttk
import time

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
            self.vsb = tk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        else:
            self.vsb = scrollbar
            self.vsb.configure(command=self.canvas.yview)

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

    def _on_mousewheel(self, event):
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
