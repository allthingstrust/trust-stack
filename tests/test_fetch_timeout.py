
import unittest
from unittest.mock import patch
import time
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.playwright_manager import get_browser_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_timeout')

class TestFetchTimeout(unittest.TestCase):
    def test_fetch_timeout(self):
        manager = get_browser_manager()
        
        # Ensure manager is started
        manager.start()
        
        # Patch _process_fetch to sleep
        original_process = manager._process_fetch
        
        def slow_process(*args, **kwargs):
            time.sleep(2)
            return original_process(*args, **kwargs)
            
        manager._process_fetch = slow_process
        
        try:
            logger.info("Testing fetch with 1s timeout (should fail)...")
            start_time = time.time()
            # Set timeout to 1s, while process takes 2s
            result = manager.fetch_page("https://example.com", "TestAgent", timeout=1)
            duration = time.time() - start_time
            
            logger.info(f"Fetch returned in {duration:.2f}s")
            
            self.assertIn("error", result)
            self.assertEqual(result["error"], "Timeout waiting for browser")
            self.assertLess(duration, 1.5) # Should be close to 1s
            
        finally:
            # Restore original method
            manager._process_fetch = original_process
            manager.close()

if __name__ == "__main__":
    unittest.main()
