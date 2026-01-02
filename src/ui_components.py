"""
Custom Tkinter UI components for Lokality.
"""
import tkinter as tk
from dataclasses import dataclass
from typing import Optional
from utils import round_rectangle

class CustomScrollbar(tk.Frame):
    """
    A custom-styled scrollbar consisting of a canvas-drawn thumb within a frame.
    """
    def __init__(self, parent, command, **kwargs):
        super().__init__(parent, **kwargs)
        self.command = command
        self.canvas = tk.Canvas(
            self, width=12, highlightthickness=0, bg=parent["bg"]
        )
        self.canvas.pack(fill="both", expand=True)
        self.thumb_color = "#424242"
        self.thumb_hover = "#616161"
        self.radius = 6

        self.thumb_id = round_rectangle(
            self.canvas, (2, 0, 10, 0), radius=self.radius, fill=self.thumb_color
        )

        self.canvas.bind("<Enter>", lambda e: self.canvas.itemconfig(
            self.thumb_id, fill=self.thumb_hover
        ))
        self.canvas.bind("<Leave>", lambda e: self.canvas.itemconfig(
            self.thumb_id, fill=self.thumb_color
        ))
        self.canvas.bind("<B1-Motion>", self.on_scroll)
        self.canvas.bind("<Button-1>", self.on_scroll)

    def set(self, low, high):
        """Sets the position and size of the scrollbar thumb."""
        height = self.winfo_height()
        if height <= 1:
            return

        y1, y2 = float(low) * height, float(high) * height
        if (y2 - y1) < 20:
            y2 = y1 + 20 # Min thumb size
        if y2 > height:
            y1, y2 = height - (y2 - y1), height

        radius = self.radius
        pts = [
            2+radius, y1, 10-radius, y1, 10, y1, 10, y1+radius,
            10, y2-radius, 10, y2, 10-radius, y2, 2+radius, y2,
            2, y2, 2, y2-radius, 2, y1+radius, 2, y1
        ]
        self.canvas.coords(self.thumb_id, *pts)

    def on_scroll(self, event):
        """Handles scroll interaction."""
        if self.winfo_height() > 0:
            self.command("moveto", event.y / self.winfo_height())

@dataclass
class InfoUI:
    """Holds UI component references for InfoPanel."""
    canvas: Optional[tk.Canvas] = None
    bg_id: Optional[int] = None
    inner_frame: Optional[tk.Frame] = None
    window_id: Optional[int] = None

class InfoPanel(tk.Frame):
    """
    A status bar panel that displays model and system statistics.
    """
    def __init__(self, parent, theme, fonts, **kwargs):
        super().__init__(parent, bg=theme.BG_COLOR, **kwargs)
        self.theme = theme
        self.fonts = fonts
        self.show_info = False
        self.labels = []
        self.ui = InfoUI()

        self.ui.canvas = tk.Canvas(
            self, bg=theme.BG_COLOR, height=0, highlightthickness=0
        )
        self.ui.canvas.pack(fill="both", expand=True)

        self.ui.bg_id = round_rectangle(
            self.ui.canvas, (4, 4, 10, 10), radius=15, fill=theme.BG_COLOR
        )
        self.ui.inner_frame = tk.Frame(self.ui.canvas, bg=theme.BG_COLOR)
        self.ui.window_id = self.ui.canvas.create_window(
            10, 10, anchor="nw", window=self.ui.inner_frame
        )

        self._setup_labels()
        self.ui.canvas.bind("<Configure>", lambda e: self.after(100, self._perform_layout))

    def _setup_labels(self):
        """Creates the labels for statistics."""
        for _ in range(5):
            container = tk.Frame(self.ui.inner_frame, bg=self.theme.BG_COLOR)
            stack = tk.Frame(container, bg=self.theme.BG_COLOR)
            stack.pack(expand=True, padx=10)
            name_lbl = tk.Label(
                stack, text="", font=self.fonts["small"],
                bg=self.theme.BG_COLOR, fg="#BDBDBD"
            )
            name_lbl.pack(side="left")
            val_lbl = tk.Label(
                stack, text="", font=self.fonts["bold"],
                bg=self.theme.BG_COLOR, fg="#BDBDBD"
            )
            val_lbl.pack(side="left")
            unit_lbl = tk.Label(
                stack, text="", font=self.fonts["unit"],
                bg=self.theme.BG_COLOR, fg="#BDBDBD"
            )
            unit_lbl.pack(side="left", pady=(2, 0))
            self.labels.append((container, name_lbl, val_lbl, unit_lbl))

    def toggle(self):
        """Toggles the visibility of the info panel."""
        self.show_info = not self.show_info
        if self.show_info:
            self.grid()
        else:
            self.grid_remove()
        return self.show_info

    def update_stats(self, stats):
        """Updates the labels with the latest system statistics."""
        ram_v, ram_u = (stats['ram_mb'], "MB") if stats['ram_mb'] > 0 else ("-", "")
        vram_v, vram_u = (
            stats['vram_mb'], "MB"
        ) if stats['vram_mb'] > 0 else ("-", "")

        data = [
            ("Model: ", stats['model'], ""),
            ("Remaining Context: ", f"{100-stats['context_pct']:.1f}", "%"),
            ("Long Term Memory: ", f"{stats['memory_entries']}", " rows"),
            ("RAM Usage: ", ram_v, ram_u),
            ("VRAM Usage: ", vram_v, vram_u)
        ]
        for i, (name, val, unit) in enumerate(data):
            self.labels[i][1].config(text=name)
            self.labels[i][2].config(text=val)
            self.labels[i][3].config(text=unit)
        self._perform_layout()

    def _perform_layout(self):
        """Recalculates the position of labels based on available width."""
        width = self.winfo_width()
        if width < 100:
            return
        max_w = width - 40
        rows, cur_w = [[]], 0
        for container, _, _, _ in self.labels:
            f_w = container.winfo_reqwidth()
            if cur_w + f_w > max_w and rows[-1]:
                rows.append([])
                cur_w = 0
            rows[-1].append((container, f_w))
            cur_w += f_w + 20

        y_pos = 0
        for row in rows:
            if not row:
                continue
            pad = (max_w - sum(i[1] for i in row)) / (len(row) + 1)
            x_pos, row_h = pad, 0
            for container, f_w in row:
                container.place(x=x_pos, y=y_pos)
                x_pos += f_w + pad
                row_h = max(row_h, container.winfo_reqheight())
            y_pos += row_h + 5

        total_h = max(40, y_pos + 10)
        if abs(self.ui.canvas.winfo_height() - total_h) > 5:
            self.ui.canvas.config(height=total_h)
        self.ui.canvas.delete(self.ui.bg_id)
        self.ui.bg_id = round_rectangle(
            self.ui.canvas, (4, 4, width-4, self.ui.canvas.winfo_height()-4),
            radius=15, fill=self.theme.BG_COLOR
        )
        self.ui.canvas.tag_lower(self.ui.bg_id)
        self.ui.canvas.itemconfig(self.ui.window_id, width=max_w, height=y_pos)
        self.ui.canvas.coords(self.ui.window_id, 20, (self.ui.canvas.winfo_height() - y_pos) / 2)
