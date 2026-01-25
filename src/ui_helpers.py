"""
GUI helper functions for Lokality.
"""
import tkinter as tk
import theme as Theme
from utils import CanvasConfig, round_rectangle, SidebarConfig

def update_canvas_region(cfg: CanvasConfig) -> int:
    """Unified helper to update rounded rectangles on resize."""
    w, h = cfg.size
    outline, line_w, fill = cfg.style
    px, py = cfg.pad

    # Polygons are best updated by completely redrawing them
    # because the number of points changes with radius/smooth.
    # To avoid "random borders", we MUST delete the old one first.
    cfg.canvas.delete(cfg.bg_id)

    nbg = round_rectangle(cfg.canvas, (4, 4, w-4, h-4), radius=cfg.radius,
                          outline=outline, width=line_w, fill=fill)
    cfg.canvas.tag_lower(nbg)
    if cfg.win_id is not None:
        cfg.canvas.itemconfig(cfg.win_id, width=max(1, w-(px*2)),
                              height=max(1, h-(py*2)))
        cfg.canvas.coords(cfg.win_id, px, py)
    return nbg

def update_lower_border(ui_input, forced_h=None):
    """Redraws the input area border."""
    w = ui_input.canvas.winfo_width()
    h = forced_h if forced_h is not None else ui_input.canvas.winfo_height()
    if w < 10 or h < 10:
        return ui_input.bg_id

    inner_h = ui_input.field.winfo_reqheight()
    cfg = CanvasConfig(
        canvas=ui_input.canvas,
        bg_id=ui_input.bg_id,
        size=(w, h),
        radius=20,
        style=(Theme.COMMAND_COLOR, 6, Theme.INPUT_BG),
        win_id=ui_input.window_id,
        pad=(8, (h - inner_h) / 2)
    )
    return update_canvas_region(cfg)

def highlight_commands(ui_input, commands):
    """Applies syntax highlighting to valid slash commands."""
    ui_input.field.tag_remove("command_highlight", "1.0", tk.END)
    content = ui_input.field.get("1.0", tk.END).strip()
    if content.startswith("/"):
        end_idx = content.find(" ")
        if end_idx == -1:
            end_idx = content.find("\n")

        cmd = content[:end_idx] if end_idx != -1 else content
        valid_cmds = [c[0] for c in commands]

        if cmd in valid_cmds:
            tag_end = f"1.{end_idx}" if end_idx != -1 else "1.end"
            ui_input.field.tag_add("command_highlight", "1.0", tag_end)

def handle_tab(ui_input, commands):
    """Handles Tab key for command completion."""
    content = ui_input.field.get("1.0", tk.INSERT).strip()
    if content.startswith("/"):
        matches = [c[0] for c in commands if c[0].startswith(content)]
        if matches:
            ui_input.field.delete("1.0", tk.INSERT)
            ui_input.field.insert("1.0", min(matches, key=len))
        return "break"
    return None

def adjust_input_height(ui_input):
    """Dynamically adjusts the input field height based on content."""
    try:
        if ui_input.field.winfo_width() <= 1:
            new_h = 1
        else:
            content = ui_input.field.get("1.0", "end-1c")
            if not content:
                new_h = 1
            else:
                ui_input.field.update_idletasks()
                try:
                    res = ui_input.field.count("1.0", "end", "displaylines")
                    new_h = res[0] if res else 1
                except (tk.TclError, AttributeError):
                    new_h = content.count('\n') + 1

        new_h = min(max(new_h, 1), 8)
        ui_input.field.config(height=new_h)
        ui_input.field.update_idletasks()

        total_h = ui_input.field.winfo_reqheight() + 20
        if abs(int(ui_input.canvas.cget("height")) - total_h) > 2:
            ui_input.canvas.config(height=total_h)
            ui_input.bg_id = update_lower_border(ui_input, total_h)
    except tk.TclError:
        pass

