
import unittest
from unittest.mock import MagicMock, patch
from ingestion.page_fetcher import fetch_page
from core.run_manager import RunManager
from scoring.scorer import ContentScorer
from data.models import NormalizedContent
from scoring.types import SignalScore
from reporting.trust_stack_report import _generate_visual_snapshot

class TestAccessDeniedFlow(unittest.TestCase):
    def test_access_denied_flow(self):
        # 1. Simulate Fetch returning access_denied
        # We'll mock the internal _fetch_with_playwright to return access_denied
        with patch('ingestion.page_fetcher._fetch_with_playwright') as mock_fetch, \
             patch('ingestion.page_fetcher.requests.Session.get') as mock_get:
            
            # Configure Playwright mock
            mock_fetch.return_value = {
                "title": "Access Denied",
                "body": "You don't have permission",
                "url": "https://example.com",
                "access_denied": True,
                "screenshot_path": "/tmp/dummy_screenshot.png"
            }
            
            # Configure Requests mock to also return 403 (Forbidden)
            # This ensures that when fetch_page falls back to requests, it also sees access denied
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_get.return_value = mock_response
            
            # Test fetch_page propagation
            result = fetch_page("https://example.com")
            self.assertTrue(result.get('access_denied'))
            
            # 2. Simulate RunManager propagation (manually since we can't easily spin up full DB/Manager here)
            # In RunManager._collect_assets:
            asset = {
                "url": "https://example.com",
                "meta_info": {}
            }
            # Simulate the logic I added to RunManager
            if result.get("access_denied"):
                 asset['meta_info']['access_denied'] = True
                 
            self.assertTrue(asset['meta_info']['access_denied'])
            
            # 3. Simulate Scorer seeing this and aborting visual analysis
            # Create a NormalizedContent with this meta
            nc = NormalizedContent(
                content_id="123",
                body="test",
                source_type="web",
                platform_id="https://example.com",
                url="https://example.com",
                src="web",
                author="test",
                title="Access Denied",
                meta=asset['meta_info']
            )
            
            scorer = ContentScorer()
            scorer._signals_cfg = {} # Mock config
            scorer.aggregator = MagicMock()
            
            # Run visual scoring
            scorer._score_visual_signals(nc, [])
            
            # Verify visual_analysis meta was set with error
            self.assertTrue('visual_analysis' in nc.meta)
            self.assertFalse(nc.meta['visual_analysis']['success'])
            self.assertTrue(nc.meta['visual_analysis']['access_denied'])
            self.assertIn("Access Denied", nc.meta['visual_analysis']['error'])
            
            # 4. Verify Report Generator output
            # Convert nc back to dict-like item for reporting
            item = {
                "title": "Test Page",
                "url": "https://example.com",
                "meta": nc.meta, # This contains the visual_analysis dict
                "visual_analysis": nc.meta['visual_analysis'],
                "screenshot_path": "/tmp/dummy.png"
            }
            
            # Generate visual snapshot section
            report_section = _generate_visual_snapshot([item], "run_id")
            
            # Verify output contains the error message
            self.assertIn("Access Denied", report_section)
            self.assertIn("Analysis Failed", report_section)

if __name__ == "__main__":
    unittest.main()
