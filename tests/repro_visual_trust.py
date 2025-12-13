
import os
import sys
import logging
from ingestion.page_fetcher import fetch_page
from scoring.visual_analyzer import get_visual_analyzer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_visual_trust(url):
    print(f"\nTesting Visual Analysis for: {url}")
    print("-" * 50)
    
    # 1. Fetch Page & Capture Screenshot (Triggering new logic)
    # Patch SETTINGS directly since it's already imported
    from config.settings import SETTINGS
    SETTINGS['visual_analysis_enabled'] = True
    
    # Also set env var for any fresh imports or subprocesses
    os.environ['VISUAL_ANALYSIS_ENABLED'] = 'true'
    
    # We need to simulate the environment where Playwright is available
    # Assuming the environment has playwright installed.
    
    result = fetch_page(url)
    
    screenshot_path = result.get('screenshot_path')
    if not screenshot_path:
        print("❌ Screenshot capture failed or disabled.")
        return

    print(f"✅ Screenshot captured: {screenshot_path}")

    # 2. visual_analyzer.analyze (Triggering new prompt)
    analyzer = get_visual_analyzer()
    
    # Analyze needs bytes. Screenshot path might be a file URI or S3 URI.
    # For local dev, likely file://
    
    from ingestion.screenshot_capture import get_screenshot_capture
    capture = get_screenshot_capture()
    screenshot_bytes = capture.get_screenshot_bytes(screenshot_path)
    
    if not screenshot_bytes:
         print("❌ Failed to retrieve screenshot bytes.")
         return

    analysis = analyzer.analyze(screenshot_bytes, url, brand_context={"brand_name": "Test Brand"})
    
    if not analysis.success:
        print(f"❌ Analysis failed: {analysis.error}")
        return

    # 3. Check Results
    trust_signal = analysis.signals.get('vis_trust_indicators')
    if trust_signal:
        print(f"Score: {trust_signal.score}")
        print(f"Confidence: {trust_signal.confidence}")
        print(f"Evidence: {trust_signal.evidence}")
        
        if trust_signal.score > 0.6:
             print("✅ visual_analyzer detected trust indicators!")
        else:
             print("⚠️ visual_analyzer did NOT detect strong trust indicators (Score <= 0.6).")
    else:
        print("❌ 'vis_trust_indicators' signal missing from response.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Default test URL (something with a badge)
        url = "https://www.instagram.com/nike/" 
    
    verify_visual_trust(url)
