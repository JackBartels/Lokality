"""
Unit tests for the ComplexityScorer class.
"""
import unittest
from unittest.mock import patch
from complexity_scorer import ComplexityScorer

class TestComplexityScorer(unittest.TestCase):
    """Test suite for ComplexityScorer."""

    def setUp(self):
        # Mock system resources to ensure consistent test results regardless of host hardware
        self.resource_patcher = patch('complexity_scorer.get_system_resources')
        self.mock_resources = self.resource_patcher.start()
        # Simulate 16GB RAM, 8GB VRAM
        self.mock_resources.return_value = (16384, 8192)

        # Mock model size to simulate 4GB model
        self.size_patcher = patch(
            'complexity_scorer.ComplexityScorer._get_loaded_model_size_mb'
        )
        self.mock_size = self.size_patcher.start()
        self.mock_size.return_value = 4096

        # Mock model max context
        self.ctx_patcher = patch('complexity_scorer.ComplexityScorer._get_model_max_ctx')
        self.mock_ctx = self.ctx_patcher.start()
        self.mock_ctx.return_value = 8192

    def tearDown(self):
        self.resource_patcher.stop()
        self.size_patcher.stop()
        self.ctx_patcher.stop()

    def test_minimal_complexity(self):
        """Test very simple inputs trigger MINIMAL level."""
        res = ComplexityScorer.analyze("Hi")
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MINIMAL)
        self.assertGreaterEqual(res['params']['num_ctx'], 512)

    def test_simple_greeting(self):
        """Test simple inputs like greetings."""
        res = ComplexityScorer.analyze("Hello there")
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MINIMAL)
        self.assertGreaterEqual(res['params']['num_ctx'], 512)

    def test_moderate_question(self):
        """Test standard questions."""
        text = (
            "I would like to know what is the capital of France "
            "and what is the population there."
        )
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MODERATE)
        self.assertGreaterEqual(res['params']['num_ctx'], 2048)

    def test_true_moderate(self):
        """Test a request that should be MODERATE."""
        text = (
            "Can you write a short story about a robot? "
            "Please include some details about its internal class structure."
        )
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MODERATE)
        self.assertGreaterEqual(res['params']['num_ctx'], 2048)

    def test_deterministic_complex(self):
        """Test a technical request remains deterministic."""
        text = "Please write a complex Python script to calculate the entropy of a file."
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_COMPLEX)
        self.assertGreaterEqual(res['params']['num_ctx'], 2048)
        self.assertLessEqual(res['params']['temperature'], 0.2)

    def test_creative_simple(self):
        """Test a creative request triggers higher sampling even if simple."""
        text = "Write a beautiful and funny story about a space cat."
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_SIMPLE)
        self.assertGreater(res['params']['temperature'], 0.5)
        self.assertGreater(res['params']['top_p'], 0.6)

    def test_short_but_complex_task(self):
        """Test that short prompts demanding high thinking effort are boosted."""
        text = "Explain quantum physics in detail."
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MODERATE)
        self.assertGreaterEqual(res['params']['num_ctx'], 2048)
        self.assertEqual(res['params']['temperature'], 0.1)

if __name__ == '__main__':
    unittest.main()
