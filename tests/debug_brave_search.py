
import logging
import os
import sys
from typing import List, Dict

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.brave_search import search_brave

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('debug_brave')

def run_debug():
    query = "latest sustainable fashion trends 2024"
    logger.info(f"Testing search_brave with query: {query}")
    
    try:
        results = search_brave(query, size=10, start_offset=0)
        logger.info(f"Results found: {len(results)}")
        for i, res in enumerate(results):
            logger.info(f"Result {i+1}: {res.get('title')} - {res.get('url')}")
            
    except Exception as e:
        logger.error(f"Search failed: {e}")

if __name__ == "__main__":
    run_debug()
