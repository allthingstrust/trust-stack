#!/usr/bin/env python3
"""Test Playwright browser manager with various URLs."""
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.DEBUG)

from ingestion.playwright_manager import PlaywrightBrowserManager

# URL to test - change this to test different sites
test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.nytimes.com"

manager = PlaywrightBrowserManager()
if manager.start():
    print(f"Browser started successfully")
    print(f"Testing: {test_url}")
    result = manager.fetch_page(
        test_url,
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        timeout=35
    )
    print(f"Result: title={result.get('title', '')[:50]}, body_len={len(result.get('body', ''))}, error={result.get('error', '')}")
    manager.close()
    print("Browser closed")
else:
    print("Failed to start browser")
