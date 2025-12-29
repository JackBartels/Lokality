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
        # We need to patch MemoryStore before LocalChatAssistant is instantiated
        self.memory_patcher = patch('local_assistant.MemoryStore')
        self.mock_memory_class = self.memory_patcher.start()
        self.mock_memory = self.mock_memory_class.return_value
        self.mock_memory.get_relevant_facts.return_value = []
        
        self.client_patcher = patch('local_assistant.client')
        self.mock_client = self.client_patcher.start()
        
        # Now instantiate
        self.assistant = LocalChatAssistant()
        self.assistant.messages = []

    def tearDown(self):
        self.memory_patcher.stop()
        self.client_patcher.stop()

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_triggered_for_factual_query(self, mock_search):
        # Mock LLM decision
        self.mock_client.generate.return_value = {'response': 'SEARCH: price of gold'}
        mock_search.return_value = "Gold is $2000"
        
        res = self.assistant.decide_and_search("What is the current price of gold?")
        
        self.assertIn("Gold is $2000", res)
        # Search will have date appended because "price of gold" doesn't match date patterns
        import datetime
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        mock_search.assert_called_once_with(f"price of gold {date_str}")

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_greeting(self, mock_search):
        self.mock_client.generate.return_value = {'response': 'DONE'}
        
        res = self.assistant.decide_and_search("Hello, how are you?")
        
        self.assertIsNone(res)
        mock_search.assert_not_called()

    @patch('local_assistant.SearchEngine.web_search')
    def test_search_not_triggered_for_common_knowledge(self, mock_search):
        self.mock_client.generate.return_value = {'response': 'DONE'}
        
        res = self.assistant.decide_and_search("What is the freezing point of water?")
        
        self.assertIsNone(res)
        mock_search.assert_not_called()

    def test_search_heuristic_skip(self):
        # Should NOT call generate because of heuristic
        res = self.assistant.decide_and_search("Hi", skip_llm=True)
        self.assertIsNone(res)
        self.mock_client.generate.assert_not_called()

    def test_system_prompt_contains_factuality_rules(self):
        self.assertIn("PROTOCOL", self.assistant.system_prompt)
        self.assertIn("SEARCH_CONTEXT", self.assistant.system_prompt)
        self.assertIn("USER IDENTITY", self.assistant.system_prompt)

if __name__ == '__main__':
    unittest.main()