import sys
import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, select, desc
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from data.models import ContentAsset
from ingestion.screenshot_capture import get_screenshot_capture
from config.settings import SETTINGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_pipeline():
    logger.info("--- visual_analysis_enabled: %s", SETTINGS.get('visual_analysis_enabled'))
    logger.info("--- screenshot_s3_bucket: %s", SETTINGS.get('screenshot_s3_bucket'))
    logger.info("--- report_s3_bucket: %s", SETTINGS.get('report_s3_bucket'))

    # 1. Check Database
    db_path = "sqlite:///./truststack.db"
    engine = create_engine(db_path)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get latest asset with screenshot_path
        stmt = select(ContentAsset).where(ContentAsset.screenshot_path.is_not(None)).order_by(desc(ContentAsset.created_at)).limit(1)
        asset = session.execute(stmt).scalars().first()

        if not asset:
            logger.error("NO ASSETS found with screenshot_path in DB. Capture is failing or not persisting.")
            return

        logger.info(f"Latest Asset with Screenshot: ID={asset.id}, URL={asset.url}, Path={asset.screenshot_path}")
        
        # 2. Test Archive Copy
        logger.info("Attempting test copy to report bucket...")
        capture = get_screenshot_capture()
        
        # Use existing path from DB
        src_path = asset.screenshot_path
        run_id = "debug_test_run"
        
        result_url = capture.archive_report_image(src_path, run_id)
        
        if result_url:
            logger.info(f"SUCCESS: Copied to {result_url}")
        else:
            logger.error("FAILURE: archive_report_image returned None.")
            
    except Exception as e:
        logger.error(f"Exception during debug: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    debug_pipeline()
