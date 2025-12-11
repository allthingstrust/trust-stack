"""
Unit tests for verification manager claim extraction.
Tests that first-party ecommerce data is excluded from verification.
"""
import pytest
from unittest.mock import patch, MagicMock
from data.models import NormalizedContent
from scoring.verification_manager import VerificationManager
from prompts.verification import build_claim_extraction_prompt


class TestFirstPartyDataExclusion:
    """Test that first-party ecommerce data is excluded from claim verification."""
    
    def test_brand_owned_flag_passed_to_prompt(self):
        """Verify that brand-owned content passes is_brand_owned=True to prompt builder."""
        content = NormalizedContent(
            content_id="test_1",
            src="murrayscheese.com",
            platform_id="web",
            author="",
            title="Jasper Hill Winnimere",
            body="Jasper Hill Winnimere is priced at $35.00 per 13 oz wheel. This award-winning cheese is aged for 60 days.",
            url="https://www.murrayscheese.com/cheese/winnimere",
            source_type="brand_owned",  # Key: this is brand-owned content
            channel="web",
            platform_type="owned"
        )
        
        manager = VerificationManager()
        
        # Patch the prompt builder to capture what's passed
        with patch('scoring.verification_manager.build_claim_extraction_prompt') as mock_prompt:
            mock_prompt.return_value = "mocked prompt"
            
            # Patch LLM client to avoid actual API calls
            with patch.object(manager.llm_client.client, 'chat') as mock_chat:
                mock_chat.return_value = {'content': '{"claims": []}'}
                
                manager._extract_claims(content)
                
                # Verify is_brand_owned=True was passed
                mock_prompt.assert_called_once()
                call_kwargs = mock_prompt.call_args
                assert call_kwargs.kwargs.get('is_brand_owned') == True, \
                    "is_brand_owned should be True for brand_owned content"
    
    def test_third_party_flag_not_passed(self):
        """Verify that third-party content does NOT pass is_brand_owned=True."""
        content = NormalizedContent(
            content_id="test_2",
            src="reddit.com",
            platform_id="reddit",
            author="cheese_lover",
            title="Review of Murray's cheese",
            body="I bought the Jasper Hill Winnimere for $35.00. It was amazing!",
            url="https://www.reddit.com/r/cheese/comments/xyz",
            source_type="third_party",  # Key: this is NOT brand-owned
            channel="reddit",
            platform_type="social"
        )
        
        manager = VerificationManager()
        
        with patch('scoring.verification_manager.build_claim_extraction_prompt') as mock_prompt:
            mock_prompt.return_value = "mocked prompt"
            
            with patch.object(manager.llm_client.client, 'chat') as mock_chat:
                mock_chat.return_value = {'content': '{"claims": []}'}
                
                manager._extract_claims(content)
                
                # Verify is_brand_owned=False was passed
                mock_prompt.assert_called_once()
                call_kwargs = mock_prompt.call_args
                assert call_kwargs.kwargs.get('is_brand_owned') == False, \
                    "is_brand_owned should be False for third_party content"


class TestClaimExtractionPrompt:
    """Test the claim extraction prompt builder."""
    
    def test_brand_owned_adds_source_context(self):
        """Verify that is_brand_owned=True adds exclusion context to prompt."""
        prompt = build_claim_extraction_prompt(
            content_body="Product costs $35.00",
            is_brand_owned=True
        )
        
        # Should contain source context about excluding first-party data
        assert "<source_context>" in prompt
        assert "BRAND'S OWN website" in prompt
        assert "prices" in prompt.lower()
    
    def test_third_party_no_source_context(self):
        """Verify that is_brand_owned=False does NOT add source context."""
        prompt = build_claim_extraction_prompt(
            content_body="Product costs $35.00",
            is_brand_owned=False
        )
        
        # Should NOT contain source context
        assert "<source_context>" not in prompt


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
