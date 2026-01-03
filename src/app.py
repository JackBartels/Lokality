"""
Main GUI application for Lokality.
Orchestrates the chat interface, model interaction, and UI components.
"""
import logging
import os
import queue
import signal
import sys
import threading
import tkinter as tk
import traceback
from tkinter import font

import mistune
import ollama
from mistune.plugins.formatting import superscript, subscript

import config
import local_assistant
from complexity_scorer import ComplexityScorer
from config import VERSION
from logger import logger
from markdown_engine import MarkdownEngine
from settings import Settings
from shell_integration import run_ollama_bypass
import theme as Theme
from app_state import AppState, AppUI, CanvasConfig, SLASH_COMMANDS
from ui_components import CustomScrollbar, InfoPanel
from ui_helpers import (
    update_canvas_region, update_lower_border, highlight_commands, handle_tab,
    adjust_input_height
)
from utils import (
    RedirectedStdout,
    debug_print,
    error_print,
    format_error_msg,
    get_ollama_client,
    info_print,
    round_rectangle,
    thread_excepthook,
    verify_env_health,
)

threading.excepthook = thread_excepthook

class AssistantApp:
    """The main application class for the Lokality GUI."""
    def __init__(self, root):
        self.root = root
        self.root.report_callback_exception = self.handle_tk_exception
        self.root.title(f"Lokality ({VERSION})")
        self.root.geometry("900x700")
        self.root.minsize(500, 400)
        self.root.configure(bg=Theme.BG_COLOR)

        self.fonts = Theme.get_fonts()
        self.settings = Settings()
        self.state = AppState()

        # Load persistent toggles
        config.DEBUG = self.settings.get("debug", False)
        self.state.ui_state.show_info = self.settings.get("show_info", False)
        config.MODEL_NAME = self.settings.get("model_name", config.MODEL_NAME)
        if config.DEBUG:
            logger.setLevel(logging.DEBUG)

        self.ui = AppUI()

        self._setup_markdown()
        self._setup_ui()

        self.root.bind("<Escape>", self._cancel_generation)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._check_queue)

        sys.stdout = RedirectedStdout(self.state.msg_queue, "system")
        sys.stderr = RedirectedStdout(self.state.msg_queue, "error")

        info_print(f"Lokality {VERSION} starting...")
        threading.Thread(target=self._initialize_async, daemon=True).start()

    def _setup_markdown(self):
        """Initializes the markdown engine and parser."""
        try:
            self.markdown_engine = MarkdownEngine(
                None, self._handle_tooltip
            )
            self.md_parser = mistune.create_markdown(
                renderer=None,
                plugins=['table', 'strikethrough', superscript, subscript]
            )
        except (ImportError, AttributeError):
            self.markdown_engine = MarkdownEngine(
                None, self._handle_tooltip
            )
            self.md_parser = lambda x: [{"type": "text", "text": x}]

    def _initialize_async(self):
        """Heavy initialization tasks run in background."""
        try:
            self.state.assistant = local_assistant.LocalChatAssistant()
            info_print("Chat Assistant ready.")

            # Initial info update if panel is visible
            self._update_info_display()

            _, errors = verify_env_health()
            for err in errors:
                error_print(f"Environment check failed: {err}")

            print("Type /help for commands.\n")
        except (ImportError, RuntimeError, ValueError, ConnectionError) as exc:
            error_print(f"Initialization failed: {format_error_msg(exc)}")

    def handle_tk_exception(self, exc, val, tback):
        """Global hook for catching Tkinter callback exceptions."""
        err_msg = f"GUI Error: {exc.__name__}: {val}"
        error_print(err_msg)
        if config.DEBUG:
            traceback.print_exception(exc, val, tback)

    def _setup_ui(self):
        """Configures the main window layout and components."""
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=0) # Sidebar column
        self.root.grid_columnconfigure(1, weight=1) # Chat column

        self._setup_sidebar()
        self._setup_chat_area()
        self.markdown_engine.text_widget = self.ui.chat.display

        self.ui.info_panel = InfoPanel(self.root, Theme, self.fonts)
        self.ui.info_panel.show_info = self.state.ui_state.show_info
        self.ui.info_panel.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=0)
        if not self.state.ui_state.show_info:
            self.ui.info_panel.grid_remove()

        self._setup_input_area()
        self._bind_events()
        self._adjust_input_height()

    def _setup_sidebar(self):
        """Initializes the model selection sidebar."""
        self.ui.sidebar.frame = tk.Frame(
            self.root, bg=Theme.BG_COLOR, width=0, highlightthickness=0
        )
        self.ui.sidebar.frame.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=(10, 7))
        self.ui.sidebar.frame.grid_remove() # Hidden by default

    def _setup_chat_area(self):
        """Sets up the scrollable chat display area."""
        self.ui.chat.canvas = tk.Canvas(
            self.root, bg=Theme.BG_COLOR, highlightthickness=0
        )
        self.ui.chat.canvas.grid(
            row=0, column=1, sticky="nsew", padx=10, pady=(10, 7)
        )
        self.ui.chat.bg_id = round_rectangle(
            self.ui.chat.canvas, (4, 4, 10, 10), radius=25,
            outline=Theme.ACCENT_COLOR, width=6, fill=Theme.BG_COLOR
        )

        self.ui.chat.inner = tk.Frame(self.ui.chat.canvas, bg=Theme.BG_COLOR)
        self.ui.chat.window_id = self.ui.chat.canvas.create_window(
            10, 10, anchor="nw", window=self.ui.chat.inner
        )
        self.ui.chat.inner.grid_rowconfigure(0, weight=1)
        self.ui.chat.inner.grid_columnconfigure(0, weight=1)

        self.ui.chat.display = tk.Text(
            self.ui.chat.inner, state='disabled', wrap='word',
            font=self.fonts["base"], bg=Theme.BG_COLOR, fg=Theme.FG_COLOR,
            insertbackground=Theme.FG_COLOR, borderwidth=0,
            highlightthickness=0, padx=15, pady=15,
            spacing1=1, spacing2=3, spacing3=1
        )
        self.ui.chat.display.grid(row=0, column=0, sticky="nsew")

        self.ui.chat.scrollbar = CustomScrollbar(
            self.ui.chat.inner, command=self.ui.chat.display.yview,
            bg=Theme.BG_COLOR
        )
        self.ui.chat.scrollbar.grid(row=0, column=1, sticky="ns", pady=15)

        # Modified scroll command to track auto-scroll state
        def on_display_scroll(*args):
            self.ui.chat.scrollbar.set(*args)
            self._check_scroll_position()

        self.ui.chat.display.config(yscrollcommand=on_display_scroll)

        # "Jump to latest" button (Canvas-based for styling)
        self.ui.chat.jump_btn_canvas = tk.Canvas(
            self.root, width=300, height=80,
            bg=Theme.BG_COLOR, highlightthickness=0, bd=0
        )

        # Shadow (drawn first)
        round_rectangle(
            self.ui.chat.jump_btn_canvas, (8, 8, 292, 72), radius=25,
            fill="#111111", outline="", width=0, tags="btn_shadow"
        )

        # Draw the button content
        round_rectangle(
            self.ui.chat.jump_btn_canvas, (2, 2, 284, 64), radius=25,
            fill=Theme.JUMP_BTN_BG, outline="", width=0, tags="btn_bg"
        )

        # Text (Simple, no border)
        self.ui.chat.jump_btn_canvas.create_text(
            143, 33, text="↓   Jump to latest", fill=Theme.FG_COLOR,
            font=self.fonts["bold"], tags="btn_text"
        )

        # Bindings
        for tag in ("btn_bg", "btn_text", "btn_shadow"):
            self.ui.chat.jump_btn_canvas.tag_bind(
                tag, "<Button-1>", lambda e: self.scroll_to_bottom()
            )
            self.ui.chat.jump_btn_canvas.tag_bind(
                tag, "<Enter>",
                lambda e: self.ui.chat.jump_btn_canvas.config(cursor="hand2")
            )
            self.ui.chat.jump_btn_canvas.tag_bind(
                tag, "<Leave>",
                lambda e: self.ui.chat.jump_btn_canvas.config(cursor="")
            )

        self._configure_tags()
        self.ui.chat.display.mark_set("assistant_msg_start", "1.0")
        self.ui.chat.display.mark_gravity("assistant_msg_start", tk.LEFT)

        # Bind user scroll events to disable auto-scroll
        self.ui.chat.display.bind("<MouseWheel>", self._on_manual_scroll)
        self.ui.chat.display.bind("<Button-4>", self._on_manual_scroll)
        self.ui.chat.display.bind("<Button-5>", self._on_manual_scroll)
        self.ui.chat.display.bind("<B1-Motion>", self._on_manual_scroll)

    def _setup_input_area(self):
        """Sets up the user input field at the bottom."""
        line_h = font.Font(font=self.fonts["base"]).metrics('linespace')
        self.ui.input.canvas = tk.Canvas(
            self.root, bg=Theme.BG_COLOR, highlightthickness=0,
            height=line_h + 20
        )
        self.ui.input.canvas.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(7, 20)
        )
        self.ui.input.bg_id = round_rectangle(
            self.ui.input.canvas, (4, 4, 10, 10), radius=20,
            outline=Theme.COMMAND_COLOR, width=6, fill=Theme.INPUT_BG
        )
        self.ui.input.inner = tk.Frame(self.ui.input.canvas, bg=Theme.INPUT_BG)
        self.ui.input.window_id = self.ui.input.canvas.create_window(
            5, 5, anchor="nw", window=self.ui.input.inner
        )
        self.ui.input.inner.grid_columnconfigure(0, weight=1)
        self.ui.input.inner.grid_rowconfigure(0, weight=1)

        self.ui.input.field = tk.Text(
            self.ui.input.inner, height=1, width=1, wrap='word',
            font=self.fonts["base"], bg=Theme.INPUT_BG, fg=Theme.FG_COLOR,
            insertbackground=Theme.FG_COLOR, borderwidth=0,
            highlightthickness=0, padx=15, pady=10
        )
        self.ui.input.field.grid(row=0, column=0, sticky="nsew")
        self.ui.input.field.tag_config(
            "command_highlight", foreground=Theme.SLASH_COLOR,
            font=self.fonts["bold"]
        )

    def _configure_tags(self):
        """Sets up text tags for different message types."""
        cfg = self.ui.chat.display.tag_config
        cfg("user", foreground=Theme.USER_COLOR, font=self.fonts["bold"])
        cfg("assistant", foreground=Theme.FG_COLOR, font=self.fonts["base"])
        cfg("indicator", foreground=Theme.INDICATOR_COLOR, font=self.fonts["indicator"])
        cfg("system", foreground=Theme.SYSTEM_COLOR, font=self.fonts["small"],
            tabs=("240",))
        cfg("error", foreground=Theme.ERROR_COLOR)
        cfg("cancelled", foreground=Theme.CANCELLED_COLOR, font=self.fonts["bold"])
        cfg("md_bold", font=self.fonts["bold"])
        cfg("md_italic", font=self.fonts["italic"])
        cfg("md_bold_italic", font=self.fonts["bold_italic"])
        cfg("md_sub", font=self.fonts["small_base"], offset=-2)
        cfg("md_sup", font=self.fonts["small_base"], offset=4)
        cfg("md_strikethrough", overstrike=True)
        cfg("md_code", font=self.fonts["code"], background=Theme.CODE_BG,
            foreground=Theme.CODE_FG)
        cfg("md_h1", font=self.fonts["h1"], spacing1=10, spacing3=5)
        cfg("md_h2", font=self.fonts["h2"], spacing1=8, spacing3=4)
        cfg("md_h3", font=self.fonts["h3"], spacing1=6, spacing3=3)
        cfg("md_link", foreground=Theme.LINK_COLOR)
        cfg("md_quote", font=self.fonts["italic"], foreground=Theme.SYSTEM_COLOR,
            lmargin1=40, lmargin2=40)
        cfg("md_quote_bar", foreground=Theme.ACCENT_COLOR, font=self.fonts["bold"])

    def _bind_events(self):
        """Binds GUI events to their respective handlers."""
        self.ui.chat.canvas.bind("<Configure>", self._on_chat_canvas_configure)
        self.ui.input.canvas.bind("<Configure>", self._on_lower_canvas_configure)
        self.ui.input.field.bind("<Tab>", self._handle_tab)
        self.ui.input.field.bind("<Return>", self._handle_return)
        self.ui.input.field.bind("<KeyRelease>", self._on_key_release)
        self.ui.input.field.bind("<Control-c>", self._cancel_generation)
        self.ui.input.field.bind("<Configure>", self._adjust_input_height)

    def _stop_active_process(self):
        """Safely terminates any active background process."""
        if self.state.process.active:
            try:
                if self.state.process.active.poll() is None:
                    os.kill(self.state.process.active.pid, signal.SIGTERM)
            except OSError:
                pass
            self.state.process.active = None

    def _update_canvas_region(self, cfg: CanvasConfig):
        return update_canvas_region(cfg)

    def _on_chat_canvas_configure(self, event):
        """Updates the chat area border on resize."""
        if event.width < 50 or event.height < 50:
            return
        cfg = CanvasConfig(
            canvas=self.ui.chat.canvas,
            bg_id=self.ui.chat.bg_id,
            size=(event.width, event.height),
            radius=25,
            style=(Theme.ACCENT_COLOR, 6, Theme.BG_COLOR),
            win_id=self.ui.chat.window_id,
            pad=(12, 12)
        )
        self.ui.chat.bg_id = self._update_canvas_region(cfg)

    def _on_sidebar_canvas_configure(self, event):
        """Maintains the sidebar background shape on resize."""
        w, h = event.width, event.height
        cfg = CanvasConfig(
            canvas=self.ui.sidebar.canvas,
            bg_id=self.ui.sidebar.bg_id,
            size=(w, h),
            radius=25,
            style=(Theme.ACCENT_COLOR, 6, Theme.INPUT_BG),
            win_id=self.ui.sidebar.window_id,
            pad=(12, 12)
        )
        self.ui.sidebar.bg_id = self._update_canvas_region(cfg)

    def _on_manual_scroll(self, _):
        """Disables auto-scroll when user interacts with the chat history."""
        # Only disable if user actually scrolls UP
        if self.ui.chat.display.yview()[1] < 0.99:
            self.state.auto_scroll = False
            self._check_scroll_position()

    def scroll_to_bottom(self):
        """Scrolls the chat display to the very bottom."""
        self.state.auto_scroll = True
        self.ui.chat.display.see(tk.END)
        self._check_scroll_position()

    def _check_scroll_position(self):
        """Shows or hides the jump button based on scroll state."""
        if not self.ui.chat.jump_btn_canvas:
            return

        is_at_bottom = self.ui.chat.display.yview()[1] >= 0.99
        if is_at_bottom:
            self.state.auto_scroll = True
            self.ui.chat.jump_btn_canvas.place_forget()
        elif not self.state.auto_scroll:
            # Place relative to the container. Since jump_btn_canvas parent is ui.chat.canvas,
            # and ui.chat.canvas fills the area, this works.
            # However, ensure it's on top. 'place' usually puts it on top.
            self.ui.chat.jump_btn_canvas.place(
                in_=self.ui.chat.canvas, relx=1.0, rely=1.0, anchor="se", x=-30, y=-30
            )
            # Explicit Tcl call to avoid Canvas.lift() override issues
            self.root.tk.call('raise', str(self.ui.chat.jump_btn_canvas))

    def _on_lower_canvas_configure(self, event):
        """Updates the input area border on resize."""
        if event.width > 50 and event.height > 20:
            self._update_lower_border()

    def _adjust_input_height(self, _=None):
        adjust_input_height(self.ui.input)


    def _update_lower_border(self, forced_h=None):
        self.ui.input.bg_id = update_lower_border(self.ui.input, forced_h)

    def _handle_tab(self, _):
        return handle_tab(self.ui.input, SLASH_COMMANDS)

    def _handle_return(self, event):
        """Sends the message on Enter, inserts newline on Shift+Enter."""
        if not event.state & 0x1:
            self.send_message()
            return "break"
        return None

    def _on_key_release(self, event=None):
        """Triggers command highlighting and height adjustment."""
        if event and event.keysym in ("Shift_L", "Shift_R"):
            return
        highlight_commands(self.ui.input, SLASH_COMMANDS)
        self._adjust_input_height()

    def _highlight_commands(self):
        highlight_commands(self.ui.input, SLASH_COMMANDS)

    def send_message(self):
        """Validates input and initiates assistant processing."""
        if self.state.process.is_busy:
            return

        user_input = self.ui.input.field.get("1.0", "end-1c").strip()
        if not user_input:
            return

        self.state.process.is_busy = True
        self.ui.input.field.delete("1.0", tk.END)
        self._adjust_input_height()
        self.state.msg_queue.put(("text", user_input + "\n", "user"))
        self.process_input(user_input)

    def _get_assistant_msgs(self, user_input, search_context):
        """Constructs the message list for the LLM."""
        msgs = [
            {"role": "system", "content": self.state.assistant.system_prompt}
        ] + self.state.assistant.messages + [{"role": "user", "content": user_input}]

        if search_context:
            final_instr = (
                "CRITICAL FACTUAL OVERRIDE: You MUST use the following search "
                "data to answer. This data is THE current reality.\n\n"
                f"<SEARCH_CONTEXT>\n{search_context}\n</SEARCH_CONTEXT>\n\n"
                f"ORIGINAL INTENT: Find: '{user_input}'\n\n"
                "STRICT DIRECTIVES:\n"
                "1. Answer using ONLY relevant facts from <SEARCH_CONTEXT>.\n"
                "2. NEVER mention internal tags like '<SEARCH_CONTEXT>'.\n"
                "3. Ignore noise. 4. If data is missing, admit it."
            )
            msgs.append({"role": "system", "content": final_instr})
        return msgs

    def _run_streaming_chat(self, user_input, complexity, msgs):
        """Handles the streaming response from the LLM."""
        try:
            full_resp = ""
            stream = get_ollama_client().chat(
                model=config.MODEL_NAME, messages=msgs,
                stream=True, options=complexity['params']
            )
            for chunk in stream:
                if self.state.process.stop_generation:
                    break
                cnt = chunk['message']['content']
                full_resp += cnt
                self.state.msg_queue.put(("text", cnt, "assistant"))

            self._finalize_chat_response(user_input, full_resp)
        except (ollama.ResponseError, AttributeError, ConnectionError) as exc:
            error_print(f"Assistant Error: {format_error_msg(exc)}")

    def _finalize_chat_response(self, user_input, full_resp):
        """Stores result and triggers final rendering."""
        if self.state.process.stop_generation:
            self.state.msg_queue.put(("text", " [Interrupted]", "cancelled"))
            res = full_resp + " [Interrupted]"
        else:
            self.state.msg_queue.put(("text", "\n", "assistant"))
            res = full_resp

        self.state.assistant.messages.extend([
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": res}
        ])

        self.state.msg_queue.put(("final_render", "", "assistant"))
        if not self.state.process.stop_generation:
            self.state.assistant.update_memory_async(user_input, full_resp)

        if len(self.state.assistant.messages) > 20:
            self.state.assistant.messages = self.state.assistant.messages[-20:]

    def process_input(self, user_input):
        """Orchestrates complexity analysis, search, and LLM chat."""
        self.state.process.stop_generation = False
        try:
            cmd_map = {
                '/clear': self._cmd_clear, '/debug': self._cmd_debug,
                '/forget': self._cmd_forget, '/info': self._cmd_info,
                '/help': self._cmd_help, '/exit': self._cmd_exit,
                '/model': self._cmd_model,
                'exit': self._cmd_exit, 'quit': self._cmd_exit
            }
            parts = user_input.lower().split()
            first = parts[0] if parts else ""
            if first in cmd_map:
                cmd_map[first](user_input)
                return
            if first == '/bypass':
                self._cmd_bypass(user_input)
                return

            self.state.msg_queue.put(("start_indicator", None, None))

            def run_assistant():
                try:
                    complexity = ComplexityScorer.analyze(user_input)

                    skip_search = complexity['level'] == ComplexityScorer.LEVEL_MINIMAL
                    ctx = self.state.assistant.decide_and_search(
                        user_input, skip_llm=skip_search
                    )

                    self.state.assistant.update_system_prompt(user_input)
                    msgs = self._get_assistant_msgs(user_input, ctx)
                    self._run_streaming_chat(user_input, complexity, msgs)
                finally:
                    self.state.msg_queue.put(("enable", None, None))

            threading.Thread(target=run_assistant, daemon=True).start()

        except (RuntimeError, ValueError, AttributeError, KeyError, ollama.ResponseError) as exc:
            logger.error("Error processing input: %s", exc)
            self.state.msg_queue.put(("text", f"Error: {format_error_msg(exc)}\n", "error"))
            self.state.msg_queue.put(("enable", None, None))

    def _cmd_exit(self, _):
        logger.info("Exit command received.")
        self.state.msg_queue.put(("quit", None, None))

    def _cmd_clear(self, _):
        if self.state.assistant:
            self.state.assistant.messages = []
            self.markdown_engine.clear()
            info_print("Conversation history cleared.")
            self.state.msg_queue.put(("clear", None, None))
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_forget(self, _):
        if self.state.assistant:
            info_print("Requesting to forget long-term memory...")
            self.state.assistant.clear_long_term_memory()
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_debug(self, _):
        config.DEBUG = not config.DEBUG
        self.settings.set("debug", config.DEBUG)
        msg = f"[*] Debug mode {"ENABLED" if config.DEBUG else "DISABLED"}"
        info_print(msg)
        logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_info(self, _):
        self.state.msg_queue.put(("toggle_info", None, None))
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_help(self, _):
        logger.info("Help command invoked.")
        lines = []
        for cmd, desc in SLASH_COMMANDS:
            if cmd == "/exit":
                lines.append("")
            lines.append(f"    {cmd}\t{desc}")
        print("Available Commands:\n" + "\n".join(lines))
        self.state.msg_queue.put(("separator", None, None))
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_model(self, _):
        """Displays the sidebar to switch the current Ollama model."""
        if not self.state.assistant:
            self.state.msg_queue.put(("enable", None, None))
            return

        if self.state.ui_state.sidebar_visible:
            self._close_sidebar()
            return

        models = self.state.assistant.get_available_models()
        if not models:
            error_print("No models found in Ollama.")
            self.state.msg_queue.put(("enable", None, None))
            return

        self._build_model_sidebar(models)

    def _build_model_sidebar(self, models):
        """Constructs the model selection UI components."""
        for widget in self.ui.sidebar.frame.winfo_children():
            widget.destroy()

        self.state.ui_state.sidebar_visible = True
        self.ui.sidebar.frame.grid()

        header = tk.Frame(self.ui.sidebar.frame, bg=Theme.BG_COLOR)
        header.pack(fill="x", padx=10, pady=(5, 0))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(header, text="Models", font=self.fonts["h3"],
                 bg=Theme.BG_COLOR, fg=Theme.FG_COLOR).grid(row=0, column=0)

        tk.Button(header, text="<", command=self._close_sidebar, font=("Roboto", 24),
                  bg=Theme.BG_COLOR, fg=Theme.SYSTEM_COLOR, borderwidth=0,
                  highlightthickness=0, activebackground=Theme.BG_COLOR,
                  activeforeground=Theme.FG_COLOR, cursor="hand2").grid(row=0, column=0, sticky="w")

        self.ui.sidebar.canvas = tk.Canvas(
            self.ui.sidebar.frame, bg=Theme.BG_COLOR, highlightthickness=0
        )
        self.ui.sidebar.canvas.pack(fill="both", expand=True, padx=10, pady=(2, 0))

        self.ui.sidebar.bg_id = round_rectangle(
            self.ui.sidebar.canvas, (4, 4, 10, 10), radius=25,
            outline=Theme.ACCENT_COLOR, width=6, fill=Theme.INPUT_BG
        )

        inner = tk.Frame(self.ui.sidebar.canvas, bg=Theme.INPUT_BG)
        self.ui.sidebar.window_id = self.ui.sidebar.canvas.create_window(
            12, 12, anchor="nw", window=inner
        )

        self._create_model_listbox(inner, models)
        self.ui.sidebar.canvas.bind("<Configure>", self._on_sidebar_canvas_configure)

    def _create_model_listbox(self, parent, models):
        """Creates and populates the model listbox."""
        listbox = tk.Listbox(
            parent, font=self.fonts["base"], bg=Theme.INPUT_BG,
            fg=Theme.FG_COLOR, selectbackground=Theme.USER_COLOR,
            selectforeground=Theme.BG_COLOR, borderwidth=0,
            highlightthickness=0, activestyle='none', width=25
        )
        listbox.pack(side="left", fill="both", expand=True)

        scrollbar = CustomScrollbar(parent, command=listbox.yview, bg=Theme.INPUT_BG)
        scrollbar.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scrollbar.set)

        curr = config.MODEL_NAME
        for i, model in enumerate(models):
            display_name = f"{model} (Current)" if model == curr else model
            listbox.insert(tk.END, display_name)
            if model == curr:
                listbox.selection_set(i)
                listbox.see(i)

        def _confirm(_=None):
            selection = listbox.curselection()
            if selection:
                new_model = models[selection[0]]
                if new_model != config.MODEL_NAME:
                    self._switch_model_logic(new_model)
            self._close_sidebar()

        listbox.bind("<Return>", _confirm)
        listbox.bind("<Double-Button-1>", _confirm)
        listbox.focus_set()

    def _switch_model_logic(self, new_model):
        """Handles the actual model switching process."""
        info_print(f"Switching to model: {new_model}...")
        self.state.assistant.switch_model(new_model)
        self.settings.set("model_name", new_model)
        info_print(f"Model switched to {new_model}. History cleared.")
        self.markdown_engine.clear()
        self.state.msg_queue.put(("clear", None, None))
        self._update_info_display()

    def _close_sidebar(self):
        """Closes the model selection sidebar."""
        self.state.ui_state.sidebar_visible = False
        self.ui.sidebar.frame.grid_remove()
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_bypass(self, user_input):
        raw = user_input[7:].strip()
        logger.info("Bypass command invoked: %s...", raw[:50])
        if not raw:
            self.state.msg_queue.put(("text", "Usage: /bypass <prompt>\n", "system"))
            self.state.msg_queue.put(("enable", None, None))
        else:
            self.state.msg_queue.put(("start_indicator", None, None))

            def _assign_proc(proc):
                self.state.process.active = proc

            def run_bypass():
                try:
                    run_ollama_bypass(
                        raw, self.state.msg_queue,
                        lambda: self.state.process.stop_generation,
                        start_callback=_assign_proc
                    )
                    msg = "[Interrupted]" if self.state.process.stop_generation else "\n"
                    tag = "cancelled" if self.state.process.stop_generation else "assistant"
                    self.state.msg_queue.put(("text", msg, tag))
                    if not self.state.process.stop_generation:
                        self.state.msg_queue.put(("final_render", "", "assistant"))
                    self._stop_active_process()
                finally:
                    self.state.msg_queue.put(("enable", None, None))

            threading.Thread(target=run_bypass, daemon=True).start()

    def _replace_last_message(self, text, tag):
        """Replaces the last message in the chat."""
        self.ui.chat.display.config(state='normal')
        try:
            self.ui.chat.display.delete("end-1c linestart", "end-1c")
            self.ui.chat.display.insert("end-1c", text, tag)
            if self.state.auto_scroll:
                self.ui.chat.display.see(tk.END)
        except tk.TclError:
            pass
        finally:
            self.ui.chat.display.config(state='disabled')

    def _render_assistant_stream(self, text, final):
        """Helper to render assistant text stream with markdown."""
        if not final:
            self.state.response.full_text += text
        if "\n" in text or final:
            cur = self.state.response.full_text.strip()
            if len(cur) > self.state.response.last_rendered_len or final:
                self.ui.chat.display.delete("assistant_msg_start", tk.END)

                # Ensure we are still on a new line after deletion
                if self.ui.chat.display.index("assistant_msg_start") != "1.0":
                    if self.ui.chat.display.get("assistant_msg_start - 1 chars") != "\n":
                        self.ui.chat.display.mark_gravity("assistant_msg_start", tk.RIGHT)
                        self.ui.chat.display.insert("assistant_msg_start", "\n")
                        self.ui.chat.display.mark_gravity("assistant_msg_start", tk.LEFT)

                if self.state.indicator.active:
                    self.ui.chat.display.insert(
                        "assistant_msg_start", f"{self.state.indicator.char} ", "indicator"
                    )
                try:
                    toks = self.md_parser(cur)
                    self.markdown_engine.render_tokens(toks, "assistant")
                    self.state.response.last_rendered_len = len(cur)
                except (ValueError, TypeError):
                    self.ui.chat.display.insert(
                        "end-1c", self.state.response.full_text, "assistant"
                    )
            if final:
                self._finalize_message_turn()
        else:
            self.ui.chat.display.insert("end-1c", text, "assistant")

    def _display_message(self, text, tag, final=False):
        """Renders messages in the chat display with Markdown support."""
        self.ui.chat.display.config(state='normal')
        try:
            if tag == "cancelled":
                self.ui.chat.display.delete("assistant_msg_start", tk.END)
                try:
                    toks = self.md_parser(self.state.response.full_text.strip())
                    self.markdown_engine.render_tokens(toks, "assistant")
                except (ValueError, TypeError):
                    self.ui.chat.display.insert(
                        "end-1c", self.state.response.full_text, "assistant"
                    )
                self.ui.chat.display.insert("end-1c", text, "cancelled")
                self._finalize_message_turn()
            elif tag == "assistant":
                self._render_assistant_stream(text, final)
            else:
                if self.state.indicator.active and tag in ("system", "error"):
                    # Insert before the indicator/response region to avoid interference
                    if not text.endswith("\n"):
                        text += "\n"
                    self.ui.chat.display.mark_gravity("assistant_msg_start", tk.RIGHT)
                    self.ui.chat.display.insert("assistant_msg_start", text, tag)
                    self.ui.chat.display.mark_gravity("assistant_msg_start", tk.LEFT)
                else:
                    self.ui.chat.display.insert("end-1c", text, tag)
                self.state.response.full_text = ""
                self.state.response.last_rendered_len = 0
                if tag == "user":
                    self._finalize_message_turn()
        except (tk.TclError, ValueError) as exc:
            self.ui.chat.display.insert("end-1c", f"\n[GUI Error: {exc}]\n", "error")
        finally:
            if self.state.auto_scroll:
                self.ui.chat.display.see(tk.END)
            self.ui.chat.display.config(state='disabled')

    def _finalize_message_turn(self):
        """Handles post-message-turn cleanup and UI elements."""
        try:
            # Only delete the trailing newline if it's strictly AFTER the assistant_msg_start mark.
            # This prevents merging lines if the response is empty.
            if self.ui.chat.display.compare("end-2c", ">", "assistant_msg_start"):
                if self.ui.chat.display.get("end-2c", "end-1c") == "\n":
                    self.ui.chat.display.delete("end-2c", "end-1c")
            self._insert_separator(height=40)
            self.ui.chat.display.mark_set("assistant_msg_start", "end-1c")
            self.state.response.full_text = ""
        except tk.TclError:
            pass

    def _insert_separator(self, height=25):
        """Inserts a thematic separator in the chat."""
        try:
            # Ensure separator starts on a new line
            if self.ui.chat.display.index("end-1c") != "1.0":
                if self.ui.chat.display.get("end-2c", "end-1c") != "\n":
                    self.ui.chat.display.insert("end-1c", "\n")

            w = max(600, self.ui.chat.display.winfo_width() - 40)
            canv = tk.Canvas(self.ui.chat.display, bg=Theme.BG_COLOR, height=height,
                             highlightthickness=0, width=w)
            canv.create_line(10, height//2, w-10, height//2, fill=Theme.SEPARATOR_COLOR)

            def _on_mousewheel(event):
                self.ui.chat.display.yview_scroll(int(-1*(event.delta/120)), "units")
            def _on_linux_up(_):
                self.ui.chat.display.yview_scroll(-1, "units")
            def _on_linux_down(_):
                self.ui.chat.display.yview_scroll(1, "units")

            canv.bind("<MouseWheel>", _on_mousewheel)
            canv.bind("<Button-4>", _on_linux_up)
            canv.bind("<Button-5>", _on_linux_down)

            self.ui.chat.display.window_create("end-1c", window=canv)
            self.ui.chat.display.insert("end-1c", "\n")
        except tk.TclError:
            self.ui.chat.display.insert("end-1c", "-"*20 + "\n")

    def _handle_tooltip(self, _, url):
        """Displays a tooltip for links."""
        if not url:
            if self.ui.tooltip_window:
                try:
                    self.ui.tooltip_window.destroy()
                except tk.TclError:
                    pass
                self.ui.tooltip_window = None
            return
        if self.ui.tooltip_window:
            return
        try:
            xp, yp = self.root.winfo_pointerx() + 15, self.root.winfo_pointery() + 15
            self.ui.tooltip_window = win = tk.Toplevel(self.root)
            win.wm_overrideredirect(True)
            win.wm_geometry(f"+{xp}+{yp}")
            tk.Label(win, text=f"Ctrl + Click to open {url}",
                     background=Theme.TOOLTIP_BG, foreground=Theme.FG_COLOR,
                     relief='solid', borderwidth=1, font=self.fonts["tooltip"],
                     padx=5, pady=2).pack()
        except tk.TclError:
            self.ui.tooltip_window = None

    def _check_queue(self):
        """Polls the message queue for UI updates."""
        try:
            while not self.state.msg_queue.empty():
                action, content, tag = self.state.msg_queue.get_nowait()
                self._dispatch_queue_action(action, content, tag)
        except queue.Empty:
            pass
        except (tk.TclError, ValueError) as exc:
            debug_print(f"Error processing queue: {exc}")
        finally:
            self.root.after(30, self._check_queue)

    def _dispatch_queue_action(self, action, content, tag):
        """Dispatcher for UI actions from the message queue."""
        if action == "text":
            if tag == "cancelled":
                self.state.indicator.active = False
            self._display_message(content, tag)
        elif action == "start_indicator":
            self._start_indicator()
        elif action == "replace_last":
            self._replace_last_message(content, tag)
        elif action == "clear":
            self.ui.chat.display.config(state='normal')
            self.ui.chat.display.delete("1.0", tk.END)
            self.ui.chat.display.config(state='disabled')
            self._display_message("Type /help for commands.\n\n", "system")
        elif action == "separator":
            self.ui.chat.display.config(state='normal')
            self._insert_separator(height=40)
            self.ui.chat.display.config(state='disabled')
        elif action == "final_render":
            self.state.indicator.active = False
            self._display_message("", tag, final=True)
            self._update_info_display()
        elif action == "toggle_info":
            self.state.ui_state.show_info = self.ui.info_panel.toggle()
            self.settings.set("show_info", self.state.ui_state.show_info)
            self._update_info_display()
        elif action == "update_info_ui":
            self.ui.info_panel.update_stats(content)
        elif action == "enable":
            self.state.process.is_busy = False
            self.ui.input.field.focus_set()
            self._adjust_input_height()
        elif action == "quit":
            self.root.quit()

    def _update_info_display(self):
        """Fetches and displays model info in the info panel."""
        if not self.state.ui_state.show_info or not self.state.assistant:
            return

        def _fetch():
            try:
                info = self.state.assistant.get_model_info()
                self.state.msg_queue.put(("update_info_ui", info, None))
            except ConnectionError:
                # Silently ignore connection errors during background stats refresh
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def _cancel_generation(self, _=None):
        """Cancels any ongoing model generation."""
        if self.state.process.is_busy:
            self.state.process.stop_generation = True
            self._stop_active_process()

    def _on_close(self):
        """Handles application shutdown."""
        self._stop_active_process()
        self.root.destroy()

    def _start_indicator(self):
        """Starts the thinking/responding indicator."""
        if not self.state.indicator.active:
            self.state.indicator.active = True
            self.state.indicator.char = config.INDICATOR_CHARS[0]
            self.ui.chat.display.config(state='normal')
            try:
                # Ensure we start on a new line
                if self.ui.chat.display.index("end-1c") != "1.0":
                    if self.ui.chat.display.get("end-2c", "end-1c") != "\n":
                        self.ui.chat.display.insert("end-1c", "\n")

                # Move mark to current end to isolate from previous logs
                self.ui.chat.display.mark_set("assistant_msg_start", "end-1c")

                self.ui.chat.display.insert(
                    "assistant_msg_start", f"{self.state.indicator.char} ", "indicator"
                )
            except tk.TclError:
                pass
            finally:
                self.ui.chat.display.config(state='disabled')
            self._toggle_indicator()

    def _toggle_indicator(self):
        """Alternates the indicator symbol every second."""
        if not self.state.indicator.active:
            return

        chars = config.INDICATOR_CHARS
        try:
            idx = chars.index(self.state.indicator.char)
            self.state.indicator.char = chars[(idx + 1) % len(chars)]
        except ValueError:
            self.state.indicator.char = chars[0]

        self._update_indicator_ui()
        self.root.after(700, self._toggle_indicator)

    def _update_indicator_ui(self):
        """Updates the indicator symbol in the chat display."""
        if not self.state.indicator.active:
            return
        self.ui.chat.display.config(state='normal')
        try:
            # Replace only the symbol character, preserving the trailing space
            self.ui.chat.display.delete("assistant_msg_start", "assistant_msg_start + 1 chars")
            self.ui.chat.display.insert(
                "assistant_msg_start", self.state.indicator.char, "indicator"
            )
        except tk.TclError:
            pass
        finally:
            self.ui.chat.display.config(state='disabled')

if __name__ == "__main__":
    root_win = tk.Tk()
    AssistantApp(root_win)
    root_win.mainloop()
