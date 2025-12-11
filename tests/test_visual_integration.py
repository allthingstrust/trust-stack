"""
Integration test for Visual Analysis System.
Verifies the flow from page fetching -> screenshot capture -> persistence -> scoring.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import classes to test
from ingestion.page_fetcher import fetch_page
from scoring.scorer import ContentScorer
from data.models import NormalizedContent
from scoring.visual_analyzer import VisualAnalysisResult, VisualSignal

class TestVisualIntegration:
    
    @pytest.fixture
    def mock_capture(self):
        with patch('ingestion.page_fetcher.get_screenshot_capture') as mock_get:
            mock_capture = Mock()
            mock_capture.capture_above_fold.return_value = (b"fake_png_data", {"success": True})
            mock_capture.upload_to_s3.return_value = "s3://bucket/test.png"
            mock_capture.get_screenshot_bytes.return_value = b"fake_png_data"
            mock_get.return_value = mock_capture
            yield mock_capture

    @pytest.fixture
    def mock_analyzer(self):
        # Patch where it is defined, as scorer imports it locally
        with patch('scoring.visual_analyzer.get_visual_analyzer') as mock_get:
            mock_analyzer = Mock()
            
            # Mock successful analysis result
            result = VisualAnalysisResult(
                url="https://example.com",
                success=True,
                signals={
                    "vis_design_quality": VisualSignal("vis_design_quality", "Design Quality", 0.9, 0.8, "High quality"),
                    "vis_dark_patterns": VisualSignal("vis_dark_patterns", "Dark Patterns", 0.9, 0.9, "No dark patterns"),
                },
                overall_visual_score=0.9
            )
            mock_analyzer.analyze.return_value = result
            mock_get.return_value = mock_analyzer
            yield mock_analyzer

    @patch('ingestion.page_fetcher.should_use_playwright')
    @patch('ingestion.page_fetcher._PLAYWRIGHT_AVAILABLE', True)
    def test_fetch_triggering_capture(self, mock_should_pw, mock_capture):
        """Test that fetching a landing page triggers screenshot capture when enabled."""
        
        # Enable visual analysis via SETTINGS dict patch
        with patch.dict('config.settings.SETTINGS', {'visual_analysis_enabled': True}):
            # Test URL that looks like a landing page
            url = "https://example.com/"
            
            # Mock browser manager 
            mock_bm = Mock()
            mock_bm.is_started = True
            mock_bm.fetch_page.return_value = {
                "title": "Title", 
                "body": "Body", 
                "url": url, 
                "screenshot_path": "s3://bucket/test.png"
            }
            
            # Call fetch_page WITH the mock browser manager
            result = fetch_page(url, browser_manager=mock_bm)
            
            # Verify valid result
            assert result['screenshot_path'] == "s3://bucket/test.png"
            
            # Verify fetch_page was called with capture_screenshot=True
            # This confirms logic in page_fetcher.py correctly computed capture_needed based on SETTINGS
            mock_bm.fetch_page.assert_called_once()
            call_args = mock_bm.fetch_page.call_args
            assert call_args.kwargs.get('capture_screenshot') is True

    @patch('ingestion.screenshot_capture.get_screenshot_capture')
    def test_scoring_with_visual_analysis(self, mock_get_capture, mock_analyzer):
        """Test ContentScorer calls visual analysis when screenshot is present."""
        
        # Enable visual analysis via SETTINGS dict patch
        with patch.dict('config.settings.SETTINGS', {'visual_analysis_enabled': True}):
            
            # Mock screenshot capture getting bytes
            mock_capture = Mock()
            mock_capture.get_screenshot_bytes.return_value = b"bytes"
            mock_get_capture.return_value = mock_capture
            
            # Create content with screenshot path (as propagated from fetcher)
            content = NormalizedContent(
                content_id="test_id",
                url="https://example.com",
                title="Test",
                body="Test body content.",
                src="web",
                platform_id="web",
                author="unknown",
                screenshot_path="s3://bucket/test.png"
            )
            
            scorer = ContentScorer()
            
            # Spy on _score_visual_signals or just mock other steps
            with patch.object(scorer, '_score_provenance', return_value=(0.5, 1.0)), \
                 patch.object(scorer, '_score_verification', return_value=(0.5, 1.0)), \
                 patch.object(scorer, '_score_transparency', return_value=(0.5, 1.0)), \
                 patch.object(scorer, '_score_coherence', return_value=(0.5, 1.0)), \
                 patch.object(scorer, '_score_resonance', return_value=(0.5, 1.0)):
                 
                 trust_score = scorer.score_content(content, {"keywords": []})
                 
                 # Verify analyzer called
                 mock_analyzer.analyze.assert_called_once()
                 
                 # Verify signals added to aggregator logic (check if visual signals in score)
                 # Since we mocked analyzer to return result, they should be in the content structure 
                 # or accessible.
                 assert 'visual_analysis' in content.meta
                 assert content.meta['visual_analysis']['success'] is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
