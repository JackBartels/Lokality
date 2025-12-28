import tkinter as tk
from utils import round_rectangle

class CustomScrollbar(tk.Canvas):
    def __init__(self, parent, command, **kwargs):
        super().__init__(parent, **kwargs)
        self.command = command
        self.config(width=12, highlightthickness=0, bg=parent["bg"])
        self.thumb_color = "#424242"
        self.thumb_hover = "#616161"
        self.radius = 6
        
        self.thumb_id = round_rectangle(self, 2, 0, 10, 0, radius=self.radius, fill=self.thumb_color)
        
        self.bind("<Enter>", lambda e: self.itemconfig(self.thumb_id, fill=self.thumb_hover))
        self.bind("<Leave>", lambda e: self.itemconfig(self.thumb_id, fill=self.thumb_color))
        self.bind("<B1-Motion>", self.on_scroll)
        self.bind("<Button-1>", self.on_scroll)

    def set(self, low, high):
        h = self.winfo_height()
        if h <= 1: return
        
        y1, y2 = float(low) * h, float(high) * h
        if (y2 - y1) < 20: y2 = y1 + 20 # Min thumb size
        if y2 > h: y1, y2 = h - (y2 - y1), h

        # Draw rounded rectangle using 4 arcs and 4 lines (simplified programmatic coords)
        r = self.radius
        pts = [2+r, y1, 10-r, y1, 10, y1, 10, y1+r, 10, y2-r, 10, y2, 10-r, y2, 2+r, y2, 2, y2, 2, y2-r, 2, y1+r, 2, y1]
        self.coords(self.thumb_id, *pts)

    def on_scroll(self, event):
        if self.winfo_height() > 0: self.command("moveto", event.y / self.winfo_height())

class InfoPanel(tk.Canvas):
    def __init__(self, parent, theme, fonts, **kwargs):
        super().__init__(parent, bg=theme.BG_COLOR, height=0, highlightthickness=0, **kwargs)
        self.theme, self.fonts, self.show_info = theme, fonts, False
        self.bg_id = round_rectangle(self, 4, 4, 10, 10, radius=15, fill=theme.BG_COLOR)
        self.inner_frame = tk.Frame(self, bg=theme.BG_COLOR)
        self.window_id = self.create_window(10, 10, anchor="nw", window=self.inner_frame)
        
        self.labels = []
        for _ in range(5):
            f = tk.Frame(self.inner_frame, bg=theme.BG_COLOR)
            s = tk.Frame(f, bg=theme.BG_COLOR); s.pack(expand=True, padx=10)
            nl = tk.Label(s, text="", font=fonts["small"], bg=theme.BG_COLOR, fg="#BDBDBD"); nl.pack(side="left")
            vl = tk.Label(s, text="", font=fonts["bold"], bg=theme.BG_COLOR, fg="#BDBDBD"); vl.pack(side="left")
            ul = tk.Label(s, text="", font=fonts["unit"], bg=theme.BG_COLOR, fg="#BDBDBD"); ul.pack(side="left", pady=(2, 0))
            self.labels.append((f, nl, vl, ul))
        self.bind("<Configure>", lambda e: self.after(100, self._perform_layout))

    def toggle(self):
        self.show_info = not self.show_info
        self.grid() if self.show_info else self.grid_remove()
        return self.show_info

    def update_stats(self, stats):
        rv, ru = (stats['ram_mb'], "MB") if stats['ram_mb'] > 0 else ("-", "")
        vv, vu = (stats['vram_mb'], "MB") if stats['vram_mb'] > 0 else ("-", "")
        data = [("Model: ", stats['model'], ""), ("Remaining Context: ", f"{100-stats['context_pct']:.1f}", "%"),
                ("Long Term Memory: ", f"{stats['memory_entries']}", " rows"), ("RAM Usage: ", rv, ru), ("VRAM Usage: ", vv, vu)]
        for i, (n, v, u) in enumerate(data):
            self.labels[i][1].config(text=n); self.labels[i][2].config(text=v); self.labels[i][3].config(text=u)
        self._perform_layout()

    def _perform_layout(self):
        w = self.winfo_width()
        if w < 100: return
        max_w = w - 40
        rows, cur_w = [[]], 0
        for f, _, _, _ in self.labels:
            fw = f.winfo_reqwidth()
            if cur_w + fw > max_w and rows[-1]: rows.append([]); cur_w = 0
            rows[-1].append((f, fw)); cur_w += fw + 20
        
        y = 0
        for row in rows:
            if not row: continue
            pad = (max_w - sum(i[1] for i in row)) / (len(row) + 1)
            x, rh = pad, 0
            for f, fw in row:
                f.place(x=x, y=y); x += fw + pad
                rh = max(rh, f.winfo_reqheight())
            y += rh + 5

        th = max(40, y + 10)
        if abs(self.winfo_height() - th) > 5: self.config(height=th)
        self.delete(self.bg_id)
        self.bg_id = round_rectangle(self, 4, 4, w-4, self.winfo_height()-4, radius=15, fill=self.theme.BG_COLOR)
        self.tag_lower(self.bg_id)
        self.itemconfig(self.window_id, width=max_w, height=y)
        self.coords(self.window_id, 20, (self.winfo_height() - y) / 2)
