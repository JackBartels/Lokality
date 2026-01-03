"""
Unit tests for the MemoryManager class.
"""
import unittest
from unittest.mock import patch
from memory_manager import MemoryManager

class TestMemoryManager(unittest.TestCase):
    """Test suite for MemoryManager."""

    @patch('memory_manager.ComplexityScorer.get_safe_context_size')
    @patch('memory_manager.get_ollama_client')
    def test_extract_facts_add(self, mock_get_client, mock_ctx):
        """Test extracting a single fact addition."""
        mock_client = mock_get_client.return_value
        mock_ctx.return_value = 2048
        # Mock LLM response for fact extraction
        mock_client.chat.return_value = {
            'message': {
                'content': '{"operations": [{'
                           '"op": "add", "entity": "User", "fact": "Lives in Paris"'
                           '}]}'
            }
        }

        ops = MemoryManager.extract_facts("I live in Paris", "That is a beautiful city!", "")

        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]['op'], 'add')
        self.assertEqual(ops[0]['fact'], 'Lives in Paris')

    @patch('memory_manager.ComplexityScorer.get_safe_context_size')
    @patch('memory_manager.get_ollama_client')
    def test_extract_facts_no_change(self, mock_get_client, mock_ctx):
        """Test when no facts are extracted."""
        mock_client = mock_get_client.return_value
        mock_ctx.return_value = 2048
        mock_client.chat.return_value = {
            'message': {
                'content': '{"operations": []}'
            }
        }

        ops = MemoryManager.extract_facts("Hello", "Hi there!", "")
        self.assertEqual(len(ops), 0)

    @patch('memory_manager.ComplexityScorer.get_safe_context_size')
    @patch('memory_manager.get_ollama_client')
    def test_extract_facts_multiple(self, mock_get_client, mock_ctx):
        """Test extracting multiple facts."""
        mock_client = mock_get_client.return_value
        mock_ctx.return_value = 2048
        # Mock LLM response for multiple operations
        mock_client.chat.return_value = {
            'message': {
                'content': '{"operations": [{'
                           '"op": "add", "entity": "User", "fact": "Likes tea"}, {'
                           '"op": "add", "entity": "User", "fact": "Has a cat"'
                           '}]}'
            }
        }

        ops = MemoryManager.extract_facts("I like tea and have a cat", "Nice!", "")

        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]['fact'], 'Likes tea')
        self.assertEqual(ops[1]['fact'], 'Has a cat')

if __name__ == "__main__":
    unittest.main()
