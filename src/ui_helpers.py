"""
GUI helper functions for Lokality.
"""
from dataclasses import dataclass
from typing import Any
import tkinter as tk
from tkinter import font as tk_font
import theme as Theme
from utils import CanvasConfig, round_rectangle, SidebarConfig

@dataclass
class StyleConfig:
    """Configuration for UI styling."""
    theme: Any
    fonts: dict
    scale: float = 1.0

def update_canvas_region(cfg: CanvasConfig) -> int:
    """Unified helper to update rounded rectangles on resize."""
    w, h = cfg.size
    outline, line_w, fill = cfg.style
    px, py = cfg.pad

    # Polygons are best updated by completely redrawing them
    # because the number of points changes with radius/smooth.
    # To avoid "random borders", we MUST delete the old one first.
    cfg.canvas.delete(cfg.bg_id)
    if hasattr(cfg.canvas, "pil_images") and cfg.bg_id in cfg.canvas.pil_images:
        del cfg.canvas.pil_images[cfg.bg_id]

    # Coords need to be slightly offset by half line width for pixel perfection
    nbg = round_rectangle(cfg.canvas, (line_w/2 + 1, line_w/2 + 1, w-line_w/2 - 1, h-line_w/2 - 1),
                          radius=cfg.radius, outline=outline, width=line_w, fill=fill)
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
    scale = getattr(ui_input, "ui_scale", 1.0)
    cfg = CanvasConfig(
        canvas=ui_input.canvas,
        bg_id=ui_input.bg_id,
        size=(w, h),
        radius=int(15 * scale),
        # Using 5px border to match the look of the output box (compensates for color bloom)
        style=(Theme.COMMAND_COLOR, int(5 * scale), Theme.INPUT_BG),
        win_id=ui_input.window_id,
        pad=(int(12 * scale), (h - inner_h) / 2)
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
        # Detect scale if possible
        scale = getattr(text_widget.master, "ui_scale", 1.0)
        def s(v):
            return int(v * scale)

        # Ensure separator starts on a new line
        if text_widget.index("end-1c") != "1.0":
            if text_widget.get("end-2c", "end-1c") != "\n":
                text_widget.insert("end-1c", "\n")

        w = max(400, text_widget.winfo_width() - s(40))
        canv = tk.Canvas(text_widget, bg=theme.BG_COLOR, height=height,
                         highlightthickness=0, width=w)
        canv.create_line(s(10), height//2, w-s(10), height//2, fill=theme.SEPARATOR_COLOR)

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

def build_chat_area(root, ui_chat, style: StyleConfig, callbacks):
    """Sets up the scrollable chat display area."""
    def s(v):
        return int(v * style.scale)

    ui_chat.canvas = tk.Canvas(
        root, bg=style.theme.BG_COLOR, highlightthickness=0
    )
    ui_chat.canvas.grid(
        row=1, column=1, sticky="nsew", padx=s(10), pady=(s(10), s(7))
    )
    ui_chat.bg_id = round_rectangle(
        ui_chat.canvas, (4, 4, 10, 10), radius=s(25),
        outline=style.theme.ACCENT_COLOR, width=s(6), fill=style.theme.BG_COLOR
    )

    ui_chat.inner = tk.Frame(ui_chat.canvas, bg=style.theme.BG_COLOR)
    # radius is s(25), setting padding to s(20) for a clean look
    ui_chat.window_id = ui_chat.canvas.create_window(
        s(20), s(20), anchor="nw", window=ui_chat.inner
    )
    ui_chat.inner.grid_rowconfigure(0, weight=1)
    ui_chat.inner.grid_columnconfigure(0, weight=1)

    ui_chat.display = tk.Text(
        ui_chat.inner, state='disabled', wrap='word',
        font=style.fonts["base"], bg=style.theme.BG_COLOR, fg=style.theme.FG_COLOR,
        insertbackground=style.theme.FG_COLOR, borderwidth=0,
        highlightthickness=0, padx=s(15), pady=s(15),
        spacing1=1, spacing2=3, spacing3=1
    )
    ui_chat.display.grid(row=0, column=0, sticky="nsew")

    ui_chat.scrollbar = CustomScrollbar(
        ui_chat.inner, command=ui_chat.display.yview,
        bg=style.theme.BG_COLOR, scale=style.scale
    )
    ui_chat.scrollbar.grid(row=0, column=1, sticky="ns", pady=s(15))

    ui_chat.display.config(yscrollcommand=callbacks["on_scroll"])

    ui_chat.jump_btn_canvas = setup_jump_button(
        root, style.fonts, callbacks["scroll_to_bottom"], style.scale
    )

    ui_chat.display.mark_set("assistant_msg_start", "1.0")
    ui_chat.display.mark_gravity("assistant_msg_start", tk.LEFT)

    # Bind user scroll events
    ui_chat.display.bind("<MouseWheel>", callbacks["on_manual_scroll"])
    ui_chat.display.bind("<Button-4>", callbacks["on_manual_scroll"])
    ui_chat.display.bind("<Button-5>", callbacks["on_manual_scroll"])
    ui_chat.display.bind("<B1-Motion>", callbacks["on_manual_scroll"])

def build_input_area(root, ui_input, theme, fonts, scale=1.0):
    """Sets up the user input field at the bottom."""
    def s(v):
        return int(v * scale)
    line_h = tk_font.Font(font=fonts["base"]).metrics('linespace')
    ui_input.canvas = tk.Canvas(
        root, bg=theme.BG_COLOR, highlightthickness=0,
        height=line_h + s(20)
    )
    ui_input.canvas.grid(
        row=3, column=0, columnspan=2, sticky="ew", padx=s(10), pady=(s(7), s(20))
    )
    ui_input.bg_id = round_rectangle(
        ui_input.canvas, (4, 4, 10, 10), radius=s(15),
        outline=theme.COMMAND_COLOR, width=s(5), fill=theme.INPUT_BG
    )
    ui_input.inner = tk.Frame(ui_input.canvas, bg=Theme.INPUT_BG)
    # Radius s(15) allows s(12) padding for a more left-aligned start
    ui_input.window_id = ui_input.canvas.create_window(
        s(12), s(12), anchor="nw", window=ui_input.inner
    )
    ui_input.inner.grid_columnconfigure(0, weight=1)
    ui_input.inner.grid_rowconfigure(0, weight=1)

    ui_input.field = tk.Text(
        ui_input.inner, height=1, width=1, wrap='word',
        font=fonts["base"], bg=theme.INPUT_BG, fg=theme.FG_COLOR,
        insertbackground=theme.FG_COLOR, borderwidth=0,
        highlightthickness=0, padx=s(15), pady=s(10)
    )
    ui_input.field.grid(row=0, column=0, sticky="nsew")
    ui_input.field.tag_config(
        "command_highlight", foreground=theme.SLASH_COLOR,
        font=fonts["bold"]
    )

def setup_jump_button(root, fonts, scroll_command, scale=1.0):
    """Sets up the 'Jump to latest' button."""
    def s(v):
        return int(v * scale)
    # Balanced middle-ground size
    canvas = tk.Canvas(
        root, width=s(200), height=s(50),
        bg=Theme.BG_COLOR, highlightthickness=0, bd=0
    )

    # Shadow
    round_rectangle(
        canvas, (s(6), s(6), s(194), s(44)), radius=s(20),
        fill="#111111", outline="", width=0, tags="btn_shadow"
    )

    # Main button
    round_rectangle(
        canvas, (s(2), s(2), s(188), s(38)), radius=s(20),
        fill=Theme.JUMP_BTN_BG, outline="", width=0, tags="btn_bg"
    )

    canvas.create_text(
        s(95), s(20), text="Jump to Latest",
        fill="#FFFFFF", font=fonts["bold"], tags="btn_text"
    )

    # Bindings
    def _on_click(_):
        scroll_command()

    for tag in ["btn_bg", "btn_text", "btn_shadow"]:
        canvas.tag_bind(tag, "<Button-1>", _on_click)
        canvas.tag_bind(tag, "<Enter>", lambda e: canvas.config(cursor="hand2"))
        canvas.tag_bind(tag, "<Leave>", lambda e: canvas.config(cursor=""))

    return canvas

class CustomScrollbar(tk.Frame):
    """
    A custom-styled scrollbar consisting of a canvas-drawn thumb within a frame.
    """
    def __init__(self, parent, command, scale=1.0, **kwargs):
        super().__init__(parent, **kwargs)
        self.command = command
        self.scale = scale
        def s(v):
            return int(v * scale)
        self.canvas = tk.Canvas(
            self, width=s(12), highlightthickness=0, bg=parent["bg"]
        )
        self.canvas.pack(fill="both", expand=True)
        self.thumb_color = "#424242"
        self.thumb_hover = "#616161"
        self.radius = s(6)

        self.thumb_id = round_rectangle(
            self.canvas, (s(2), 0, s(10), 0), radius=self.radius,
            fill=self.thumb_color, use_pil=False
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
        def s(v):
            return int(v * self.scale)
        height = self.winfo_height()
        if height <= 1:
            return

        y1, y2 = float(low) * height, float(high) * height
        if (y2 - y1) < s(20):
            y2 = y1 + s(20) # Min thumb size
        if y2 > height:
            y1, y2 = height - (y2 - y1), height

        radius = self.radius
        pts = [
            s(2)+radius, y1, s(10)-radius, y1, s(10), y1, s(10), y1+radius,
            s(10), y2-radius, s(10), y2, s(10)-radius, y2, s(2)+radius, y2,
            s(2), y2, s(2), y2-radius, s(2), y1+radius, s(2), y1
        ]
        self.canvas.coords(self.thumb_id, *pts)

    def on_scroll(self, event):
        """Handles scroll interaction."""
        if self.winfo_height() > 0:
            self.command("moveto", event.y / self.winfo_height())

def _setup_sidebar_header(cfg, s_func):
    """Creates the sidebar header."""
    header = tk.Frame(cfg.parent, bg=cfg.theme.BG_COLOR)
    header.pack(fill="x", padx=s_func(5), pady=(s_func(2), 0))
    header.grid_columnconfigure(0, weight=1)

    tk.Label(header, text="Models", font=cfg.fonts["h3"],
             bg=cfg.theme.BG_COLOR, fg=cfg.theme.FG_COLOR).grid(row=0, column=0)

    tk.Button(header, text="<", command=cfg.callbacks.on_close, font=cfg.fonts["h1"],
              bg=cfg.theme.BG_COLOR, fg=cfg.theme.SYSTEM_COLOR, borderwidth=0,
              highlightthickness=0, activebackground=cfg.theme.BG_COLOR,
              activeforeground=cfg.theme.FG_COLOR, cursor="hand2").grid(row=0, column=0, sticky="w")

def _setup_sidebar_listbox(inner, cfg, sorted_models, scale):
    """Creates and populates the sidebar listbox."""
    max_w = 8
    for model in sorted_models:
        name_len = len(model) + (10 if model == cfg.current_model else 0)
        max_w = max(max_w, name_len)

    listbox = tk.Listbox(
        inner, font=cfg.fonts["base"], bg=cfg.theme.INPUT_BG,
        fg=cfg.theme.FG_COLOR, selectbackground=cfg.theme.USER_COLOR,
        selectforeground=cfg.theme.BG_COLOR, borderwidth=0,
        highlightthickness=0, activestyle='none', width=max_w
    )
    listbox.pack(side="left", fill="both", expand=True)

    scrollbar = CustomScrollbar(
        inner, command=listbox.yview, bg=cfg.theme.INPUT_BG, scale=scale
    )
    scrollbar.pack(side="right", fill="y")
    listbox.config(yscrollcommand=scrollbar.set)

    for i, model in enumerate(sorted_models):
        display_name = f"{model} (Current)" if model == cfg.current_model else model
        listbox.insert(tk.END, display_name)
        if model == cfg.current_model:
            listbox.selection_set(i)
            listbox.see(i)
            listbox.activate(i)
    return listbox

def build_model_sidebar(cfg: SidebarConfig, scale=1.0):
    """Constructs the model selection UI components."""
    def s(v):
        return int(v * scale)
    for widget in cfg.parent.winfo_children():
        widget.destroy()

    _setup_sidebar_header(cfg, s)

    canvas = tk.Canvas(cfg.parent, bg=cfg.theme.BG_COLOR, highlightthickness=0)
    canvas.pack(fill="both", expand=True, padx=s(5), pady=(s(2), 0))

    bg_id = round_rectangle(
        canvas, (4, 4, 10, 10), radius=s(15),
        outline=cfg.theme.ACCENT_COLOR, width=s(4), fill=cfg.theme.INPUT_BG
    )

    inner = tk.Frame(canvas, bg=cfg.theme.INPUT_BG)
    win_id = canvas.create_window(s(15), s(15), anchor="nw", window=inner)

    sorted_models = sorted(cfg.models)
    listbox = _setup_sidebar_listbox(inner, cfg, sorted_models, scale)

    def _confirm(_=None):
        selection = listbox.curselection()
        if selection:
            new_model = sorted_models[selection[0]]
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
