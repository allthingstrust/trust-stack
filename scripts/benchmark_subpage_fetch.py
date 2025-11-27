
import time
import logging
import os
import sys
from urllib.parse import urlparse

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.serper_search import collect_serper_pages
from ingestion.domain_classifier import URLCollectionConfig
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def benchmark_subpage_fetching():
    # Mocking or using a real query that triggers subpage fetching
    # We need a query that returns brand-owned pages which then trigger subpage extraction.
    # "nike running shoes" is a good candidate as nike.com is likely to be brand-owned.
    
    query = "nike running shoes"
    target_count = 5
    
    # Configure to force brand-owned collection
    config = URLCollectionConfig(
        brand_owned_ratio=1.0, # Force 100% brand owned to trigger subpage logic
        third_party_ratio=0.0
    )
    
    logger.info(f"Starting benchmark for query: '{query}'")
    start_time = time.time()
    
    results = collect_serper_pages(
        query=query,
        target_count=target_count,
        url_collection_config=config
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    logger.info(f"Benchmark completed in {duration:.2f} seconds")
    logger.info(f"Collected {len(results)} pages")
    for res in results:
        logger.info(f" - {res.get('url')} ({res.get('source_type')}, {res.get('source_tier')})")

if __name__ == "__main__":
    benchmark_subpage_fetching()
