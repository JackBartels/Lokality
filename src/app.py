import tkinter as tk
from tkinter import font, ttk
import threading
import queue
import sys
import os
import signal

# Local imports
from config import VERSION, MODEL_NAME
from theme import Theme
from utils import RedirectedStdout, round_rectangle
from ui_components import CustomScrollbar
from markdown_engine import MarkdownEngine
from shell_integration import ShellIntegration
import local_assistant
import mistune

class AssistantApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Lokality v{VERSION}")
        self.root.geometry("900x700")
        self.root.configure(bg=Theme.BG_COLOR)

        self.fonts = Theme.get_fonts()
        self.setup_ui()
        
        # Logic Setup
        self.assistant = local_assistant.LocalChatAssistant()
        self.msg_queue = queue.Queue()
        self.markdown_engine = MarkdownEngine(self.chat_display, self.handle_tooltip)
        self.md_parser = mistune.create_markdown(renderer=None, plugins=['table', 'strikethrough'])
        
        self.SLASH_COMMANDS = [
            ["/bypass", "Send raw prompt directly to model"],
            ["/clear", "Clear conversation history"],
            ["/forget", "Reset long-term memory"],
            ["/help", "Show this help message"],
            ["/info", "Toggle model & system information"],
            ["/exit", "Exit the application"]
        ]
        # Interruption Flag
        self.stop_generation = False
        self.active_process = None
        self.full_current_response = ""
        self.tooltip_window = None
        self.show_info = False

        self.root.bind("<Escape>", self.cancel_generation)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Redirect Stdout/Stderr
        sys.stdout = RedirectedStdout(self.msg_queue, "system")
        sys.stderr = RedirectedStdout(self.msg_queue, "error")

        self.root.after(100, self.check_queue)
        self.display_message("Type /help for commands.\n\n", "system")

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
        self.chat_display.tag_config("md_code", font=self.fonts["code"], background=Theme.CODE_BG, foreground=Theme.CODE_FG)
        self.chat_display.tag_config("md_h1", font=self.fonts["h1"], spacing1=10, spacing3=5)
        self.chat_display.tag_config("md_h2", font=self.fonts["h2"], spacing1=8, spacing3=4)
        self.chat_display.tag_config("md_h3", font=self.fonts["h3"], spacing1=6, spacing3=3)
        self.chat_display.tag_config("md_link", foreground=Theme.LINK_COLOR)

        self.chat_display.mark_set("assistant_msg_start", "1.0")
        self.chat_display.mark_gravity("assistant_msg_start", tk.LEFT)

        # 2. Info Panel
        self.info_canvas = tk.Canvas(self.root, bg=Theme.BG_COLOR, height=0, highlightthickness=0)
        self.info_canvas.grid(row=1, column=0, sticky="ew", padx=10, pady=0)
        self.info_canvas.grid_remove()
        self.info_bg_id = round_rectangle(self.info_canvas, 4, 4, 10, 10, radius=15, fill=Theme.BG_COLOR)
        self.info_inner = tk.Frame(self.info_canvas, bg=Theme.BG_COLOR)
        self.info_window_id = self.info_canvas.create_window(10, 10, anchor="nw", window=self.info_inner)
        self.info_labels = []
        for i in range(5):
            item_frame = tk.Frame(self.info_inner, bg=Theme.BG_COLOR)
            sub = tk.Frame(item_frame, bg=Theme.BG_COLOR)
            sub.pack(expand=True, padx=10)
            name_lbl = tk.Label(sub, text="", font=self.fonts["small"], bg=Theme.BG_COLOR, fg="#BDBDBD")
            name_lbl.pack(side="left")
            val_lbl = tk.Label(sub, text="", font=self.fonts["bold"], bg=Theme.BG_COLOR, fg="#BDBDBD")
            val_lbl.pack(side="left")
            unit_lbl = tk.Label(sub, text="", font=self.fonts["unit"], bg=Theme.BG_COLOR, fg="#BDBDBD")
            unit_lbl.pack(side="left", pady=(2, 0)) # Slight offset down for alignment
            self.info_labels.append((item_frame, name_lbl, val_lbl, unit_lbl))

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
        self.info_canvas.bind("<Configure>", self.on_info_canvas_configure)
        self.lower_canvas.bind("<Configure>", self.on_lower_canvas_configure)
        self.input_field.bind("<Tab>", self.handle_tab)
        self.input_field.bind("<Return>", self.handle_return)
        self.input_field.bind("<KeyRelease>", self.on_key_release)
        self.lower_canvas.bind("<Button-1>", lambda e: self.input_field.focus_set())
        self.input_field.bind("<Configure>", self.adjust_input_height)

        self.adjust_input_height()

    # --- UI Callbacks ---
    def on_chat_canvas_configure(self, event):
        w, h, pad = event.width, event.height, 12
        self.chat_canvas.delete(self.chat_bg_id)
        self.chat_bg_id = round_rectangle(self.chat_canvas, 4, 4, w-4, h-4, radius=25, 
                                          outline=Theme.ACCENT_COLOR, width=6, fill=Theme.BG_COLOR)
        self.chat_canvas.tag_lower(self.chat_bg_id)
        self.chat_canvas.itemconfig(self.chat_window_id, width=w-(pad*2), height=h-(pad*2))
        self.chat_canvas.coords(self.chat_window_id, pad, pad)

    def on_lower_canvas_configure(self, event):
        self.update_lower_border()

    def on_info_canvas_configure(self, event):
        w = self.info_canvas.winfo_width()
        if w < 10: return
        max_w = w - 40
        rows, current_row_w = [[]], 0
        for item_frame, _, _, _ in self.info_labels:
            item_frame.update_idletasks()
            item_w = item_frame.winfo_reqwidth()
            if current_row_w + item_w > max_w and rows[-1]:
                rows.append([])
                current_row_w = 0
            rows[-1].append((item_frame, item_w))
            current_row_w += item_w + 20
        
        y, total_h = 0, 0
        for row in rows:
            if not row: continue
            row_items_w = sum(item[1] for item in row)
            pad = (max_w - row_items_w) / (len(row) + 1)
            x, row_h = pad, 0
            for item_frame, item_w in row:
                item_frame.place(x=x, y=y)
                x += item_w + pad
                row_h = max(row_h, item_frame.winfo_reqheight())
            y += row_h + 5
            total_h = y

        if self.show_info:
            target_h = max(40, total_h + 10)
            if abs(self.info_canvas.winfo_height() - target_h) > 5:
                self.info_canvas.config(height=target_h)
            self.info_canvas.delete(self.info_bg_id)
            self.info_bg_id = round_rectangle(self.info_canvas, 4, 4, w-4, self.info_canvas.winfo_height()-4, radius=15, fill=Theme.BG_COLOR)
            self.info_canvas.tag_lower(self.info_bg_id)
            self.info_canvas.itemconfig(self.info_window_id, width=max_w, height=total_h)
            self.info_canvas.coords(self.info_window_id, 20, (self.info_canvas.winfo_height() - total_h) / 2)

    def adjust_input_height(self, event=None):
        # If the widget hasn't been assigned a real width yet, assume 1 line
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
        
        # Update widget height
        self.input_field.config(height=new_h)
        # Force a layout update to get accurate requested height
        self.input_field.update_idletasks()
        
        # Use the actual requested height of the text widget + constant vertical padding (py*2 = 20)
        py = 10
        total_h = self.input_field.winfo_reqheight() + (py * 2)
        
        if str(self.lower_canvas.cget("height")) != str(total_h):
            self.lower_canvas.config(height=total_h)
            self.update_lower_border(total_h)

    def update_lower_border(self, forced_h=None):
        w = self.lower_canvas.winfo_width()
        h = forced_h if forced_h is not None else self.lower_canvas.winfo_height()
        if w < 10 or h < 10: return
        
        self.lower_canvas.delete(self.lower_bg_id)
        self.lower_bg_id = round_rectangle(self.lower_canvas, 4, 4, w-4, h-4, radius=20, 
                                          outline=Theme.COMMAND_COLOR, width=6, fill=Theme.INPUT_BG)
        self.lower_canvas.tag_lower(self.lower_bg_id)
        
        px, py = 8, 10
        # Vertically center the inner window
        self.lower_canvas.itemconfig(self.lower_window_id, width=w-(px*2), height=h-(py*2))
        self.lower_canvas.coords(self.lower_window_id, px, py)

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
        if not event.state & 0x1: # Check if Shift key is NOT pressed
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
                '/clear': self._cmd_clear,
                '/forget': self._cmd_forget,
                '/info': self._cmd_info,
                '/help': self._cmd_help,
                '/exit': self._cmd_exit,
                'exit': self._cmd_exit,
                'quit': self._cmd_exit
            }
            
            clean_input = user_input.lower().split()
            first_word = clean_input[0] if clean_input else ""
            
            if first_word in cmd_map:
                cmd_map[first_word](user_input)
                return

            if first_word == '/bypass':
                self._cmd_bypass(user_input)
                return

            # Main Assistant
            self.msg_queue.put(("text", "\n", "assistant") )
            
            def run_assistant():
                try:
                    search_context = self.assistant.decide_and_search(user_input)
                    self.assistant._update_system_prompt(user_input)
                    msgs = [{"role": "system", "content": self.assistant.system_prompt}] + self.assistant.messages
                    if search_context:
                        msgs.append({"role": "system", "content": f"EXTRACTED INTERNET CONTEXT:\n{search_context}"})
                    msgs.append({"role": "user", "content": user_input})

                    full_response = ""
                    stream = local_assistant.client.chat(model=MODEL_NAME, messages=msgs, stream=True)
                    for chunk in stream:
                        if self.stop_generation:
                            self.msg_queue.put(("text", "[Interrupted]", "cancelled") )
                            break
                        content = chunk['message']['content']
                        full_response += content
                        self.msg_queue.put(("text", content, "assistant") )
                    
                    if not self.stop_generation:
                        self.msg_queue.put(("text", "\n", "assistant") )
                        self.assistant.messages.extend([{"role": "user", "content": user_input}, {"role": "assistant", "content": full_response}])
                        self.msg_queue.put(("final_render", "", "assistant") )
                        self.assistant.update_memory_async(user_input, full_response)
                        if len(self.assistant.messages) > 20: self.assistant.messages = self.assistant.messages[-20:]
                except Exception as e:
                    self.msg_queue.put(("text", f"Error: {e}\n", "error") )
                finally:
                    self.msg_queue.put(("enable", None, None))

            threading.Thread(target=run_assistant, daemon=True).start()
            return

        except Exception as e:
            self.msg_queue.put(("text", f"Error: {e}\n", "error") )
            self.msg_queue.put(("enable", None, None))

    # --- Command Handlers ---
    def _cmd_exit(self, _):
        self.msg_queue.put(("quit", None, None))

    def _cmd_clear(self, _):
        self.assistant.messages = []
        print("Conversation memory cleared.")
        self.msg_queue.put(("clear", None, None))
        self.msg_queue.put(("enable", None, None))

    def _cmd_forget(self, _):
        self.assistant.clear_long_term_memory()
        self.msg_queue.put(("enable", None, None))

    def _cmd_info(self, _):
        self.msg_queue.put(("toggle_info", None, None))
        self.msg_queue.put(("enable", None, None))

    def _cmd_help(self, _):
        help_text = "Available Commands:\n" + "\n".join([f"    {c}\t{d}" for c, d in self.SLASH_COMMANDS])
        print(help_text)
        self.msg_queue.put(("separator", None, None))
        self.msg_queue.put(("enable", None, None))

    def _cmd_bypass(self, user_input):
        raw = user_input[7:].strip()
        if not raw:
            self.msg_queue.put(("text", "Usage: /bypass <prompt>\n", "system") )
        else:
            self.msg_queue.put(("text", "\n", "assistant"))
            res, proc = ShellIntegration.run_ollama_bypass(raw, self.msg_queue, lambda: self.stop_generation)
            self.active_process = proc
            if self.stop_generation:
                self.msg_queue.put(("text", "[Interrupted]", "cancelled"))
            else:
                self.msg_queue.put(("text", "\n", "assistant"))
                self.msg_queue.put(("final_render", "", "assistant"))
            if self.active_process:
                try: os.kill(self.active_process.pid, signal.SIGTERM)
                except: pass
                self.active_process = None
        self.msg_queue.put(("enable", None, None))

    # --- Rendering ---
    def display_message(self, text, tag, final=False):
        self.chat_display.config(state='normal')
        if tag == "cancelled":
            self.chat_display.delete("assistant_msg_start", tk.END)
            tokens = self.md_parser(self.full_current_response.strip())
            self.markdown_engine.render_tokens(tokens, "assistant")
            self.chat_display.insert(tk.END, text, "cancelled")
            self.finalize_message_turn()
        elif tag == "assistant":
            if not final: self.full_current_response += text
            # OPTIMIZATION: Only do full markdown re-render on newlines or final, 
            # otherwise just append the raw text for speed.
            if "\n" in text or final:
                self.chat_display.delete("assistant_msg_start", tk.END)
                tokens = self.md_parser(self.full_current_response.strip())
                self.markdown_engine.render_tokens(tokens, "assistant")
                if final: self.finalize_message_turn()
            else:
                self.chat_display.insert(tk.END, text, "assistant")
        else:
            self.chat_display.insert(tk.END, text, tag)
            self.full_current_response = ""
            if tag == "user": self.finalize_message_turn()
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def finalize_message_turn(self):
        if self.chat_display.get("end-2c", "end-1c") == "\n": self.chat_display.delete("end-2c", "end-1c")
        self.insert_separator(height=40)
        self.chat_display.mark_set("assistant_msg_start", "end-1c")
        self.full_current_response = ""

    def insert_separator(self, height=25):
        w = max(600, self.chat_display.winfo_width() - 40)
        canv = tk.Canvas(self.chat_display, bg=Theme.BG_COLOR, height=height, highlightthickness=0, width=w)
        canv.create_line(10, height//2, w-10, height//2, fill=Theme.SEPARATOR_COLOR)
        self.chat_display.window_create(tk.END, window=canv)
        self.chat_display.insert(tk.END, "\n")

    def handle_tooltip(self, event, url):
        if not url: 
            if self.tooltip_window: self.tooltip_window.destroy(); self.tooltip_window = None
            return
        if self.tooltip_window: return
        x, y = self.root.winfo_pointerx() + 15, self.root.winfo_pointery() + 15
        self.tooltip_window = tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=f"Ctrl + Click to open {url}", background=Theme.TOOLTIP_BG, foreground=Theme.FG_COLOR,
                 relief='solid', borderwidth=1, font=self.fonts["tooltip"], padx=5, pady=2).pack()

    def check_queue(self):
        while not self.msg_queue.empty():
            action, content, tag = self.msg_queue.get_nowait()
            if action == "text": self.display_message(content, tag)
            elif action == "clear":
                self.chat_display.config(state='normal'); self.chat_display.delete("1.0", tk.END); self.chat_display.config(state='disabled')
                self.display_message("Type /help for commands.\n\n", "system")
            elif action == "separator":
                self.chat_display.config(state='normal'); self.insert_separator(height=40); self.chat_display.config(state='disabled')
            elif action == "final_render": self.display_message("", tag, final=True); self.update_info_display()
            elif action == "toggle_info": self.show_info = not self.show_info; self.info_canvas.grid() if self.show_info else self.info_canvas.grid_remove(); self.update_info_display()
            elif action == "update_info": self.update_info_display()
            elif action == "update_info_ui": self.update_info_ui(content)
            elif action == "enable": self.input_field.config(state='normal'); self.input_field.focus_set()
            elif action == "quit": self.root.quit()
        self.root.after(30, self.check_queue) # OPTIMIZATION: Faster polling for smoother UI

    def update_info_display(self):
        if not self.show_info: return
        
        def gather():
            stats = self.assistant.get_model_info()
            self.msg_queue.put(("update_info_ui", stats, None))
        
        threading.Thread(target=gather, daemon=True).start()

    def update_info_ui(self, stats):
        ram_val = stats['ram_mb'] if stats['ram_mb'] > 0 else "-"
        ram_unit = "MB" if stats['ram_mb'] > 0 else ""
        
        vram_val = stats['vram_mb'] if stats['vram_mb'] > 0 else "-"
        vram_unit = "MB" if stats['vram_mb'] > 0 else ""
        
        data = [
            ("Model: ", stats['model'], ""), 
            ("Remaining Context: ", f"{100-stats['context_pct']:.1f}", "%"),
            ("Long Term Memory: ", f"{stats['memory_entries']}", " rows"), 
            ("RAM Usage: ", ram_val, ram_unit), 
            ("VRAM Usage: ", vram_val, vram_unit)
        ]
        for i, (name, val, unit) in enumerate(data):
            self.info_labels[i][1].config(text=name)
            self.info_labels[i][2].config(text=val)
            self.info_labels[i][3].config(text=unit)
        self.on_info_canvas_configure(None)

    def cancel_generation(self, event=None):
        if self.input_field['state'] == 'disabled':
            self.stop_generation = True
            if self.active_process:
                try: os.kill(self.active_process.pid, signal.SIGTERM)
                except: pass

    def on_close(self):
        if self.active_process:
            try: os.kill(self.active_process.pid, signal.SIGTERM)
            except: pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AssistantApp(root)
    root.mainloop()
