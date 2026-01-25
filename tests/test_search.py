"""
Unit tests for the SearchEngine class.
"""
import unittest
from unittest.mock import patch
from search_engine import SearchEngine

class TestSearchEngine(unittest.TestCase):
    """Test suite for SearchEngine."""

    @patch('search_engine.DDGS')
    def test_web_search_success(self, mock_ddgs):
        """Test successful web search."""
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
        # Verify updated max_results
        mock_instance.text.assert_called_once_with("test query", max_results=8)

    @patch('search_engine.DDGS')
    def test_web_search_no_results(self, mock_ddgs):
        """Test web search with no results."""
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.return_value = []

        results = SearchEngine.web_search("test query")
        self.assertEqual(results, "No recent web results found.")

    @patch('search_engine.DDGS')
    def test_web_search_error(self, mock_ddgs):
        """Test handling of generic search errors."""
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.side_effect = RuntimeError("Network error")

        results = SearchEngine.web_search("test query")
        self.assertIn("Search failed for query 'test query': Network error", results)

    @patch('search_engine.DDGS')
    def test_web_search_connectivity_error(self, mock_ddgs):
        """Test handling of connectivity errors."""
        mock_instance = mock_ddgs.return_value.__enter__.return_value
        mock_instance.text.side_effect = ValueError("Connection timeout")

        results = SearchEngine.web_search("test query")
        self.assertIn("CRITICAL: Web search failed due to a connectivity issue", results)

    @patch('search_engine.trafilatura.fetch_url')
    @patch('search_engine.trafilatura.extract')
    def test_scrape_url_success(self, mock_extract, mock_fetch):
        """Test successful URL scraping with Trafilatura."""
        mock_fetch.return_value = "<html>Content</html>"
        mock_extract.return_value = "Cleaned content text"

        content = SearchEngine.scrape_url("https://example.com")

        self.assertEqual(content, "Cleaned content text")
        mock_fetch.assert_called_once_with("https://example.com")
        mock_extract.assert_called_once_with("<html>Content</html>")

    @patch('search_engine.trafilatura.fetch_url')
    def test_scrape_url_fetch_error(self, mock_fetch):
        """Test handling of fetch failure (None return)."""
        mock_fetch.return_value = None

        content = SearchEngine.scrape_url("https://example.com/bad")
        self.assertIn("Failed to scrape URL 'https://example.com/bad'", content)
        self.assertIn("Failed to fetch content", content)

    @patch('search_engine.trafilatura.fetch_url')
    @patch('search_engine.trafilatura.extract')
    def test_scrape_url_extract_error(self, mock_extract, mock_fetch):
        """Test handling of extraction failure."""
        mock_fetch.return_value = "<html>Empty or bad</html>"
        mock_extract.return_value = None

        content = SearchEngine.scrape_url("https://example.com/empty")
        self.assertIn("Failed to scrape URL", content)
        self.assertIn("Failed to extract text", content)

if __name__ == "__main__":
    unittest.main()
