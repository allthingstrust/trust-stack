
import os
import sys
import logging
from pathlib import Path
from PIL import Image

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.run_manager import RunManager
from data import store
from scoring.scorer import ContentScorer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_fix():
    # 1. Create a dummy image
    temp_dir = os.path.join(PROJECT_ROOT, 'data', 'temp_uploads')
    os.makedirs(temp_dir, exist_ok=True)
    image_path = os.path.join(temp_dir, 'verification_test.png')
    
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save(image_path)
    logger.info(f"Created test image at {image_path}")

    # 2. Setup Run Config with visual analysis ENABLED
    run_config = {
        "brand_name": "VerificationBrand",
        "scenario_name": "Config Check",
        "visual_analysis_enabled": True, # This is the key flag we fixed
        "assets": [
            {
                "url": "http://example.com/manual-upload",
                "title": "Manual Upload Test",
                "source_type": "web",
                "screenshot_path": f"file://{image_path}",
                "raw_content": "This is a test of visual analysis configuration propagation."
            }
        ],
        "sources": ["web"],
        "keywords": ["test"],
        "scenario_config": {
            "summary_model": "gpt-4o-mini" 
        }
    }

    # 3. specific setting of global settings to FALSE to ensure override works
    from config.settings import SETTINGS
    SETTINGS['visual_analysis_enabled'] = False
    logger.info("Global SETTINGS['visual_analysis_enabled'] set to False to test override.")

    # 4. Run Analysis
    engine = store.init_db()
    
    # MOCK the VisualAnalyzer to avoid actual API calls/failures, 
    # OR rely on the fact that if it runs it produces distinct output in 'visual_analysis'.
    # For now, let's let it run. If it fails due to API key, the error will still be in visual_analysis.
    # If it is SKIPPED, visual_analysis column will be None/Empty.
    
    scorer = ContentScorer()
    manager = RunManager(engine=engine, scoring_pipeline=scorer)

    logger.info("Starting analysis...")
    try:
        run = manager.run_analysis("verification-brand", "config-check", run_config)
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return

    # 5. Check Results
    asset = run.assets[0]
    
    logger.info(f"Asset path: {asset.screenshot_path}")
    
    # We need to query the DB to check the persisted visual_analysis column
    # BUT RunManager.run_analysis returns a potentially detached object or one from a closed session.
    # However, create_run returns it. Let's inspect the `run` object returned.
    
    # Wait, `run.assets` might not be loaded if session closed? 
    # RunManager.run_analysis does eager loading before expunging.
    
    asset = run.assets[0]
    scores = asset.scores[0]
    
    rationale = scores.rationale or {}
    visual_result = rationale.get('visual_analysis')
    
    logger.info(f"Visual Analysis Result in Rationale: {visual_result}")
    
    if visual_result:
        logger.info("✅ SUCCESS: Visual Analysis data was found! Config propagation worked.")
        print("VERIFICATION_SUCCESS")
    else:
        logger.error("❌ FAILURE: Visual Analysis data missing. Config propagation likely failed.")
        print("VERIFICATION_FAILURE")

if __name__ == "__main__":
    verify_fix()
