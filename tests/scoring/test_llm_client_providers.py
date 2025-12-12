import pytest
from unittest.mock import MagicMock, patch
from scoring.llm_client import ChatClient, LLMProvider

class TestChatClientProviders:
    """Tests for ChatClient provider cost tracking."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset usages."""
        from scoring.cost_tracker import CostTracker
        CostTracker._instance = None
        yield
        CostTracker._instance = None

    @patch('scoring.llm_client.Anthropic')
    def test_anthropic_client_records_usage(self, mock_anthropic):
        """Test Anthropic calls record usage."""
        from scoring.cost_tracker import CostTracker
        
        # Setup mock
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Claude response")]
        mock_response.usage = MagicMock(
            input_tokens=42,
            output_tokens=17
        )
        mock_client.messages.create.return_value = mock_response
        
        tracker = CostTracker()
        
        # Inject mocks
        with patch('scoring.cost_tracker.cost_tracker', tracker):
            client = ChatClient(api_key="sk-fake", anthropic_api_key="sk-ant-fake")
            
            # Call with Claude model
            client.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-3-5-sonnet-20241022",
                provider="anthropic" # Explicitly ignored by logic but model prefix used
            )
            
            # Check cost tracker
            summary = tracker.get_summary()
            assert "claude-3-5-sonnet-20241022" in summary["models"]
            assert summary["models"]["claude-3-5-sonnet-20241022"]["prompt_tokens"] == 42
            assert summary["models"]["claude-3-5-sonnet-20241022"]["completion_tokens"] == 17

    @patch('scoring.llm_client.genai')
    def test_google_client_records_usage(self, mock_genai):
        """Test Google ChatClient calls record usage."""
        from scoring.cost_tracker import CostTracker
        
        # Mock GenerativeModel
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        
        # Mock response
        mock_response = MagicMock()
        mock_response.text = "Gemini response"
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=99,
            candidates_token_count=33,
            total_token_count=132
        )
        
        # Mock generate_content (single message case)
        mock_model.generate_content.return_value = mock_response
        
        tracker = CostTracker()
        
        with patch('scoring.cost_tracker.cost_tracker', tracker):
            client = ChatClient(api_key="sk-fake", google_api_key="fake-google")
            
            # Call with Gemini model
            client.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="gemini-1.5-pro",
            )
            
            # Check cost tracker
            summary = tracker.get_summary()
            assert "gemini-1.5-pro" in summary["models"]
            assert summary["models"]["gemini-1.5-pro"]["prompt_tokens"] == 99
            assert summary["models"]["gemini-1.5-pro"]["completion_tokens"] == 33
