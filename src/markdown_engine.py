import tkinter as tk
import webbrowser

from theme import Theme

class MarkdownEngine:
    def __init__(self, text_widget, tooltip_callback):
        self.text_widget = text_widget
        self.tooltip_callback = tooltip_callback
        self.fonts = Theme.get_fonts()
        self.url_map = {} # Maps tag ranges to URLs
        
        # Configure the shared link tag once
        self.text_widget.tag_config("md_link", foreground=Theme.LINK_COLOR, underline=True)
        self.text_widget.tag_bind("md_link", "<Control-Button-1>", self._on_link_click)
        self.text_widget.tag_bind("md_link", "<Enter>", self._on_link_enter)
        self.text_widget.tag_bind("md_link", "<Leave>", self._on_link_leave)
        self.text_widget.tag_bind("md_link", "<Motion>", self._on_link_motion)

    def clear(self):
        """Resets the URL mapping to prevent memory leaks."""
        self.url_map.clear()

    def _get_url_at_index(self, index):
        """Finds the URL associated with the link at the given text index."""
        # Tkinter doesn't easily store metadata per-range, so we use a range map
        # However, for a chat app, we can just look at tags at that position
        tags = self.text_widget.tag_names(index)
        for t in tags:
            if t.startswith("link_data_"):
                return self.url_map.get(t)
        return None

    def _on_link_click(self, event):
        url = self._get_url_at_index(f"@{event.x},{event.y}")
        if url: webbrowser.open(url)

    def _on_link_enter(self, event):
        self.text_widget.config(cursor="hand2")

    def _on_link_leave(self, event):
        self.text_widget.config(cursor="")
        self.tooltip_callback(None, None)

    def _on_link_motion(self, event):
        url = self._get_url_at_index(f"@{event.x},{event.y}")
        self.tooltip_callback(event, url)

    def _bind_scroll(self, widget):
        """Helper to propagate scroll events from embedded widgets to the main text area."""
        def _on_mousewheel(event):
            self.text_widget.yview_scroll(int(-1*(event.delta/120)), "units")
        def _on_linux_scroll_up(event):
            self.text_widget.yview_scroll(-1, "units")
        def _on_linux_scroll_down(event):
            self.text_widget.yview_scroll(1, "units")
            
        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", _on_linux_scroll_up)
        widget.bind("<Button-5>", _on_linux_scroll_down)
        
        # Also bind for all children if any (e.g. Labels in a Table Frame)
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def render_tokens(self, tokens, base_tag, extra_tags=None, level=0):
        # Accumulate tags for nested styling
        style_tags = []
        if extra_tags:
            if isinstance(extra_tags, (list, tuple)): style_tags.extend(extra_tags)
            else: style_tags.append(extra_tags)
        
        for token in tokens:
            t_type = token['type']
            
            # Helper to manage nested styles (Bold + Italic)
            def get_nested_tags(new_style):
                new_list = style_tags + [new_style]
                if "md_bold" in new_list and "md_italic" in new_list:
                    # Replace both with the combined tag
                    res = [t for t in new_list if t not in ("md_bold", "md_italic")]
                    res.append("md_bold_italic")
                    return res
                return new_list

            handlers = {
                'paragraph': lambda t: (self.render_tokens(t['children'], base_tag, style_tags, level), 
                                        self.text_widget.insert(tk.END, "\n") if level > 0 else self.text_widget.insert(tk.END, "\n\n")),
                'block_text': lambda t: self.render_tokens(t['children'], base_tag, style_tags, level),
                'text': lambda t: self.text_widget.insert(tk.END, t.get('raw', t.get('text', '')), tuple(style_tags + [base_tag])),
                'strong': lambda t: self.render_tokens(t['children'], base_tag, get_nested_tags("md_bold"), level),
                'emphasis': lambda t: self.render_tokens(t['children'], base_tag, get_nested_tags("md_italic"), level),
                'subscript': lambda t: self.render_tokens(t['children'], base_tag, style_tags + ["md_sub"], level),
                'superscript': lambda t: self.render_tokens(t['children'], base_tag, style_tags + ["md_sup"], level),
                'strikethrough': lambda t: self.render_tokens(t['children'], base_tag, style_tags + ["md_strikethrough"], level),
                'codespan': lambda t: self.text_widget.insert(tk.END, t.get('raw', ''), ("md_code", base_tag)),
                'block_code': lambda t: (self.text_widget.insert(tk.END, t.get('raw', ''), ("md_code", base_tag)), self.text_widget.insert(tk.END, "\n", base_tag)),
                'heading': lambda t: (self.text_widget.insert(tk.END, "\n") if self.text_widget.index("end-1c") != "1.0" else None, 
                                      self.render_tokens(t['children'], base_tag, f"md_h{min(3, t['attrs']['level'])}", level), 
                                      self.text_widget.insert(tk.END, "\n")),
                'table': lambda t: (self.render_table(t, base_tag), self.text_widget.insert(tk.END, "\n")),
                'list': lambda t: self._render_list(t, base_tag, level),
                'block_quote': lambda t: self._render_blockquote(t, base_tag, style_tags, level),
                'thematic_break': lambda t: self._render_hr(base_tag),
                'softbreak': lambda t: self.text_widget.insert(tk.END, "\n"),
                'link': self._render_link
            }
            
            if t_type in handlers:
                handlers[t_type](token)

    def _render_hr(self, base_tag):
        """Renders a thick horizontal rule."""
        w = max(400, self.text_widget.winfo_width() - 60)
        canv = tk.Canvas(self.text_widget, bg=Theme.BG_COLOR, height=6, highlightthickness=0, width=w)
        canv.create_line(0, 3, w, 3, fill=Theme.ACCENT_COLOR, width=4)
        self._bind_scroll(canv)
        self.text_widget.insert(tk.END, "\n")
        self.text_widget.window_create(tk.END, window=canv)
        self.text_widget.insert(tk.END, "\n\n")

    def _render_blockquote(self, token, base_tag, style_tags, level):
        """Renders a blockquote with a vertical sidebar indicator."""
        if self.text_widget.index("end-1c") != "1.0":
            self.text_widget.insert(tk.END, "\n")
        
        # Apply md_quote to the whole block by passing it to children
        # We also prepend the bar character
        self.text_widget.insert(tk.END, "┃ ", ("md_quote_bar", base_tag))
        self.render_tokens(token['children'], base_tag, style_tags + ["md_quote"], level + 1)
        
        if self.text_widget.get("end-2c", "end-1c") != "\n":
            self.text_widget.insert(tk.END, "\n")

    def _render_list(self, token, base_tag, level=0):
        attrs = token.get('attrs', {})
        ordered = attrs.get('ordered', False)
        start = attrs.get('start', 1)
        indent = "    " * level
        for i, item in enumerate(token['children']):
            # Ensure we are on a new line for each item
            if self.text_widget.get("end-2c", "end-1c") != "\n" and self.text_widget.index("end-1c") != "1.0":
                self.text_widget.insert(tk.END, "\n")
                
            prefix = f"{indent}{start + i}. " if ordered else f"{indent}• "
            self.text_widget.insert(tk.END, prefix, base_tag)
            
            # List items in Mistune usually contain blocks (like paragraph)
            self.render_tokens(item['children'], base_tag, level=level + 1)
            
        if level == 0:
            self.text_widget.insert(tk.END, "\n")

    def _render_link(self, token):
        link_text = self.get_token_text(token['children'])
        url = token['attrs']['url']
        link_id = f"link_data_{hash(url)}"
        self.url_map[link_id] = url
        # Use tags to identify links and their specific data ID
        self.text_widget.insert(tk.END, link_text, ("md_link", link_id))

    def render_table(self, token, base_tag):
        try:
            header_cells, rows = [], []
            # 1. Try Mistune 3.x structure (thead/tbody)
            sections = token.get('children', [])
            if any(s['type'] in ['thead', 'tbody'] for s in sections):
                for section in sections:
                    if section['type'] == 'thead':
                        for tr in section['children']:
                            header_cells = [self.get_token_text(td['children']) for td in tr['children']]
                    elif section['type'] == 'tbody':
                        for tr in section['children']:
                            rows.append([self.get_token_text(td['children']) for td in tr['children']])
            else:
                # 2. Try older/simpler structure
                if len(sections) >= 1:
                    header_cells = [self.get_token_text(c['children']) for c in sections[0]['children']]
                    if len(sections) > 1:
                        for row_token in sections[1]['children']:
                            rows.append([self.get_token_text(c['children']) for c in row_token['children']])
            
            if not header_cells and rows: header_cells = [""] * len(rows[0])
            if not header_cells: return

            table_frame = tk.Frame(self.text_widget, bg=Theme.ACCENT_COLOR, bd=0)
            for j, val in enumerate(header_cells):
                tk.Label(table_frame, text=val, font=self.fonts["bold"], bg=Theme.BG_COLOR, fg=Theme.FG_COLOR, 
                         padx=10, pady=5, relief="flat", anchor="w", highlightthickness=1, highlightbackground=Theme.ACCENT_COLOR).grid(row=0, column=j, sticky="nsew")
                
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    tk.Label(table_frame, text=val, font=self.fonts["base"], bg=Theme.BG_COLOR, fg=Theme.FG_COLOR, 
                             padx=10, pady=5, relief="flat", anchor="w", highlightthickness=1, highlightbackground=Theme.ACCENT_COLOR).grid(row=i+1, column=j, sticky="nsew")

            for j in range(len(header_cells)): table_frame.grid_columnconfigure(j, weight=1)

            self._bind_scroll(table_frame)
            self.text_widget.insert(tk.END, "\n")
            self.text_widget.window_create(tk.END, window=table_frame)
            self.text_widget.insert(tk.END, "\n")
            
        except Exception as e:
            debug_print(f"Markdown: Error rendering table: {e}")

    def get_token_text(self, children):
        return "".join([c.get('raw', c.get('text', self.get_token_text(c.get('children', [])))) for c in children])
