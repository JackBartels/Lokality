"""
GUI helper functions for Lokality.
"""
import tkinter as tk
import theme as Theme
from app_state import CanvasConfig
from utils import round_rectangle

def update_canvas_region(cfg: CanvasConfig) -> int:
    """Unified helper to update rounded rectangles on resize."""
    w, h = cfg.size
    outline, line_w, fill = cfg.style
    px, py = cfg.pad
    cfg.canvas.delete(cfg.bg_id)
    nbg = round_rectangle(cfg.canvas, (4, 4, w-4, h-4), radius=cfg.radius,
                          outline=outline, width=line_w, fill=fill)
    cfg.canvas.tag_lower(nbg)
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
