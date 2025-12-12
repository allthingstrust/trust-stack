
import pytest
from unittest.mock import MagicMock, patch
from scoring.scorer import ContentScorer
from data.models import NormalizedContent

class TestModelPropagation:
    @patch('scoring.scorer.LLMScoringClient')
    def test_model_propagation_to_client(self, MockLLMClient):
        """Verify that llm_model in brand_context is passed to LLMScoringClient methods."""
        
        # Setup mock client
        mock_client_instance = MockLLMClient.return_value
        mock_client_instance.get_score.return_value = 0.8
        mock_client_instance.get_score_with_reasoning.return_value = {'score': 0.8, 'issues': []}
        mock_client_instance.get_score_with_feedback.return_value = {'score': 0.8, 'issues': []}
        
        # Initialize scorer
        scorer = ContentScorer()
        
        # Create dummy content
        content = NormalizedContent(
            content_id="test_123",
            source_tier="official",
            source_type="web",
            platform_id="https://example.com",
            title="Test Content",
            body="This is a test body.",
            url="https://example.com"
        )
        
        # Define context with explicit model
        target_model = "claude-3-5-sonnet-20240620"
        brand_context = {
            "brand_name": "TestBrand",
            "llm_model": target_model
        }
        
        # Run scoring
        scorer.batch_score_content([content], brand_context)
        
        # Verify get_score was called with model argument
        # We need to check call_args of the mock methods
        
        # Check _score_provenance call path
        # It calls _get_llm_score -> client.get_score
        found_model_call = False
        for call in mock_client_instance.get_score.call_args_list:
            args, kwargs = call
            if kwargs.get('model') == target_model:
                found_model_call = True
                break
        
        assert found_model_call, f"get_score was never called with model='{target_model}'"
        
        # Check _score_transparency call path
        # It calls _get_llm_score_with_reasoning -> client.get_score_with_reasoning
        found_model_call_reasoning = False
        for call in mock_client_instance.get_score_with_reasoning.call_args_list:
            args, kwargs = call
            if kwargs.get('model') == target_model:
                found_model_call_reasoning = True
                break
                
        assert found_model_call_reasoning, f"get_score_with_reasoning was never called with model='{target_model}'"

if __name__ == "__main__":
    pytest.main([__file__])
