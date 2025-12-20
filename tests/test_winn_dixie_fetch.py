
import os
import sys
import logging
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from ingestion.playwright_manager import get_browser_manager

def test_winn_dixie_fetch():
    urls_to_test = ["https://www.winndixie.com", "https://winndixie.com"]
    
    manager = get_browser_manager()
    if not manager.start():
        logger.error("Failed to start browser manager")
        return

    for url in urls_to_test:
        logger.info(f"Testing fetch for: {url}")
        try:
            # Increase timeout for this specific test if needed, but we want to see if it fails with defaults first
            # default timeout in playwright_manager is 20s
            logger.info("Attemping fetch...")
            start_time = time.time()
            result = manager.fetch_page(url, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", capture_screenshot=True)
            duration = time.time() - start_time
            
            logger.info(f"Fetch completed in {duration:.2f}s")
            logger.info(f"Title: {result.get('title')}")
            logger.info(f"Body length: {len(result.get('body', ''))}")
            logger.info(f"Screenshot path: {result.get('screenshot_path')}")
            
            if result.get('screenshot_path'):
                logger.info("✅ Screenshot captured successfully")
                break # Stop if successful
            else:
                logger.error("❌ Screenshot NOT captured")
                
            if result.get('access_denied'):
                logger.warning("⚠️ Access Denied detected")

        except Exception as e:
            logger.error(f"❌ Fetch failed for {url}: {e}")
            
    manager.close()

if __name__ == "__main__":
    test_winn_dixie_fetch()
