
import unittest
from unittest.mock import MagicMock, patch
import json
import logging
import sys

# Configure logging to show everything
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

from core.run_manager import RunManager

class TestRunManagerIngestion(unittest.TestCase):
    @patch('ingestion.page_fetcher.fetch_pages_parallel')
    @patch('ingestion.playwright_manager.get_browser_manager')
    def test_collect_assets_extracts_metadata(self, mock_get_browser_manager, mock_fetch_pages):
        # Setup mocks
        mock_browser_manager = MagicMock()
        mock_get_browser_manager.return_value = mock_browser_manager
        
        # Mock HTML with JSON-LD
        html_content = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Test Article",
                    "author": {
                        "@type": "Person",
                        "name": "Validation Author"
                    }
                }
                </script>
            </head>
            <body>
                <h1>Test Article</h1>
                <p>This is the body content.</p>
            </body>
        </html>
        """
        
        # Mock fetch result
        mock_fetch_pages.return_value = [{
            "url": "https://example.com/test",
            "html": html_content,
            "body": "Test Article\nThis is the body content.",
            "title": "Test Article",
            "screenshot_path": "/tmp/screenshot.png"
        }]
        
        # Initialize RunManager (no engine needed if we don't use DB features in this test path)
        manager = RunManager(engine=MagicMock(), settings={})
        
        # Config to trigger asset fetch
        run_config = {
            "assets": [
                {"url": "https://example.com/test"} 
            ],
            # Ensure we don't try to use smart reuse (DB)
            "reuse_data": False
        }
        
        # Run collection
        assets = manager._collect_assets(run_config)
        
        
        # Verify fetch was called
        mock_fetch_pages.assert_called()
        
        # Assertions
        self.assertEqual(len(assets), 1)
        asset = assets[0]
        
        print("\nCollected Asset Meta Info:")
        print(json.dumps(asset.get("meta_info", {}), indent=2))
        
        # Check if schema_org was extracted
        meta_info = asset.get("meta_info", {})
        self.assertIn("schema_org", meta_info)
        
        # parse schema_org content
        schema_data = json.loads(meta_info["schema_org"])
        json_ld = schema_data.get("json_ld", [])
        
        found_author = False
        if json_ld:
            for item in json_ld:
                if item.get("author", {}).get("name") == "Validation Author":
                    found_author = True
                    break
        
        self.assertTrue(found_author, "Could not find 'Validation Author' in extracted schema data")
        print("\nSUCCESS: 'Validation Author' found in extracted metadata!")

if __name__ == '__main__':
    unittest.main(buffer=False)
