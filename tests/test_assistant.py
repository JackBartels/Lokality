"""
Unit tests for the LocalChatAssistant class.
"""
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

    def test_decide_and_search_yes(self):
        """Test that search is performed when LLM decides so."""
        # Mock Search decision
        self.mocks['client'].chat.return_value = {
            "message": {"content": '{"action": "search", "query": "weather today", "type": "none"}'}
        }

        with patch("search_engine.SearchEngine.web_search") as mock_search, \
             patch("search_engine.SearchEngine.wikipedia_search") as mock_wiki:
            mock_wiki.return_value = None
            mock_search.return_value = "It is sunny."
            # Use longer input to avoid skip_llm heuristic
            query = "Please check the current weather in New York City."
            result = self.assistant.decide_and_search(query)

            self.assertIsNotNone(result)
            self.assertIn("sunny", result)
            mock_search.assert_called_once()

    def test_decide_and_search_weather_routing(self):
        """Test that weather queries are routed to SpecializedSearch."""
        # Mock Search decision
        self.mocks['client'].chat.return_value = {
            "message": {"content": '{"action": "search", "query": "New York", "type": "weather"}'}
        }

        with patch("specialized_search.SpecializedSearch.get_weather") as mock_weather:
            mock_weather.return_value = "It is 72 degrees and sunny in New York."

            result = self.assistant.decide_and_search("What is the weather in New York?")

            self.assertIsNotNone(result)
            self.assertIn("72 degrees", result)
            mock_weather.assert_called_once_with("New York")

    def test_decide_and_search_news_routing(self):
        """Test that news queries are routed to SpecializedSearch."""
        # Mock Search decision
        self.mocks['client'].chat.return_value = {
            "message": {"content": '{"action": "search", "query": "AI news", "type": "news"}'}
        }

        with patch("specialized_search.SpecializedSearch.get_news") as mock_news:
            mock_news.return_value = "Latest AI news: Gemma 3 released."

            result = self.assistant.decide_and_search("Search for latest AI news.")

            self.assertIsNotNone(result)
            self.assertIn("Gemma 3", result)
            mock_news.assert_called_once_with("AI news")

    def test_decide_and_search_with_scrape(self):
        """Test search and scrape workflow."""
        # generate: 1. Distillation
        self.mocks['client'].generate.side_effect = [
            {"response": "Extracted fact."} # Distillation
        ]
        # chat: 1. Search Decision, 2. Scrape Decision
        self.mocks['client'].chat.side_effect = [
            {"message": {"content": (
                '{"action": "search", "query": "London weather", "type": "none"}'
            )}},
            {"message": {"content": '{"action": "scrape", "url": "https://weather.com"}'}}
        ]

        with patch("search_engine.SearchEngine.web_search") as mock_search, \
             patch("search_engine.SearchEngine.scrape_url") as mock_scrape, \
             patch("search_engine.SearchEngine.wikipedia_search") as mock_wiki:

            mock_wiki.return_value = None
            mock_search.return_value = "Source: https://weather.com\nSnippet: Check London weather."
            mock_scrape.return_value = "Detailed weather report."

            # Longer input to avoid heuristic
            query = "What is the detailed weather forecast for London right now?"
            result = self.assistant.decide_and_search(query)

            self.assertIsNotNone(result)
            self.assertIn("Extracted fact.", result)
            mock_search.assert_called_once()
            mock_scrape.assert_called_once_with("https://weather.com")

    def test_wikipedia_fallback(self):
        """Test that search falls back to Wikipedia."""
        # Mock Search decision
        self.mocks['client'].chat.return_value = {
            "message": {"content": '{"action": "search", "query": "Python"}'}
        }

        with patch("search_engine.SearchEngine.wikipedia_search") as mock_wiki:
            mock_wiki.return_value = "Source: wiki\nTitle: Python\nSummary: A language."

            result = self.assistant.decide_and_search("Tell me about Python")

            self.assertIsNotNone(result)
            self.assertIn("Wikipedia Result", result)
            self.assertIn("A language", result)
            mock_wiki.assert_called_once()

    def test_specialized_to_web_fallback(self):
        """Test that specialized search falls back to Web Search instead of Wikipedia on failure."""
        # Mock Search decision
        self.mocks['client'].chat.return_value = {
            "message": {"content": '{"action": "search", "query": "New York", "type": "weather"}'}
        }

        with patch("specialized_search.SpecializedSearch.get_weather") as mock_weather, \
             patch("search_engine.SearchEngine.wikipedia_search") as mock_wiki, \
             patch("search_engine.SearchEngine.web_search") as mock_web:
            mock_weather.return_value = None
            mock_web.return_value = "DDG weather results"

            result = self.assistant.decide_and_search("What's the weather in New York?")

            self.assertIsNotNone(result)
            self.assertIn("Search for 'weather in New York", result)
            self.assertIn("DDG weather results", result)
            mock_weather.assert_called_once()
            mock_wiki.assert_not_called()
            mock_web.assert_called_once()

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
        # Search decision returns 'done'
        self.mocks['client'].chat.return_value = {
            "message": {"content": '{"action": "done"}'}
        }

        result = self.assistant.decide_and_search("Hello")

        self.assertIsNone(result)

    def test_clear_long_term_memory(self):
        """Test clearing long term memory."""
        self.assistant.clear_long_term_memory()
        self.mocks['memory_instance'].clear.assert_called_once()

    @patch('local_assistant.LocalChatAssistant._get_search_decision')
    def test_prepare_turn_parallel_execution(self, mock_decision):
        """Test that prepare_turn executes memory and decision logic."""
        mock_decision.return_value = {"action": "done"}
        self.mocks['memory_instance'].get_relevant_facts.return_value = [{'id': 1, 'fact': 'test'}]

        # Reset mock to ignore the call from __init__
        self.mocks['memory_instance'].get_relevant_facts.reset_mock()

        res = self.assistant.prepare_turn("Hello")

        self.mocks['memory_instance'].get_relevant_facts.assert_called_once()
        mock_decision.assert_called_once()
        self.assertEqual(res['facts'], [{'id': 1, 'fact': 'test'}])
        self.assertIsNone(res['search_context'])

    @patch('local_assistant.LocalChatAssistant.decide_and_search')
    @patch('local_assistant.LocalChatAssistant._get_search_decision')
    def test_prepare_turn_triggers_search(self, mock_decision, mock_decide):
        """Test that prepare_turn triggers full search if decision approves."""
        mock_decision.return_value = {"action": "search", "query": "weather"}
        mock_decide.return_value = "Search Results"

        res = self.assistant.prepare_turn("Current weather")

        mock_decide.assert_called_once()
        self.assertEqual(res['search_context'], "Search Results")

    @patch('local_assistant.MemoryManager.extract_facts')
    def test_perform_memory_update_integration(self, mock_extract):
        """Test memory update integration."""
        real_memory = MemoryStore(db_path=":memory:")
        self.assistant.memory = real_memory

        mock_extract.return_value = [
            {'op': 'add', 'entity': 'User', 'fact': 'Lives in Tokyo'}
        ]

        self.assistant.perform_memory_update("I live in Tokyo", "That's great!")

        facts = real_memory.get_all_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['fact'], 'Lives in Tokyo')

if __name__ == "__main__":
    unittest.main()
