import os
import shutil
import unittest
from core.run_manager import RunManager
from data.models import ContentAsset

class TestSocialUpload(unittest.TestCase):
    def setUp(self):
        # Create a dummy screenshot file
        self.test_screenshot = "test_screenshot.png"
        with open(self.test_screenshot, "wb") as f:
            f.write(b"dummy image content")
            
        self.screenshot_path = os.path.abspath(self.test_screenshot)
        
    def tearDown(self):
        if os.path.exists(self.test_screenshot):
            os.remove(self.test_screenshot)
            
    def test_run_manager_ingests_manual_assets(self):
        """Test that RunManager correctly ingests manually provided assets with screenshot paths."""
        
        # Simulate the asset structure created in app.py
        manual_assets = [{
            "url": "https://www.linkedin.com/company/testbrand",
            "title": "Test Brand on LinkedIn (Manual Upload)",
            "source_type": "social",
            "channel": "social",
            "raw_content": "Manual upload content",
            "screenshot_path": f"file://{self.screenshot_path}",
            "visual_analysis": True,
            "meta_info": {
                "manual_upload": True,
                "platform": "LinkedIn"
            }
        }]
        
        run_config = {
            "brand_slug": "testbrand",
            "brand_name": "Test Brand",
            "assets": manual_assets,
            "sources": [], 
            "keywords": ["test"],
            "scenario_name": "Test Scenario",
            "limit": 1
        }
        
        # Initialize RunManager (using in-memory DB or temporary file would be ideal, 
        # but defaulting to standard init_db is fine for this integration test)
        manager = RunManager()
        
        # Run analysis (lightweight, no actual scoring needed to verify ingestion)
        # We can mock _score_assets or just let it run with the fallback heuristic
        run = manager.run_analysis("testbrand", "test-scenario", run_config)
        
        # Verify assets were persisted correctly
        self.assertEqual(len(run.assets), 1)
        asset = run.assets[0]
        
        print(f"Asset Source Type: {asset.source_type}")
        print(f"Asset Screenshot Path: {asset.screenshot_path}")
        print(f"Asset Meta Info: {asset.meta_info}")
        
        self.assertEqual(asset.source_type, "social")
        self.assertTrue(asset.screenshot_path.endswith(self.test_screenshot))
        self.assertTrue(asset.meta_info.get("manual_upload"))
        self.assertEqual(asset.meta_info.get("platform"), "LinkedIn")
        
        # Verify build_report_data includes it
        report_data = manager.build_report_data(run.id)
        report_items = report_data.get("items", [])
        
        # Find our item
        found = False
        for item in report_items:
            # Source type is not exposed at top level of item in build_report_data, 
            # but we can identify it by meta_info which is copied to 'meta'
            meta = item.get("meta", {})
            if meta.get("manual_upload"):
                found = True
                self.assertEqual(item.get("screenshot_path"), f"file://{self.screenshot_path}")
                break
                
        self.assertTrue(found, "Manually uploaded asset not found in report data")

if __name__ == "__main__":
    unittest.main()
