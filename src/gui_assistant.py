import mistune
import tkinter as tk
from tkinter import scrolledtext, font, ttk
import threading
import queue
import sys
import re
import webbrowser
import local_assistant  # Access to client and classes
from utils import RedirectedStdout
from ui_components import CustomScrollbar

class AssistantGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Lokality v{local_assistant.VERSION}")
        self.root.geometry("900x700")
        
        # --- THEME & COLORS ---
        self.BG_COLOR = "#212121"       # Dark Grey
        self.FG_COLOR = "#ECECEC"       # Off-white
        self.ACCENT_COLOR = "#617D62"   # Duller/Muted Sage Green (Top border)
        self.COMMAND_COLOR = "#4CAF50"  # Brighter/Vibrant Green (Slash commands/Bottom border)
        self.INPUT_BG = "#303030"       # Slightly lighter grey for inputs
        self.BUTTON_FG = "#FFFFFF"

        self.root.configure(bg=self.BG_COLOR)

        # Markdown Parser
        self.md = mistune.create_markdown(plugins=['table', 'strikethrough'])

        # Style configuration for ttk widgets
        style = ttk.Style()
        style.theme_use('clam')

        style.configure("TFrame", background=self.BG_COLOR)
        
        # Font setup
        self.base_font = ("Roboto", 11)
        self.bold_font = ("Roboto", 11, "bold")
        self.italic_font = ("Roboto", 11, "italic")
        self.small_font = ("Roboto", 10, "italic")
        self.code_font = ("Consolas", 10) if sys.platform == "win32" else ("Monospace", 10)
        self.h1_font = ("Roboto", 16, "bold")
        self.h2_font = ("Roboto", 14, "bold")
        self.h3_font = ("Roboto", 12, "bold")

        # Configure Grid
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # Chat display area container (Rounded with 6px border)
        self.chat_canvas = tk.Canvas(root, bg=self.BG_COLOR, highlightthickness=0)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.chat_bg_id = self.round_rectangle(self.chat_canvas, 4, 4, 10, 10, radius=25, 
                                               outline=self.ACCENT_COLOR, width=6, fill=self.BG_COLOR)
        
        # Inner container for the actual text widget and scrollbar
        self.chat_inner = tk.Frame(self.chat_canvas, bg=self.BG_COLOR)
        self.chat_window_id = self.chat_canvas.create_window(10, 10, anchor="nw", window=self.chat_inner)
        
        self.chat_inner.grid_rowconfigure(0, weight=1)
        self.chat_inner.grid_columnconfigure(0, weight=1)

        self.chat_display = tk.Text(self.chat_inner, 
                                    state='disabled', 
                                    wrap='word', 
                                    font=self.base_font,
                                    bg=self.BG_COLOR,
                                    fg=self.FG_COLOR,
                                    insertbackground=self.FG_COLOR,
                                    borderwidth=0,
                                    highlightthickness=0,
                                    padx=15, pady=15)
        self.chat_display.grid(row=0, column=0, sticky="nsew")

        self.scrollbar = CustomScrollbar(self.chat_inner, command=self.chat_display.yview, bg=self.BG_COLOR)
        self.scrollbar.grid(row=0, column=1, sticky="ns", pady=15)
        self.chat_display.config(yscrollcommand=self.scrollbar.set)
        
        self.chat_canvas.bind("<Configure>", self.on_chat_canvas_configure)
        
        # Tags for Coloring & Markdown
        self.chat_display.tag_config("user", foreground="#81D4FA", font=self.bold_font) 
        self.chat_display.tag_config("assistant", foreground="#ECECEC", font=self.base_font) 
        self.chat_display.tag_config("system", foreground="#B0BEC5", font=self.small_font, tabs=("240",)) 
        self.chat_display.tag_config("error", foreground="#EF9A9A") 
        
        # Markdown specific tags
        self.chat_display.tag_config("md_bold", font=self.bold_font)
        self.chat_display.tag_config("md_italic", font=self.italic_font)
        self.chat_display.tag_config("md_code", font=self.code_font, background="#2D2D2D", foreground="#F8F8F2")
        self.chat_display.tag_config("md_h1", font=self.h1_font, spacing1=10, spacing3=5)
        self.chat_display.tag_config("md_h2", font=self.h2_font, spacing1=8, spacing3=4)
        self.chat_display.tag_config("md_h3", font=self.h3_font, spacing1=6, spacing3=3)
        self.chat_display.tag_config("md_table", font=self.code_font, background="#282828", spacing1=2, spacing3=2)
        self.chat_display.tag_config("md_link", foreground="#64B5F6", underline=False)

        # Bindings for links cursor
        self.chat_display.tag_bind("md_link", "<Enter>", lambda e: self.chat_display.config(cursor="hand2"))
        self.chat_display.tag_bind("md_link", "<Leave>", lambda e: self.chat_display.config(cursor=""))

        # State for streaming markdown
        self.chat_display.mark_set("assistant_msg_start", "1.0")
        self.chat_display.mark_gravity("assistant_msg_start", tk.LEFT)
        self.full_current_response = ""
        self.tooltip_window = None

        # Input Area Container (Rounded with 6px COMMAND_COLOR border)
        self.lower_canvas = tk.Canvas(root, bg=self.BG_COLOR, highlightthickness=0)
        self.lower_canvas.grid(row=1, column=0, sticky="ew", padx=10, pady=(25, 20))
        
        self.lower_bg_id = self.round_rectangle(self.lower_canvas, 4, 4, 10, 10, radius=20, 
                                               outline=self.COMMAND_COLOR, width=6, fill=self.INPUT_BG)
        
        self.lower_inner = tk.Frame(self.lower_canvas, bg=self.INPUT_BG)
        self.lower_window_id = self.lower_canvas.create_window(5, 5, anchor="nw", window=self.lower_inner)
        self.lower_inner.grid_columnconfigure(0, weight=1)
        self.lower_inner.grid_rowconfigure(0, weight=1)

        self.input_field = tk.Text(self.lower_inner, 
                                   height=1, 
                                   wrap='word', 
                                   font=self.base_font,
                                   bg=self.INPUT_BG,
                                   fg=self.FG_COLOR,
                                   insertbackground=self.FG_COLOR,
                                   borderwidth=0, 
                                   highlightthickness=0,
                                   padx=0, pady=0)
        self.input_field.grid(row=0, column=0, sticky="nsew", padx=15, pady=10)
        
        self.input_field.bind("<Tab>", self.handle_tab)
        self.input_field.bind("<Return>", self.handle_return)
        self.input_field.bind("<KeyRelease>", self.on_key_release)
        self.lower_canvas.bind("<Button-1>", lambda e: self.input_field.focus_set())

        self.lower_canvas.bind("<Configure>", self.on_lower_canvas_configure)

        # Logic Setup
        self.assistant = local_assistant.LocalChatAssistant()
        self.msg_queue = queue.Queue()
        self.SLASH_COMMANDS = [
            ["/help", "Show this help message"],
            ["/clear", "Clear conversation history"],
            ["/clear-long-term", "Reset long-term memory"],
            ["/exit", "Exit the application"]
        ]
        
        # Input highlighting tag
        self.input_field.tag_config("command_highlight", foreground=self.COMMAND_COLOR)
        
        # Force initial height adjustment
        self.adjust_input_height()
        
        # Redirect Stdout/Stderr
        sys.stdout = RedirectedStdout(self.msg_queue, "system")
        sys.stderr = RedirectedStdout(self.msg_queue, "error")

        self.root.after(100, self.check_queue)
        
        self.display_message("Type /help for commands.\n", "system")

    def round_rectangle(self, canvas, x1, y1, x2, y2, radius=25, **kwargs):
        points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
        return canvas.create_polygon(points, **kwargs, smooth=True)

    def on_chat_canvas_configure(self, event):
        w, h = event.width, event.height
        self.chat_canvas.delete(self.chat_bg_id)
        # Offset to 4px for 6px border
        self.chat_bg_id = self.round_rectangle(self.chat_canvas, 4, 4, w-4, h-4, radius=25, 
                                               outline=self.ACCENT_COLOR, width=6, fill=self.BG_COLOR)
        self.chat_canvas.tag_lower(self.chat_bg_id)
        
        # Resize inner window and provide enough padding to avoid clipping at corners
        pad = 12 
        self.chat_canvas.itemconfig(self.chat_window_id, width=w-(pad*2), height=h-(pad*2))
        self.chat_canvas.coords(self.chat_window_id, pad, pad)

    def on_lower_canvas_configure(self, event):
        self.update_lower_border()

    def update_lower_border(self):
        w = self.lower_canvas.winfo_width()
        h = self.lower_canvas.winfo_height()
        if w < 10 or h < 10: return
        self.lower_canvas.delete(self.lower_bg_id)
        # Offset to 4 to ensure 6px border is fully inside and not clipped
        self.lower_bg_id = self.round_rectangle(self.lower_canvas, 4, 4, w-4, h-4, radius=20, 
                                               outline=self.COMMAND_COLOR, width=6, fill=self.INPUT_BG)
        self.lower_canvas.tag_lower(self.lower_bg_id)
        
        # Window offset at 8,8 to be inside the 6px border
        pad_x = 8
        pad_y = 8
        self.lower_canvas.itemconfig(self.lower_window_id, width=w-(pad_x*2), height=h-(pad_y*2))
        self.lower_canvas.coords(self.lower_window_id, pad_x, pad_y)

    def on_key_release(self, event=None):
        self.adjust_input_height(event)
        self.highlight_commands()

    def highlight_commands(self):
        self.input_field.tag_remove("command_highlight", "1.0", tk.END)
        content = self.input_field.get("1.0", tk.END).strip()
        if content.startswith("/"):
            # Check if it matches exactly any of the commands
            first_word = content.split()[0] if content.split() else ""
            if any(first_word == cmd[0] for cmd in self.SLASH_COMMANDS):
                end_index = f"1.{len(first_word)}"
                self.input_field.tag_add("command_highlight", "1.0", end_index)

    def handle_tab(self, event):
        content = self.input_field.get("1.0", tk.INSERT).strip()
        if content.startswith("/"):
            matches = [cmd[0] for cmd in self.SLASH_COMMANDS if cmd[0].startswith(content)]
            if matches:
                # If multiple matches, pick the shortest one
                best_match = min(matches, key=len)
                self.input_field.delete("1.0", tk.INSERT)
                self.input_field.insert("1.0", best_match)
                self.highlight_commands()
            return "break"

    def adjust_input_height(self, event=None):
        # Calculate needed height
        content = self.input_field.get("1.0", "end-1c")
        num_lines = content.count('\n') + 1
        new_height = min(max(num_lines, 1), 8)
        self.input_field.config(height=new_height)
        
        # Adjust canvas height
        line_height = font.Font(font=self.input_field['font']).metrics('linespace')
        # pady=10 in grid + 8px canvas window offset = 18px top/bottom
        total_height = (new_height * line_height) + 36
        
        self.lower_canvas.config(height=total_height)
        self.update_lower_border()

    def on_btn_press(self, event):
        pass

    def on_btn_release(self, event):
        pass

    def handle_return(self, event):
        if not event.state & 0x1: # Shift not held
             self.send_message()
             return "break"

    def send_message(self):
        user_input = self.input_field.get("1.0", tk.END).strip()
        if not user_input:
            return

        self.input_field.delete("1.0", tk.END)
        self.adjust_input_height() # Reset height to 1 line
        
        self.display_message(f"\n{user_input}\n\n", "user")
        self.input_field.config(state='disabled')
        
        threading.Thread(target=self.process_input, args=(user_input,), daemon=True).start()

    def process_input(self, user_input):
        try:
            # Commands
            if user_input.lower() in ['/exit', 'exit', 'quit']:
                self.msg_queue.put(("quit", None, None))
                return
            if user_input.lower() == '/clear':
                self.assistant.messages = []
                print("Conversation memory cleared.")
                self.msg_queue.put(("clear", None, None))
                self.msg_queue.put(("enable", None, None))
                return
            if user_input.lower() == '/clear-long-term':
                self.assistant.clear_long_term_memory()
                self.msg_queue.put(("enable", None, None))
                return
            if user_input.lower() == '/help':
                help_text = "Available Commands:\n" + "\n".join([f"  {cmd}\t{desc}" for cmd, desc in self.SLASH_COMMANDS])
                print(help_text)
                self.msg_queue.put(("enable", None, None))
                return

            # Assistant Logic
            # decide_and_search prints to stdout, captured by RedirectedStdout
            search_context = self.assistant.decide_and_search(user_input)

            # Refresh contextual memory
            self.assistant._update_system_prompt(user_input)

            current_turn_messages = [{"role": "system", "content": self.assistant.system_prompt}] + self.assistant.messages
            if search_context:
                current_turn_messages.append({
                    "role": "system", 
                    "content": f"EXTRACTED INTERNET CONTEXT:\n{search_context}\n\nUse this to answer the next message."
                })
            current_turn_messages.append({"role": "user", "content": user_input})

            self.msg_queue.put(("text", "\n", "assistant"))
            
            full_response = ""
            stream = local_assistant.client.chat(model=local_assistant.MODEL_NAME, messages=current_turn_messages, stream=True)
            
            for chunk in stream:
                content = chunk['message']['content']
                full_response += content
                self.msg_queue.put(("text", content, "assistant"))
            
            self.msg_queue.put(("text", "\n", "assistant"))

            # Update History
            self.assistant.messages.append({"role": "user", "content": user_input})
            self.assistant.messages.append({"role": "assistant", "content": full_response})
            
            # Final Render trigger
            self.msg_queue.put(("final_render", "", "assistant"))

            # Memory update (Non-blocking)
            threading.Thread(target=self.assistant._update_memory, args=(user_input, full_response), daemon=True).start()

            if len(self.assistant.messages) > 20:
                self.assistant.messages = self.assistant.messages[-20:]

        except Exception as e:
            self.msg_queue.put(("text", f"Error: {e}\n", "error"))
        finally:
            self.msg_queue.put(("enable", None, None))

    def display_message(self, text, tag, final=False):
        self.chat_display.config(state='normal')
        
        if tag == "assistant":
            if not final:
                self.full_current_response += text
            
            # Optimization: Only re-render on newline, if text is getting long, or if it's the final render
            if "\n" in text or len(text) > 20 or final:
                self.chat_display.delete("assistant_msg_start", "end-1c")
                try:
                    ast_parser = mistune.create_markdown(renderer=None, plugins=['table', 'strikethrough'])
                    tokens = ast_parser(self.full_current_response)
                    self.render_tokens(tokens, "assistant")
                except Exception:
                    self.chat_display.insert(tk.END, self.full_current_response, "assistant")
            else:
                # Just append raw during character streaming for smoothness
                self.chat_display.insert(tk.END, text, "assistant")
        else:
            self.chat_display.insert(tk.END, text, tag)
            self.chat_display.mark_set("assistant_msg_start", "end-1c")
            self.full_current_response = ""
            
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def render_tokens(self, tokens, base_tag, extra_tags=None):
        tags = (base_tag,) if extra_tags is None else (extra_tags, base_tag)
        
        for token in tokens:
            t_type = token['type']
            
            if t_type == 'paragraph' or t_type == 'block_text':
                self.render_tokens(token['children'], base_tag)
                if t_type == 'paragraph':
                    self.chat_display.insert(tk.END, "\n\n")
            
            elif t_type == 'text':
                self.chat_display.insert(tk.END, token.get('raw', token.get('text', '')), tags)
            
            elif t_type == 'strong':
                self.render_tokens(token['children'], base_tag, "md_bold")
            
            elif t_type == 'emphasis':
                self.render_tokens(token['children'], base_tag, "md_italic")
            
            elif t_type == 'codespan':
                self.chat_display.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))
            
            elif t_type == 'block_code':
                self.chat_display.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))
                self.chat_display.insert(tk.END, "\n", base_tag)
            
            elif t_type == 'heading':
                level = token['attrs']['level']
                h_tag = f"md_h{level}" if level <= 3 else "md_h3"
                self.render_tokens(token['children'], base_tag, h_tag)
                self.chat_display.insert(tk.END, "\n")
            
            elif t_type == 'table':
                try:
                    self.render_table(token, base_tag)
                except Exception:
                    pass
                self.chat_display.insert(tk.END, "\n")

            elif t_type == 'list':
                self.render_tokens(token['children'], base_tag)
                self.chat_display.insert(tk.END, "\n")

            elif t_type == 'list_item':
                self.chat_display.insert(tk.END, "• ", base_tag)
                self.render_tokens(token['children'], base_tag)
                if self.chat_display.get("end-2c", "end-1c") != "\n":
                    self.chat_display.insert(tk.END, "\n")

            elif t_type == 'softbreak':
                self.chat_display.insert(tk.END, "\n")
            
            elif t_type == 'link':
                link_text = self.get_token_text(token['children'])
                url = token['attrs']['url']
                # Store URL in a unique tag for this specific link instance
                unique_tag = f"link_{id(token)}"
                self.chat_display.tag_config(unique_tag, underline=False) 
                self.chat_display.insert(tk.END, link_text, ("md_link", unique_tag, base_tag))
                
                # Bindings for this specific link
                self.chat_display.tag_bind(unique_tag, "<Control-Button-1>", lambda e, u=url: webbrowser.open(u))
                self.chat_display.tag_bind(unique_tag, "<Enter>", lambda e, u=url: self.show_tooltip(e, u))
                self.chat_display.tag_bind(unique_tag, "<Leave>", self.hide_tooltip)

    def show_tooltip(self, event, url):
        if self.tooltip_window:
            return
        
        # Calculate position
        x = self.root.winfo_pointerx() + 15
        y = self.root.winfo_pointery() + 15
        
        self.tooltip_window = tw = tk.Toplevel(self.root)
        tw.wm_overrideredirect(True) # Remove window decorations
        tw.wm_geometry(f"{x}+{y}")
        
        label = tk.Label(tw, text=f"Ctrl + Click to open {url}", 
                         justify='left', background="#37474F", foreground="#ECECEC",
                         relief='solid', borderwidth=1, font=("Roboto", 9),
                         padx=5, pady=2)
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def open_link(self, event):
        # This is a fallback/generic handler if needed
        pass

    def render_table(self, token, base_tag):
        # mistune 3.x structure:
        # children[0] is table_head
        # children[1] is table_body
        
        try:
            head_token = token['children'][0]
            body_token = token['children'][1] if len(token['children']) > 1 else None
            
            # Extract header cells
            header_cells = [self.get_token_text(c['children']) for c in head_token['children']]
            
            # Extract body rows
            rows = []
            if body_token:
                for row_token in body_token['children']:
                    rows.append([self.get_token_text(c['children']) for c in row_token['children']])
            
            # --- Graphical Rendering using a Frame ---
            # Create a frame to hold the grid - transparent look by using same bg as display
            table_frame = tk.Frame(self.chat_display, bg=self.ACCENT_COLOR, bd=0)
            
            # Column headers
            for j, val in enumerate(header_cells):
                # Use highlightthickness to simulate a border while keeping transparency
                lbl = tk.Label(table_frame, text=val, font=self.bold_font, 
                               bg=self.BG_COLOR, fg=self.FG_COLOR, 
                               padx=10, pady=5, relief="flat", anchor="w",
                               highlightthickness=2, highlightbackground=self.ACCENT_COLOR)
                lbl.grid(row=0, column=j, sticky="nsew")
                
            # Data rows
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    lbl = tk.Label(table_frame, text=val, font=self.base_font, 
                                   bg=self.BG_COLOR, fg=self.FG_COLOR, 
                                   padx=10, pady=5, relief="flat", anchor="w",
                                   highlightthickness=2, highlightbackground=self.ACCENT_COLOR)
                    lbl.grid(row=i+1, column=j, sticky="nsew")

            # Ensure columns expand
            for j in range(len(header_cells)):
                table_frame.grid_columnconfigure(j, weight=1)

            # Insert the frame into the text widget
            self.chat_display.insert(tk.END, "\n")
            self.chat_display.window_create(tk.END, window=table_frame)
            self.chat_display.insert(tk.END, "\n")
            
        except Exception as e:
            # If parsing fails during streaming (e.g. incomplete table), 
            # we could show raw text if we had it, but here we just skip 
            # until it's valid.
            pass

    def get_token_text(self, children):
        text = ""
        for child in children:
            if 'raw' in child:
                text += child['raw']
            elif 'text' in child:
                text += child['text']
            elif 'children' in child:
                text += self.get_token_text(child['children'])
        return text

    def check_queue(self):
        while not self.msg_queue.empty():
            action, content, tag = self.msg_queue.get_nowait()
            if action == "text":
                self.display_message(content, tag)
            elif action == "clear":
                self.chat_display.config(state='normal')
                self.chat_display.delete("1.0", tk.END)
                self.chat_display.config(state='disabled')
                self.display_message("Type /help for commands.\n", "system")
                self.full_current_response = ""
            elif action == "final_render":
                self.display_message("", tag, final=True)
            elif action == "enable":
                self.input_field.config(state='normal')
                self.input_field.focus_set()
            elif action == "quit":
                self.root.quit()
        self.root.after(100, self.check_queue)

if __name__ == "__main__":
    try:
        root = tk.Tk()
        gui = AssistantGUI(root)
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        pass
