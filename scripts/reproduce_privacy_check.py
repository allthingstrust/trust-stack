import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.page_fetcher import fetch_page

def check_privacy(url):
    print(f"Fetching {url}...")
    result = fetch_page(url)
    
    print(f"\n[Privacy] {result.get('privacy')}")
    print(f"[Terms] {result.get('terms')}")
    
    if result.get('privacy'):
        print("[SUCCESS] Privacy policy detected.")
    else:
        print("[FAILURE] Privacy policy NOT detected.")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://allthingstrust.com"
    check_privacy(url)
