
import unittest
from unittest.mock import patch, MagicMock
import time
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.serper_search import collect_serper_pages

# Configure logging
logging.basicConfig(level=logging.INFO)

class TestConcurrentSearch(unittest.TestCase):
    
    @patch('ingestion.playwright_manager.PlaywrightBrowserManager')
    @patch('ingestion.serper_search.search_serper')
    @patch('ingestion.page_fetcher.fetch_page')
    def test_concurrent_collection(self, mock_fetch, mock_search, mock_browser_manager):
        # Setup mocks
        
        # Mock search to return batches of results
        def search_side_effect(query, size=10, start_page=1):
            results = []
            start_idx = (start_page - 1) * 10
            for i in range(size):
                idx = start_idx + i
                results.append({
                    'title': f'Result {idx}',
                    'url': f'http://example{idx}.com/page',
                    'snippet': 'snippet'
                })
            return results
        
        mock_search.side_effect = search_side_effect
        
        # Mock fetch to simulate latency
        def fetch_side_effect(url, **kwargs):
            time.sleep(0.1) # Simulate network delay
            return {
                'title': 'Test Page',
                'body': 'This is a test page with enough content to pass the filter.' * 10,
                'url': url
            }
        
        mock_fetch.side_effect = fetch_side_effect
        
        # Run collection
        start_time = time.time()
        target_count = 20
        results = collect_serper_pages("test query", target_count=target_count)
        duration = time.time() - start_time
        
        # Verify
        self.assertEqual(len(results), target_count)
        
        # Check performance
        # If sequential: 20 pages * 0.1s = 2.0s + search overhead
        # If parallel (5 workers): 20 pages / 5 = 4 batches * 0.1s = 0.4s + overhead
        # We expect duration < 1.5s
        print(f"Collected {len(results)} pages in {duration:.2f}s")
        self.assertLess(duration, 1.5, "Concurrent collection should be faster than sequential")
        
        # Verify search was called
        self.assertTrue(mock_search.called)
        
    @patch('ingestion.playwright_manager.PlaywrightBrowserManager')
    @patch('ingestion.page_fetcher.fetch_page')
    @patch('ingestion.serper_search.search_serper')
    def test_concurrent_collection_with_failures(self, mock_search, mock_fetch, mock_browser_manager):
        # Setup mocks
        
        # Mock search
        mock_search.return_value = [{'url': f'http://example{i}.com/page'} for i in range(50)]
        
        # Mock fetch to fail for half the pages (thin content)
        def fetch_side_effect(url, **kwargs):
            time.sleep(0.01)
            # Fail even numbered domains
            import re
            match = re.search(r'example(\d+)', url)
            idx = int(match.group(1)) if match else 0
            
            if idx % 2 == 0:
                return {'body': 'short', 'url': url} # Fail
            return {'body': 'long content ' * 50, 'url': url} # Pass
            
        mock_fetch.side_effect = fetch_side_effect
        
        target_count = 10
        results = collect_serper_pages("test query", target_count=target_count)
        
        self.assertEqual(len(results), target_count)
        # Should have fetched at least 20 pages to get 10 valid ones
        self.assertGreaterEqual(mock_fetch.call_count, 20)

if __name__ == '__main__':
    unittest.main()
