"""
Custom Tkinter UI components for Lokality.
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from utils import CanvasConfig, round_rectangle
from ui_helpers import update_canvas_region

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
            self.update_idletasks()
            self.after(50, self._perform_layout)
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
        self.update_idletasks()
        self._perform_layout()

    def _perform_layout(self):
        """Recalculates the position of labels based on available width."""
        width = self.winfo_width()
        if width < 100:
            width = self.master.winfo_width()
            if width < 100:
                width = 600

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
            self.update_idletasks()
        self.ui.canvas.delete(self.ui.bg_id)
        self.ui.bg_id = round_rectangle(
            self.ui.canvas, (4, 4, width-4, total_h-4),
            radius=15, fill=self.theme.BG_COLOR
        )
        self.ui.canvas.tag_lower(self.ui.bg_id)
        self.ui.canvas.itemconfig(self.ui.window_id, width=max_w, height=y_pos)
        self.ui.canvas.coords(self.ui.window_id, 20, (total_h - y_pos) / 2)

class ProfilerPanel(tk.Frame):
    """
    A panel that displays real-time performance metrics from the Profiler.
    """
    COLORS = ["#2E5DA1", "#2D8A75", "#A12E2E", "#B17A19", "#6A1DA1"]
    MARGIN = 12
    LINE_H = 28

    def __init__(self, parent, theme, fonts):
        super().__init__(parent, bg=theme.BG_COLOR)
        self.theme = theme
        self.fonts = fonts
        self.visible = False

        self.canvas = tk.Canvas(self, bg=theme.BG_COLOR, highlightthickness=0, height=35)
        self.canvas.pack(fill="x", padx=10, pady=(5, 5))

        self.bg_id = round_rectangle(
            self.canvas, (0, 0, 10, 10), radius=10,
            fill="#1E1E1E", outline=theme.ACCENT_COLOR, width=1
        )
        self.canvas.bind("<Configure>", self._resize)

    def update_data(self, tasks):
        """
        Draws the task breakdown vertically with proportional bar widths.
        """
        self.canvas.delete("bar")
        self.canvas.delete("label")

        if not tasks:
            self.canvas.config(height=35)
            self.canvas.create_text(
                15, 18, anchor="w", text="Profiler Active - Waiting for data...",
                fill=self.theme.FG_COLOR, font=self.fonts["unit"], tags="label"
            )
            self._resize(None)
            return

        total_h = (len(tasks) * self.LINE_H) + (self.MARGIN * 2)
        self.canvas.config(height=total_h)

        max_dur = max(t['duration'] for t in tasks) or 1
        canvas_w = max(100, self.canvas.winfo_width())
        if canvas_w < 100:
            canvas_w = 800
        available_w = canvas_w - 60

        for i, task in enumerate(tasks):
            y_off = self.MARGIN + (i * self.LINE_H)
            dur = int(task['duration'])
            text = f"{task['name']}: {dur}ms"
            text_w = len(text) * 7.5 + 20
            bar_w = max(text_w / 5, int((task['duration'] / max_dur) * available_w))

            self.canvas.create_rectangle(
                15, y_off, 15 + bar_w, y_off + 22,
                fill=self.COLORS[i % len(self.COLORS)], outline="", tags="bar"
            )
            text_x = 22 if bar_w >= text_w else (15 + bar_w + 8)
            self.canvas.create_text(
                text_x, y_off + 11, anchor="w", text=text,
                fill="#FFFFFF", font=self.fonts["unit"], tags="label"
            )
        self._resize(None)

    def _resize(self, event):
        w = event.width if event else self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w > 20:
            self.bg_id = update_canvas_region(CanvasConfig(
                canvas=self.canvas, bg_id=self.bg_id,
                size=(w, h), radius=10,
                style=(self.theme.ACCENT_COLOR, 1, "#1E1E1E"),
                pad=(0, 0)
            ))
