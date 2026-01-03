"""
Base class for assistant-related unit tests.
"""
import unittest
from datetime import datetime
from unittest.mock import patch

class BaseAssistantTest(unittest.TestCase):
    """Common setup and teardown for assistant tests."""

    def setUp(self):
        """Set up common patches and mocks."""
        self.patchers = {}
        self.mocks = {}

        # MemoryStore patch
        self.patchers['memory'] = patch('local_assistant.MemoryStore')
        self.mocks['memory_class'] = self.patchers['memory'].start()
        self.mocks['memory_instance'] = self.mocks['memory_class'].return_value
        self.mocks['memory_instance'].get_relevant_facts.return_value = []
        # Support both 'memory_instance' and 'memory' names used in different tests
        self.mocks['memory'] = self.mocks['memory_instance']

        # client patch
        self.patchers['client'] = patch('local_assistant.get_ollama_client')
        self.mocks['get_client'] = self.patchers['client'].start()
        self.mocks['client'] = self.mocks['get_client'].return_value
        # Also patch it in other modules just in case
        self.patchers['client_mm'] = patch(
            'memory_manager.get_ollama_client', new=self.mocks['get_client']
        )
        self.patchers['client_mm'].start()
        self.patchers['client_sc'] = patch(
            'stats_collector.get_ollama_client', new=self.mocks['get_client']
        )
        self.patchers['client_sc'].start()

        # Mock datetime for determinism
        self.patchers['datetime'] = patch('local_assistant.datetime')
        self.mocks['datetime'] = self.patchers['datetime'].start()
        # Default mock date
        self.set_mock_date(datetime(2025, 12, 27, 10, 30))
        self.mocks['datetime'].strftime = datetime.strftime

    def set_mock_date(self, dt_obj):
        """Helper to update the mocked current time."""
        self.mocks['datetime'].now.return_value = dt_obj

    def tearDown(self):
        """Stop all active patchers."""
        for patcher in self.patchers.values():
            patcher.stop()
