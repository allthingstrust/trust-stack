
import sys
import os
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.models import NormalizedContent
from scoring.scorer import ContentScorer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_guideline_override():
    logger.info("Starting Guideline Override Verification...")
    
    # 1. Create Mock Content with Slang
    content = NormalizedContent(
        content_id="test_slang_content",
        src="social",
        platform_id="twitter_123",
        author="BrandAccount",
        title="Slang Post",
        body="OMG this drop is gonna be lit! thx for waiting u guys.",
        run_id="test_run_override",
        event_ts=datetime.now().isoformat(),
        meta={"url": "http://twitter.com/brand/status/123"}
    )
    
    # 2. Mock Brand Guidelines
    # We mock the _load_brand_guidelines method to return guidelines that allow slang
    mock_guidelines = """
    VOICE & TONE:
    Our brand is young, energetic, and speaks the language of Gen Z.
    Slang is encouraged! Use words like 'lit', 'fam', 'thx', 'u'.
    Be authentic and casual.
    """
    
    # 3. Initialize Scorer
    scorer = ContentScorer(use_attribute_detection=True)
    
    # Patch the guideline loader
    with patch.object(scorer, '_load_brand_guidelines', return_value=mock_guidelines):
        brand_context = {"keywords": ["drop"], "brand_name": "CoolBrand", "use_guidelines": True}
        
        logger.info("Scoring content with guidelines enabled...")
        score = scorer.score_content(content, brand_context)
        
        # 4. Verify Results
        
        # Check if guidelines were used
        if content.meta.get('guidelines_used'):
            logger.info("✅ Guidelines were successfully loaded and used.")
        else:
            logger.error("❌ Guidelines were NOT used.")
            
        # Check Coherence Signals
        coherence = score.dimensions.get('coherence')
        coh_signals = [s.id for s in coherence.signals]
        
        logger.info(f"Coherence Signals: {coh_signals}")
        
        # The heuristic detector WOULD have flagged "gonna", "thx", "u" as unprofessional
        # and returned a 'coh_voice_consistency' signal with a low score (4.0).
        # But since we have guidelines, it should be OVERRIDDEN (removed).
        # The LLM signal 'legacy_coherence_llm' will still be there.
        
        if "coh_voice_consistency" in coh_signals:
            # Check if it's the heuristic one (we can check the value or rationale)
            # But wait, if the LLM *also* returns a signal with this ID in the future, this test might break.
            # Currently LLM returns 'legacy_coherence_llm'.
            # So 'coh_voice_consistency' ONLY comes from the heuristic detector.
            
            # If it's present, it means the override FAILED (or the heuristic returned 10.0? No, slang is present).
            # Let's check the value.
            signal_obj = next(s for s in coherence.signals if s.id == "coh_voice_consistency")
            if signal_obj.value < 5.0:
                logger.error(f"❌ Heuristic signal 'coh_voice_consistency' was NOT overridden! Value: {signal_obj.value}")
            else:
                 logger.info(f"⚠️ 'coh_voice_consistency' is present but has high value {signal_obj.value}. Did the heuristic fail to detect slang?")
        else:
            logger.info("✅ Heuristic signal 'coh_voice_consistency' was successfully overridden (removed)!")

if __name__ == "__main__":
    verify_guideline_override()
