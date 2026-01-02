"""
Tests for system robustness and concurrency.
"""
import os
import sqlite3
import threading
import time
import unittest
from memory import MemoryStore
from utils import verify_env_health

class TestRobustness(unittest.TestCase):
    """Test suite for robustness checks."""

    def setUp(self):
        """Set up test variables."""
        self.write_result = None

    def test_verify_environment_writable(self):
        """Test environment health check."""
        # This should pass in the current environment
        success, errors = verify_env_health()
        self.assertTrue(success, f"Environment check failed: {errors}")

    def test_database_busy_retry(self):
        """Test database retry logic when locked."""
        # Use a real file for busy testing
        db_path = "test_busy.db"
        if os.path.exists(db_path):
            os.remove(db_path)

        store = MemoryStore(db_path=db_path)
        store.add_fact("Test", "Initial")

        # Lock the database manually in another connection
        conn2 = sqlite3.connect(db_path)
        conn2.execute("BEGIN EXCLUSIVE")

        def try_write():
            self.write_result = None
            try:
                store.add_fact("Test", "Secondary")
                self.write_result = True
            except (sqlite3.Error, OSError) as err:
                self.write_result = err

        t = threading.Thread(target=try_write)
        t.start()

        time.sleep(0.5) # Wait for retry to be happening
        conn2.rollback() # Release the lock
        conn2.close()

        t.join(timeout=5)
        self.assertTrue(
            self.write_result is True,
            f"Write failed or timed out: {self.write_result}"
        )

        # Cleanup
        store.close()
        if os.path.exists(db_path):
            for ext in ["", "-wal", "-shm"]:
                if os.path.exists(db_path + ext):
                    os.remove(db_path + ext)

    def test_markdown_rendering_safety(self):
        """Test markdown rendering safety (placeholder)."""
        # We can't easily test the Tkinter UI here without a display,
        # but we can verify the logic in app.py would handle it.
        # This is more of a manual verification of the code changes in app.py.

if __name__ == "__main__":
    unittest.main()
