
import logging
import sys
import os
from ingestion.screenshot_capture import get_screenshot_capture, should_capture_screenshot
from ingestion.playwright_manager import get_browser_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('debug_screenshot')

def test_flow():
    url = "https://example.com"
    run_id = "debug_run_001"
    
    # 1. Capture
    logger.info(f"Step 1: Capturing screenshot for {url}")
    manager = get_browser_manager()
    manager.start()
    
    try:
        result = manager.fetch_page(url, "Mozilla/5.0", capture_screenshot=True)
        screenshot_path = result.get('screenshot_path')
        logger.info(f"Capture Result Path: {screenshot_path}")
        
        if not screenshot_path:
            logger.error("Screenshot capture failed to return a path.")
            return

        # 2. Simulate Report Generation Archive
        logger.info(f"Step 2: Archiving report image from {screenshot_path}")
        capture = get_screenshot_capture()
        final_path = capture.archive_report_image(screenshot_path, run_id)
        
        logger.info(f"Archive Result Path: {final_path}")
        
        if screenshot_path == final_path and "report-images" not in final_path:
             logger.warning("Archive did not change path. Copy might have failed or source/dest buckets are identical without copy logic triggering.")

    finally:
        manager.close()

if __name__ == "__main__":
    test_flow()
