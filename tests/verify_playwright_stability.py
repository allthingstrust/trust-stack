
import logging
import time
import threading
import queue
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.playwright_manager import get_browser_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('stability_test')

def test_browser_stability():
    logger.info("Starting Playwright Stability Test...")
    
    manager = get_browser_manager()
    
    # URLs to fetch (safe, public URLs)
    urls = [
        "https://example.com",
        "https://www.google.com",
        "https://www.python.org",
        "https://github.com"
    ]
    
    results = []
    
    def worker(url):
        try:
            logger.info(f"Fetching {url}...")
            res = manager.fetch_page(url, "Mozilla/5.0 TestAgent")
            if res.get('error'):
                logger.error(f"Failed to fetch {url}: {res['error']}")
            else:
                logger.info(f"Successfully fetched {url} ({len(res.get('body', ''))} chars)")
            results.append(res)
        except Exception as e:
            logger.error(f"Exception fetching {url}: {e}")

    threads = []
    for url in urls:
        t = threading.Thread(target=worker, args=(url,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    logger.info(f"Fetched {len(results)} pages.")
    
    # Verify manager is still running
    if manager.is_started:
        logger.info("Manager is still running (expected).")
    else:
        logger.error("Manager stopped unexpectedly!")
        
    # Explicitly close to test clean shutdown
    logger.info("Closing manager...")
    manager.close()
    logger.info("Manager closed.")
    
    if not manager.is_started:
        logger.info("Manager shutdown verified.")
    else:
        logger.error("Manager failed to shutdown!")

if __name__ == "__main__":
    test_browser_stability()
