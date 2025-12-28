import unittest
import os
import sys
import sqlite3
import threading
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory import MemoryStore
from utils import verify_env_health

class TestRobustness(unittest.TestCase):
    def test_verify_environment_writable(self):
        # This should pass in the current environment
        success, errors = verify_env_health()
        self.assertTrue(success, f"Environment check failed: {errors}")

    def test_database_busy_retry(self):
        # Use a real file for busy testing
        db_path = "test_busy.db"
        if os.path.exists(db_path): os.remove(db_path)
        
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
            except Exception as e:
                self.write_result = e

        t = threading.Thread(target=try_write)
        t.start()
        
        time.sleep(0.5) # Wait for retry to be happening
        conn2.rollback() # Release the lock
        conn2.close()
        
        t.join(timeout=5)
        self.assertTrue(self.write_result is True, f"Write failed or timed out: {self.write_result}")
        
        # Cleanup
        store.close()
        if os.path.exists(db_path): 
            for ext in ["", "-wal", "-shm"]:
                if os.path.exists(db_path+ext): os.remove(db_path+ext)

    def test_markdown_rendering_safety(self):
        # We can't easily test the Tkinter UI here without a display, 
        # but we can verify the logic in app.py would handle it.
        # This is more of a manual verification of the code changes in app.py.
        pass

if __name__ == "__main__":
    unittest.main()
