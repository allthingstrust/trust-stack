
import logging
import sys
import os
from data.models import NormalizedContent
from unittest.mock import patch
from ingestion.serper_search import search_serper
from scoring.verification_manager import VerificationManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_verification():
    # Create a dummy content with a fake claim
    content = NormalizedContent(
        content_id="test_1",
        body="The population of sdlfkjsdflkjsdflkjsdflkjsdflkjsdf is exactly 1.",
        title="Test Content",
        src="test",
        event_ts="2024-01-01",
        platform_id="test_platform",
        author="test_author"
    )
    
    print(f"Testing VerificationManager with content: {content.body}")
    
    with patch('scoring.verification_manager.search_serper', return_value=[]), \
         patch.object(VerificationManager, '_extract_claims', return_value=["The population of sdlfkjsdflkjsdflkjsdflkjsdflkjsdf is exactly 1."]):
        manager = VerificationManager()
        result = manager.verify_content(content)
    
    print("\nVerification Result:")
    print(f"Score: {result.get('score')}")
    print(f"Issues: {len(result.get('issues', []))}")
    for issue in result.get('issues', []):
        print(f" - Type: {issue.get('type')}")
        print(f"   Confidence: {issue.get('confidence')}")
        print(f"   Evidence: {issue.get('evidence')}")
        print(f"   Suggestion: {issue.get('suggestion')}")

if __name__ == "__main__":
    test_verification()
