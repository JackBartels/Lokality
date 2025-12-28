import os
import sys
import unittest
from unittest.mock import patch

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory_manager import MemoryManager

class TestMemoryManager(unittest.TestCase):
    @patch('memory_manager.client')
    def test_extract_facts_add(self, mock_client):
        # Mock LLM response for fact extraction
        mock_client.chat.return_value = {
            'message': {
                'content': '[{"op": "add", "entity": "User", "fact": "Lives in Paris"}]'
            }
        }
        
        ops = MemoryManager.extract_facts("I live in Paris", "That is a beautiful city!", "")
        
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]['op'], 'add')
        self.assertEqual(ops[0]['fact'], 'Lives in Paris')

    @patch('memory_manager.client')
    def test_extract_facts_no_change(self, mock_client):
        mock_client.chat.return_value = {
            'message': {
                'content': '[]'
            }
        }
        
        ops = MemoryManager.extract_facts("Hello", "Hi there!", "")
        self.assertEqual(len(ops), 0)

    @patch('memory_manager.client')
    def test_extract_facts_multiple(self, mock_client):
        # Mock LLM response for multiple operations
        mock_client.chat.return_value = {
            'message': {
                'content': '[{"op": "add", "entity": "User", "fact": "Likes tea"}, {"op": "add", "entity": "User", "fact": "Has a cat"}]'
            }
        }
        
        ops = MemoryManager.extract_facts("I like tea and have a cat", "Nice!", "")
        
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]['fact'], 'Likes tea')
        self.assertEqual(ops[1]['fact'], 'Has a cat')

if __name__ == "__main__":
    unittest.main()
