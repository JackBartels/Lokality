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
            patch('app.tk.Toplevel'),
            patch('app.tk.Canvas'),
            patch('app.tk.Text'),
            patch('app.tk.Frame'),
            patch('app.tk.font.Font'),
            patch('app.MarkdownEngine'),
            patch('app.mistune.create_markdown'),
            patch('app.local_assistant.LocalChatAssistant'),
            patch('app.ImageTk.PhotoImage')
        ]

        # Start all patchers and get mocks
        mocks = [p.start() for p in self.patchers]

        # Configure Text mock (index 3)
        mock_text_inst = mocks[3].return_value
        mock_text_inst.winfo_width.return_value = 100
        mock_text_inst.winfo_height.return_value = 100
        mock_text_inst.winfo_reqheight.return_value = 20
        mock_text_inst.count.return_value = [1]
        mock_text_inst.get.return_value = ""

        # Configure Canvas mock (index 2)
        mock_canvas_inst = mocks[2].return_value
        mock_canvas_inst.winfo_width.return_value = 100
        mock_canvas_inst.winfo_height.return_value = 100

        # Tk mock (index 0)
        root = mocks[0].return_value
        # Toplevel mock (index 1)
        self.mock_toplevel = mocks[1]

        with patch('app.Settings') as mock_settings:
            # We'll use a real dict to back it for convenience in tests.
            self.test_settings_dict = {
                "debug": config.DEBUG,
                "show_info": False,
                "skip_forget_confirmation": False
            }
            mock_inst = mock_settings.return_value
            mock_inst.get.side_effect = self.test_settings_dict.get
            mock_inst.set.side_effect = self.test_settings_dict.__setitem__

            self.app = AssistantApp(root, skip_init=True)
            self.app.settings = mock_inst

        # Manually trigger assistant initialization with a mock
        self.app.state.assistant = MagicMock()
        self.app.state.assistant.messages = []

    def tearDown(self):
        """Stop all patchers."""
        for p in self.patchers:
            p.stop()

    def test_command_clear_logic(self):
        """Test the /clear command."""
        # Verify that /clear actually calls clear_conversation and puts "clear" in queue
        self.app.process_input("/clear")

        self.app.state.assistant.clear_conversation.assert_called_once()

        # Check queue for expected signals
        queue_actions = []
        while not self.app.state.msg_queue.empty():
            queue_actions.append(self.app.state.msg_queue.get()[0])

        self.assertIn("clear", queue_actions)
        self.assertIn("enable", queue_actions)

    def test_command_forget_logic(self):
        """Test the /forget command with popup."""
        # 1. Test popup appears when setting is False
        self.test_settings_dict["skip_forget_confirmation"] = False
        self.app.process_input("/forget")
        self.mock_toplevel.assert_called_once()
        self.app.state.assistant.clear_long_term_memory.assert_not_called()

        # 2. Test direct call when setting is True
        self.mock_toplevel.reset_mock()
        self.app.state.assistant.clear_long_term_memory.reset_mock()
        self.test_settings_dict["skip_forget_confirmation"] = True
        self.app.process_input("/forget")
        self.mock_toplevel.assert_not_called()
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
