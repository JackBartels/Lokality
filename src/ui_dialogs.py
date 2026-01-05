"""
Dialog windows for Lokality.
"""
import tkinter as tk
import theme as Theme

def _create_checkbox(parent, fonts, var):
    """Creates a custom large checkbox."""
    cb_frame = tk.Frame(parent, bg=Theme.BG_COLOR, cursor="hand2")
    cb_frame.pack(pady=(10, 30))

    indicator_lbl = tk.Label(
        cb_frame, text="☐", font=("Roboto", 20),
        bg=Theme.BG_COLOR, fg=Theme.SYSTEM_COLOR
    )
    indicator_lbl.pack(side="left")

    text_lbl = tk.Label(
        cb_frame, text=" Don't ask me again", font=fonts["base"],
        bg=Theme.BG_COLOR, fg=Theme.SYSTEM_COLOR
    )
    text_lbl.pack(side="left", padx=(5, 0))

    def toggle_cb(_=None):
        new_val = not var.get()
        var.set(new_val)
        if new_val:
            indicator_lbl.config(text="☑", fg=Theme.USER_COLOR)
            text_lbl.config(fg=Theme.FG_COLOR)
        else:
            indicator_lbl.config(text="☐", fg=Theme.SYSTEM_COLOR)
            text_lbl.config(fg=Theme.SYSTEM_COLOR)

    cb_frame.bind("<Button-1>", toggle_cb)
    indicator_lbl.bind("<Button-1>", toggle_cb)
    text_lbl.bind("<Button-1>", toggle_cb)
    return cb_frame

def _center_dialog(dialog, parent):
    """Centers the dialog window relative to its parent."""
    dialog.update_idletasks()
    dw, dh = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
    rw, rh = parent.winfo_width(), parent.winfo_height()
    rx, ry = parent.winfo_x(), parent.winfo_y()
    dialog.geometry(f"{dw}x{dh}+{rx + (rw-dw)//2}+{ry + (rh-dh)//2}")

def show_forget_dialog(parent, fonts, settings, on_confirm, on_cancel):
    """Shows a confirmation dialog for clearing long-term memory."""
    dialog = tk.Toplevel(parent)
    dialog.title("Confirm Forget")
    dialog.configure(bg=Theme.BG_COLOR)
    dialog.transient(parent)
    dialog.grab_set()

    content = tk.Frame(dialog, bg=Theme.BG_COLOR, padx=30, pady=25)
    content.pack(fill="both", expand=True)

    tk.Label(
        content, text="Permanently erase long-term memory?",
        font=fonts["h2"], bg=Theme.BG_COLOR, fg=Theme.FG_COLOR,
        wraplength=500, justify="center"
    ).pack(pady=(0, 15), fill="x")

    desc_lbl = tk.Label(
        content, text=(
            "This cannot be undone. It is highly recommended to perform a backup of "
            "'res/memory.db' if you wish to keep your current memories."
        ),
        font=fonts["base"], bg=Theme.BG_COLOR, fg=Theme.SYSTEM_COLOR,
        wraplength=500, justify="center"
    )
    desc_lbl.pack(pady=(0, 20), fill="x")

    dont_ask_var = tk.BooleanVar(value=False)
    _create_checkbox(content, fonts, dont_ask_var)

    btn_frame = tk.Frame(content, bg=Theme.BG_COLOR)
    btn_frame.pack(fill="x")

    def _on_yes():
        if dont_ask_var.get():
            settings.set("skip_forget_confirmation", True)
        on_confirm()
        dialog.destroy()

    def _on_no():
        on_cancel()
        dialog.destroy()

    tk.Button(
        btn_frame, text="Yes, Forget", command=_on_yes,
        bg=Theme.ACCENT_COLOR, fg=Theme.BUTTON_FG, font=fonts["bold"],
        padx=25, pady=8, borderwidth=0, cursor="hand2"
    ).pack(side="left", expand=True, padx=15)

    tk.Button(
        btn_frame, text="No, Keep It", command=_on_no,
        bg=Theme.INPUT_BG, fg=Theme.FG_COLOR, font=fonts["bold"],
        padx=25, pady=8, borderwidth=0, cursor="hand2"
    ).pack(side="right", expand=True, padx=15)

    dialog.resizable(True, True)
    dialog.minsize(400, 250)
    _center_dialog(dialog, parent)

    dialog.protocol("WM_DELETE_WINDOW", _on_no)

    def _on_resize(event):
        if event.widget == dialog:
            new_wrap = max(300, event.width - 60)
            desc_lbl.config(wraplength=new_wrap)

    dialog.bind("<Configure>", _on_resize)
