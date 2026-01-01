import os
import sys
import unittest
from unittest.mock import MagicMock, patch

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
        self.assertIn("Search failed for query 'test query': Network error", results)

    @patch('search_engine.DDGS')
    def test_web_search_connectivity_error(self, mock_ddgs):
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.side_effect = Exception("Connection timeout")
        
        results = SearchEngine.web_search("test query")
        self.assertIn("CRITICAL: Web search failed due to a connectivity issue", results)

    @patch('search_engine.requests.get')
    def test_scrape_url_success(self, mock_get):
        # Mock HTML response
        mock_response = MagicMock()
        mock_response.text = "<html><body><header>Nav</header><p>Main content</p><footer>Footer</footer></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        content = SearchEngine.scrape_url("https://example.com")
        
        # Should contain main content but NOT header/footer
        self.assertIn("Main content", content)
        self.assertNotIn("Nav", content)
        self.assertNotIn("Footer", content)

    @patch('search_engine.requests.get')
    def test_scrape_url_error(self, mock_get):
        mock_get.side_effect = Exception("HTTP 404")
        
        content = SearchEngine.scrape_url("https://example.com/bad")
        self.assertIn("Failed to scrape URL 'https://example.com/bad': HTTP 404", content)

if __name__ == "__main__":
    unittest.main()
