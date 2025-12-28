import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import config
from app import AssistantApp

class TestCommands(unittest.TestCase):
    @patch('app.tk.Tk')
    @patch('app.tk.Canvas')
    @patch('app.tk.Text')
    @patch('app.tk.Frame')
    @patch('app.font.Font')
    @patch('app.round_rectangle')
    @patch('app.CustomScrollbar')
    @patch('app.MarkdownEngine')
    @patch('app.mistune.create_markdown')
    @patch('app.local_assistant.LocalChatAssistant')
    def setUp(self, mock_assistant, mock_md, mock_engine, mock_scroll, mock_round, mock_font, mock_frame, mock_text, mock_canvas, mock_tk):
        # Mock UI elements to avoid Tkinter dependency issues in headless environments
        self.root = mock_tk()
        
        # Configure mocks to return valid integers for winfo calls
        mock_text_inst = mock_text.return_value
        mock_text_inst.winfo_width.return_value = 100
        mock_text_inst.winfo_height.return_value = 100
        mock_text_inst.winfo_reqheight.return_value = 20
        mock_text_inst.count.return_value = [1]
        mock_text_inst.get.return_value = "" # Default to empty for adjust_input_height logic
        
        mock_canvas_inst = mock_canvas.return_value
        mock_canvas_inst.winfo_width.return_value = 100
        mock_canvas_inst.winfo_height.return_value = 100
        
        self.app = AssistantApp(self.root)

    def test_command_clear_logic(self):
        # Verify that /clear actually resets messages and puts "clear" in queue
        self.app.assistant.messages = [{"role": "user", "content": "hi"}]
        self.app.process_input("/clear")
        
        self.assertEqual(self.app.assistant.messages, [])
        
        # Check queue for expected signals
        queue_actions = []
        while not self.app.msg_queue.empty():
            queue_actions.append(self.app.msg_queue.get()[0])
        
        self.assertIn("clear", queue_actions)
        self.assertIn("enable", queue_actions)

    def test_command_forget_logic(self):
        # Verify that /forget calls assistant.clear_long_term_memory
        self.app.process_input("/forget")
        self.app.assistant.clear_long_term_memory.assert_called_once()
        
        queue_actions = []
        while not self.app.msg_queue.empty():
            queue_actions.append(self.app.msg_queue.get()[0])
        self.assertIn("enable", queue_actions)

    def test_command_debug_logic(self):
        # Verify that /debug toggles config.DEBUG
        initial = config.DEBUG
        self.app.process_input("/debug")
        self.assertEqual(config.DEBUG, not initial)
        
        # Toggle back
        self.app.process_input("/debug")
        self.assertEqual(config.DEBUG, initial)

    def test_command_info_logic(self):
        # Verify that /info puts toggle_info in queue
        self.app.process_input("/info")
        
        queue_actions = []
        while not self.app.msg_queue.empty():
            queue_actions.append(self.app.msg_queue.get()[0])
        self.assertIn("toggle_info", queue_actions)

if __name__ == "__main__":
    unittest.main()