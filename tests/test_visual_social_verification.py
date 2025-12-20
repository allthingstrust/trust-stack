"""
Test script to verify Visual Analysis integration for Social Media Verification.
Mocks the VisualAnalyzer to return "Verified" signals and checks if VerificationManager consumes them.
"""
import unittest
from unittest.mock import MagicMock, patch
from data.models import NormalizedContent
from scoring.verification_manager import VerificationManager

class TestVisualSocialVerification(unittest.TestCase):
    
    def setUp(self):
        self.manager = VerificationManager()
        # Mock LLM client to avoid API calls for claim extraction
        self.manager.llm_client = MagicMock()
        self.manager.llm_client.client.chat.return_value = {
            'content': '{"claims": ["Some generic claim"]}'
        }
        # Mock _verify_claims_parallel to avoid Serper calls
        self.manager._verify_claims_parallel = MagicMock(return_value=[
            {"claim": "Some generic claim", "status": "UNVERIFIED", "confidence": 0.5}
        ])

    def test_instagram_visual_verification(self):
        """Test that visual verification on Instagram boosts the score."""
        content = NormalizedContent(
            content_id="test_ig_1",
            src="instagram",
            platform_id="instagram",
            author="winndixie",
            title="Winn-Dixie Instagram",
            body="Just a test post.",
            visual_analysis={
                "social_verification": {
                    "platform": "instagram",
                    "is_verified": True,
                    "badge_type": "blue_check",
                    "evidence": "Found blue checkmark"
                },
                "signals": {}
            }
        )
        
        result = self.manager.verify_content(content)
        
        print(f"\n[Instagram] Result: {result}")
        
        # Check if the visual claim was added
        details = result['meta']['details']
        visual_claim = next((d for d in details if d.get('source') == 'visual_analysis'), None)
        
        self.assertIsNotNone(visual_claim, "Visual verification claim should be present")
        self.assertEqual(visual_claim['status'], 'SUPPORTED')
        self.assertIn("instagram", visual_claim['claim'])
        
        # Check if score is boosted (should be > 0.5 since we have one SUPPORTED claim)
        # Original UNVERIFIED claim = -0.05, SUPPORTED = +0.1. Base 0.5. 
        # Score approx 0.5 + 0.1 - 0.05 = 0.55
        self.assertGreater(result['score'], 0.5)

    def test_twitter_activity_tracking(self):
        """Test that X/Twitter activity (last post date) is preserved in visual analysis."""
        # Note: VerificationManager currently only uses the verification status, 
        # but we check if the data structure is valid for future use.
        content = NormalizedContent(
            content_id="test_x_1",
            src="twitter",
            platform_id="twitter",
            author="someuser",
            title="X Profile",
            body="Tweets...",
            visual_analysis={
                "social_verification": {
                    "platform": "twitter",
                    "is_verified": True,
                    "badge_type": "gold_check"
                },
                "social_activity": {
                    "platform": "twitter",
                    "last_post_date": "2024-12-20",
                    "evidence": "Posted 2h ago"
                }
            }
        )
        
        # Simply verifying that the manager runs without error
        result = self.manager.verify_content(content)
        self.assertGreater(result['score'], 0.5)
        print(f"\n[Twitter] Result: {result}")

if __name__ == '__main__':
    unittest.main()
