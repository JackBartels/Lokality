"""
Unit tests for the Profiler class.
"""
import unittest
import time
from src.profiler import Profiler

class TestProfiler(unittest.TestCase):
    """Test suite for the Profiler singleton."""
    def setUp(self):
        """Reset the profiler before each test."""
        self.profiler = Profiler()
        self.profiler.enabled = True
        self.profiler.reset()

    def test_singleton(self):
        """Verify that Profiler is a singleton."""
        p1 = Profiler()
        p2 = Profiler()
        self.assertIs(p1, p2)

    def test_profiling_flow(self):
        """Test the basic start/stop/get_data flow."""
        self.profiler.start("test_task")
        time.sleep(0.01)
        self.profiler.stop("test_task")

        data = self.profiler.get_latest_data()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "test_task")
        self.assertGreater(data[0]["duration"], 0)

    def test_reset(self):
        """Verify that reset clears profiling data."""
        self.profiler.start("test_task")
        self.profiler.stop("test_task")
        self.profiler.reset()
        self.assertEqual(len(self.profiler.get_latest_data()), 0)

    def test_disabled(self):
        """Test that profiling is skipped when disabled."""
        self.profiler.enabled = False
        self.profiler.start("disabled_task")
        self.profiler.stop("disabled_task")
        self.assertEqual(len(self.profiler.get_latest_data()), 0)

if __name__ == "__main__":
    unittest.main()
