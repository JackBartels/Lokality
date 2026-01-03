"""
Unit tests for application commands.
"""
import unittest
from unittest.mock import MagicMock, patch
import config
from app import AssistantApp

class TestCommands(unittest.TestCase):
    """Test suite for application commands."""

    def setUp(self):
        """Set up the test environment with mocked UI components."""
        # Create patchers
        self.patchers = [
            patch('app.tk.Tk'),
            patch('app.tk.Canvas'),
            patch('app.tk.Text'),
            patch('app.tk.Frame'),
            patch('app.font.Font'),
            patch('app.round_rectangle'),
            patch('app.CustomScrollbar'),
            patch('app.MarkdownEngine'),
            patch('app.mistune.create_markdown'),
            patch('app.local_assistant.LocalChatAssistant')
        ]

        # Start all patchers and get mocks
        mocks = [p.start() for p in self.patchers]

        # Configure Text mock (index 2)
        mock_text_inst = mocks[2].return_value
        mock_text_inst.winfo_width.return_value = 100
        mock_text_inst.winfo_height.return_value = 100
        mock_text_inst.winfo_reqheight.return_value = 20
        mock_text_inst.count.return_value = [1]
        mock_text_inst.get.return_value = ""

        # Configure Canvas mock (index 1)
        mock_canvas_inst = mocks[1].return_value
        mock_canvas_inst.winfo_width.return_value = 100
        mock_canvas_inst.winfo_height.return_value = 100

        # Tk mock (index 0)
        root = mocks[0].return_value

        self.app = AssistantApp(root)
        # Manually trigger assistant initialization with a mock
        self.app.state.assistant = MagicMock()
        self.app.state.assistant.messages = []

    def tearDown(self):
        """Stop all patchers."""
        for p in self.patchers:
            p.stop()

    def test_command_clear_logic(self):
        """Test the /clear command."""
        # Verify that /clear actually resets messages and puts "clear" in queue
        self.app.state.assistant.messages = [{"role": "user", "content": "hi"}]
        self.app.process_input("/clear")

        self.assertEqual(self.app.state.assistant.messages, [])

        # Check queue for expected signals
        queue_actions = []
        while not self.app.state.msg_queue.empty():
            queue_actions.append(self.app.state.msg_queue.get()[0])

        self.assertIn("clear", queue_actions)
        self.assertIn("enable", queue_actions)

    def test_command_forget_logic(self):
        """Test the /forget command."""
        # Verify that /forget calls assistant.clear_long_term_memory
        self.app.process_input("/forget")
        self.app.state.assistant.clear_long_term_memory.assert_called_once()

        queue_actions = []
        while not self.app.state.msg_queue.empty():
            queue_actions.append(self.app.state.msg_queue.get()[0])
        self.assertIn("enable", queue_actions)

    def test_command_debug_logic(self):
        """Test the /debug command."""
        # Verify that /debug toggles config.DEBUG
        initial = config.DEBUG
        self.app.process_input("/debug")
        self.assertEqual(config.DEBUG, not initial)

        # Toggle back
        self.app.process_input("/debug")
        self.assertEqual(config.DEBUG, initial)

    def test_command_info_logic(self):
        """Test the /info command."""
        # Verify that /info puts toggle_info in queue
        self.app.process_input("/info")

        queue_actions = []
        while not self.app.state.msg_queue.empty():
            queue_actions.append(self.app.state.msg_queue.get()[0])
        self.assertIn("toggle_info", queue_actions)

    @patch('app.run_ollama_bypass')
    @patch('app.threading.Thread')
    def test_command_bypass_logic(self, mock_thread, mock_bypass):
        """Test the /bypass command."""
        # Mock Thread to run target immediately
        mock_thread.side_effect = lambda target, **_kwargs: MagicMock(start=target)

        # Mock bypass return
        mock_bypass.return_value = ("COMPLETED", MagicMock())

        self.app.process_input("/bypass hi")

        # Verify bypass was called
        mock_bypass.assert_called_once()
        self.assertIn("hi", mock_bypass.call_args[0])

        queue_actions = []
        while not self.app.state.msg_queue.empty():
            queue_actions.append(self.app.state.msg_queue.get()[0])

        self.assertIn("start_indicator", queue_actions)
        self.assertIn("text", queue_actions)
        self.assertIn("final_render", queue_actions)
        self.assertIn("enable", queue_actions)

if __name__ == "__main__":
    unittest.main()
