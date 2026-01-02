"""
Markdown rendering engine for Lokality.
Converts Markdown tokens into Tkinter text widget elements.
"""
import tkinter as tk
import webbrowser
from utils import debug_print
from theme import Theme

class MarkdownEngine:
    """
    Renders a stream of Markdown tokens into a Tkinter Text widget.
    """
    def __init__(self, text_widget, tooltip_callback):
        self._text_widget = None
        self.tooltip_callback = tooltip_callback
        self.fonts = Theme.get_fonts()
        self.url_map = {} # Maps tag names to URLs

        # Use the setter if a widget is provided
        self.text_widget = text_widget

    @property
    def text_widget(self):
        """Returns the current text widget."""
        return self._text_widget

    @text_widget.setter
    def text_widget(self, widget):
        """Sets the text widget and configures tags if widget is not None."""
        self._text_widget = widget
        if self._text_widget:
            self._configure_widget()

    def _configure_widget(self):
        """Configures tags and bindings on the text widget."""
        self._text_widget.tag_config(
            "md_link", foreground=Theme.LINK_COLOR, underline=True
        )
        self._text_widget.tag_bind(
            "md_link", "<Control-Button-1>", self._on_link_click
        )
        self._text_widget.tag_bind("md_link", "<Enter>", self._on_link_enter)
        self._text_widget.tag_bind("md_link", "<Leave>", self._on_link_leave)
        self._text_widget.tag_bind("md_link", "<Motion>", self._on_link_motion)

    def clear(self):
        """Resets the URL mapping to prevent memory leaks."""
        self.url_map.clear()

    def _get_url_at_index(self, index):
        """Finds the URL associated with the link at the given text index."""
        tags = self.text_widget.tag_names(index)
        for tag in tags:
            if tag.startswith("link_data_"):
                return self.url_map.get(tag)
        return None

    def _on_link_click(self, event):
        url = self._get_url_at_index(f"@{event.x},{event.y}")
        if url:
            webbrowser.open(url)

    def _on_link_enter(self, _):
        self.text_widget.config(cursor="hand2")

    def _on_link_leave(self, _):
        self.text_widget.config(cursor="")
        self.tooltip_callback(None, None)

    def _on_link_motion(self, event):
        url = self._get_url_at_index(f"@{event.x},{event.y}")
        self.tooltip_callback(event, url)

    def _bind_scroll(self, widget):
        """Propagates scroll events from embedded widgets to main text area."""
        def _on_mousewheel(event):
            self.text_widget.yview_scroll(int(-1*(event.delta/120)), "units")
        def _on_linux_up(_):
            self.text_widget.yview_scroll(-1, "units")
        def _on_linux_down(_):
            self.text_widget.yview_scroll(1, "units")

        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", _on_linux_up)
        widget.bind("<Button-5>", _on_linux_down)

        for child in widget.winfo_children():
            self._bind_scroll(child)

    def render_tokens(self, tokens, base_tag, extra_tags=None, level=0):
        """Main entry point for rendering a list of tokens."""
        if not self.text_widget:
            return

        style_tags = []
        if extra_tags:
            if isinstance(extra_tags, (list, tuple)):
                style_tags.extend(extra_tags)
            else:
                style_tags.append(extra_tags)

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
        """Helper to manage combined tags (e.g. Bold + Italic)."""
        new_list = current_tags + [new_style]
        if "md_bold" in new_list and "md_italic" in new_list:
            res = [t for t in new_list if t not in ("md_bold", "md_italic")]
            res.append("md_bold_italic")
            return res
        return new_list

    # --- Token Handlers ---

    def _handle_paragraph(self, token, base_tag, style_tags, level):
        """Renders a paragraph token."""
        self.render_tokens(token['children'], base_tag, style_tags, level)
        self.text_widget.insert(tk.END, "\n" if level > 0 else "\n\n")

    def _handle_block_text(self, token, base_tag, style_tags, level):
        """Renders a block_text token."""
        self.render_tokens(token['children'], base_tag, style_tags, level)

    def _handle_text(self, token, base_tag, style_tags, level):
        """Renders a text token."""
        del level
        content = token.get('raw', token.get('text', ''))
        self.text_widget.insert(tk.END, content, tuple(style_tags + [base_tag]))

    def _handle_strong(self, token, base_tag, style_tags, level):
        """Renders a strong token."""
        tags = self._get_nested_tags(style_tags, "md_bold")
        self.render_tokens(token['children'], base_tag, tags, level)

    def _handle_emphasis(self, token, base_tag, style_tags, level):
        """Renders an emphasis token."""
        tags = self._get_nested_tags(style_tags, "md_italic")
        self.render_tokens(token['children'], base_tag, tags, level)

    def _handle_subscript(self, token, base_tag, style_tags, level):
        """Renders a subscript token."""
        self.render_tokens(token['children'], base_tag, style_tags + ["md_sub"], level)

    def _handle_superscript(self, token, base_tag, style_tags, level):
        """Renders a superscript token."""
        self.render_tokens(token['children'], base_tag, style_tags + ["md_sup"], level)

    def _handle_strikethrough(self, token, base_tag, style_tags, level):
        """Renders a strikethrough token."""
        tags = style_tags + ["md_strikethrough"]
        self.render_tokens(token['children'], base_tag, tags, level)

    def _handle_codespan(self, token, base_tag, style_tags, level):
        """Renders a codespan token."""
        del style_tags, level
        self.text_widget.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))

    def _handle_block_code(self, token, base_tag, style_tags, level):
        """Renders a block_code token."""
        del style_tags, level
        self.text_widget.insert(tk.END, token.get('raw', ''), ("md_code", base_tag))
        self.text_widget.insert(tk.END, "\n", base_tag)

    def _handle_heading(self, token, base_tag, style_tags, level):
        """Renders a heading token."""
        del style_tags
        if self.text_widget.index("end-1c") != "1.0":
            self.text_widget.insert(tk.END, "\n")
        h_level = min(3, token['attrs']['level'])
        self.render_tokens(token['children'], base_tag, f"md_h{h_level}", level)
        self.text_widget.insert(tk.END, "\n")

    def _handle_softbreak(self, token, base_tag, style_tags, level):
        """Renders a softbreak token."""
        del token, base_tag, style_tags, level
        self.text_widget.insert(tk.END, "\n")

    def _handle_thematic_break(self, token, base_tag, style_tags, level):
        """Renders a thick horizontal rule."""
        del token, base_tag, style_tags, level
        width = max(400, self.text_widget.winfo_width() - 60)
        canv = tk.Canvas(
            self.text_widget, bg=Theme.BG_COLOR, height=6,
            highlightthickness=0, width=width
        )
        canv.create_line(0, 3, width, 3, fill=Theme.ACCENT_COLOR, width=4)
        self._bind_scroll(canv)
        self.text_widget.insert(tk.END, "\n")
        self.text_widget.window_create(tk.END, window=canv)
        self.text_widget.insert(tk.END, "\n\n")

    def _handle_block_quote(self, token, base_tag, style_tags, level):
        """Renders a blockquote with a vertical sidebar indicator."""
        if self.text_widget.index("end-1c") != "1.0":
            self.text_widget.insert(tk.END, "\n")
        self.text_widget.insert(tk.END, "┃ ", ("md_quote_bar", base_tag))
        self.render_tokens(
            token['children'], base_tag, style_tags + ["md_quote"], level + 1
        )
        if self.text_widget.get("end-2c", "end-1c") != "\n":
            self.text_widget.insert(tk.END, "\n")

    def _handle_list(self, token, base_tag, style_tags, level):
        """Renders a list token."""
        del style_tags
        attrs = token.get('attrs', {})
        ordered = attrs.get('ordered', False)
        start = attrs.get('start', 1)
        indent = "    " * level
        for i, item in enumerate(token['children']):
            if (
                self.text_widget.get("end-2c", "end-1c") != "\n" and
                self.text_widget.index("end-1c") != "1.0"
            ):
                self.text_widget.insert(tk.END, "\n")
            prefix = f"{indent}{start + i}. " if ordered else f"{indent}• "
            self.text_widget.insert(tk.END, prefix, base_tag)
            self.render_tokens(item['children'], base_tag, level=level + 1)
        if level == 0:
            self.text_widget.insert(tk.END, "\n")

    def _handle_link(self, token, base_tag, style_tags, level):
        """Renders a link token."""
        del base_tag, style_tags, level
        link_text = self.get_token_text(token['children'])
        url = token['attrs']['url']
        link_id = f"link_data_{hash(url)}"
        self.url_map[link_id] = url
        self.text_widget.insert(tk.END, link_text, ("md_link", link_id))

    def _handle_table(self, token, base_tag, style_tags, level):
        """Parses and renders a Markdown table."""
        del base_tag, style_tags, level
        try:
            header_cells, rows = self._parse_table_data(token)
            if not header_cells and rows:
                header_cells = [""] * len(rows[0])
            if not header_cells:
                return

            frame = tk.Frame(self.text_widget, bg=Theme.ACCENT_COLOR, bd=0)
            self._render_table_content(frame, header_cells, rows)

            for j in range(len(header_cells)):
                frame.grid_columnconfigure(j, weight=1)

            self._bind_scroll(frame)
            self.text_widget.insert(tk.END, "\n")
            self.text_widget.window_create(tk.END, window=frame)
            self.text_widget.insert(tk.END, "\n")

        except (ValueError, TypeError, KeyError) as exc:
            debug_print(f"Markdown: Error rendering table: {exc}")

    def _render_table_content(self, frame, header_cells, rows):
        """Helper to render headers and rows into the frame."""
        for j, val in enumerate(header_cells):
            lbl = tk.Label(
                frame, text=val, font=self.fonts["bold"],
                bg=Theme.BG_COLOR, fg=Theme.FG_COLOR,
                padx=10, pady=5, relief="flat", anchor="w",
                highlightthickness=1, highlightbackground=Theme.ACCENT_COLOR
            )
            lbl.grid(row=0, column=j, sticky="nsew")

        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                lbl = tk.Label(
                    frame, text=val, font=self.fonts["base"],
                    bg=Theme.BG_COLOR, fg=Theme.FG_COLOR,
                    padx=10, pady=5, relief="flat", anchor="w",
                    highlightthickness=1,
                    highlightbackground=Theme.ACCENT_COLOR
                )
                lbl.grid(row=i+1, column=j, sticky="nsew")

    def _parse_table_data(self, token):
        """Extracts headers and rows from table tokens."""
        header_cells, rows = [], []
        sections = token.get('children', [])
        if any(sec['type'] in ['thead', 'tbody'] for sec in sections):
            for sec in sections:
                if sec['type'] == 'thead':
                    for row_tok in sec['children']:
                        header_cells = [
                            self.get_token_text(c['children'])
                            for c in row_tok['children']
                        ]
                elif sec['type'] == 'tbody':
                    for row_tok in sec['children']:
                        rows.append([
                            self.get_token_text(c['children'])
                            for c in row_tok['children']
                        ])
        else:
            if len(sections) >= 1:
                header_cells = [
                    self.get_token_text(c['children'])
                    for c in sections[0]['children']
                ]
                if len(sections) > 1:
                    for row_tok in sections[1]['children']:
                        rows.append([
                            self.get_token_text(c['children'])
                            for c in row_tok['children']
                        ])
        return header_cells, rows

    def get_token_text(self, children):
        """Recursively extracts plain text from a list of tokens."""
        res = []
        for child in children:
            text = child.get('raw', child.get('text'))
            if text is None:
                text = self.get_token_text(child.get('children', []))
            res.append(text)
        return "".join(res)
