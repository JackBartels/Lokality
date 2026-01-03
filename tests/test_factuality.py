"""
Unit tests for factuality and search triggering logic.
"""
import json
import unittest
from datetime import datetime
from unittest.mock import patch
from local_assistant import LocalChatAssistant
from tests.base_test import BaseAssistantTest

class TestFactuality(BaseAssistantTest):
    """Test suite for factuality checks."""

    def setUp(self):
        super().setUp()
        self.set_mock_date(datetime(2026, 1, 2, 12, 0))
        # Now instantiate
        self.assistant = LocalChatAssistant()
        self.assistant.messages = []

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_triggered_for_factual_query(self, mock_search):
        """Test that search is triggered for factual queries."""
        # Mock LLM decision to search
        self.mocks['client'].generate.return_value = {
            'response': json.dumps({"action": "search", "query": "price of gold"})
        }
        mock_search.return_value = "Gold is $2000"

        res = self.assistant.decide_and_search("What is the current price of gold?")

        self.assertIn("Gold is $2000", res)
        # Verify call
        mock_search.assert_called_once_with("price of gold 2026-01-02")

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_greeting(self, mock_search):
        """Test that search is not triggered for greetings."""
        self.mocks['client'].generate.return_value = {'response': '{"action": "done"}'}

        res = self.assistant.decide_and_search("Hello, how are you?")

        self.assertIsNone(res)
        mock_search.assert_not_called()

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_common_knowledge(self, mock_search):
        """Test that search is not triggered for common knowledge."""
        self.mocks['client'].generate.return_value = {'response': '{"action": "done"}'}

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
            c for c in self.mocks['client'].generate.call_args_list
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
