"""
Unit tests for factuality and search triggering logic.
"""
import json
import unittest
from unittest.mock import patch
from local_assistant import LocalChatAssistant

class TestFactuality(unittest.TestCase):
    """Test suite for factuality checks."""

    def setUp(self):
        # We need to patch MemoryStore before LocalChatAssistant is instantiated
        self.memory_patcher = patch('local_assistant.MemoryStore')
        self.mock_memory = self.memory_patcher.start().return_value
        self.mock_memory.get_relevant_facts.return_value = []

        self.client_patcher = patch('local_assistant.client')
        self.mock_client = self.client_patcher.start()

        self.ctx_patcher = patch('local_assistant.ComplexityScorer.get_safe_context_size')
        self.mock_ctx = self.ctx_patcher.start()
        self.mock_ctx.return_value = 2048

        # Now instantiate
        self.assistant = LocalChatAssistant()
        self.assistant.messages = []

    def tearDown(self):
        self.memory_patcher.stop()
        self.client_patcher.stop()
        self.ctx_patcher.stop()

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_triggered_for_factual_query(self, mock_search):
        """Test that search is triggered for factual queries."""
        # Mock LLM decision to search
        self.mock_client.generate.return_value = {
            'response': json.dumps({"action": "search", "query": "price of gold"})
        }
        mock_search.return_value = "Gold is $2000"

        res = self.assistant.decide_and_search("What is the current price of gold?")

        self.assertIn("Gold is $2000", res)
        # Verify call
        mock_search.assert_called_once_with("price of gold")

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_greeting(self, mock_search):
        """Test that search is not triggered for greetings."""
        self.mock_client.generate.return_value = {'response': '{"action": "done"}'}

        res = self.assistant.decide_and_search("Hello, how are you?")

        self.assertIsNone(res)
        mock_search.assert_not_called()

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_common_knowledge(self, mock_search):
        """Test that search is not triggered for common knowledge."""
        self.mock_client.generate.return_value = {'response': '{"action": "done"}'}

        res = self.assistant.decide_and_search("What is the freezing point of water?")

        self.assertIsNone(res)
        mock_search.assert_not_called()

    def test_search_heuristic_skip(self):
        """Test heuristic skipping of search decision LLM."""
        # Should NOT call generate for search purposes because of heuristic
        res = self.assistant.decide_and_search("Hi", skip_llm=True)
        self.assertIsNone(res)
        # Filter out warmup calls
        search_calls = [
            c for c in self.mock_client.generate.call_args_list
            if c.kwargs.get('prompt') != ""
        ]
        self.assertEqual(len(search_calls), 0)

    def test_system_prompt_contains_factuality_rules(self):
        """Test that system prompt contains factuality protocols."""
        self.assertIn("PROTOCOL", self.assistant.system_prompt)
        self.assertIn("SEARCH_CONTEXT", self.assistant.system_prompt)
        self.assertIn("USER IDENTITY", self.assistant.system_prompt)

if __name__ == '__main__':
    unittest.main()
