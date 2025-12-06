import logging
import sys
import time
from ingestion.playwright_manager import get_browser_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_browser_lifecycle():
    logger.info("Starting browser manager...")
    manager = get_browser_manager()
    
    if not manager.start():
        logger.error("Failed to start browser manager")
        return
        
    logger.info("Browser manager started. Fetching a page...")
    
    # Fetch a simple page (example.com)
    result = manager.fetch_page("https://example.com", "Mozilla/5.0")
    
    if result.get("error"):
        logger.error(f"Fetch failed: {result.get('error')}")
    else:
        logger.info(f"Fetch successful: {result.get('title')}")
        
    logger.info("Closing browser manager...")
    manager.close()
    logger.info("Browser manager closed.")

if __name__ == "__main__":
    test_browser_lifecycle()
    logger.info("Exiting main thread.")
