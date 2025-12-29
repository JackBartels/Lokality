import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import local_assistant
# Import utils to patch glob/open there
import utils 

class TestModelPull(unittest.TestCase):
    def setUp(self):
        self.memory_patcher = patch('local_assistant.MemoryStore')
        self.mock_memory = self.memory_patcher.start()
        
        self.client_patcher = patch('local_assistant.client')
        self.mock_client = self.client_patcher.start()
        
        # We will mock resources per test or keep generic patch
        self.resources_patcher = patch('local_assistant.get_system_resources')
        self.mock_resources = self.resources_patcher.start()

    def tearDown(self):
        self.memory_patcher.stop()
        self.client_patcher.stop()
        self.resources_patcher.stop()

    def test_init_with_existing_models(self):
        self.mock_client.list.return_value = {'models': ['some-model']}
        assistant = local_assistant.LocalChatAssistant()
        self.mock_client.pull.assert_not_called()

    def test_init_no_models_pulls_best_fit(self):
        self.mock_client.list.return_value = {'models': []}
        self.mock_resources.return_value = (16384, 8192) # 16GB RAM, 8GB VRAM
        self.mock_client.pull.return_value = [{'status': 'success'}]
        
        assistant = local_assistant.LocalChatAssistant()
        expected_model = "gemma3:4b-it-qat"
        self.mock_client.pull.assert_called_with(expected_model, stream=True)

    def test_init_insufficient_vram_pulls_nothing(self):
        self.mock_client.list.return_value = {'models': []}
        self.mock_resources.return_value = (16384, 512)
        assistant = local_assistant.LocalChatAssistant()
        self.mock_client.pull.assert_not_called()

    def test_init_mixed_resources_picks_correct_size(self):
        self.mock_client.list.return_value = {'models': []}
        self.mock_resources.return_value = (65536, 1536)
        self.mock_client.pull.return_value = [{'status': 'success'}]
        
        assistant = local_assistant.LocalChatAssistant()
        expected_model = "gemma3:270m"
        self.mock_client.pull.assert_called_with(expected_model, stream=True)

class TestIntelSupport(unittest.TestCase):
    def setUp(self):
        # We need to test utils.get_system_resources specifically
        pass

    @patch('utils.psutil.virtual_memory')
    @patch('utils.subprocess.check_output')
    @patch('utils.glob.glob')
    @patch('builtins.open', new_callable=mock_open, read_data='0x8086')
    def test_intel_igpu_detection(self, mock_file, mock_glob, mock_subprocess, mock_vm):
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
        mock_file.assert_called_with("/sys/class/drm/card0/device/vendor", 'r')

if __name__ == '__main__':
    unittest.main()