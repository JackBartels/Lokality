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

from PIL import Image, ImageTk
import mistune
import ollama
from mistune.plugins.formatting import superscript, subscript

import config
import local_assistant
from complexity_scorer import ComplexityScorer
from config import VERSION
from logger import logger
from markdown_engine import MarkdownEngine
from profiler import Profiler
from settings import Settings
from shell_integration import run_ollama_bypass
import theme as Theme
from app_state import AppState, AppUI, SLASH_COMMANDS
from ui_components import InfoPanel, ProfilerPanel
from ui_helpers import (
    update_canvas_region, update_lower_border, highlight_commands, handle_tab,
    adjust_input_height, configure_chat_tags, insert_chat_separator,
    build_model_sidebar, handle_link_tooltip, build_chat_area, StyleConfig,
    build_input_area
)
from ui_dialogs import show_forget_dialog
from utils import (
    CanvasConfig,
    SidebarCallbacks,
    SidebarConfig,
    RedirectedStdout,
    debug_print,
    error_print,
    format_error_msg,
    get_ollama_client,
    info_print,
    thread_excepthook,
    verify_env_health,
)

threading.excepthook = thread_excepthook

class AssistantApp:
    """The main application class for the Lokality GUI."""
    def __init__(self, root, skip_init=False):
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
        self.state.ui_state.show_profiler = self.settings.get("show_profiler", False)
        Profiler().enabled = self.state.ui_state.show_profiler
        config.MODEL_NAME = self.settings.get("model_name", config.MODEL_NAME)
        if config.DEBUG:
            logger.setLevel(logging.DEBUG)

        self.ui = AppUI()

        self._setup_markdown()
        self._setup_ui()
        self._setup_window_icon()

        self.root.bind("<Escape>", self._cancel_generation)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._check_queue)

        sys.stdout = RedirectedStdout(self.state.msg_queue, "system")
        sys.stderr = RedirectedStdout(self.state.msg_queue, "error")

        info_print(f"Lokality {VERSION} starting...")
        if not skip_init:
            threading.Thread(target=self._initialize_async, daemon=True).start()

    def _setup_markdown(self):
        """Initializes the markdown engine and parser."""
        try:
            self.ui.markdown.engine = MarkdownEngine(
                None, self._handle_tooltip
            )
            self.ui.markdown.parser = mistune.create_markdown(
                renderer=None,
                plugins=['table', 'strikethrough', superscript, subscript]
            )
        except (ImportError, AttributeError):
            self.ui.markdown.engine = MarkdownEngine(
                None, self._handle_tooltip
            )
            self.ui.markdown.parser = lambda x: [{"type": "text", "text": x}]

    def _initialize_async(self):
        """Heavy initialization tasks run in background."""
        try:
            self.state.assistant = local_assistant.LocalChatAssistant()
            self.state.assistant.stop_signal = lambda: self.state.process.stop_generation
            self.state.assistant.on_search_start = lambda: self.state.msg_queue.put(
                ("search_start", None, None)
            )
            self.state.assistant.on_search_end = lambda: self.state.msg_queue.put(
                ("search_end", None, None)
            )
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

    def _setup_window_icon(self):
        """Loads and sets the application window icon."""
        try:
            # Use absolute path to the res/icon.png
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "res", "icon.png"
            )
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                # Keep a reference to prevent garbage collection
                self.ui.icon_img = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self.ui.icon_img)
        except (OSError, tk.TclError, ImportError) as exc:
            debug_print(f"Failed to load window icon: {exc}")

    def _setup_ui(self):
        """Configures the main window layout and components."""
        self.root.grid_rowconfigure(0, weight=0) # Profiler row
        self.root.grid_rowconfigure(1, weight=1) # Chat row
        self.root.grid_columnconfigure(0, weight=0) # Sidebar column
        self.root.grid_columnconfigure(1, weight=1) # Chat column

        self.ui.panels.profiler = ProfilerPanel(self.root, Theme, self.fonts)
        self.ui.panels.profiler.grid(row=0, column=0, columnspan=2, sticky="ew")
        if not self.state.ui_state.show_profiler:
            self.ui.panels.profiler.grid_remove()

        self._setup_sidebar()
        self._setup_chat_area()
        self.ui.markdown.engine.text_widget = self.ui.chat.display

        self.ui.panels.info = InfoPanel(self.root, Theme, self.fonts)
        self.ui.panels.info.show_info = self.state.ui_state.show_info
        self.ui.panels.info.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=0)
        if not self.state.ui_state.show_info:
            self.ui.panels.info.grid_remove()

        self._setup_input_area()
        self._bind_events()
        self._adjust_input_height()

    def _setup_sidebar(self):
        """Initializes the model selection sidebar."""
        self.ui.sidebar.frame = tk.Frame(
            self.root, bg=Theme.BG_COLOR, width=0, highlightthickness=0
        )
        self.ui.sidebar.frame.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(10, 7))
        self.ui.sidebar.frame.grid_remove() # Hidden by default

    def _setup_chat_area(self):
        """Sets up the scrollable chat display area."""
        def on_display_scroll(*args):
            self.ui.chat.scrollbar.set(*args)
            self._check_scroll_position()

        callbacks = {
            "on_scroll": on_display_scroll,
            "on_manual_scroll": self._on_manual_scroll,
            "scroll_to_bottom": self.scroll_to_bottom
        }
        style = StyleConfig(theme=Theme, fonts=self.fonts)
        build_chat_area(self.root, self.ui.chat, style, callbacks)

        self._configure_tags()

    def _setup_input_area(self):
        """Sets up the user input field at the bottom."""
        build_input_area(self.root, self.ui.input, Theme, self.fonts)

    def _configure_tags(self):
        """Sets up text tags for different message types."""
        configure_chat_tags(self.ui.chat.display, Theme, self.fonts)

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
            pad=(15, 15)
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
            self.state.ui_state.auto_scroll = False
            self._check_scroll_position()

    def scroll_to_bottom(self):
        """Scrolls the chat display to the very bottom."""
        self.state.ui_state.auto_scroll = True
        self.ui.chat.display.see(tk.END)
        self._check_scroll_position()

    def _check_scroll_position(self):
        """Shows or hides the jump button based on scroll state."""
        if not self.ui.chat.jump_btn_canvas:
            return

        is_at_bottom = self.ui.chat.display.yview()[1] >= 0.99
        if is_at_bottom:
            self.state.ui_state.auto_scroll = True
            self.ui.chat.jump_btn_canvas.place_forget()
        elif not self.state.ui_state.auto_scroll:
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
        if self.state.process.stop_generation:
            self.state.msg_queue.put(("text", " [Interrupted]", "cancelled"))
            return

        Profiler().start("Response Generation")
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

            Profiler().stop("Response Generation")
            self._finalize_chat_response(user_input, full_resp)
        except (ollama.ResponseError, AttributeError, ConnectionError) as exc:
            Profiler().stop("Response Generation")
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
            def on_mem_complete():
                if self.state.ui_state.show_profiler:
                    self.state.msg_queue.put((
                        "update_profiler_ui", Profiler().get_latest_data(), None
                    ))

            self.state.assistant.update_memory_async(
                user_input, full_resp, on_complete=on_mem_complete
            )

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
                '/model': self._cmd_model, '/profiler': self._cmd_profiler,
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
                    if self.state.process.stop_generation:
                        self.state.msg_queue.put(("text", " [Interrupted]", "cancelled"))
                        return

                    skip_search = complexity['level'] == ComplexityScorer.LEVEL_MINIMAL

                    # PARALLEL STEP: Retrieve memory facts and check search
                    prep_result = self.state.assistant.prepare_turn(
                        user_input, skip_search=skip_search
                    )

                    if self.state.process.stop_generation:
                        self.state.msg_queue.put(("text", " [Interrupted]", "cancelled"))
                        return

                    facts = prep_result["facts"]
                    ctx = prep_result["search_context"]

                    # ROLEPLAY/CRISIS detection
                    stype = prep_result.get("search_type")
                    if stype == "roleplay":
                        debug_print("[*] Roleplay detected: Maximizing creativity parameters.")
                        complexity['params']['temperature'] = 1.0
                        complexity['params']['top_p'] = 1.0
                    elif stype == "crisis":
                        debug_print("[*] Crisis detected: Prioritizing safety protocol.")

                    self.state.assistant.update_system_prompt(
                        user_input, facts=facts
                    )
                    msgs = self._get_assistant_msgs(user_input, ctx)
                    self._run_streaming_chat(user_input, complexity, msgs)
                except Exception as exc: # pylint: disable=broad-exception-caught
                    error_print(f"Thread Error ({threading.current_thread().name}): {exc}")
                    logger.exception("Assistant thread failed")
                finally:
                    if self.state.ui_state.show_profiler:
                        self.state.msg_queue.put((
                            "update_profiler_ui", Profiler().get_latest_data(), None
                        ))
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
            self.state.assistant.clear_conversation()
            self.ui.markdown.engine.clear()
            info_print("Conversation history cleared.")
            self.state.msg_queue.put(("clear", None, None))
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_forget(self, _):
        """Initiates the confirmation for clearing long-term memory."""
        if self.settings.get("skip_forget_confirmation"):
            self._finalize_forget()
            return

        show_forget_dialog(
            self.root, self.fonts, self.settings,
            on_confirm=self._finalize_forget,
            on_cancel=lambda: self.state.msg_queue.put(("enable", None, None))
        )

    def _finalize_forget(self):
        """Actually clears the long-term memory."""
        if self.state.assistant:
            info_print("Requesting to forget long-term memory...")
            self.state.assistant.clear_long_term_memory()
            # Issue #52: Immediately reset long term memory rows count in info panel
            self._update_info_display()
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

    def _cmd_profiler(self, _):
        """Toggles the performance profiler display."""
        self.state.ui_state.show_profiler = not self.state.ui_state.show_profiler
        self.settings.set("show_profiler", self.state.ui_state.show_profiler)
        Profiler().enabled = self.state.ui_state.show_profiler

        if self.state.ui_state.show_profiler:
            self.ui.panels.profiler.grid()
            # Immediately show any existing data from the last turn
            self.ui.panels.profiler.update_data(Profiler().get_latest_data())
        else:
            self.ui.panels.profiler.grid_remove()
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
        self.state.ui_state.sidebar_visible = True
        self.ui.sidebar.frame.grid()
        callbacks = SidebarCallbacks(
            on_switch=self._switch_model_logic,
            on_close=self._close_sidebar,
            on_resize=self._on_sidebar_canvas_configure
        )
        cfg = SidebarConfig(
            parent=self.ui.sidebar.frame, theme=Theme, fonts=self.fonts,
            models=models, current_model=config.MODEL_NAME,
            callbacks=callbacks
        )
        self.ui.sidebar.canvas, self.ui.sidebar.bg_id, self.ui.sidebar.window_id = \
            build_model_sidebar(cfg)

    def _switch_model_logic(self, new_model):
        """Handles the actual model switching process."""
        info_print(f"Switching to model: {new_model}...")
        self.state.assistant.switch_model(new_model)
        self.settings.set("model_name", new_model)
        info_print(f"Model switched to {new_model}. History cleared.")
        self.ui.markdown.engine.clear()
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
            if self.state.ui_state.auto_scroll:
                self.ui.chat.display.see(tk.END)
        except tk.TclError:
            pass
        finally:
            self.ui.chat.display.config(state='disabled')

    def _render_assistant_stream(self, text, final):
        """Helper to render assistant text stream with markdown."""
        if not final:
            self.state.response.full_text += text

        # Sanitize buffer to prevent tag leakage
        self.state.response.full_text = self.state.response.full_text.replace(
            "<SEARCH_CONTEXT>", "").replace("</SEARCH_CONTEXT>", "")

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
                    toks = self.ui.markdown.parser(cur)
                    self.ui.markdown.engine.render_tokens(toks, "assistant")
                    self.state.response.last_rendered_len = len(cur)
                except (ValueError, TypeError):
                    self.ui.chat.display.insert(
                        "end-1c", self.state.response.full_text, "assistant"
                    )
            if final:
                self._finalize_message_turn()
        else:
            clean_text = text.replace("<SEARCH_CONTEXT>", "").replace("</SEARCH_CONTEXT>", "")
            self.ui.chat.display.insert("end-1c", clean_text, "assistant")

    def _display_message(self, text, tag, final=False):
        """Renders messages in the chat display with Markdown support."""
        self.ui.chat.display.config(state='normal')
        try:
            if tag == "cancelled":
                self.ui.chat.display.delete("assistant_msg_start", tk.END)
                try:
                    toks = self.ui.markdown.parser(self.state.response.full_text.strip())
                    self.ui.markdown.engine.render_tokens(toks, "assistant")
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
            if self.state.ui_state.auto_scroll:
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
            self._insert_separator(height=24)
            self.ui.chat.display.mark_set("assistant_msg_start", "end-1c")
            self.state.response.full_text = ""
        except tk.TclError:
            pass

    def _insert_separator(self, height=25):
        """Inserts a thematic separator in the chat."""
        insert_chat_separator(self.ui.chat.display, Theme, height=height)

    def _handle_tooltip(self, _, url):
        """Displays a tooltip for links."""
        self.ui.tooltip_window = handle_link_tooltip(
            self.root, self.ui.tooltip_window, url, Theme, self.fonts
        )

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
        dispatch = {
            "text": self._handle_action_text,
            "start_indicator": self._handle_action_start_indicator,
            "search_start": self._handle_action_search_start,
            "search_end": self._handle_action_search_end,
            "replace_last": self._replace_last_message,
            "clear": self._handle_action_clear,
            "separator": self._handle_action_separator,
            "final_render": self._handle_action_final_render,
            "toggle_info": self._handle_action_toggle_info,
            "update_info_ui": self._handle_action_update_info,
            "update_profiler_ui": self._handle_action_update_profiler,
            "enable": self._handle_action_enable,
            "quit": self._handle_action_quit
        }

        if action in dispatch:
            dispatch[action](content, tag)

    def _handle_action_update_info(self, content, _tag):
        """Handles update_info_ui action."""
        self.ui.panels.info.update_stats(content)

    def _handle_action_update_profiler(self, content, _tag):
        """Handles update_profiler_ui action."""
        self.ui.panels.profiler.update_data(content)

    def _handle_action_quit(self, _content, _tag):
        """Handles quit action."""
        self.root.quit()

    def _handle_action_text(self, content, tag):
        """Handles text action from queue."""
        if tag == "cancelled":
            self.state.indicator.active = False
        self._display_message(content, tag)

    def _handle_action_start_indicator(self, _content, _tag):
        """Handles start_indicator action from queue."""
        self._start_indicator()

    def _handle_action_search_start(self, _content, _tag):
        """Handles search_start action from queue."""
        self.state.indicator.mode = "searching"
        self.state.indicator.char = config.SEARCH_INDICATOR_CHAR
        self._update_indicator_ui()

    def _handle_action_search_end(self, _content, _tag):
        """Handles search_end action from queue."""
        self.state.indicator.mode = "thinking"
        self.state.indicator.char = config.INDICATOR_CHARS[0]
        self._update_indicator_ui()

    def _handle_action_clear(self, _content, _tag):
        """Handles clear action from queue."""
        self.ui.chat.display.config(state='normal')
        self.ui.chat.display.delete("1.0", tk.END)
        self.ui.chat.display.config(state='disabled')
        self._display_message("Type /help for commands.\n\n", "system")

    def _handle_action_separator(self, _content, _tag):
        """Handles separator action from queue."""
        self.ui.chat.display.config(state='normal')
        self._insert_separator(height=24)
        self.ui.chat.display.config(state='disabled')

    def _handle_action_final_render(self, _content, tag):
        """Handles final_render action from queue."""
        self.state.indicator.active = False
        self._display_message("", tag, final=True)
        self._update_info_display()

    def _handle_action_toggle_info(self, _content, _tag):
        """Handles toggle_info action from queue."""
        self.state.ui_state.show_info = self.ui.panels.info.toggle()
        self.settings.set("show_info", self.state.ui_state.show_info)
        self._update_info_display()

    def _handle_action_enable(self, _content, _tag):
        """Handles enable action from queue."""
        self.state.process.is_busy = False
        self.ui.input.field.focus_set()
        self._adjust_input_height()

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
            self.state.indicator.mode = "thinking"
            self.state.indicator.char = config.INDICATOR_CHARS[0]
            self.state.indicator.color_idx = 0
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
        """Alternates the indicator symbol or color every 700ms."""
        if not self.state.indicator.active:
            return

        if self.state.indicator.mode == "thinking":
            chars = config.INDICATOR_CHARS
            try:
                idx = chars.index(self.state.indicator.char)
                self.state.indicator.char = chars[(idx + 1) % len(chars)]
            except ValueError:
                self.state.indicator.char = chars[0]
        else:  # searching
            self.state.indicator.char = config.SEARCH_INDICATOR_CHAR
            cycle = config.SEARCH_COLOR_CYCLE
            self.state.indicator.color_idx = (self.state.indicator.color_idx + 1) % len(cycle)

        self._update_indicator_ui()
        self.root.after(700, self._toggle_indicator)

    def _update_indicator_ui(self):
        """Updates the indicator symbol and color in the chat display."""
        if not self.state.indicator.active:
            return
        self.ui.chat.display.config(state='normal')
        try:
            # Update the color if searching
            color = Theme.INDICATOR_COLOR
            if self.state.indicator.mode == "searching":
                color = config.SEARCH_COLOR_CYCLE[self.state.indicator.color_idx]
            self.ui.chat.display.tag_config("indicator", foreground=color)

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
