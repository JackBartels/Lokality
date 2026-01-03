"""
Unit tests for settings persistence.
"""
import unittest
import os
import shutil
import src.settings
from src.settings import Settings

class TestSettings(unittest.TestCase):
    """Test suite for settings management."""

    def setUp(self):
        """Set up a temporary res directory."""
        self.res_dir = "res_test"
        if os.path.exists(self.res_dir):
            shutil.rmtree(self.res_dir)
        os.makedirs(self.res_dir)

        # Patch SETTINGS_FILE in settings module
        self.original_file = src.settings.SETTINGS_FILE
        src.settings.SETTINGS_FILE = os.path.join(self.res_dir, "settings.json")

    def tearDown(self):
        """Clean up the temporary res directory."""
        if os.path.exists(self.res_dir):
            shutil.rmtree(self.res_dir)

        # Restore SETTINGS_FILE
        src.settings.SETTINGS_FILE = self.original_file

    def test_default_settings(self):
        """Test that default settings are correct."""
        settings = Settings()
        self.assertFalse(settings.get("debug"))
        self.assertFalse(settings.get("show_info"))

    def test_save_load_settings(self):
        """Test saving and then loading settings."""
        settings = Settings()
        settings.set("debug", True)
        settings.set("show_info", True)
        settings.set("model_name", "test-model")

        # Create a new settings object to force reload
        new_settings = Settings()
        self.assertTrue(new_settings.get("debug"))
        self.assertTrue(new_settings.get("show_info"))
        self.assertEqual(new_settings.get("model_name"), "test-model")

    def test_invalid_json(self):
        """Test behavior with invalid JSON in settings file."""
        with open(src.settings.SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write("invalid json")

        settings = Settings()
        # Should fall back to defaults
        self.assertFalse(settings.get("debug"))
