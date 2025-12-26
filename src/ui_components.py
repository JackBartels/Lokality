import tkinter as tk
from utils import round_rectangle

class CustomScrollbar(tk.Canvas):
    def __init__(self, parent, command, **kwargs):
        tk.Canvas.__init__(self, parent, **kwargs)
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
        height = self.winfo_height()
        if height <= 1: return
        
        y1 = float(low) * height
        y2 = float(high) * height
        # Ensure minimum thumb size
        if (y2 - y1) < 20: y2 = y1 + 20
        if y2 > height: 
            diff = y2 - height
            y1 -= diff
            y2 = height

        # Update coordinates instead of deleting and re-creating
        points = [2+self.radius, y1, 2+self.radius, y1, 10-self.radius, y1, 10-self.radius, y1, 10, y1, 10, y1+self.radius, 10, y1+self.radius, 10, y2-self.radius, 10, y2-self.radius, 10, y2, 10-self.radius, y2, 10-self.radius, y2, 2+self.radius, y2, 2+self.radius, y2, 2, y2, 2, y2-self.radius, 2, y2-self.radius, 2, y1+self.radius, 2, y1+self.radius, 2, y1]
        self.coords(self.thumb_id, *points)

    def on_scroll(self, event):
        height = self.winfo_height()
        if height <= 0: return
        self.command("moveto", event.y / height)
