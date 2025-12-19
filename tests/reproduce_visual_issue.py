
import os
import sys
import logging
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO)

from config.settings import SETTINGS
from scoring.scorer import ContentScorer
from data.models import NormalizedContent
from scoring.types import SignalScore

# Enable visual analysis
SETTINGS['visual_analysis_enabled'] = True

def reproduce():
    # Path to the uploaded image
    image_path = "/Users/andrewdeutsch/.gemini/antigravity/brain/1ab0b9eb-e957-4466-87f3-9c512bfefb40/uploaded_image_1766155093281.png"
    
    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        return

    # Mock content
    content = NormalizedContent(
        content_id="test_visual_analysis",
        src="company_website",
        platform_id="test_platform",
        author="test_author",
        title="Costco Wholesale Corporation - Investor Relations",
        body="Test body",
        url="https://investor.costco.com/overview/default.aspx",
        event_ts="2023-10-27T10:00:00Z"
    )
    content.screenshot_path = f"file://{image_path}"
    content.meta = {}

    print(f"Testing visual analysis for: {content.url}")
    print(f"Screenshot path: {content.screenshot_path}")

    scorer = ContentScorer(use_attribute_detection=False)
    
    # Mock get_screenshot_capture to return bytes from file directly
    # This avoids setting up the actual screenshot capture infrastructure (Playwright etc)
    # which might not be needed if we just want to test the analyzer part.
    # However, Scorer uses `get_screenshot_capture().get_screenshot_bytes(path)`
    # The default implementation likely reads from file if local path.
    # Let's check `ingestion/screenshot_capture.py` first? 
    # Actually, I'll just rely on `_score_visual_signals` calling `get_screenshot_capture`.
    # If that fails, I'll know.
    
    signals = []
    scorer._score_visual_signals(content, signals)
    
    print("\n--- Results ---")
    if 'visual_analysis' in content.meta:
        va = content.meta['visual_analysis']
        print(f"Success: {va.get('success')}")
        print(f"Error: {va.get('error')}")
        print(f"Signals in metadata: {len(va.get('signals', {}))}")
    else:
        print("No 'visual_analysis' in metadata!")

    print(f"\nGenerated Signals ({len(signals)}):")
    for s in signals:
        print(f"- {s.id}: {s.value} (Confidence: {s.confidence})")

if __name__ == "__main__":
    reproduce()
