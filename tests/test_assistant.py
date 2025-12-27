import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import local_assistant
from local_assistant import LocalChatAssistant

class TestLocalChatAssistant(unittest.TestCase):
    def setUp(self):
        self.memory_patcher = patch('local_assistant.MemoryStore')
        self.mock_memory_class = self.memory_patcher.start()
        self.mock_memory_instance = self.mock_memory_class.return_value
        self.mock_memory_instance.get_relevant_facts.return_value = []
        
        self.client_patcher = patch('local_assistant.client')
        self.mock_client = self.client_patcher.start()

        # Mock datetime for determinism
        self.datetime_patcher = patch('local_assistant.datetime')
        self.mock_datetime = self.datetime_patcher.start()
        self.mock_datetime.now.return_value = datetime(2025, 12, 27, 10, 30)
        self.mock_datetime.strftime = datetime.strftime
        
        self.assistant = LocalChatAssistant()

    def tearDown(self):
        self.memory_patcher.stop()
        self.client_patcher.stop()
        self.datetime_patcher.stop()

    def test_update_system_prompt(self):
        self.mock_memory_instance.get_relevant_facts.return_value = [
            {"entity": "User", "fact": "Likes pizza", "id": 1}
        ]
        self.assistant._update_system_prompt("query")
        
        self.assertIn("Likes pizza", self.assistant.system_prompt)
        self.assertIn("Lokality", self.assistant.system_prompt)
        # Check if date is in prompt
        self.assertIn("Saturday, December 27, 2025", self.assistant.system_prompt)
        self.assertIn("10:30 AM", self.assistant.system_prompt)

    @patch('local_assistant.SearchEngine.web_search')
    def test_decide_and_search_yes(self, mock_web_search):
        # Mock LLM decision to search
        self.mock_client.generate.return_value = {'response': 'SEARCH: weather in London'}
        mock_web_search.return_value = "It is sunny."
        
        result = self.assistant.decide_and_search("What is the weather?")
        
        self.assertEqual(result, "It is sunny.")
        mock_web_search.assert_called_once_with("weather in London")

    def test_accuracy_context_incorporation(self):
        # Verify that memory is in system prompt
        self.mock_memory_instance.get_relevant_facts.return_value = [
            {"entity": "User", "fact": "Has a dog named Buster", "id": 1}
        ]
        self.assistant._update_system_prompt("dog")
        self.assertIn("Has a dog named Buster", self.assistant.system_prompt)
        
        # Verify that system prompt starts with identity
        self.assertIn("You are Lokality", self.assistant.system_prompt)

    def test_decide_and_search_no(self):
        # Mock LLM decision NOT to search
        self.mock_client.generate.return_value = {'response': 'NO'}
        
        result = self.assistant.decide_and_search("Hello")
        
        self.assertIsNone(result)

    def test_clear_long_term_memory(self):
        self.assistant.clear_long_term_memory()
        self.mock_memory_instance.clear.assert_called_once()

    @patch('local_assistant.MemoryManager.extract_facts')
    def test_perform_memory_update_integration(self, mock_extract):
        # Setup: Real MemoryStore (in-memory) for integration feel, 
        # but we already mocked it in setUp. Let's use a real one for this specific test.
        from memory import MemoryStore
        real_memory = MemoryStore(db_path=":memory:")
        self.assistant.memory = real_memory
        
        mock_extract.return_value = [
            {'op': 'add', 'entity': 'User', 'fact': 'Lives in Tokyo'}
        ]
        
        # This calls the logic that filters and commits to DB
        self.assistant._perform_memory_update("I live in Tokyo", "That's great!")
        
        facts = real_memory.get_all_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['fact'], 'Lives in Tokyo')

if __name__ == "__main__":
    unittest.main()