def configure_chat_tags(text_widget, theme, fonts):
    """Sets up text tags for different message types."""
    cfg = text_widget.tag_config
    cfg("user", foreground=theme.USER_COLOR, font=fonts["bold"])
    cfg("assistant", foreground=theme.FG_COLOR, font=fonts["base"])
    cfg("indicator", foreground=theme.INDICATOR_COLOR, font=fonts["indicator"])
    cfg("system", foreground=theme.SYSTEM_COLOR, font=fonts["small"],
        tabs=("240",))
    cfg("error", foreground=theme.ERROR_COLOR)
    cfg("cancelled", foreground=theme.CANCELLED_COLOR, font=fonts["bold"])
    cfg("md_bold", font=fonts["bold"])
    cfg("md_italic", font=fonts["italic"])
    cfg("md_bold_italic", font=fonts["bold_italic"])
    cfg("md_sub", font=fonts["small_base"], offset=-2)
    cfg("md_sup", font=fonts["small_base"], offset=4)
    cfg("md_strikethrough", overstrike=True)
    cfg("md_code", font=fonts["code"], background=theme.CODE_BG,
        foreground=theme.CODE_FG)
    cfg("md_h1", font=fonts["h1"], spacing1=10, spacing3=5)
    cfg("md_h2", font=fonts["h2"], spacing1=8, spacing3=4)
    cfg("md_h3", font=fonts["h3"], spacing1=6, spacing3=3)
    cfg("md_link", foreground=theme.LINK_COLOR)
    cfg("md_quote", font=fonts["italic"], foreground=theme.SYSTEM_COLOR,
        lmargin1=40, lmargin2=40)
    cfg("md_quote_bar", foreground=theme.ACCENT_COLOR, font=fonts["bold"])

