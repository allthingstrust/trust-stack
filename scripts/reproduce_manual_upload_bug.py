
import os
import sys
import logging
import time
import shutil
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

def reproduce_issue():
    # 1. Simulate the exact file setup from webapp/app.py
    temp_dir = os.path.join(PROJECT_ROOT, 'data', 'temp_uploads')
    os.makedirs(temp_dir, exist_ok=True)
    
    brand_id = "test_brand_manual"
    platform = "linkedin"
    timestamp = int(time.time())
    fname = "pasted_linkedin.png"
    
    filename = f"{brand_id}_{platform}_{timestamp}_{fname}"
    file_path = os.path.join(temp_dir, filename)
    
    # Create a dummy image
    img = Image.new('RGB', (200, 200), color = 'blue')
    img.save(file_path)
    logger.info(f"Created test image at {file_path}")

    # 2. Construct assets_config exactly as webapp/app.py does
    platform_names = {'linkedin': 'LinkedIn'}
    platform_urls = {'linkedin': f'https://www.linkedin.com/company/{brand_id}'}
    
    asset = {
        "url": platform_urls.get(platform),
        "title": f"{brand_id} on {platform_names.get(platform)} (Manual Upload)",
        "source_type": "social",
        "channel": "social",
        "raw_content": f"Manual upload of {platform_names.get(platform)} profile for {brand_id}.",
        "normalized_content": f"Manual upload of {platform_names.get(platform)} profile for {brand_id}.",
        "screenshot_path": f"file://{file_path}", 
        "visual_analysis": True, # Force visual analysis
        "meta_info": {
            "manual_upload": True,
            "platform": platform_names.get(platform)
        }
    }
    
    run_config = {
        "brand_name": brand_id,
        "scenario_name": "Manual Upload Repro",
        "visual_analysis_enabled": True, 
        "assets": [asset],
        "sources": ["web"], # Dummy source
        "keywords": ["test"],
        "scenario_config": {
            "summary_model": "gpt-4o-mini" 
        }
    }

    # 3. Run Analysis
    engine = store.init_db()
    scorer = ContentScorer()
    manager = RunManager(engine=engine, scoring_pipeline=scorer)

    logger.info("Starting analysis...")
    try:
        run = manager.run_analysis(brand_id, "repro-manual", run_config)
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return

    # 4. Inspect Results
    # We need to re-fetch or rely on eager loaded run
    # Note: run.assets might be populated if manager returns it eagerly loaded.
    
    if not run.assets:
        logger.error("No assets found in run!")
        return

    scored_asset = run.assets[0]
    scores = scored_asset.scores[0]
    
    rationale = scores.rationale or {}
    visual_result = rationale.get('visual_analysis')
    
    logger.info(f"Asset Screenshot Path: {scored_asset.screenshot_path}")
    logger.info(f"Visual Analysis Result: {visual_result}")
    
    if visual_result:
        # Check if it's an error dict or actual analysis
        if visual_result.get('error'):
             logger.warning(f"Visual analysis attempted but failed with error: {visual_result.get('error')}")
        else:
             logger.info("✅ SUCCESS (Unexpected): Visual analysis succeeded.")
    else:
        logger.error("❌ FAILURE (Reproduced): Visual Analysis is missing.")

if __name__ == "__main__":
    reproduce_issue()
