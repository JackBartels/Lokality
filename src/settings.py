"""
Persistent settings management for Lokality.
"""
import json
import os
from logger import logger

SETTINGS_FILE = os.path.join("res", "settings.json")

class Settings:
    """Handles loading and saving application settings."""
    def __init__(self):
        self.settings = {
            "debug": False,
            "show_info": False
        }
        self.load()

    def load(self):
        """Loads settings from the JSON file."""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to load settings: %s", exc)

    def save(self):
        """Saves current settings to the JSON file."""
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)

    def get(self, key, default=None):
        """Retrieves a setting value."""
        return self.settings.get(key, default)

    def set(self, key, value):
        """Sets a setting value and saves."""
        self.settings[key] = value
        self.save()
