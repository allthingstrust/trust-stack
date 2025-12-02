"""Test script for parallel Serper search"""
import time
import logging
import os

import pytest

from ingestion.serper_search import collect_serper_pages

RUN_SERPER_LIVE_TESTS = os.getenv("RUN_SERPER_LIVE_TESTS") == "1"
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
IN_CI = os.getenv("CI") == "true" or os.getenv("CI") == "1" or os.getenv("GITHUB_ACTIONS")

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_search():
    query = "Nike sustainability"
    target_count = 5
    
    print(f"Starting search for '{query}' (target: {target_count})...")
    start_time = time.time()
    
    results = collect_serper_pages(query, target_count=target_count)
    
    elapsed = time.time() - start_time
    print(f"\nSearch completed in {elapsed:.2f} seconds")
    print(f"Collected {len(results)} pages")
    
    for i, page in enumerate(results):
        print(f"{i+1}. {page.get('title', 'No Title')} ({len(page.get('body', ''))} chars)")

if __name__ == "__main__":
    if IN_CI:
        print("Skipping parallel Serper test in CI to avoid live calls.")
    elif not (SERPER_API_KEY and RUN_SERPER_LIVE_TESTS):
        print("Skipping parallel Serper test without RUN_SERPER_LIVE_TESTS=1 and SERPER_API_KEY.")
    else:
        test_search()
