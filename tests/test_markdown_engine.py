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

    def test_render_paragraph(self):
        tokens = [{
            'type': 'paragraph',
            'children': [{'type': 'text', 'text': 'Para'}]
        }]
        self.engine.render_tokens(tokens, "base")
        # Check if text was inserted and then newlines
        self.mock_text.insert.assert_any_call(tk.END, 'Para', ('base',))
        self.mock_text.insert.assert_any_call(tk.END, '\n\n')

    def test_render_codespan(self):
        tokens = [{'type': 'codespan', 'raw': 'code'}]
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_called_with(tk.END, 'code', ('md_code', 'base'))

    def test_render_list_item(self):
        tokens = [{
            'type': 'list',
            'children': [{
                'type': 'list_item',
                'children': [{'type': 'text', 'text': 'Item 1'}]
            }]
        }]
        self.mock_text.get.return_value = ""
        self.engine.render_tokens(tokens, "base")
        self.mock_text.insert.assert_any_call(tk.END, "• ", "base")
        self.mock_text.insert.assert_any_call(tk.END, 'Item 1', ("base",))

    def test_render_table(self):
        # Tokens for a simple table
        tokens = [{
            'type': 'table',
            'children': [
                {
                    'type': 'table_head',
                    'children': [{
                        'type': 'table_cell', 
                        'children': [{'type': 'text', 'text': 'Header 1'}]
                    }]
                },
                {
                    'type': 'table_body',
                    'children': [
                        {
                            'type': 'table_row',
                            'children': [{
                                'type': 'table_cell', 
                                'children': [{'type': 'text', 'text': 'Body 1'}]
                            }]
                        }
                    ]
                }
            ]
        }]
        
        with patch('markdown_engine.tk.Frame') as mock_frame, \
             patch('markdown_engine.tk.Label') as mock_label:
            self.engine.render_tokens(tokens, "base")
            
            # Verify that a window was created in the text widget for the table
            self.mock_text.window_create.assert_called()
            
            # Verify labels were created with correct text
            label_texts = [call.kwargs.get('text') or call.args[1] if len(call.args) > 1 else None 
                          for call in mock_label.call_args_list]
            # Since tk.Label(parent, text="...") or tk.Label(parent, **kwargs)
            # We check if Header 1 and Body 1 are in the calls
            calls = [c.kwargs.get('text') for c in mock_label.call_args_list]
            self.assertIn('Header 1', calls)
            self.assertIn('Body 1', calls)

if __name__ == "__main__":
    unittest.main()
