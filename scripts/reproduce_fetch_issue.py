
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.page_fetcher import fetch_page

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from ingestion.playwright_manager import get_browser_manager

def test_fetch_nike():
    # Initialize browser manager
    browser_manager = get_browser_manager()
    if not browser_manager.start():
        print("❌ Failed to start browser manager")
        return

    urls = ["https://www.nike.com", "https://careers.nike.com"]
    
    for url in urls:
        print(f"Fetching {url} with browser_manager...")
        
        # Pass browser_manager
        result = fetch_page(url, browser_manager=browser_manager)
        
        print(f"\n--- Fetch Result for {url} ---")
        print(f"Title: '{result.get('title')}'")
        print(f"Body Length: {len(result.get('body', ''))}")
        print("--------------------")
        
        if not result.get('title'):
            print("❌ Title is missing!")
        else:
            print("✅ Title found.")

        if len(result.get('body', '')) < 200:
            print("⚠️ Body is thin.")
            print(f"Body Content: {result.get('body', '')}")
        else:
            print("✅ Body seems substantial.")
        print("\n")
    
    # Clean up
    browser_manager.close()

if __name__ == "__main__":
    test_fetch_nike()
