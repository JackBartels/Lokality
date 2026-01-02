"""
Unit tests for the MemoryStore class.
"""
import threading
import unittest
from memory import MemoryStore

class TestMemoryStore(unittest.TestCase):
    """Test suite for MemoryStore."""

    def setUp(self):
        # Use an in-memory database for testing
        self.store = MemoryStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_add_and_get_all_facts(self):
        """Test adding a fact and retrieving all facts."""
        self.store.add_fact("User", "Likes pizza")
        facts = self.store.get_all_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["entity"], "User")
        self.assertEqual(facts[0]["fact"], "Likes pizza")

    def test_remove_fact(self):
        """Test removing a fact by ID."""
        self.store.add_fact("User", "Likes pizza")
        facts = self.store.get_all_facts()
        fact_id = facts[0]["id"]
        self.store.remove_fact(fact_id)
        facts = self.store.get_all_facts()
        self.assertEqual(len(facts), 0)

    def test_update_fact(self):
        """Test updating an existing fact."""
        self.store.add_fact("User", "Likes pizza")
        facts = self.store.get_all_facts()
        fact_id = facts[0]["id"]
        self.store.update_fact(fact_id, "User", "Likes tacos")
        facts = self.store.get_all_facts()
        self.assertEqual(facts[0]["fact"], "Likes tacos")

    def test_get_relevant_facts(self):
        """Test FTS5 keyword retrieval."""
        self.store.add_fact("Assistant", "I am Lokality")
        self.store.add_fact("User", "My name is Jack")
        self.store.add_fact("User", "I live in London")

        # Should always get Assistant info
        facts = self.store.get_relevant_facts("What is my name?")
        entities = [f["entity"] for f in facts]
        self.assertIn("Assistant", entities)

        # Should match keyword "name"
        facts = self.store.get_relevant_facts("What is my name?")
        fact_texts = [f["fact"] for f in facts]
        self.assertTrue(any("Jack" in f for f in fact_texts))

    def test_clear_memory(self):
        """Test clearing all memory."""
        self.store.add_fact("User", "Likes pizza")
        self.store.clear()
        self.assertEqual(self.store.get_fact_count(), 0)

    def test_concurrent_writes(self):
        """Test concurrent writes to the database."""
        def add_facts(count, start_index):
            for i in range(count):
                self.store.add_fact("User", f"Fact {start_index + i}")

        threads = []
        num_threads = 5
        facts_per_thread = 10

        for i in range(num_threads):
            t = threading.Thread(target=add_facts, args=(facts_per_thread, i * facts_per_thread))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(self.store.get_fact_count(), num_threads * facts_per_thread)

if __name__ == "__main__":
    unittest.main()
