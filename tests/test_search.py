import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from search_engine import SearchEngine

class TestSearchEngine(unittest.TestCase):
    @patch('search_engine.DDGS')
    def test_web_search_success(self, mock_ddgs):
        # Setup mock
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.return_value = [
            {'href': 'https://example.com/1', 'body': 'Snippet 1'},
            {'href': 'https://example.com/2', 'body': 'Snippet 2'}
        ]
        
        results = SearchEngine.web_search("test query")
        
        self.assertIn("Source: https://example.com/1", results)
        self.assertIn("Snippet: Snippet 1", results)
        self.assertIn("Source: https://example.com/2", results)
        self.assertIn("Snippet: Snippet 2", results)
        mock_instance.text.assert_called_once_with("test query", max_results=5)

    @patch('search_engine.DDGS')
    def test_web_search_no_results(self, mock_ddgs):
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.return_value = []
        
        results = SearchEngine.web_search("test query")
        self.assertEqual(results, "No recent web results found.")

    @patch('search_engine.DDGS')
    def test_web_search_error(self, mock_ddgs):
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.side_effect = Exception("Network error")
        
        results = SearchEngine.web_search("test query")
        self.assertIn("Error during search: Network error", results)

if __name__ == "__main__":
    unittest.main()
