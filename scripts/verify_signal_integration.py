
import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.models import NormalizedContent
from scoring.scorer import ContentScorer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_signal_integration():
    logger.info("Starting Signal Integration Verification...")
    
    # 1. Create Mock Content with attributes that should trigger signals
    content = NormalizedContent(
        content_id="test_content_1",
        src="web",
        platform_id="http://example.com/article",
        author="Verified Author",
        title="Test Article with Signals",
        body="This is a test article. It has clear authorship and transparency.",
        run_id="test_run",
        event_ts=datetime.now().isoformat(),
        meta={
            "author_verified": "true", # Should trigger prov_author_bylines
            "c2pa_manifest": "true",   # Should trigger prov_metadata_c2pa
            "c2pa_valid": "true",
            "privacy_policy_url": "http://example.com/privacy" # Should trigger trans_disclosures via detector logic
            # Note: detector logic for privacy policy might need more than just this key, 
            # but let's test the ones we know work easily first.
        }
    )
    
    # 2. Initialize Scorer
    scorer = ContentScorer(use_attribute_detection=True)
    
    # 3. Score Content
    brand_context = {"keywords": ["test"], "brand_name": "TestBrand"}
    trust_score = scorer.score_content(content, brand_context)
    
    # 4. Verify Signals
    logger.info(f"Overall Trust Score: {trust_score.overall}")
    logger.info(f"Overall Confidence: {trust_score.confidence}")
    logger.info(f"Overall Coverage: {trust_score.coverage}")
    
    provenance = trust_score.dimensions.get('provenance')
    if not provenance:
        logger.error("❌ Provenance dimension missing!")
        return
        
    logger.info(f"Provenance Score: {provenance.value}")
    logger.info(f"Provenance Confidence: {provenance.confidence}")
    logger.info(f"Provenance Coverage: {provenance.coverage}")
    
    # Check for specific signals
    signal_ids = [s.id for s in provenance.signals]
    logger.info(f"Provenance Signals: {signal_ids}")
    
    if "prov_author_bylines" in signal_ids:
        logger.info("✅ prov_author_bylines signal found!")
    else:
        logger.error("❌ prov_author_bylines signal NOT found!")
        
    if "prov_metadata_c2pa" in signal_ids:
        logger.info("✅ prov_metadata_c2pa signal found!")
    else:
        logger.error("❌ prov_metadata_c2pa signal NOT found!")

    # Check for Transparency signal
    transparency = trust_score.dimensions.get('transparency')
    if transparency:
        trans_signals = [s.id for s in transparency.signals]
        if "trans_disclosures" in trans_signals:
            logger.info("✅ trans_disclosures signal found!")
        else:
            logger.error("❌ trans_disclosures signal NOT found!")
        
    # Check if legacy signals are also present
    if "legacy_provenance_llm" in signal_ids:
        logger.info("✅ legacy_provenance_llm signal found!")
    else:
        logger.error("❌ legacy_provenance_llm signal NOT found!")

if __name__ == "__main__":
    verify_signal_integration()
