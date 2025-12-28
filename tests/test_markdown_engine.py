import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import tkinter as tk

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from markdown_engine import MarkdownEngine

class TestMarkdownEngine(unittest.TestCase):
    def setUp(self):
        self.mock_text = MagicMock(spec=tk.Text)
        self.mock_tooltip = MagicMock()
        self.mock_text.index.return_value = "1.0"
        self.mock_text.get.return_value = ""
        self.mock_text.winfo_width.return_value = 800
        self.engine = MarkdownEngine(self.mock_text, self.mock_tooltip)

    def test_render_text(self):
        tokens = [{'type': 'text', 'text': 'Hello world'}]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'Hello world', ('base',))

    def test_render_bold(self):
        tokens = [{
            'type': 'strong',
            'children': [{'type': 'text', 'text': 'Bold text'}]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'Bold text', ('md_bold', 'base'))

    def test_render_italic(self):
        tokens = [{
            'type': 'emphasis',
            'children': [{'type': 'text', 'text': 'Italic text'}]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'Italic text', ('md_italic', 'base'))

    def test_render_bold_italic(self):
        # Nested bold and italic
        tokens = [{
            'type': 'strong',
            'children': [{
                'type': 'emphasis',
                'children': [{'type': 'text', 'text': 'Bold Italic'}]
            }]
        }]
        self.engine.render_tokens(tokens, "base")
        # Should use the combined tag
        self.mock_text.insert.assert_called_with(tk.END, 'Bold Italic', ('md_bold_italic', 'base'))

    def test_render_strikethrough(self):
        tokens = [{
            'type': 'strikethrough',
            'children': [{'type': 'text', 'text': 'deleted'}]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'deleted', ('md_strikethrough', 'base'))

    def test_render_subscript(self):
        tokens = [{
            'type': 'subscript',
            'children': [{'type': 'text', 'text': 'sub'}]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'sub', ('md_sub', 'base'))

    def test_render_superscript(self):
        tokens = [{
            'type': 'superscript',
            'children': [{'type': 'text', 'text': 'sup'}]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'sup', ('md_sup', 'base'))

    def test_render_paragraph(self):
        tokens = [{
            'type': 'paragraph',
            'children': [{'type': 'text', 'text': 'Para'}]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_any_call(tk.END, 'Para', ('base',))
        self.mock_text.insert.assert_any_call(tk.END, '\n\n')

    def test_render_codespan(self):
        tokens = [{'type': 'codespan', 'raw': 'code'}]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'code', ('md_code', 'base'))

    def test_render_list_simple(self):
        tokens = [{
            'type': 'list',
            'attrs': {'ordered': False},
            'children': [
                {'type': 'list_item', 'children': [{'type': 'text', 'text': 'Item 1'}]}
            ]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_any_call(tk.END, "• ", "base")
        self.mock_text.insert.assert_any_call(tk.END, 'Item 1', ('base',))

    def test_render_list_ordered(self):
        tokens = [{
            'type': 'list',
            'attrs': {'ordered': True, 'start': 1},
            'children': [
                {'type': 'list_item', 'children': [{'type': 'text', 'text': 'First'}]}
            ]
        }]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_any_call(tk.END, "1. ", "base")
        self.mock_text.insert.assert_any_call(tk.END, 'First', ('base',))

    def test_render_list_nested(self):
        tokens = [{
            'type': 'list',
            'attrs': {'ordered': False},
            'children': [{
                'type': 'list_item',
                'children': [
                    {'type': 'text', 'text': 'Parent'},
                    {
                        'type': 'list',
                        'attrs': {'ordered': False},
                        'children': [{'type': 'list_item', 'children': [{'type': 'text', 'text': 'Child'}]}]
                    }
                ]
            }]
        }]
        self.engine.render_tokens(tokens, "base")
        # Check parent bullet
        self.mock_text.insert.assert_any_call(tk.END, "• ", "base")
        # Check nested bullet (indented)
        self.mock_text.insert.assert_any_call(tk.END, "    • ", "base")
        self.mock_text.insert.assert_any_call(tk.END, 'Child', ('base',))

    def test_render_blockquote(self):
        tokens = [{
            'type': 'block_quote',
            'children': [{'type': 'text', 'text': 'Quote'}]
        }]
        self.engine.render_tokens(tokens, "base")
        # Check for bar character and styling
        self.mock_text.insert.assert_any_call(tk.END, "┃ ", ("md_quote_bar", "base"))
        self.mock_text.insert.assert_any_call(tk.END, 'Quote', ('md_quote', 'base'))

    def test_render_thematic_break(self):
        tokens = [{'type': 'thematic_break'}]
        with patch('markdown_engine.tk.Canvas') as mock_canvas:
            self.engine.render_tokens(tokens, "base")
            self.mock_text.window_create.assert_called()

    def test_render_table_mistune_3(self):
        # Tokens for Mistune 3.x table structure
        tokens = [{
            'type': 'table',
            'children': [
                {
                    'type': 'thead',
                    'children': [{
                        'type': 'tr', 
                        'children': [{'type': 'th', 'children': [{'type': 'text', 'text': 'H1'}]}]
                    }]
                },
                {
                    'type': 'tbody',
                    'children': [{
                        'type': 'tr',
                        'children': [{'type': 'td', 'children': [{'type': 'text', 'text': 'B1'}]}]
                    }]
                }
            ]
        }]
        
        with patch('markdown_engine.tk.Frame') as mock_frame, \
             patch('markdown_engine.tk.Label') as mock_label:
            self.engine.render_tokens(tokens, "base")
            self.mock_text.window_create.assert_called()
            calls = [c.kwargs.get('text') for c in mock_label.call_args_list]
            self.assertIn('H1', calls)
            self.assertIn('B1', calls)

if __name__ == "__main__":
    unittest.main()