"""
Unit tests for Wikipedia search integration.
"""
import unittest
from search_engine import SearchEngine

class TestWikipedia(unittest.TestCase):
    """Test suite for Wikipedia search capabilities."""

    def test_wikipedia_hit(self):
        """Test successful Wikipedia search for a common topic."""
        # Testing with a very common topic
        result = SearchEngine.wikipedia_search("Python (programming language)")
        self.assertIsNotNone(result)
        self.assertIn("Source: https://en.wikipedia.org/wiki/Python_(programming_language)", result)
        self.assertIn("Python", result)

    def test_wikipedia_miss(self):
        """Test Wikipedia search with a nonexistent topic."""
        # Testing with something unlikely to be on Wikipedia
        result = SearchEngine.wikipedia_search("asdfghjkl1234567890qwertyuiop")
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
