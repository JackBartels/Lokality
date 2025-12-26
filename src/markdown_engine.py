import tkinter as tk
import mistune
import webbrowser
from theme import Theme

class MarkdownEngine:
    def __init__(self, text_widget, tooltip_callback):
        self.text_widget = text_widget
        self.tooltip_callback = tooltip_callback
        self.fonts = Theme.get_fonts()

    def render_tokens(self, tokens, base_tag, extra_tags=None):
        tags = (base_tag,) if extra_tags is None else (extra_tags, base_tag)
        
        for token in tokens:
            t_type = token['type']
            
            if t_type == 'paragraph' or t_type == 'block_text':
                self.render_tokens(token['children'], base_tag)
                if t_type == 'paragraph':
                    self.text_widget.insert(tk.END, "\n\n")
            
            elif t_type == 'text':
                self.text_widget.insert(tk.END, token.get('raw', token.get('text', '')), tags)
            
            elif t_type == 'strong':
                self.render_tokens(token['children'], base_tag, "md_bold")
            
            elif t_type == 'emphasis':
                self.render_tokens(token['children'], base_tag, "md_italic")
            
            elif t_type == 'codespan':
                self.text_widget.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))
            
            elif t_type == 'block_code':
                self.text_widget.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))
                self.text_widget.insert(tk.END, "\n", base_tag)
            
            elif t_type == 'heading':
                level = token['attrs']['level']
                h_tag = f"md_h{level}" if level <= 3 else "md_h3"
                self.render_tokens(token['children'], base_tag, h_tag)
                self.text_widget.insert(tk.END, "\n")
            
            elif t_type == 'table':
                self.render_table(token, base_tag)
                self.text_widget.insert(tk.END, "\n")

            elif t_type == 'list':
                self.render_tokens(token['children'], base_tag)
                self.text_widget.insert(tk.END, "\n")

            elif t_type == 'list_item':
                self.text_widget.insert(tk.END, "• ", base_tag)
                self.render_tokens(token['children'], base_tag)
                if self.text_widget.get("end-2c", "end-1c") != "\n":
                    self.text_widget.insert(tk.END, "\n")

            elif t_type == 'softbreak':
                self.text_widget.insert(tk.END, "\n")
            
            elif t_type == 'link':
                link_text = self.get_token_text(token['children'])
                url = token['attrs']['url']
                # OPTIMIZATION: Use a fixed tag for links instead of unique per-token tags to avoid tag accumulation
                self.text_widget.insert(tk.END, link_text, ("md_link", base_tag))
                
                # We need to bind specific events for this specific range
                # Since we are using a shared tag "md_link", we'll use mark-based or range-based binds if possible
                # But for simplicity and to fix the leak, we'll keep it simple for now or use a small pool.
                # Actually, unique tags are needed for specific URLs, but we should reuse them if content is same.
                # To really optimize, we'd use one tag and find the URL at the index on click.
                
                unique_tag = f"link_{hash(url)}" # Reuse tag for same URL
                self.text_widget.tag_add(unique_tag, "end-1c - %dc" % len(link_text), "end-1c")
                self.text_widget.tag_bind(unique_tag, "<Control-Button-1>", lambda e, u=url: webbrowser.open(u))
                self.text_widget.tag_bind(unique_tag, "<Enter>", lambda e, u=url: self.tooltip_callback(e, u))
                self.text_widget.tag_bind(unique_tag, "<Leave>", lambda e: self.tooltip_callback(None, None))

    def render_table(self, token, base_tag):
        try:
            head_token = token['children'][0]
            body_token = token['children'][1] if len(token['children']) > 1 else None
            header_cells = [self.get_token_text(c['children']) for c in head_token['children']]
            rows = []
            if body_token:
                for row_token in body_token['children']:
                    rows.append([self.get_token_text(c['children']) for c in row_token['children']])
            
            table_frame = tk.Frame(self.text_widget, bg=Theme.ACCENT_COLOR, bd=0)
            
            for j, val in enumerate(header_cells):
                lbl = tk.Label(table_frame, text=val, font=self.fonts["bold"], 
                               bg=Theme.BG_COLOR, fg=Theme.FG_COLOR, 
                               padx=10, pady=5, relief="flat", anchor="w",
                               highlightthickness=2, highlightbackground=Theme.ACCENT_COLOR)
                lbl.grid(row=0, column=j, sticky="nsew")
                
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    lbl = tk.Label(table_frame, text=val, font=self.fonts["base"], 
                                   bg=Theme.BG_COLOR, fg=Theme.FG_COLOR, 
                                   padx=10, pady=5, relief="flat", anchor="w",
                                   highlightthickness=2, highlightbackground=Theme.ACCENT_COLOR)
                    lbl.grid(row=i+1, column=j, sticky="nsew")

            for j in range(len(header_cells)):
                table_frame.grid_columnconfigure(j, weight=1)

            self.text_widget.insert(tk.END, "\n")
            # OPTIMIZATION: Removed table_frame.update_idletasks() - it's very slow in a loop
            self.text_widget.window_create(tk.END, window=table_frame)
            self.text_widget.insert(tk.END, "\n ") 
            
        except Exception:
            pass

    def get_token_text(self, children):
        return "".join([c.get('raw', c.get('text', self.get_token_text(c.get('children', [])))) for c in children])
