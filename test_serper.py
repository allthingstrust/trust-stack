
import os
import sys
import logging
from ingestion.serper_search import search_serper, get_serper_stats
from config.settings import get_secret

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_search():
    print("Checking SERPER_API_KEY...")
    key = get_secret('SERPER_API_KEY')
    if key:
        print(f"Key found: {key[:5]}...{key[-5:]}")
    else:
        print("ERROR: SERPER_API_KEY not found in settings/env")
        return

    print("\nChecking Search Stats...")
    stats = get_serper_stats()
    print(f"Stats: {stats}")

    query = "All Things Trust (site:allthingstrust.com OR site:investors.allthingstrust.com OR site:products.allthingstrust.com OR site:careers.allthingstrust.com OR site:news.allthingstrust.com OR site:developer.allthingstrust.com OR site:intl.allthingstrust.com OR site:allthingstrust.co.uk OR site:allthingstrust.com.au OR site:allthingstrust.eu)"
    print(f"\nRunning Test Search for '{query}'...")
    try:
        results = search_serper(query, size=5)
        print(f"Found {len(results)} results")
        for i, res in enumerate(results):
            print(f"{i+1}. {res['title']} ({res['url']})")
            
        if not results:
            print("WARNING: No results returned.")
            
    except Exception as e:
        print(f"ERROR executing search: {e}")

if __name__ == "__main__":
    test_search()
