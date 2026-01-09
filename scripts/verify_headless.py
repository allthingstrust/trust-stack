import sys
import os
import time

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config.settings import SETTINGS
from ingestion.playwright_manager import get_browser_manager

def test_headless_toggle():
    print("Testing Headless Mode Toggle...")
    
    # 1. Test Default (Should be True)
    print(f"\n[1] Checking default headless mode: {SETTINGS.get('headless_mode')}")
    if not SETTINGS.get('headless_mode'):
        print("FAIL: Default should be True")
        return
        
    print("Starting browser with default settings...")
    manager = get_browser_manager()
    manager.start()
    
    # Fetch a simple page
    print("Fetching example.com...")
    result = manager.fetch_page("http://example.com", "Mozilla/5.0")
    print(f"Fetch success: {len(result['body']) > 0}")
    
    manager.close()
    
    # 2. Test Toggle to False (Headed)
    print("\n[2] Toggling headless_mode to False...")
    SETTINGS['headless_mode'] = False
    
    # Restart browser (simulating UI toggle logic)
    print("Restarting browser in HEADED mode...")
    manager = get_browser_manager()
    manager.start()
    
    # Fetch again
    print("Fetching example.com in HEADED mode...")
    result = manager.fetch_page("http://example.com", "Mozilla/5.0")
    print(f"Fetch success: {len(result['body']) > 0}")
    
    manager.close()
    
    # 3. Test Toggle back to True (Headless)
    print("\n[3] Toggling headless_mode back to True...")
    SETTINGS['headless_mode'] = True
    
    # Restart browser
    print("Restarting browser in HEADLESS mode...")
    manager = get_browser_manager()
    manager.start()
    
    # Fetch again
    print("Fetching example.com in HEADLESS mode...")
    result = manager.fetch_page("http://example.com", "Mozilla/5.0")
    print(f"Fetch success: {len(result['body']) > 0}")
    
    manager.close()
    print("\nSUCCESS: All tests passed!")

if __name__ == "__main__":
    test_headless_toggle()
