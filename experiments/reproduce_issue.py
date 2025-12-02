import os
import logging
import sys
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
env_file = find_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Found .env file at: {env_file}")
load_dotenv(env_file)

# Add the project root to the python path
sys.path.append(os.getcwd())

from ingestion.serper_search import search_serper, collect_serper_pages

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_serper_search():
    query = "procter and gamble"
    print(f"Testing Serper search for query: '{query}'")
    
    api_key = os.getenv('SERPER_API_KEY')
    if not api_key:
        print("ERROR: SERPER_API_KEY not found in environment variables.")
        return

    print(f"SERPER_API_KEY is set: {api_key[:4]}...{api_key[-4:]}")

    try:
        # Test raw search
        print("\n--- Testing search_serper (raw results) ---")
        results = search_serper(query, size=10)
        print(f"Found {len(results)} raw results.")
        for i, res in enumerate(results[:3]):
            print(f"Result {i+1}: {res.get('title')} - {res.get('url')}")

        if not results:
            print("WARNING: No raw results found.")
        
        # Test collection with page fetching
        print("\n--- Testing collect_serper_pages (fetched content) ---")
        pages = collect_serper_pages(query, target_count=5)
        print(f"Collected {len(pages)} pages.")
        for i, page in enumerate(pages[:3]):
            print(f"Page {i+1}: {page.get('title')} - {len(page.get('body', ''))} bytes")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_serper_search()
