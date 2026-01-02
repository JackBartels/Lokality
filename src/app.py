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
from dataclasses import dataclass, field
from tkinter import font
from typing import Optional, Any

import mistune
import ollama
from mistune.plugins.formatting import superscript, subscript

import config
import local_assistant
from complexity_scorer import ComplexityScorer
from config import VERSION
from logger import logger
from markdown_engine import MarkdownEngine
from shell_integration import ShellIntegration
from theme import Theme
from ui_components import CustomScrollbar, InfoPanel
from utils import (
    RedirectedStdout,
    debug_print,
    error_print,
    format_error_msg,
    info_print,
    round_rectangle,
    verify_env_health,
)

def thread_excepthook(args):
    """Global hook for catching uncaught exceptions in threads."""
    err_msg = (
        f"Thread Error ({args.thread.name}): "
        f"{args.exc_type.__name__}: {args.exc_value}"
    )
    error_print(err_msg)
    if config.DEBUG:
        traceback.print_exception(
            args.exc_type, args.exc_value, args.exc_traceback
        )

threading.excepthook = thread_excepthook

@dataclass
class AppState:
    """Holds the application state."""
    assistant: Optional[Any] = None
    stop_generation: bool = False
    active_process: Optional[Any] = None
    full_current_response: str = ""
    last_rendered_len: int = 0
    show_info: bool = False
    msg_queue: queue.Queue = field(default_factory=queue.Queue)

@dataclass
class ChatUI:
    """Holds chat display UI component references."""
    canvas: Optional[tk.Canvas] = None
    bg_id: Optional[int] = None
    inner: Optional[tk.Frame] = None
    window_id: Optional[int] = None
    display: Optional[tk.Text] = None
    scrollbar: Optional[CustomScrollbar] = None

@dataclass
class InputUI:
    """Holds input area UI component references."""
    canvas: Optional[tk.Canvas] = None
    bg_id: Optional[int] = None
    inner: Optional[tk.Frame] = None
    window_id: Optional[int] = None
    field: Optional[tk.Text] = None

@dataclass
class AppUI:
    """Holds UI component references."""
    chat: ChatUI = field(default_factory=ChatUI)
    input: InputUI = field(default_factory=InputUI)
    info_panel: Optional[InfoPanel] = None
    tooltip_window: Optional[tk.Toplevel] = None

