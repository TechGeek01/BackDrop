import tkinter as tk
from tkinter import ttk
import time

class ScrollableFrame(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent)
        self.pack_propagate(0)

        self.canvas = tk.Canvas(self, *args, **kwargs)
        self.vsb = tk.Scrollbar(self, orient='vertical', command=self.canvas.yview)

        self.frame = ttk.Frame(self.canvas)
        self.frame.bind('<Configure>', lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox('all')
        ))
        self.canvas.create_window((0, 0), window=self.frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side='left', fill='both', expand=1)
        self.vsb.pack(side='left', fill='y')

    def configure(self, *args, **kwargs):
        self.frame.configure(*args, **kwargs)

    def show_items(self, limit=None):
        if limit is not None and isinstance(limit, int):
            for widget in self.frame.winfo_children()[:-limit]:
                widget.destroy()

        time.sleep(0.01)
        self.canvas.yview_moveto(1)

    def empty(self):
        self.canvas.yview_moveto(0)
        for widget in self.frame.winfo_children():
            widget.destroy()
