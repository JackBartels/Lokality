"""
Unit tests for the StatsCollector class.
"""
import unittest
from unittest.mock import MagicMock, patch
import ollama
from stats_collector import get_model_info

class TestStatsCollector(unittest.TestCase):
    """Test suite for StatsCollector."""

    @patch('stats_collector.get_ollama_client')
    def test_get_model_info(self, mock_get_client):
        """Test retrieving model info from Ollama."""
        mock_client = mock_get_client.return_value
        # Mock memory store
        mock_memory = MagicMock()
        mock_memory.get_fact_count.return_value = 10

        # Mock client.ps()
        mock_model = MagicMock()
        mock_model.model = "llama3:latest"
        mock_model.size_vram = 4000 * 1024 * 1024
        mock_model.size = 5000 * 1024 * 1024

        mock_ps = MagicMock()
        mock_ps.models = [mock_model]
        mock_client.ps.return_value = mock_ps

        # Mock client.show()
        mock_show = MagicMock()
        mock_show.model_dump.return_value = {
            'modelinfo': {
                'llama.context_length': 8192
            }
        }
        mock_client.show.return_value = mock_show

        # Change config.MODEL_NAME for test
        with patch('stats_collector.MODEL_NAME', 'llama3'):
            stats = get_model_info(
                mock_memory, "System prompt", [{"content": "User message"}]
            )

            self.assertEqual(stats['model'], 'llama3')
            self.assertEqual(stats['memory_entries'], 10)
            self.assertEqual(stats['vram_mb'], 4000)
            self.assertEqual(stats['ram_mb'], 1000)
            self.assertGreater(stats['context_pct'], 0)

    @patch('stats_collector.get_ollama_client')
    def test_get_model_info_error(self, mock_get_client):
        """Test handling of Ollama errors."""
        mock_client = mock_get_client.return_value
        # Simulate an error in ollama client
        mock_client.ps.side_effect = ollama.ResponseError("Ollama offline")

        mock_memory = MagicMock()
        mock_memory.get_fact_count.return_value = 5

        # We need to catch the exception or verify default behavior
        # StatsCollector should handle the exception and return default stats
        stats = get_model_info(mock_memory, "prompt", [])

        # Should still return default stats and not crash
        self.assertEqual(stats['memory_entries'], 5)
        self.assertEqual(stats['ram_mb'], 0)
        self.assertEqual(stats['vram_mb'], 0)

if __name__ == "__main__":
    unittest.main()
