
import os
import time
import logging
from ingestion.playwright_manager import get_browser_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_headless():
    # Force HEADLESS_MODE to true
    os.environ['HEADLESS_MODE'] = 'true'
    
    manager = get_browser_manager()
    try:
        logger.info("Starting browser manager with HEADLESS_MODE=true...")
        success = manager.start()
        if not success:
            logger.error("Failed to start browser manager")
            return
            
        logger.info("Browser manager started. Fetching example.com...")
        result = manager.fetch_page("https://example.com", "Mozilla/5.0")
        
        if result.get('error'):
            logger.error(f"Fetch failed: {result.get('error')}")
        else:
            logger.info(f"Fetch successful! Title: {result.get('title')}")
            logger.info("If you didn't see a browser window, New Headless mode is working.")
            
    finally:
        manager.close()

if __name__ == "__main__":
    verify_headless()
