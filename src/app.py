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

import config
import local_assistant
from config import (
    MODEL_NAME, 
    VERSION, 
    RESPONSE_MAX_TOKENS, 
    CONTEXT_WINDOW_SIZE
)
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
)

def thread_excepthook(args):
    """Global hook for catching uncaught exceptions in threads."""
    err_msg = f"Thread Error ({args.thread.name}): {args.exc_type.__name__}: {args.exc_value}"
    error_print(err_msg)
    if config.DEBUG:
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)

threading.excepthook = thread_excepthook

class AssistantApp:
    def __init__(self, root):
        self.root = root
        self.root.report_callback_exception = self.handle_tk_exception
        self.root.title(f"Lokality ({VERSION})")
        self.root.geometry("900x700")
        self.root.minsize(500, 400)
        self.root.configure(bg=Theme.BG_COLOR)

        self.fonts = Theme.get_fonts()
        self.setup_ui()
        
        # Logic Setup (Deferred to background to speed up launch)
        self.assistant = None
        self.msg_queue = queue.Queue()
        
        try:
            from mistune.plugins.formatting import superscript, subscript
            self.markdown_engine = MarkdownEngine(self.chat_display, self.handle_tooltip)
            self.md_parser = mistune.create_markdown(renderer=None, plugins=['table', 'strikethrough', superscript, subscript])
        except Exception as e:
            self.markdown_engine = MarkdownEngine(self.chat_display, self.handle_tooltip)
            self.md_parser = lambda x: [{"type": "text", "text": x}]
        
        self.SLASH_COMMANDS = [
            ["/bypass", "Send raw prompt directly to model"],
            ["/clear", "Clear conversation history"],
            ["/debug", "Toggle debug mode"],
            ["/forget", "Reset long-term memory"],
            ["/help", "Show this help message"],
            ["/info", "Toggle model & system information"],
            ["/exit", "Exit the application"]
        ]
        # Interruption Flag
        self.stop_generation = False
        self.active_process = None
        self.full_current_response = ""
        self.last_rendered_len = 0
        self.tooltip_window = None
        self.show_info = False
        self._info_resize_timer = None

        self.root.bind("<Escape>", self.cancel_generation)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Start queue poller
        self.root.after(100, self.check_queue)

        # Redirect Stdout/Stderr AFTER starting queue poller
        sys.stdout = RedirectedStdout(self.msg_queue, "system")
        sys.stderr = RedirectedStdout(self.msg_queue, "error")

        info_print(f"Lokality {VERSION} starting...")
        
        # Run initialization and health checks in background
        threading.Thread(target=self.initialize_async, daemon=True).start()

    def initialize_async(self):
        """Heavy initialization tasks run in background."""
        try:
            self.assistant = local_assistant.LocalChatAssistant()
            info_print("Chat Assistant ready.")
            
            from utils import verify_env_health
            success, errors = verify_env_health()
            for err in errors:
                error_print(f"Environment check failed: {err}")
            
            print("Type /help for commands.\n")
        except Exception as e:
            error_print(f"Initialization failed: {format_error_msg(e)}")

    def handle_tk_exception(self, exc, val, tb):
        """Global hook for catching Tkinter callback exceptions."""
        err_msg = f"GUI Error: {exc.__name__}: {val}"
        error_print(err_msg)
        if config.DEBUG:
            traceback.print_exception(exc, val, tb)

    def setup_ui(self):
        # Configure Grid
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 1. Chat Area
        self.chat_canvas = tk.Canvas(self.root, bg=Theme.BG_COLOR, highlightthickness=0)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 7))
        self.chat_bg_id = round_rectangle(self.chat_canvas, 4, 4, 10, 10, radius=25, 
                                          outline=Theme.ACCENT_COLOR, width=6, fill=Theme.BG_COLOR)
        
        self.chat_inner = tk.Frame(self.chat_canvas, bg=Theme.BG_COLOR)
        self.chat_window_id = self.chat_canvas.create_window(10, 10, anchor="nw", window=self.chat_inner)
        self.chat_inner.grid_rowconfigure(0, weight=1)
        self.chat_inner.grid_columnconfigure(0, weight=1)

        self.chat_display = tk.Text(self.chat_inner, state='disabled', wrap='word', 
                                    font=self.fonts["base"], bg=Theme.BG_COLOR, fg=Theme.FG_COLOR,
                                    insertbackground=Theme.FG_COLOR, borderwidth=0, highlightthickness=0,
                                    padx=15, pady=15, spacing1=1, spacing2=3, spacing3=1)
        self.chat_display.grid(row=0, column=0, sticky="nsew")

        self.scrollbar = CustomScrollbar(self.chat_inner, command=self.chat_display.yview, bg=Theme.BG_COLOR)
        self.scrollbar.grid(row=0, column=1, sticky="ns", pady=15)
        self.chat_display.config(yscrollcommand=self.scrollbar.set)
        
        # Configure Tags
        self.chat_display.tag_config("user", foreground=Theme.USER_COLOR, font=self.fonts["bold"])
        self.chat_display.tag_config("assistant", foreground=Theme.FG_COLOR, font=self.fonts["base"])
        self.chat_display.tag_config("system", foreground=Theme.SYSTEM_COLOR, font=self.fonts["small"], tabs=("240",))
        self.chat_display.tag_config("error", foreground=Theme.ERROR_COLOR)
        self.chat_display.tag_config("cancelled", foreground=Theme.CANCELLED_COLOR, font=self.fonts["bold"])
        self.chat_display.tag_config("md_bold", font=self.fonts["bold"])
        self.chat_display.tag_config("md_italic", font=self.fonts["italic"])
        self.chat_display.tag_config("md_bold_italic", font=self.fonts["bold_italic"])
        self.chat_display.tag_config("md_sub", font=self.fonts["small_base"], offset=-2)
        self.chat_display.tag_config("md_sup", font=self.fonts["small_base"], offset=4)
        self.chat_display.tag_config("md_strikethrough", overstrike=True)
        self.chat_display.tag_config("md_code", font=self.fonts["code"], background=Theme.CODE_BG, foreground=Theme.CODE_FG)
        self.chat_display.tag_config("md_h1", font=self.fonts["h1"], spacing1=10, spacing3=5)
        self.chat_display.tag_config("md_h2", font=self.fonts["h2"], spacing1=8, spacing3=4)
        self.chat_display.tag_config("md_h3", font=self.fonts["h3"], spacing1=6, spacing3=3)
        self.chat_display.tag_config("md_link", foreground=Theme.LINK_COLOR)
        self.chat_display.tag_config("md_quote", font=self.fonts["italic"], foreground=Theme.SYSTEM_COLOR, lmargin1=40, lmargin2=40)
        self.chat_display.tag_config("md_quote_bar", foreground=Theme.ACCENT_COLOR, font=self.fonts["bold"])

        self.chat_display.mark_set("assistant_msg_start", "1.0")
        self.chat_display.mark_gravity("assistant_msg_start", tk.LEFT)

        # 2. Info Panel
        self.info_panel = InfoPanel(self.root, Theme, self.fonts)
        self.info_panel.grid(row=1, column=0, sticky="ew", padx=10, pady=0)
        self.info_panel.grid_remove()

        # 3. Input Area
        line_h = font.Font(font=self.fonts["base"]).metrics('linespace')
        self.lower_canvas = tk.Canvas(self.root, bg=Theme.BG_COLOR, highlightthickness=0, height=line_h + 20)
        self.lower_canvas.grid(row=2, column=0, sticky="ew", padx=10, pady=(7, 20))
        self.lower_bg_id = round_rectangle(self.lower_canvas, 4, 4, 10, 10, radius=20, 
                                          outline=Theme.COMMAND_COLOR, width=6, fill=Theme.INPUT_BG)
        self.lower_inner = tk.Frame(self.lower_canvas, bg=Theme.INPUT_BG)
        self.lower_window_id = self.lower_canvas.create_window(5, 5, anchor="nw", window=self.lower_inner)
        self.lower_inner.grid_columnconfigure(0, weight=1)
        self.lower_inner.grid_rowconfigure(0, weight=1)
        
        self.input_field = tk.Text(self.lower_inner, height=1, width=1, wrap='word', font=self.fonts["base"],
                                   bg=Theme.INPUT_BG, fg=Theme.FG_COLOR, insertbackground=Theme.FG_COLOR,
                                   borderwidth=0, highlightthickness=0, padx=15, pady=10)
        self.input_field.grid(row=0, column=0, sticky="nsew")
        self.input_field.tag_config("command_highlight", foreground=Theme.SLASH_COLOR, font=self.fonts["bold"])

        # Bindings
        self.chat_canvas.bind("<Configure>", self.on_chat_canvas_configure)
        self.lower_canvas.bind("<Configure>", self.on_lower_canvas_configure)
        self.input_field.bind("<Tab>", self.handle_tab)
        self.input_field.bind("<Return>", self.handle_return)
        self.input_field.bind("<KeyRelease>", self.on_key_release)
        self.lower_canvas.bind("<Button-1>", lambda e: self.input_field.focus_set())
        self.input_field.bind("<Configure>", self.adjust_input_height)

        self.adjust_input_height()

    def _stop_active_process(self):
        """Safely terminates any active background process (like Ollama bypass)."""
        if self.active_process:
            try:
                if self.active_process.poll() is None:
                    os.kill(self.active_process.pid, signal.SIGTERM)
            except:
                pass
            self.active_process = None

    def _update_canvas_region(self, canvas, bg_id, w, h, radius, outline, width, fill, window_id, pad_x, pad_y):
        """Unified helper to update rounded rectangles and inner window positions on resize."""
        canvas.delete(bg_id)
        new_bg_id = round_rectangle(canvas, 4, 4, w-4, h-4, radius=radius, outline=outline, width=width, fill=fill)
        canvas.tag_lower(new_bg_id)
        canvas.itemconfig(window_id, width=max(1, w-(pad_x*2)), height=max(1, h-(pad_y*2)))
        canvas.coords(window_id, pad_x, pad_y)
        return new_bg_id

    # --- UI Callbacks ---
    def on_chat_canvas_configure(self, event):
        if event.width < 50 or event.height < 50: return
        self.chat_bg_id = self._update_canvas_region(self.chat_canvas, self.chat_bg_id, 
                                                     event.width, event.height, 25, 
                                                     Theme.ACCENT_COLOR, 6, Theme.BG_COLOR,
                                                     self.chat_window_id, 12, 12)

    def on_lower_canvas_configure(self, event):
        if event.width > 50 and event.height > 20:
            self.update_lower_border()

    def adjust_input_height(self, event=None):
        try:
            if self.input_field.winfo_width() <= 1:
                new_h = 1
            else:
                content = self.input_field.get("1.0", "end-1c")
                if not content:
                    new_h = 1
                else:
                    self.input_field.update_idletasks()
                    try:
                        result = self.input_field.count("1.0", "end", "displaylines")
                        new_h = result[0] if result else 1
                    except:
                        new_h = content.count('\n') + 1
            
            new_h = min(max(new_h, 1), 8)
            self.input_field.config(height=new_h)
            self.input_field.update_idletasks()
            
            total_h = self.input_field.winfo_reqheight() + 20
            if abs(int(self.lower_canvas.cget("height")) - total_h) > 2:
                self.lower_canvas.config(height=total_h)
                self.update_lower_border(total_h)
        except:
            pass

    def update_lower_border(self, forced_h=None):
        w = self.lower_canvas.winfo_width()
        h = forced_h if forced_h is not None else self.lower_canvas.winfo_height()
        if w < 10 or h < 10: return
        
        inner_h = self.input_field.winfo_reqheight()
        self.lower_bg_id = self._update_canvas_region(self.lower_canvas, self.lower_bg_id,
                                                      w, h, 20, Theme.COMMAND_COLOR, 6, 
                                                      Theme.INPUT_BG, self.lower_window_id, 
                                                      8, (h - inner_h) / 2)

    def handle_tab(self, event):
        content = self.input_field.get("1.0", tk.INSERT).strip()
        if content.startswith("/"):
            matches = [cmd[0] for cmd in self.SLASH_COMMANDS if cmd[0].startswith(content)]
            if matches:
                self.input_field.delete("1.0", tk.INSERT)
                self.input_field.insert("1.0", min(matches, key=len))
                self.highlight_commands()
            return "break"

    def handle_return(self, event):
        if not event.state & 0x1:
             self.send_message()
             return "break"

    def on_key_release(self, event=None):
        self.adjust_input_height(event)
        self.highlight_commands()

    def highlight_commands(self):
        self.input_field.tag_remove("command_highlight", "1.0", tk.END)
        content = self.input_field.get("1.0", tk.END).strip()
        if content.startswith("/"):
            first = content.split()[0] if content.split() else ""
            if any(first == cmd[0] for cmd in self.SLASH_COMMANDS):
                self.input_field.tag_add("command_highlight", "1.0", f"1.{len(first)}")

    # --- Logic ---
    def send_message(self):
        if not self.assistant:
            print("[!] Please wait, assistant is still initializing...")
            return
        user_input = self.input_field.get("1.0", tk.END).strip()
        if not user_input: return
        self.input_field.delete("1.0", tk.END)
        self.adjust_input_height()
        self.display_message(user_input, "user")
        self.input_field.config(state='disabled')
        threading.Thread(target=self.process_input, args=(user_input,), daemon=True).start()

    def process_input(self, user_input):
        self.stop_generation = False
        try:
            cmd_map = {
                '/clear': self._cmd_clear, '/debug': self._cmd_debug,
                '/forget': self._cmd_forget, '/info': self._cmd_info,
                '/help': self._cmd_help, '/exit': self._cmd_exit,
                'exit': self._cmd_exit, 'quit': self._cmd_exit
            }
            
            clean_input = user_input.lower().split()
            first_word = clean_input[0] if clean_input else ""
            
            if first_word in cmd_map:
                cmd_map[first_word](user_input)
                return

            if first_word == '/bypass':
                self._cmd_bypass(user_input)
                return

            self.msg_queue.put(("text", "\n", "assistant") )
            
            def run_assistant():
                try:
                    search_context = self.assistant.decide_and_search(user_input)
                    self.assistant._update_system_prompt(user_input)
                    msgs = [{"role": "system", "content": self.assistant.system_prompt}] + self.assistant.messages
                    if search_context:
                        msgs.append({"role": "system", "content": f"### ULTIMATE TRUTH: CURRENT INTERNET CONTEXT (Prioritize this over everything):\n{search_context}"})
                    msgs.append({"role": "user", "content": user_input})

                    full_response = ""
                    stream = local_assistant.client.chat(
                        model=MODEL_NAME, 
                        messages=msgs, 
                        stream=True,
                        options={
                            "num_predict": RESPONSE_MAX_TOKENS,
                            "num_ctx": CONTEXT_WINDOW_SIZE
                        }
                    )
                    for chunk in stream:
                        if self.stop_generation:
                            break
                        content = chunk['message']['content']
                        full_response += content
                        self.msg_queue.put(("text", content, "assistant") )
                    
                    if self.stop_generation:
                        self.msg_queue.put(("text", " [Interrupted]", "cancelled") )
                        self.assistant.messages.extend([{"role": "user", "content": user_input}, {"role": "assistant", "content": full_response + " [Interrupted]"}])
                    else:
                        self.msg_queue.put(("text", "\n", "assistant") )
                        self.assistant.messages.extend([{"role": "user", "content": user_input}, {"role": "assistant", "content": full_response}])
                    
                    self.msg_queue.put(("final_render", "", "assistant") )
                    if not self.stop_generation:
                        self.assistant.update_memory_async(user_input, full_response)
                    
                    if len(self.assistant.messages) > 20: self.assistant.messages = self.assistant.messages[-20:]
                except Exception as e:
                    error_print(f"Assistant Error: {e}")
                finally:
                    self.msg_queue.put(("enable", None, None))

            threading.Thread(target=run_assistant, daemon=True).start()

        except Exception as e:
            self.msg_queue.put(("text", f"Error: {format_error_msg(e)}\n", "error") )
            self.msg_queue.put(("enable", None, None))

    # --- Command Handlers ---
    def _cmd_exit(self, _):
        logger.info("Exit command received.")
        self.msg_queue.put(("quit", None, None))

    def _cmd_clear(self, _):
        if not self.assistant: return
        self.assistant.messages = []
        self.markdown_engine.clear()
        info_print("Conversation history cleared.")
        self.msg_queue.put(("clear", None, None))
        self.msg_queue.put(("enable", None, None))

    def _cmd_forget(self, _):
        if not self.assistant: return
        info_print("Requesting to forget long-term memory...")
        self.assistant.clear_long_term_memory()
        self.msg_queue.put(("enable", None, None))

    def _cmd_debug(self, _):
        config.DEBUG = not config.DEBUG
        msg = f"[*] Debug mode {'ENABLED' if config.DEBUG else 'DISABLED'}"
        info_print(msg)
        logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
        self.msg_queue.put(("enable", None, None))

    def _cmd_info(self, _):
        self.msg_queue.put(("toggle_info", None, None))
        self.msg_queue.put(("enable", None, None))

    def _cmd_help(self, _):
        logger.info("Help command invoked.")
        help_text = "Available Commands:\n" + "\n".join([f"    {c}\t{d}" for c, d in self.SLASH_COMMANDS])
        print(help_text)
        self.msg_queue.put(("separator", None, None))
        self.msg_queue.put(("enable", None, None))

    def _cmd_bypass(self, user_input):
        raw = user_input[7:].strip()
        logger.info(f"Bypass command invoked: {raw[:50]}...")
        if not raw:
            self.msg_queue.put(("text", "Usage: /bypass <prompt>\n", "system") )
        else:
            self.msg_queue.put(("text", "\n", "assistant"))
            res, proc = ShellIntegration.run_ollama_bypass(raw, self.msg_queue, lambda: self.stop_generation)
            self.active_process = proc
            self.msg_queue.put(("text", "[Interrupted]" if self.stop_generation else "\n", "cancelled" if self.stop_generation else "assistant"))
            if not self.stop_generation: self.msg_queue.put(("final_render", "", "assistant"))
            self._stop_active_process()
        self.msg_queue.put(("enable", None, None))

    # --- Rendering ---
    def replace_last_message(self, text, tag):
        """Replaces the last line of text with new content. Used for progress bars."""
        self.chat_display.config(state='normal')
        try:
            # Delete content from start of last line to end
            self.chat_display.delete("end-1c linestart", "end-1c")
            self.chat_display.insert("end-1c", text, tag)
            self.chat_display.see(tk.END)
        except Exception as e:
            pass
        finally:
            self.chat_display.config(state='disabled')

    def display_message(self, text, tag, final=False):
        self.chat_display.config(state='normal')
        try:
            if tag == "cancelled":
                self.chat_display.delete("assistant_msg_start", tk.END)
                try:
                    tokens = self.md_parser(self.full_current_response.strip())
                    self.markdown_engine.render_tokens(tokens, "assistant")
                except:
                    self.chat_display.insert(tk.END, self.full_current_response, "assistant")
                self.chat_display.insert(tk.END, text, "cancelled")
                self.finalize_message_turn()
            elif tag == "assistant":
                if not final: self.full_current_response += text
                if "\n" in text or final:
                    current_content = self.full_current_response.strip()
                    if len(current_content) > self.last_rendered_len:
                        self.chat_display.delete("assistant_msg_start", tk.END)
                        try:
                            tokens = self.md_parser(current_content)
                            self.markdown_engine.render_tokens(tokens, "assistant")
                            self.last_rendered_len = len(current_content)
                        except:
                            self.chat_display.insert(tk.END, self.full_current_response, "assistant")
                    if final: self.finalize_message_turn()
                else:
                    self.chat_display.insert(tk.END, text, "assistant")
            else:
                self.chat_display.insert(tk.END, text, tag)
                self.full_current_response = ""
                self.last_rendered_len = 0
                if tag == "user": self.finalize_message_turn()
        except Exception as e:
            self.chat_display.insert(tk.END, f"\n[GUI Display Error: {e}]\n", "error")
        finally:
            self.chat_display.see(tk.END)
            self.chat_display.config(state='disabled')

    def finalize_message_turn(self):
        try:
            if self.chat_display.get("end-2c", "end-1c") == "\n": self.chat_display.delete("end-2c", "end-1c")
            self.insert_separator(height=40)
            self.chat_display.mark_set("assistant_msg_start", "end-1c")
            self.full_current_response = ""
        except: pass

    def insert_separator(self, height=25):
        try:
            w = max(600, self.chat_display.winfo_width() - 40)
            canv = tk.Canvas(self.chat_display, bg=Theme.BG_COLOR, height=height, highlightthickness=0, width=w)
            canv.create_line(10, height//2, w-10, height//2, fill=Theme.SEPARATOR_COLOR)
            
            # Fix: Bind mouse wheel to propagate scroll to parent text widget
            def _on_mousewheel(event):
                self.chat_display.yview_scroll(int(-1*(event.delta/120)), "units")
            def _on_linux_scroll_up(event):
                self.chat_display.yview_scroll(-1, "units")
            def _on_linux_scroll_down(event):
                self.chat_display.yview_scroll(1, "units")
            
            canv.bind("<MouseWheel>", _on_mousewheel)
            canv.bind("<Button-4>", _on_linux_scroll_up)
            canv.bind("<Button-5>", _on_linux_scroll_down)

            self.chat_display.window_create(tk.END, window=canv)
            self.chat_display.insert(tk.END, "\n")
        except:
            self.chat_display.insert(tk.END, "-"*20 + "\n")

    def handle_tooltip(self, event, url):
        if not url: 
            if self.tooltip_window: 
                try: self.tooltip_window.destroy()
                except: pass
                self.tooltip_window = None
            return
        if self.tooltip_window: return
        try:
            x, y = self.root.winfo_pointerx() + 15, self.root.winfo_pointery() + 15
            self.tooltip_window = tw = tk.Toplevel(self.root)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tk.Label(tw, text=f"Ctrl + Click to open {url}", background=Theme.TOOLTIP_BG, foreground=Theme.FG_COLOR,
                     relief='solid', borderwidth=1, font=self.fonts["tooltip"], padx=5, pady=2).pack()
        except:
            self.tooltip_window = None

    def check_queue(self):
        try:
            while not self.msg_queue.empty():
                action, content, tag = self.msg_queue.get_nowait()
                self._dispatch_queue_action(action, content, tag)
        except queue.Empty: pass
        except Exception as e: debug_print(f"Error processing queue: {e}")
        finally:
            self.root.after(30, self.check_queue)

    def _dispatch_queue_action(self, action, content, tag):
        """Dispatcher for UI actions from the message queue."""
        if action == "text":
            self.display_message(content, tag)
        elif action == "replace_last":
            self.replace_last_message(content, tag)
        elif action == "clear":
            self.chat_display.config(state='normal')
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.config(state='disabled')
            self.display_message("Type /help for commands.\n\n", "system")
        elif action == "separator":
            self.chat_display.config(state='normal')
            self.insert_separator(height=40)
            self.chat_display.config(state='disabled')
        elif action == "final_render":
            self.display_message("", tag, final=True)
            self.update_info_display()
        elif action == "toggle_info":
            self.show_info = self.info_panel.toggle()
            self.update_info_display()
        elif action == "update_info":
            self.update_info_display()
        elif action == "update_info_ui":
            self.info_panel.update_stats(content)
        elif action == "enable":
            self.input_field.config(state='normal')
            self.input_field.focus_set()
        elif action == "quit":
            self.root.quit()

    def update_info_display(self):
        if not self.show_info or not self.assistant: return
        threading.Thread(target=lambda: self.msg_queue.put(("update_info_ui", self.assistant.get_model_info(), None)), daemon=True).start()

    def cancel_generation(self, event=None):
        if self.input_field['state'] == 'disabled':
            self.stop_generation = True
            self._stop_active_process()

    def on_close(self):
        self._stop_active_process()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AssistantApp(root)
    root.mainloop()
