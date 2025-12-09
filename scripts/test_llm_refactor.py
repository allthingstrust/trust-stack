
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scoring.llm_client import ChatClient
from scoring.scoring_llm_client import LLMScoringClient
from scoring.llm import LLMClient
from scoring.verification_manager import VerificationManager

class TestRefactor(unittest.TestCase):
    def test_imports_and_init_chat_client(self):
        print("Testing ChatClient init...")
        # Mocking API keys to avoid errors if env not set
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            client = ChatClient(api_key="test-key")
            self.assertIsNotNone(client)
            self.assertEqual(client.default_model, "gpt-4o")

    def test_imports_and_init_scoring_client(self):
        print("Testing LLMScoringClient init...")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            client = LLMScoringClient()
            self.assertIsNotNone(client)
            self.assertIsInstance(client.client, ChatClient)

    def test_imports_and_init_llm_client(self):
        print("Testing LLMClient init...")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            client = LLMClient()
            self.assertIsNotNone(client)
            self.assertIsInstance(client.chat_client, ChatClient)

    def test_verification_manager_init(self):
        print("Testing VerificationManager init...")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            manager = VerificationManager()
            self.assertIsNotNone(manager)
            self.assertIsInstance(manager.llm_client, LLMScoringClient)

    def test_chat_client_provider_detection(self):
        print("Testing provider detection...")
        client = ChatClient(api_key="test")
        self.assertEqual(client._detect_provider("gpt-4o").value, "openai")
        self.assertEqual(client._detect_provider("claude-3").value, "anthropic")
        self.assertEqual(client._detect_provider("gemini-1.5").value, "google")
        self.assertEqual(client._detect_provider("deepseek-chat").value, "deepseek")

if __name__ == '__main__':
    unittest.main()
