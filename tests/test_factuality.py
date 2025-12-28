import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import local_assistant
from local_assistant import LocalChatAssistant

class TestFactuality(unittest.TestCase):
    def setUp(self):
        with patch('local_assistant.MemoryStore'), \
             patch('local_assistant.client'):
            self.assistant = LocalChatAssistant()

    @patch('local_assistant.client.generate')
    @patch('local_assistant.SearchEngine.web_search')
    def test_search_triggered_for_factual_query(self, mock_search, mock_generate):
        # Optimized: Single pass for search decision
        mock_generate.side_effect = [
            {'response': 'SEARCH: price of gold'}
        ]
        mock_search.return_value = "Gold is $2000"
        
        res = self.assistant.decide_and_search("What is the current price of gold?")
        
        self.assertIn("Gold is $2000", res)
        self.assertEqual(mock_generate.call_count, 1)
        mock_search.assert_called_once_with("price of gold")

    @patch('local_assistant.client.generate')
    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_greeting(self, mock_search, mock_generate):
        mock_generate.side_effect = [
            {'response': 'DONE'}
        ]
        
        res = self.assistant.decide_and_search("Hello, how are you?")
        
        self.assertIsNone(res)
        mock_search.assert_not_called()

    @patch('local_assistant.client.generate')
    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_common_knowledge(self, mock_search, mock_generate):
        mock_generate.side_effect = [
            {'response': 'DONE'}
        ]
        
        res = self.assistant.decide_and_search("What is the freezing point of water?")
        
        self.assertIsNone(res)
        mock_search.assert_not_called()

    @patch('local_assistant.client.generate')
    def test_search_heuristic_skip(self, mock_generate):
        res = self.assistant.decide_and_search("Hi")
        self.assertIsNone(res)
        mock_generate.assert_not_called()

    def test_system_prompt_contains_factuality_rules(self):
        self.assertIn("ANCHORING", self.assistant.system_prompt)
        self.assertIn("common knowledge", self.assistant.system_prompt)
        self.assertIn("ABSOLUTE RECENCY", self.assistant.system_prompt)

if __name__ == '__main__':
    unittest.main()
