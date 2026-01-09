import logging
import sys
import os
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.page_fetcher import fetch_page, _domain_config
from ingestion.playwright_manager import get_browser_manager

# Configure logging to see our "Skipping bottom" messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('verify_smart_capture')
# Quiet other loggers
logging.getLogger('ingestion.page_fetcher').setLevel(logging.INFO)
logging.getLogger('ingestion.screenshot_capture').setLevel(logging.INFO)

def verify_smart_capture():
    # Use real URLs from the user's domain to test real footer dedup
    urls = [
        "https://allthingstrust.com/",
        "https://allthingstrust.com/", # Repeat same URL to force guaranteed identical footer check (cache should hit)
        "https://allthingstrust.com/about" # Different URL, likely same footer
    ]
    
    logger.info("Starting Smart Capture Verification...")
    
    # 1. Start Browser
    manager = get_browser_manager()
    manager.start()
    
    try:
        results = []
        for i, url in enumerate(urls):
            logger.info(f"\n--- Processing URL {i+1}: {url} ---")
            
            # Add timestamp to URL if it's the 2nd one to avoid internal caching if any?
            # Actually, fetch_page might stick. Let's rely on standard flow.
            
            result = fetch_page(url, "Mozilla/5.0")
            
            # Extract visual data
            visual_data = result.get('visual_analysis') or {}
            screenshots = visual_data.get('screenshots', {})
            
            logger.info(f"Main Screenshot Path: {result.get('screenshot_path')}")
            logger.info(f"Captured Screenshots: {list(screenshots.keys())}")
            
            results.append({
                "url": url,
                "screenshots": screenshots
            })
            
            # Basic validation
            if 'top' in screenshots:
                 val = screenshots['top']
                 if val:
                     logger.info(f"Top Path: {val}")
            
            if 'bottom' in screenshots:
                 val = screenshots['bottom']
                 if val:
                     logger.info(f"Bottom Path: {val}")
                     
            time.sleep(1) 

    finally:
        manager.close()
        
    logger.info("\n=== Summary ===")
    for i, res in enumerate(results):
        keys = list(res['screenshots'].keys())
        url = res['url']
        logger.info(f"URL {i+1} ({url}): Captured {keys}")

if __name__ == "__main__":
    verify_smart_capture()