@dataclass
class CanvasConfig:
    """Configuration for canvas region updates."""
    canvas: tk.Canvas
    bg_id: int
    size: tuple[int, int]
    radius: int
    style: tuple[str, int, str]
    win_id: int
    pad: tuple[int, float]

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
        self.state = AppState()
        self.ui = AppUI()

        self._setup_markdown()
        self._setup_ui()

        self.slash_commands = [
            ["/bypass", "Send raw prompt directly to model"],
            ["/clear", "Clear conversation history"],
            ["/debug", "Toggle debug mode"],
            ["/forget", "Reset long-term memory"],
            ["/help", "Show this help message"],
            ["/info", "Toggle model & system information"],
            ["/exit", "Exit the application"]
        ]

        self.root.bind("<Escape>", self.cancel_generation)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.check_queue)

        sys.stdout = RedirectedStdout(self.state.msg_queue, "system")
        sys.stderr = RedirectedStdout(self.state.msg_queue, "error")

        info_print(f"Lokality {VERSION} starting...")
        threading.Thread(target=self._initialize_async, daemon=True).start()

    def _setup_markdown(self):
        """Initializes the markdown engine and parser."""
        try:
            self.markdown_engine = MarkdownEngine(
                None, self.handle_tooltip
            )
            self.md_parser = mistune.create_markdown(
                renderer=None,
                plugins=['table', 'strikethrough', superscript, subscript]
            )
        except (ImportError, AttributeError):
            self.markdown_engine = MarkdownEngine(
                None, self.handle_tooltip
            )
            self.md_parser = lambda x: [{"type": "text", "text": x}]

    def _initialize_async(self):
        """Heavy initialization tasks run in background."""
        try:
            self.state.assistant = local_assistant.LocalChatAssistant()
            info_print("Chat Assistant ready.")

            _, errors = verify_env_health()
            for err in errors:
                error_print(f"Environment check failed: {err}")

            print("Type /help for commands.\n")
        except (ImportError, RuntimeError, ValueError) as exc:
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
        self.root.grid_columnconfigure(0, weight=1)

        self._setup_chat_area()
        self.markdown_engine.text_widget = self.ui.chat.display

        self.ui.info_panel = InfoPanel(self.root, Theme, self.fonts)
        self.ui.info_panel.grid(row=1, column=0, sticky="ew", padx=10, pady=0)
        self.ui.info_panel.grid_remove()

        self._setup_input_area()
        self._bind_events()
        self.adjust_input_height()

    def _setup_chat_area(self):
        """Sets up the scrollable chat display area."""
        self.ui.chat.canvas = tk.Canvas(
            self.root, bg=Theme.BG_COLOR, highlightthickness=0
        )
        self.ui.chat.canvas.grid(
            row=0, column=0, sticky="nsew", padx=10, pady=(10, 7)
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
        self.ui.chat.display.config(yscrollcommand=self.ui.chat.scrollbar.set)

        self._configure_tags()
        self.ui.chat.display.mark_set("assistant_msg_start", "1.0")
        self.ui.chat.display.mark_gravity("assistant_msg_start", tk.LEFT)

    def _setup_input_area(self):
        """Sets up the user input field at the bottom."""
        line_h = font.Font(font=self.fonts["base"]).metrics('linespace')
        self.ui.input.canvas = tk.Canvas(
            self.root, bg=Theme.BG_COLOR, highlightthickness=0,
            height=line_h + 20
        )
        self.ui.input.canvas.grid(
            row=2, column=0, sticky="ew", padx=10, pady=(7, 20)
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
        self.ui.chat.canvas.bind("<Configure>", self.on_chat_canvas_configure)
        self.ui.input.canvas.bind("<Configure>", self.on_lower_canvas_configure)
        self.ui.input.field.bind("<Tab>", self.handle_tab)
        self.ui.input.field.bind("<Return>", self.handle_return)
        self.ui.input.field.bind("<KeyRelease>", self.on_key_release)
        self.ui.input.canvas.bind(
            "<Button-1>", lambda e: self.ui.input.field.focus_set()
        )
        self.ui.input.field.bind("<Configure>", self.adjust_input_height)

    def _stop_active_process(self):
        """Safely terminates any active background process."""
        if self.state.active_process:
            try:
                if self.state.active_process.poll() is None:
                    os.kill(self.state.active_process.pid, signal.SIGTERM)
            except OSError:
                pass
            self.state.active_process = None

    def _update_canvas_region(self, cfg: CanvasConfig):
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

    def on_chat_canvas_configure(self, event):
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

    def on_lower_canvas_configure(self, event):
        """Updates the input area border on resize."""
        if event.width > 50 and event.height > 20:
            self.update_lower_border()

    def adjust_input_height(self, _=None):
        """Dynamically adjusts the input field height based on content."""
        try:
            if self.ui.input.field.winfo_width() <= 1:
                new_h = 1
            else:
                content = self.ui.input.field.get("1.0", "end-1c")
                if not content:
                    new_h = 1
                else:
                    self.ui.input.field.update_idletasks()
                    try:
                        res = self.ui.input.field.count("1.0", "end", "displaylines")
                        new_h = res[0] if res else 1
                    except (tk.TclError, AttributeError):
                        new_h = content.count('\n') + 1

            new_h = min(max(new_h, 1), 8)
            self.ui.input.field.config(height=new_h)
            self.ui.input.field.update_idletasks()

            total_h = self.ui.input.field.winfo_reqheight() + 20
            if abs(int(self.ui.input.canvas.cget("height")) - total_h) > 2:
                self.ui.input.canvas.config(height=total_h)
                self.update_lower_border(total_h)
        except tk.TclError:
            pass

    def update_lower_border(self, forced_h=None):
        """Updates the input area border rounded rectangle."""
        w = self.ui.input.canvas.winfo_width()
        h = forced_h if forced_h is not None else self.ui.input.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        inner_h = self.ui.input.field.winfo_reqheight()
        cfg = CanvasConfig(
            canvas=self.ui.input.canvas,
            bg_id=self.ui.input.bg_id,
            size=(w, h),
            radius=20,
            style=(Theme.COMMAND_COLOR, 6, Theme.INPUT_BG),
            win_id=self.ui.input.window_id,
            pad=(8, (h - inner_h) / 2)
        )
        self.ui.input.bg_id = self._update_canvas_region(cfg)

    def handle_tab(self, _):
        """Provides command completion for slash commands."""
        content = self.ui.input.field.get("1.0", tk.INSERT).strip()
        if content.startswith("/"):
            matches = [c[0] for c in self.slash_commands if c[0].startswith(content)]
            if matches:
                self.ui.input.field.delete("1.0", tk.INSERT)
                self.ui.input.field.insert("1.0", min(matches, key=len))
                self.highlight_commands()
            return "break"
        return None

    def handle_return(self, event):
        """Sends the message on Enter, inserts newline on Shift+Enter."""
        if not event.state & 0x1:
            self.send_message()
            return "break"
        return None

    def on_key_release(self, event=None):
        """Handles post-key-press UI updates."""
        self.adjust_input_height(event)
        self.highlight_commands()

    def highlight_commands(self):
        """Highlights known slash commands in the input field."""
        self.ui.input.field.tag_remove("command_highlight", "1.0", tk.END)
        content = self.ui.input.field.get("1.0", tk.END).strip()
        if content.startswith("/"):
            parts = content.split()
            first = parts[0] if parts else ""
            if any(first == cmd[0] for cmd in self.slash_commands):
                self.ui.input.field.tag_add("command_highlight", "1.0", f"1.{len(first)}")

    def send_message(self):
        """Starts processing the user input."""
        if not self.state.assistant:
            print("[!] Please wait, assistant is still initializing...")
            return
        user_input = self.ui.input.field.get("1.0", tk.END).strip()
        if not user_input:
            return
        self.ui.input.field.delete("1.0", tk.END)
        self.adjust_input_height()
        self.display_message(user_input, "user")
        self.ui.input.field.config(state='disabled')
        threading.Thread(
            target=self.process_input, args=(user_input,), daemon=True
        ).start()

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
            stream = local_assistant.client.chat(
                model=config.MODEL_NAME, messages=msgs,
                stream=True, options=complexity['params']
            )
            for chunk in stream:
                if self.state.stop_generation:
                    break
                cnt = chunk['message']['content']
                full_resp += cnt
                self.state.msg_queue.put(("text", cnt, "assistant"))

            self._finalize_chat_response(user_input, full_resp)
        except (ollama.ResponseError, AttributeError) as exc:
            error_print(f"Assistant Error: {exc}")

    def _finalize_chat_response(self, user_input, full_resp):
        """Stores result and triggers final rendering."""
        if self.state.stop_generation:
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
        if not self.state.stop_generation:
            self.state.assistant.update_memory_async(user_input, full_resp)

        if len(self.state.assistant.messages) > 20:
            self.state.assistant.messages = self.state.assistant.messages[-20:]

    def process_input(self, user_input):
        """Orchestrates complexity analysis, search, and LLM chat."""
        self.state.stop_generation = False
        try:
            cmd_map = {
                '/clear': self._cmd_clear, '/debug': self._cmd_debug,
                '/forget': self._cmd_forget, '/info': self._cmd_info,
                '/help': self._cmd_help, '/exit': self._cmd_exit,
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

            self.state.msg_queue.put(("text", "\n", "assistant"))

            def run_assistant():
                complexity = ComplexityScorer.analyze(user_input)
                p_params = complexity['params']

                skip_search = complexity['level'] == ComplexityScorer.LEVEL_MINIMAL
                ctx = self.state.assistant.decide_and_search(
                    user_input, skip_llm=skip_search, options=p_params
                )

                if ctx and p_params.get('num_ctx', 0) < 2048:
                    p_params['num_ctx'] = ComplexityScorer.get_safe_context_size(2048)

                self.state.assistant.update_system_prompt_for_user(user_input)
                msgs = self._get_assistant_msgs(user_input, ctx)
                self._run_streaming_chat(user_input, complexity, msgs)
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
        msg = f"[*] Debug mode {"ENABLED" if config.DEBUG else "DISABLED"}"
        info_print(msg)
        logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_info(self, _):
        self.state.msg_queue.put(("toggle_info", None, None))
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_help(self, _):
        logger.info("Help command invoked.")
        lines = [f"    {c}\t{d}" for c, d in self.slash_commands]
        print("Available Commands:\n" + "\n".join(lines))
        self.state.msg_queue.put(("separator", None, None))
        self.state.msg_queue.put(("enable", None, None))

    def _cmd_bypass(self, user_input):
        raw = user_input[7:].strip()
        logger.info("Bypass command invoked: %s...", raw[:50])
        if not raw:
            self.state.msg_queue.put(("text", "Usage: /bypass <prompt>\n", "system"))
        else:
            self.state.msg_queue.put(("text", "\n", "assistant"))
            _, proc = ShellIntegration.run_ollama_bypass(
                raw, self.state.msg_queue, lambda: self.state.stop_generation
            )
            self.state.active_process = proc
            msg = "[Interrupted]" if self.state.stop_generation else "\n"
            tag = "cancelled" if self.state.stop_generation else "assistant"
            self.state.msg_queue.put(("text", msg, tag))
            if not self.state.stop_generation:
                self.state.msg_queue.put(("final_render", "", "assistant"))
            self._stop_active_process()
        self.state.msg_queue.put(("enable", None, None))

    def replace_last_message(self, text, tag):
        """Replaces the last line of text with new content."""
        self.ui.chat.display.config(state='normal')
        try:
            self.ui.chat.display.delete("end-1c linestart", "end-1c")
            self.ui.chat.display.insert("end-1c", text, tag)
            self.ui.chat.display.see(tk.END)
        except tk.TclError:
            pass
        finally:
            self.ui.chat.display.config(state='disabled')

    def _render_assistant_stream(self, text, final):
        """Helper to render assistant text stream with markdown."""
        if not final:
            self.state.full_current_response += text
        if "\n" in text or final:
            cur = self.state.full_current_response.strip()
            if len(cur) > self.state.last_rendered_len:
                self.ui.chat.display.delete("assistant_msg_start", tk.END)
                try:
                    toks = self.md_parser(cur)
                    self.markdown_engine.render_tokens(toks, "assistant")
                    self.state.last_rendered_len = len(cur)
                except (ValueError, TypeError):
                    self.ui.chat.display.insert(
                        tk.END, self.state.full_current_response, "assistant"
                    )
            if final:
                self.finalize_message_turn()
        else:
            self.ui.chat.display.insert(tk.END, text, "assistant")

    def display_message(self, text, tag, final=False):
        """Renders messages in the chat display with Markdown support."""
        self.ui.chat.display.config(state='normal')
        try:
            if tag == "cancelled":
                self.ui.chat.display.delete("assistant_msg_start", tk.END)
                try:
                    toks = self.md_parser(self.state.full_current_response.strip())
                    self.markdown_engine.render_tokens(toks, "assistant")
                except (ValueError, TypeError):
                    self.ui.chat.display.insert(
                        tk.END, self.state.full_current_response, "assistant"
                    )
                self.ui.chat.display.insert(tk.END, text, "cancelled")
                self.finalize_message_turn()
            elif tag == "assistant":
                self._render_assistant_stream(text, final)
            else:
                self.ui.chat.display.insert(tk.END, text, tag)
                self.state.full_current_response = ""
                self.state.last_rendered_len = 0
                if tag == "user":
                    self.finalize_message_turn()
        except (tk.TclError, ValueError) as exc:
            self.ui.chat.display.insert(tk.END, f"\n[GUI Error: {exc}]\n", "error")
        finally:
            self.ui.chat.display.see(tk.END)
            self.ui.chat.display.config(state='disabled')

    def finalize_message_turn(self):
        """Handles post-message-turn cleanup and UI elements."""
        try:
            if self.ui.chat.display.get("end-2c", "end-1c") == "\n":
                self.ui.chat.display.delete("end-2c", "end-1c")
            self.insert_separator(height=40)
            self.ui.chat.display.mark_set("assistant_msg_start", "end-1c")
            self.state.full_current_response = ""
        except tk.TclError:
            pass

    def insert_separator(self, height=25):
        """Inserts a horizontal separator into the chat display."""
        try:
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

            self.ui.chat.display.window_create(tk.END, window=canv)
            self.ui.chat.display.insert(tk.END, "\n")
        except tk.TclError:
            self.ui.chat.display.insert(tk.END, "-"*20 + "\n")

    def handle_tooltip(self, _, url):
        """Displays a tooltip for links in the chat area."""
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

    def check_queue(self):
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
            self.root.after(30, self.check_queue)

    def _dispatch_queue_action(self, action, content, tag):
        """Dispatcher for UI actions from the message queue."""
        if action == "text":
            self.display_message(content, tag)
        elif action == "replace_last":
            self.replace_last_message(content, tag)
        elif action == "clear":
            self.ui.chat.display.config(state='normal')
            self.ui.chat.display.delete("1.0", tk.END)
            self.ui.chat.display.config(state='disabled')
            self.display_message("Type /help for commands.\n\n", "system")
        elif action == "separator":
            self.ui.chat.display.config(state='normal')
            self.insert_separator(height=40)
            self.ui.chat.display.config(state='disabled')
        elif action == "final_render":
            self.display_message("", tag, final=True)
            self.update_info_display()
        elif action == "toggle_info":
            self.state.show_info = self.ui.info_panel.toggle()
            self.update_info_display()
        elif action == "update_info_ui":
            self.ui.info_panel.update_stats(content)
        elif action == "enable":
            self.ui.input.field.config(state='normal')
            self.ui.input.field.focus_set()
        elif action == "quit":
            self.root.quit()

    def update_info_display(self):
        """Fetches and displays model info in the info panel."""
        if not self.state.show_info or not self.state.assistant:
            return
        threading.Thread(
            target=lambda: self.state.msg_queue.put(
                ("update_info_ui", self.state.assistant.get_model_info(), None)
            ),
            daemon=True
        ).start()

    def cancel_generation(self, _=None):
        """Cancels any ongoing model generation."""
        if self.ui.input.field['state'] == 'disabled':
            self.state.stop_generation = True
            self._stop_active_process()

    def on_close(self):
        """Handles application shutdown."""
        self._stop_active_process()
        self.root.destroy()

if __name__ == "__main__":
    root_win = tk.Tk()
    AssistantApp(root_win)
    root_win.mainloop()
