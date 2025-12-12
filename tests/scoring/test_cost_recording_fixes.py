
import pytest
from unittest.mock import MagicMock, patch
from scoring.visual_analyzer import VisualAnalyzer
from scoring.llm_client import ChatClient, LLMProvider

# --- Test VisualAnalyzer (Gemini) Cost Recording ---

@patch("scoring.visual_analyzer.genai")
@patch("scoring.cost_tracker.cost_tracker")
def test_visual_analyzer_records_cost_correctly(mock_cost_tracker, mock_genai):
    """
    Verify that VisualAnalyzer calls cost_tracker.record() with the correct arguments
    (prompt_tokens, completion_tokens) instead of record_cost().
    """
    # Setup mocks
    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    
    mock_response = MagicMock()
    mock_response.text = '{"score": 0.8, "signals": {}}'
    
    # Mock usage metadata (Gemini style)
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 123
    mock_usage.candidates_token_count = 45
    mock_response.usage_metadata = mock_usage
    
    mock_model.generate_content.return_value = mock_response
    
    # Initialize analyzer
    analyzer = VisualAnalyzer()
    analyzer.model = "gemini-test-model"
    
    # Act
    image_bytes = b"fake_image_data"
    analyzer.analyze(image_bytes, "http://example.com")
    
    # Assert
    # Verify record() was called, NOT record_cost()
    mock_cost_tracker.record.assert_called_once()
    
    # Verify arguments
    call_args = mock_cost_tracker.record.call_args
    assert call_args.kwargs['model'] == "gemini-test-model"
    assert call_args.kwargs['prompt_tokens'] == 123
    assert call_args.kwargs['completion_tokens'] == 45


# --- Test ChatClient (Anthropic) Cost Recording ---

@patch("scoring.llm_client.Anthropic")
@patch("scoring.cost_tracker.cost_tracker")
def test_chat_client_records_anthropic_cost(mock_cost_tracker, mock_anthropic_idx):
    """
    Verify that ChatClient correctly records cost for Anthropic calls.
    """
    # Setup Anthropic client mock
    mock_client_instance = MagicMock()
    mock_anthropic_idx.return_value = mock_client_instance
    
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Response content")]
    
    # Mock usage (Anthropic style)
    mock_usage = MagicMock()
    mock_usage.input_tokens = 50
    mock_usage.output_tokens = 20
    mock_message.usage = mock_usage
    
    mock_client_instance.messages.create.return_value = mock_message
    
    # Initialize client
    client = ChatClient(api_key="dummy", anthropic_api_key="dummy")
    
    # Act
    client.chat(
        messages=[{"role": "user", "content": "Hello"}],
        model="claude-3-test"
    )
    
    # Assert
    mock_cost_tracker.record.assert_called_once()
    call_args = mock_cost_tracker.record.call_args
    assert call_args.kwargs['model'] == "claude-3-test"
    assert call_args.kwargs['prompt_tokens'] == 50
    assert call_args.kwargs['completion_tokens'] == 20


# --- Test ChatClient (Google) Cost Recording ---

@patch("scoring.llm_client.genai")
@patch("scoring.cost_tracker.cost_tracker")
def test_chat_client_records_google_cost(mock_cost_tracker, mock_genai):
    """
    Verify that ChatClient correctly records cost for Google/Gemini calls.
    """
    # Setup Google/Gemini mock
    mock_model = MagicMock()
    mock_genai.GenerativeModel.return_value = mock_model
    
    mock_response = MagicMock()
    mock_response.text = "Response content"
    
    # Mock usage (Google style)
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 100
    mock_usage.candidates_token_count = 30
    mock_usage.total_token_count = 130
    mock_response.usage_metadata = mock_usage
    
    mock_model.generate_content.return_value = mock_response
    
    # Initialize client
    client = ChatClient(api_key="dummy", google_api_key="dummy")
    
    # Act
    client.chat(
        messages=[{"role": "user", "content": "Hello"}],
        model="gemini-pro-test"
    )
    
    # Assert
    mock_cost_tracker.record.assert_called_once()
    call_args = mock_cost_tracker.record.call_args
    assert call_args.kwargs['model'] == "gemini-pro-test"
    assert call_args.kwargs['prompt_tokens'] == 100
    assert call_args.kwargs['completion_tokens'] == 30
