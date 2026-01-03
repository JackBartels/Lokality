"""
Unit tests for the ComplexityScorer class.
"""
import unittest
from complexity_scorer import ComplexityScorer

class TestComplexityScorer(unittest.TestCase):
    """Test suite for ComplexityScorer."""

    def test_minimal_complexity(self):
        """Test very simple inputs trigger MINIMAL level."""
        res = ComplexityScorer.analyze("Hi")
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MINIMAL)

    def test_simple_greeting(self):
        """Test simple inputs like greetings."""
        res = ComplexityScorer.analyze("Hello there")
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MINIMAL)

    def test_moderate_question(self):
        """Test standard questions."""
        text = (
            "I would like to know what is the capital of France "
            "and what is the population there."
        )
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MODERATE)

    def test_true_moderate(self):
        """Test a request that should be MODERATE."""
        text = (
            "Can you write a short story about a robot? "
            "Please include some details about its internal class structure."
        )
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_MODERATE)

    def test_deterministic_complex(self):
        """Test a technical request remains deterministic."""
        text = "Please write a complex Python script to calculate the entropy of a file."
        res = ComplexityScorer.analyze(text)
        self.assertEqual(res['level'], ComplexityScorer.LEVEL_COMPLEX)
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
        self.assertEqual(res['params']['temperature'], 0.1)

if __name__ == '__main__':
    unittest.main()
