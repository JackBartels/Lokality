"""
Unit tests for the LocalChatAssistant class.
"""
import json
import unittest
from unittest.mock import patch
from memory import MemoryStore
from local_assistant import LocalChatAssistant
from tests.base_test import BaseAssistantTest

class TestLocalChatAssistant(BaseAssistantTest):
    """Test suite for LocalChatAssistant."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.assistant = LocalChatAssistant()

    def test_update_system_prompt(self):
        """Test that system prompt is updated with relevant facts and time."""
        self.mocks['memory_instance'].get_relevant_facts.return_value = [
            {"entity": "User", "fact": "Likes pizza", "id": 1}
        ]
        self.assistant.update_system_prompt("query")

        self.assertIn("Likes pizza", self.assistant.system_prompt)
        self.assertIn("Lokality", self.assistant.system_prompt)
        # Check if date and time are in prompt
        self.assertIn("Saturday, December 27, 2025", self.assistant.system_prompt)
        self.assertIn("10:30 AM", self.assistant.system_prompt)

    @patch('local_assistant.SearchEngine.web_search')
    def test_decide_and_search_yes(self, mock_web_search):
        """Test that search is performed when LLM decides so."""
        # Mock LLM decision to search
        self.mocks['client'].generate.return_value = {
            'response': json.dumps({"action": "search", "query": "What is the weather?"})
        }
        mock_web_search.return_value = "It is sunny."

        result = self.assistant.decide_and_search("What is the weather?")

        self.assertIn("It is sunny.", result)
        self.assertIn("--- Search for 'What is the weather? 2025-12-27' ---", result)
        # Verify call while ignoring potential warmup calls in background
        calls = [
            c for c in mock_web_search.call_args_list if "What is the weather? 2025-12-27" in str(c)
        ]
        self.assertTrue(len(calls) > 0)

    @patch('local_assistant.SearchEngine.web_search')
    @patch('local_assistant.SearchEngine.scrape_url')
    def test_decide_and_search_with_scrape(self, mock_scrape, mock_web_search):
        """Test search and scrape workflow."""
        # Mock 1: Initial search decision
        # Mock 2: Scrape decision
        # Mock 3: Distillation
        # Note: warmup generate calls might happen, so we use side_effect
        responses = [
            {'response': json.dumps(
                {"action": "search", "query": "What is the weather in London?"}
            )},
            {'response': json.dumps({"action": "scrape", "url": "https://weather.com/london"})},
            {'response': "Relevant: It is 20°C and sunny in London."}
        ]

        # Helper to return side effects while ignoring warmup
        def side_effect_handler(*_args, **kwargs):
            if kwargs.get('prompt') == "":
                return {'response': ''} # Handle warmup
            return responses.pop(0)

        self.mocks['client'].generate.side_effect = side_effect_handler
        mock_web_search.return_value = (
            "Source: https://weather.com/london\nSnippet: It might rain."
        )
        mock_scrape.return_value = (
            "<html>Large noisy page about London... 20°C and sunny...</html>"
        )

        result = self.assistant.decide_and_search("What is the weather in London?")

        self.assertIn("Relevant: It is 20°C and sunny in London.", result)
        self.assertIn("--- Search for 'What is the weather in London? 2025-12-27' ---", result)
        mock_scrape.assert_called_once_with("https://weather.com/london")

    def test_accuracy_context_incorporation(self):
        """Test that identity and context are incorporated into system prompt."""
        # Verify that memory is in system prompt
        self.mocks['memory_instance'].get_relevant_facts.return_value = [
            {"entity": "User", "fact": "Has a dog named Buster", "id": 1}
        ]
        self.assistant.update_system_prompt("dog")
        self.assertIn("Has a dog named Buster", self.assistant.system_prompt)

        # Verify that system prompt starts with identity
        self.assertIn("You are Lokality", self.assistant.system_prompt)

    def test_decide_and_search_no(self):
        """Test that no search is performed when LLM decides so."""
        # Mock LLM decision NOT to search (JSON format)
        self.mocks['client'].generate.return_value = {'response': '{"action": "done"}'}

        result = self.assistant.decide_and_search("Hello")

        self.assertIsNone(result)

    def test_clear_long_term_memory(self):
        """Test clearing long term memory."""
        self.assistant.clear_long_term_memory()
        self.mocks['memory_instance'].clear.assert_called_once()

    @patch('local_assistant.MemoryManager.extract_facts')
    def test_perform_memory_update_integration(self, mock_extract):
        """Test memory update integration."""
        # Setup: Real MemoryStore (in-memory) for integration feel,
        # but we already mocked it in setUp. Let's use a real one for this specific test.
        real_memory = MemoryStore(db_path=":memory:")
        self.assistant.memory = real_memory

        mock_extract.return_value = [
            {'op': 'add', 'entity': 'User', 'fact': 'Lives in Tokyo'}
        ]

        # This calls the logic that filters and commits to DB
        self.assistant.perform_memory_update("I live in Tokyo", "That's great!")

        facts = real_memory.get_all_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['fact'], 'Lives in Tokyo')

if __name__ == "__main__":
    unittest.main()
