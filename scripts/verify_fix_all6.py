
import sys
import os
import logging
from pathlib import Path
from sqlalchemy import create_engine
from core.run_manager import RunManager
from data.models import ContentAsset
from dotenv import load_dotenv

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify():
    load_dotenv()
    
    # Connect to DB
    engine = create_engine("sqlite:///./truststack.db")
    manager = RunManager(engine=engine)
    
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        from data import models
        # Find a run that has assets with screenshots
        # query runs, fetch assets
        runs = session.query(models.Run).order_by(models.Run.started_at.desc()).limit(5).all()
        
        target_run = None
        for r in runs:
            # Check if any asset in this run has a screenshot
            has_screenshot = False
            for asset in r.assets:
                if asset.screenshot_path:
                    has_screenshot = True
                    break
            if has_screenshot:
                target_run = r
                break
        
        if not target_run:
            logger.error("No recent runs found with screenshots. Cannot verify visual analysis extraction.")
            return

        logger.info(f"Verifying Run: {target_run.id} ({target_run.brand.name if target_run.brand else 'Unknown'})")
        
        # 2. Call build_report_data
        report_data = manager.build_report_data(target_run.id)
        
        # 3. Check for visual_analysis in items
        found_visual = False
        items_with_screenshot = 0
        items_with_screenshot_path_in_item = 0
        
        for item in report_data['items']:
            if item.get('screenshot_path'):
                items_with_screenshot_path_in_item += 1
                
                # Check directly in the item
                if item.get('visual_analysis'):
                    found_visual = True
                    logger.info(f"✅ Found visual_analysis for item {item['id']}")
                    logger.info(f"   Visual Score: {item['visual_analysis'].get('overall_visual_score')}")
                    break
        
        if items_with_screenshot_path_in_item > 0:
            if found_visual:
                logger.info("VERIFICATION SUCCESSFUL: Visual analysis data is being extracted.")
            else:
                logger.warning(f"Found {items_with_screenshot_path_in_item} items with screenshots but NO visual_analysis data in report.")
                logger.warning("Check if 'visual_analysis' was actually populated in the database for these assets.")
                
                # Double check DB directly to differentiate between "extraction failed" and "data missing"
                asset_id = item['id']
                asset = session.query(models.ContentAsset).get(asset_id) # Last item
                score = asset.scores[0] if asset.scores else None
                if score and score.rationale:
                    import json
                    r = score.rationale
                    if isinstance(r, str):
                        r = json.loads(r)
                    if r.get('visual_analysis'):
                         logger.error("❌ DATA EXSISTS in DB but was NOT extracted!")
                    else:
                         logger.warning("⚠️ Data is missing in DB 'rationale' column, so extraction correctly returned None.")
        else:
             logger.warning("Run has assets with screenshots in DB, but report_data items don't have screenshot_path?")

    finally:
        session.close()

if __name__ == "__main__":
    verify()
