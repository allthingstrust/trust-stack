"""Test script for parallel Serper search"""
import time
import logging
import os
from dotenv import load_dotenv
load_dotenv()
from ingestion.serper_search import collect_serper_pages

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
    # Ensure API key is present
    if not os.getenv('SERPER_API_KEY'):
        print("Error: SERPER_API_KEY not found in environment")
    else:
        test_search()
