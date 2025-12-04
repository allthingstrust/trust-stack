
import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.getcwd())

from ingestion.page_fetcher import fetch_page
from ingestion.brave_search import collect_brave_pages

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fetch():
    url = "https://www.nike.com"
    logger.info(f"Testing fetch_page for {url}")
    result = fetch_page(url)
    logger.info(f"Title: {result.get('title')}")
    logger.info(f"Body length: {len(result.get('body', ''))}")
    logger.info(f"Body snippet: {result.get('body', '')[:200]}")
    
    if not result.get('body'):
        logger.warning("Body is empty!")

def test_collect():
    query = "nike"
    logger.info(f"Testing collect_brave_pages for query '{query}'")
    results = collect_brave_pages(query, target_count=3)
    for i, res in enumerate(results):
        logger.info(f"Result {i+1}:")
        logger.info(f"  URL: {res.get('url')}")
        logger.info(f"  Title: {res.get('title')}")
        logger.info(f"  Body length: {len(res.get('body', ''))}")
        logger.info(f"  Snippet: {res.get('snippet')}")
        
        if not res.get('body'):
             logger.warning("  Body is empty!")

if __name__ == "__main__":
    test_fetch()
    print("-" * 50)
    test_collect()
