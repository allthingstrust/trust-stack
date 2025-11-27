
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.serper_search import collect_serper_pages
from ingestion.domain_classifier import URLCollectionConfig, URLClassification, URLSourceType
import logging

# Configure logging to stderr
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)


class TestParallelSubpageFetching(unittest.TestCase):
    @patch('ingestion.serper_search.search_serper')
    @patch('ingestion.page_fetcher.fetch_page')
    @patch('ingestion.page_fetcher.fetch_pages_parallel')
    @patch('ingestion.brave_search._extract_internal_links')
    @patch('ingestion.domain_classifier.classify_url')
    @patch('requests.get')
    def test_parallel_subpage_fetching(self, mock_get, mock_classify, mock_extract, mock_fetch_parallel, mock_fetch, mock_search):
        # Setup mocks
        
        # 1. Search returns 1 brand-owned page
        mock_search.return_value = [{'url': 'https://brand.com/home', 'title': 'Brand Home', 'snippet': 'Home'}]
        
        # 2. Classify as brand-owned
        mock_classify.return_value = URLClassification(url='https://brand.com/home', source_type=URLSourceType.BRAND_OWNED, tier=None)
        
        # 3. Fetch page returns content
        mock_fetch.return_value = {'url': 'https://brand.com/home', 'body': 'Content ' * 50, 'title': 'Brand Home'}
        
        # 4. Requests.get for subpage extraction returns 200
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>...</html>"
        mock_get.return_value = mock_resp
        
        # 5. Extract returns 5 subpages
        subpages = [f'https://brand.com/page{i}' for i in range(5)]
        mock_extract.return_value = subpages
        
        # 6. Parallel fetch returns content for subpages
        mock_fetch_parallel.return_value = [
            {'url': url, 'body': 'Subpage Content ' * 20, 'title': f'Page {i}'}
            for i, url in enumerate(subpages)
        ]
        
        # Run collection with high target to force subpage fetching
        config = URLCollectionConfig(brand_owned_ratio=1.0, third_party_ratio=0.0)
        results = collect_serper_pages(
            query="test",
            target_count=50, # Need more than the 1 search result
            url_collection_config=config
        )
        
        # Verification
        
        # Should have called search
        mock_search.assert_called_once()
        
        # Should have called extract_internal_links
        mock_extract.assert_called()
        
        # CRITICAL: Should have called fetch_pages_parallel
        mock_fetch_parallel.assert_called()
        
        # Check arguments to fetch_pages_parallel
        args, kwargs = mock_fetch_parallel.call_args
        fetched_urls = args[0]
        self.assertEqual(len(fetched_urls), 5)
        self.assertEqual(set(fetched_urls), set(subpages))
        
        # Should have collected 1 parent + 5 subpages = 6 total
        self.assertEqual(len(results), 6)
        
        print("Test passed: fetch_pages_parallel was called correctly!")

if __name__ == '__main__':
    unittest.main()
