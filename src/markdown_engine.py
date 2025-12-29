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
        
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def render_tokens(self, tokens, base_tag, extra_tags=None, level=0):
        """Main entry point for rendering a list of tokens."""
        style_tags = []
        if extra_tags:
            if isinstance(extra_tags, (list, tuple)): style_tags.extend(extra_tags)
            else: style_tags.append(extra_tags)
        
        for token in tokens:
            self._dispatch_token(token, base_tag, style_tags, level)

    def _dispatch_token(self, token, base_tag, style_tags, level):
        """Dispatcher for different token types."""
        t_type = token['type']
        
        handlers = {
            'paragraph': self._handle_paragraph,
            'block_text': self._handle_block_text,
            'text': self._handle_text,
            'strong': self._handle_strong,
            'emphasis': self._handle_emphasis,
            'subscript': self._handle_subscript,
            'superscript': self._handle_superscript,
            'strikethrough': self._handle_strikethrough,
            'codespan': self._handle_codespan,
            'block_code': self._handle_block_code,
            'heading': self._handle_heading,
            'table': self._handle_table,
            'list': self._handle_list,
            'block_quote': self._handle_block_quote,
            'thematic_break': self._handle_thematic_break,
            'softbreak': self._handle_softbreak,
            'link': self._handle_link
        }
        
        if t_type in handlers:
            handlers[t_type](token, base_tag, style_tags, level)

    def _get_nested_tags(self, current_tags, new_style):
        """Helper to manage nested styles and combined tags (e.g. Bold + Italic)."""
        new_list = current_tags + [new_style]
        if "md_bold" in new_list and "md_italic" in new_list:
            res = [t for t in new_list if t not in ("md_bold", "md_italic")]
            res.append("md_bold_italic")
            return res
        return new_list

    # --- Token Handlers ---

    def _handle_paragraph(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, style_tags, level)
        self.text_widget.insert(tk.END, "\n" if level > 0 else "\n\n")

    def _handle_block_text(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, style_tags, level)

    def _handle_text(self, token, base_tag, style_tags, level):
        content = token.get('raw', token.get('text', ''))
        self.text_widget.insert(tk.END, content, tuple(style_tags + [base_tag]))

    def _handle_strong(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, self._get_nested_tags(style_tags, "md_bold"), level)

    def _handle_emphasis(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, self._get_nested_tags(style_tags, "md_italic"), level)

    def _handle_subscript(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, style_tags + ["md_sub"], level)

    def _handle_superscript(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, style_tags + ["md_sup"], level)

    def _handle_strikethrough(self, token, base_tag, style_tags, level):
        self.render_tokens(token['children'], base_tag, style_tags + ["md_strikethrough"], level)

    def _handle_codespan(self, token, base_tag, style_tags, level):
        self.text_widget.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))

    def _handle_block_code(self, token, base_tag, style_tags, level):
        self.text_widget.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))
        self.text_widget.insert(tk.END, "\n", base_tag)

    def _handle_heading(self, token, base_tag, style_tags, level):
        if self.text_widget.index("end-1c") != "1.0":
            self.text_widget.insert(tk.END, "\n")
        h_level = min(3, token['attrs']['level'])
        self.render_tokens(token['children'], base_tag, f"md_h{h_level}", level)
        self.text_widget.insert(tk.END, "\n")

    def _handle_softbreak(self, token, base_tag, style_tags, level):
        self.text_widget.insert(tk.END, "\n")

    def _handle_thematic_break(self, token, base_tag, style_tags, level):
        """Renders a thick horizontal rule."""
        w = max(400, self.text_widget.winfo_width() - 60)
        canv = tk.Canvas(self.text_widget, bg=Theme.BG_COLOR, height=6, highlightthickness=0, width=w)
        canv.create_line(0, 3, w, 3, fill=Theme.ACCENT_COLOR, width=4)
        self._bind_scroll(canv)
        self.text_widget.insert(tk.END, "\n")
        self.text_widget.window_create(tk.END, window=canv)
        self.text_widget.insert(tk.END, "\n\n")

    def _handle_block_quote(self, token, base_tag, style_tags, level):
        """Renders a blockquote with a vertical sidebar indicator."""
        if self.text_widget.index("end-1c") != "1.0":
            self.text_widget.insert(tk.END, "\n")
        self.text_widget.insert(tk.END, "┃ ", ("md_quote_bar", base_tag))
        self.render_tokens(token['children'], base_tag, style_tags + ["md_quote"], level + 1)
        if self.text_widget.get("end-2c", "end-1c") != "\n":
            self.text_widget.insert(tk.END, "\n")

    def _handle_list(self, token, base_tag, style_tags, level):
        attrs = token.get('attrs', {})
        ordered = attrs.get('ordered', False)
        start = attrs.get('start', 1)
        indent = "    " * level
        for i, item in enumerate(token['children']):
            if self.text_widget.get("end-2c", "end-1c") != "\n" and self.text_widget.index("end-1c") != "1.0":
                self.text_widget.insert(tk.END, "\n")
            prefix = f"{indent}{start + i}. " if ordered else f"{indent}• "
            self.text_widget.insert(tk.END, prefix, base_tag)
            self.render_tokens(item['children'], base_tag, level=level + 1)
        if level == 0:
            self.text_widget.insert(tk.END, "\n")

    def _handle_link(self, token, base_tag, style_tags, level):
        link_text = self.get_token_text(token['children'])
        url = token['attrs']['url']
        link_id = f"link_data_{hash(url)}"
        self.url_map[link_id] = url
        self.text_widget.insert(tk.END, link_text, ("md_link", link_id))

    def _handle_table(self, token, base_tag, style_tags, level):
        try:
            header_cells, rows = [], []
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
            from utils import debug_print
            debug_print(f"Markdown: Error rendering table: {e}")

    def get_token_text(self, children):
        return "".join([c.get('raw', c.get('text', self.get_token_text(c.get('children', [])))) for c in children])