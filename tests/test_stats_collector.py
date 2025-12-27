import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from stats_collector import StatsCollector

class TestStatsCollector(unittest.TestCase):
    @patch('stats_collector.client')
    def test_get_model_info(self, mock_client):
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
            stats = StatsCollector.get_model_info(mock_memory, "System prompt", [{"content": "User message"}])
            
            self.assertEqual(stats['model'], 'llama3')
            self.assertEqual(stats['memory_entries'], 10)
            self.assertEqual(stats['vram_mb'], 4000)
            self.assertEqual(stats['ram_mb'], 1000)
            self.assertGreater(stats['context_pct'], 0)

    @patch('stats_collector.client')
    def test_get_model_info_error(self, mock_client):
        # Simulate an error in ollama client
        mock_client.ps.side_effect = Exception("Ollama offline")
        
        mock_memory = MagicMock()
        mock_memory.get_fact_count.return_value = 5
        
        stats = StatsCollector.get_model_info(mock_memory, "prompt", [])
        
        # Should still return default stats and not crash
        self.assertEqual(stats['memory_entries'], 5)
        self.assertEqual(stats['ram_mb'], 0)
        self.assertEqual(stats['vram_mb'], 0)

if __name__ == "__main__":
    unittest.main()
