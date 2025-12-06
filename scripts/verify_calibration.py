
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

def verify_calibration():
    logger.info("Starting Calibration Verification...")
    
    # Create Mock Content with NO metadata but with text patterns
    content = NormalizedContent(
        content_id="test_content_calibration",
        src="web",
        platform_id="http://example.com/article",
        author="", # Empty author in metadata
        title="Test Article for Calibration",
        body="""
        By Jane Doe
        
        This is a test article to verify signal calibration.
        
        Customer Reviews
        Rated 4.5 out of 5 stars based on 100 reviews.
        
        Contact Us: support@example.com
        
        See our Privacy Policy for more details.
        """,
        run_id="test_run_calib",
        event_ts=datetime.now().isoformat(),
        meta={} # Empty metadata
    )
    
    # Initialize Scorer
    scorer = ContentScorer(use_attribute_detection=True)
    
    # Score Content
    brand_context = {"keywords": ["test"], "brand_name": "TestBrand"}
    trust_score = scorer.score_content(content, brand_context)
    
    # Verify Signals
    logger.info(f"Overall Trust Score: {trust_score.overall}")
    
    # 1. Check Author Byline (Provenance)
    provenance = trust_score.dimensions.get('provenance')
    prov_signals = [s.id for s in provenance.signals]
    if "prov_author_bylines" in prov_signals:
        logger.info("✅ prov_author_bylines detected from body text!")
    else:
        logger.error("❌ prov_author_bylines NOT detected!")

    # 2. Check Contact Info (Transparency)
    transparency = trust_score.dimensions.get('transparency')
    trans_signals = [s.id for s in transparency.signals]
    
    if "trans_contact_info" in trans_signals:
        logger.info("✅ trans_contact_info detected from body text!")
    else:
        logger.error("❌ trans_contact_info NOT detected!")
        
    if "trans_disclosures" in trans_signals:
        logger.info("✅ trans_disclosures (Privacy Policy) detected from body text!")
    else:
        logger.error("❌ trans_disclosures (Privacy Policy) NOT detected!")

    # 3. Check Social Proof (Verification)
    verification = trust_score.dimensions.get('verification')
    ver_signals = [s.id for s in verification.signals]
    
    if "ver_social_proof" in ver_signals:
        logger.info("✅ ver_social_proof detected from body text!")
    else:
        logger.error("❌ ver_social_proof NOT detected!")

    # 4. Check Resonance (Readability & Cultural Fit)
    resonance = trust_score.dimensions.get('resonance')
    res_signals = [s.id for s in resonance.signals]
    
    if "res_readability" in res_signals:
        logger.info("✅ res_readability detected!")
    else:
        logger.error("❌ res_readability NOT detected!")

    if "res_cultural_fit" in res_signals:
        logger.info("✅ res_cultural_fit detected (default/match)!")
    else:
        logger.error("❌ res_cultural_fit NOT detected!")

    # 5. Check Coherence (Brand Voice)
    coherence = trust_score.dimensions.get('coherence')
    coh_signals = [s.id for s in coherence.signals]
    
    if "coh_voice_consistency" in coh_signals:
        logger.info("✅ coh_voice_consistency detected (professional voice)!")
    else:
        logger.error("❌ coh_voice_consistency NOT detected!")

    logger.info(f"All Signals: {prov_signals + trans_signals + ver_signals + res_signals + coh_signals}")

if __name__ == "__main__":
    verify_calibration()