def insert_chat_separator(text_widget, theme, height=25):
    """Inserts a thematic separator in the chat."""
    try:
        # Ensure separator starts on a new line
        if text_widget.index("end-1c") != "1.0":
            if text_widget.get("end-2c", "end-1c") != "\n":
                text_widget.insert("end-1c", "\n")

        w = max(600, text_widget.winfo_width() - 40)
        canv = tk.Canvas(text_widget, bg=theme.BG_COLOR, height=height,
                         highlightthickness=0, width=w)
        canv.create_line(10, height//2, w-10, height//2, fill=theme.SEPARATOR_COLOR)

        def _on_mousewheel(event):
            text_widget.yview_scroll(int(-1*(event.delta/120)), "units")
        def _on_linux_up(_):
            text_widget.yview_scroll(-1, "units")
        def _on_linux_down(_):
            text_widget.yview_scroll(1, "units")

        canv.bind("<MouseWheel>", _on_mousewheel)
        canv.bind("<Button-4>", _on_linux_up)
        canv.bind("<Button-5>", _on_linux_down)

        text_widget.window_create("end-1c", window=canv)
        text_widget.insert("end-1c", "\n")
    except tk.TclError:
        text_widget.insert("end-1c", "-"*20 + "\n")

def setup_jump_button(root, fonts, scroll_command):
    """Sets up the 'Jump to latest' button."""
    canvas = tk.Canvas(
        root, width=300, height=80,
        bg=Theme.BG_COLOR, highlightthickness=0, bd=0
    )

    # Shadow
    round_rectangle(
        canvas, (8, 8, 292, 72), radius=25,
        fill="#111111", outline="", width=0, tags="btn_shadow"
    )

    # Main button
    round_rectangle(
        canvas, (2, 2, 284, 64), radius=25,
        fill=Theme.JUMP_BTN_BG, outline="", width=0, tags="btn_bg"
    )

    # Text
    canvas.create_text(
        143, 33, text="↓   Jump to latest", fill=Theme.FG_COLOR,
        font=fonts["bold"], tags="btn_text"
    )

    # Bindings
    for tag in ("btn_bg", "btn_text", "btn_shadow"):
        canvas.tag_bind(tag, "<Button-1>", lambda _: scroll_command())
        canvas.tag_bind(tag, "<Enter>", lambda _: canvas.config(cursor="hand2"))
        canvas.tag_bind(tag, "<Leave>", lambda _: canvas.config(cursor=""))

    return canvas

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

def build_model_sidebar(cfg: SidebarConfig):
    """Constructs the model selection UI components."""
    for widget in cfg.parent.winfo_children():
        widget.destroy()

    header = tk.Frame(cfg.parent, bg=cfg.theme.BG_COLOR)
    header.pack(fill="x", padx=10, pady=(5, 0))
    header.grid_columnconfigure(0, weight=1)

    tk.Label(header, text="Models", font=cfg.fonts["h3"],
             bg=cfg.theme.BG_COLOR, fg=cfg.theme.FG_COLOR).grid(row=0, column=0)

    tk.Button(header, text="<", command=cfg.callbacks.on_close, font=("Roboto", 24),
              bg=cfg.theme.BG_COLOR, fg=cfg.theme.SYSTEM_COLOR, borderwidth=0,
              highlightthickness=0, activebackground=cfg.theme.BG_COLOR,
              activeforeground=cfg.theme.FG_COLOR, cursor="hand2").grid(row=0, column=0, sticky="w")

    canvas = tk.Canvas(cfg.parent, bg=cfg.theme.BG_COLOR, highlightthickness=0)
    canvas.pack(fill="both", expand=True, padx=10, pady=(2, 0))

    bg_id = round_rectangle(
        canvas, (4, 4, 10, 10), radius=25,
        outline=cfg.theme.ACCENT_COLOR, width=6, fill=cfg.theme.INPUT_BG
    )

    inner = tk.Frame(canvas, bg=cfg.theme.INPUT_BG)
    win_id = canvas.create_window(12, 12, anchor="nw", window=inner)

    listbox = tk.Listbox(
        inner, font=cfg.fonts["base"], bg=cfg.theme.INPUT_BG,
        fg=cfg.theme.FG_COLOR, selectbackground=cfg.theme.USER_COLOR,
        selectforeground=cfg.theme.BG_COLOR, borderwidth=0,
        highlightthickness=0, activestyle='none', width=25
    )
    listbox.pack(side="left", fill="both", expand=True)

    scrollbar = CustomScrollbar(inner, command=listbox.yview, bg=cfg.theme.INPUT_BG)
    scrollbar.pack(side="right", fill="y")
    listbox.config(yscrollcommand=scrollbar.set)

    for i, model in enumerate(cfg.models):
        display_name = f"{model} (Current)" if model == cfg.current_model else model
        listbox.insert(tk.END, display_name)
        if model == cfg.current_model:
            listbox.selection_set(i)
            listbox.see(i)

    def _confirm(_=None):
        selection = listbox.curselection()
        if selection:
            new_model = cfg.models[selection[0]]
            if new_model != cfg.current_model:
                cfg.callbacks.on_switch(new_model)
        cfg.callbacks.on_close()

    listbox.bind("<Return>", _confirm)
    listbox.bind("<Double-Button-1>", _confirm)
    listbox.focus_set()
    canvas.bind("<Configure>", cfg.callbacks.on_resize)
    return canvas, bg_id, win_id

def handle_link_tooltip(root, current_win, url, theme, fonts):
    """Displays a tooltip for links."""
    if not url:
        if current_win:
            try:
                current_win.destroy()
            except tk.TclError:
                pass
            return None
        return None
    if current_win:
        return current_win
    try:
        xp, yp = root.winfo_pointerx() + 15, root.winfo_pointery() + 15
        new_win = tk.Toplevel(root)
        new_win.wm_overrideredirect(True)
        new_win.wm_geometry(f"+{xp}+{yp}")
        tk.Label(new_win, text=f"Ctrl + Click to open {url}",
                 background=theme.TOOLTIP_BG, foreground=theme.FG_COLOR,
                 relief='solid', borderwidth=1, font=fonts["tooltip"],
                 padx=5, pady=2).pack()
        return new_win
    except tk.TclError:
        return None
