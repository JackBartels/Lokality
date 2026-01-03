"""
Unit tests for model pulling logic and system resource detection.
"""
import unittest
from unittest.mock import patch, mock_open, MagicMock
import local_assistant
import utils
from tests.base_test import BaseAssistantTest

class TestModelPull(BaseAssistantTest):
    """Test suite for model pulling logic."""

    def setUp(self):
        super().setUp()
        # We will mock resources per test or keep generic patch
        self.patchers['resources'] = patch('local_assistant.get_system_resources')
        self.mocks['resources'] = self.patchers['resources'].start()

    def test_init_with_existing_models(self):
        """Test initialization when models already exist."""
        mock_response = MagicMock()
        mock_response.models = [MagicMock(model='some-model')]
        self.mocks['client'].list.return_value = mock_response
        local_assistant.LocalChatAssistant()
        self.mocks['client'].pull.assert_not_called()

    def test_init_no_models_pulls_best_fit(self):
        """Test that the best fitting model is pulled if none exist."""
        mock_response = MagicMock()
        mock_response.models = []
        self.mocks['client'].list.return_value = mock_response
        self.mocks['resources'].return_value = (16384, 8192) # 16GB RAM, 8GB VRAM
        self.mocks['client'].pull.return_value = [{'status': 'success'}]

        local_assistant.LocalChatAssistant()
        expected_model = "gemma3:4b-it-qat"
        self.mocks['client'].pull.assert_called_with(expected_model, stream=True)

    def test_init_insufficient_vram_pulls_nothing(self):
        """Test that nothing is pulled if VRAM is insufficient."""
        mock_response = MagicMock()
        mock_response.models = []
        self.mocks['client'].list.return_value = mock_response
        self.mocks['resources'].return_value = (16384, 512)
        local_assistant.LocalChatAssistant()
        self.mocks['client'].pull.assert_not_called()

    def test_init_mixed_resources_picks_correct_size(self):
        """Test model selection with mixed resources."""
        mock_response = MagicMock()
        mock_response.models = []
        self.mocks['client'].list.return_value = mock_response
        self.mocks['resources'].return_value = (65536, 1536)
        self.mocks['client'].pull.return_value = [{'status': 'success'}]

        local_assistant.LocalChatAssistant()
        expected_model = "gemma3:270m"
        self.mocks['client'].pull.assert_called_with(expected_model, stream=True)

class TestIntelSupport(unittest.TestCase):
    """Test suite for Intel GPU detection."""

    def setUp(self):
        # We need to test utils.get_system_resources specifically
        pass

    @patch('utils.psutil.virtual_memory')
    @patch('utils.subprocess.check_output')
    @patch('utils.glob.glob')
    @patch('builtins.open', new_callable=mock_open, read_data='0x8086')
    def test_intel_igpu_detection(self, mock_file, mock_glob, mock_subprocess, mock_vm):
        """Test detection of Intel iGPUs."""
        # Setup: 16GB RAM, No NVIDIA/AMD
        mock_vm.return_value.total = 16 * 1024 * 1024 * 1024
        mock_subprocess.side_effect = FileNotFoundError("No nvidia-smi") # Fail NVIDIA check

        # Simulate glob finding a card
        mock_glob.return_value = ["/sys/class/drm/card0/device/vendor"]

        # Call the function
        ram, vram = utils.get_system_resources()

        # Verify RAM is 16384
        self.assertEqual(ram, 16384)

        # Verify VRAM is RAM (No buffer deducted)
        self.assertEqual(vram, 16384)

        # Verify it verified the vendor
        mock_file.assert_called_with("/sys/class/drm/card0/device/vendor", 'r', encoding='utf-8')

if __name__ == '__main__':
    unittest.main()
