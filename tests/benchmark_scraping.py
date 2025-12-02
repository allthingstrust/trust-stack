
import time
import logging
import os

import pytest

from ingestion.serper_search import collect_serper_pages
from ingestion.page_fetcher import DomainConfigCache

RUN_SERPER_LIVE_TESTS = os.getenv("RUN_SERPER_LIVE_TESTS") == "1"
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
IN_CI = os.getenv("CI") == "true" or os.getenv("CI") == "1" or os.getenv("GITHUB_ACTIONS")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('benchmark')

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        IN_CI,
        reason="Skipped in CI to avoid live Serper calls",
    ),
    pytest.mark.skipif(
        not (SERPER_API_KEY and RUN_SERPER_LIVE_TESTS),
        reason="Requires RUN_SERPER_LIVE_TESTS=1 and SERPER_API_KEY for live Serper calls",
    ),
]

def run_benchmark():
    if IN_CI:
        logger.info("Skipping benchmark in CI to avoid live Serper calls.")
        return

    if not (SERPER_API_KEY and RUN_SERPER_LIVE_TESTS):
        logger.info("Skipping benchmark without RUN_SERPER_LIVE_TESTS=1 and SERPER_API_KEY.")
        return

    queries = [
        "latest sustainable fashion trends 2024",
        "nike sustainability report 2023", # Known to have some tricky pages
        "patagonia supply chain transparency"
    ]
    
    target_count = 5
    
    logger.info("Starting scraping benchmark...")
    logger.info(f"Queries: {queries}")
    logger.info(f"Target count per query: {target_count}")
    
    total_start_time = time.time()
    total_pages = 0
    
    domain_cache = DomainConfigCache.get_instance()
    
    for query in queries:
        logger.info(f"--- Processing query: {query} ---")
        query_start_time = time.time()
        
        try:
            results = collect_serper_pages(query, target_count=target_count)
            duration = time.time() - query_start_time
            count = len(results)
            total_pages += count
            
            logger.info(f"Query '{query}' finished in {duration:.2f}s. Collected {count} pages.")
            
        except Exception as e:
            logger.error(f"Query '{query}' failed: {e}")
            
    total_duration = time.time() - total_start_time
    
    logger.info("--- Benchmark Summary ---")
    logger.info(f"Total Duration: {total_duration:.2f}s")
    logger.info(f"Total Pages Collected: {total_pages}")
    if total_pages > 0:
        logger.info(f"Average Time per Page: {total_duration / total_pages:.2f}s")
    
    # Check DomainConfigCache
    # We can't easily inspect the private dict, but we can check if it's being used by checking logs or 
    # if we had a way to peek. For now, we rely on the fact that it ran without errors.
    # To verify Smart Fallback, we'd need to hit a domain twice.
    
    # Let's try to hit a domain that might have been marked as requiring Playwright
    # This is a bit speculative without knowing exactly what was marked.
    
    logger.info("Benchmark completed.")

if __name__ == "__main__":
    run_benchmark()
