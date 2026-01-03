"""
Unit tests for model swapping functionality.
"""
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
import config
from local_assistant import LocalChatAssistant

@dataclass
class MockModel:
    """Mock model object."""
    model: str

class TestModelSwap(unittest.TestCase):
    """Test suite for model swapping."""

    @patch('local_assistant.get_ollama_client')
    def test_get_available_models(self, mock_get_client):
        """Test retrieving available models."""
        mock_client = mock_get_client.return_value

        mock_response = MagicMock()
        mock_response.models = [
            MockModel(model='model1:latest'),
            MockModel(model='model2:latest')
        ]
        mock_client.list.return_value = mock_response

        assistant = LocalChatAssistant()
        models = assistant.get_available_models()

        self.assertIn('model1:latest', models)
        self.assertIn('model2:latest', models)

    @patch('local_assistant.get_ollama_client')
    def test_switch_model(self, _mock_get_client):
        """Test switching the model."""
        assistant = LocalChatAssistant()
        assistant.messages = [{"role": "user", "content": "hello"}]

        new_model = "new-model:latest"
        assistant.switch_model(new_model)

        self.assertEqual(config.MODEL_NAME, new_model)
        self.assertEqual(assistant.messages, [])

if __name__ == '__main__':
    unittest.main()
