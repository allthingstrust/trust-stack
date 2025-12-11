"""
Tests for screenshot capture module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os


class TestScreenshotCapture:
    """Test suite for screenshot_capture.py"""

    def test_import_module(self):
        """Verify module can be imported."""
        from ingestion.screenshot_capture import (
            ScreenshotCapture,
            should_capture_screenshot,
            get_screenshot_capture,
            VIEWPORT_DESKTOP,
            VIEWPORT_MOBILE,
        )
        assert ScreenshotCapture is not None
        assert VIEWPORT_DESKTOP == {"width": 1920, "height": 1080}
        assert VIEWPORT_MOBILE == {"width": 375, "height": 812}

    def test_should_capture_screenshot_brand_owned(self):
        """Brand-owned content should always trigger visual analysis."""
        from ingestion.screenshot_capture import should_capture_screenshot
        
        assert should_capture_screenshot("landing_page", "brand_owned") is True
        assert should_capture_screenshot("blog", "brand_owned") is True
        assert should_capture_screenshot("other", "brand_owned") is True

    def test_should_capture_screenshot_landing_page(self):
        """Landing pages should trigger visual analysis regardless of source."""
        from ingestion.screenshot_capture import should_capture_screenshot
        
        # Landing pages in the scope
        assert should_capture_screenshot("landing_page", "third_party") is True

    def test_should_capture_screenshot_third_party_excluded(self):
        """Third-party non-landing content should NOT trigger visual analysis."""
        from ingestion.screenshot_capture import should_capture_screenshot
        
        # Third party content types not in scope
        assert should_capture_screenshot("blog", "third_party") is False
        assert should_capture_screenshot("article", "third_party") is False
        assert should_capture_screenshot("social_post", "user_generated") is False

    def test_screenshot_capture_init(self):
        """Test ScreenshotCapture initialization."""
        from ingestion.screenshot_capture import ScreenshotCapture
        
        capture = ScreenshotCapture(
            s3_bucket="test-bucket",
            s3_prefix="test-prefix/",
            retention_hours=48,
        )
        
        assert capture.s3_bucket == "test-bucket"
        assert capture.s3_prefix == "test-prefix/"
        assert capture.retention_hours == 48

    def test_capture_screenshot_no_playwright(self):
        """Test graceful handling when Playwright not available."""
        from ingestion.screenshot_capture import ScreenshotCapture
        
        capture = ScreenshotCapture()
        
        # Passing None as page should return empty result
        screenshot_bytes, metadata = capture.capture_screenshot(
            page=None,
            url="https://example.com",
        )
        
        assert screenshot_bytes == b""
        assert "error" in metadata or metadata.get("success") is False

    @patch('ingestion.screenshot_capture._BOTO3_AVAILABLE', False)
    def test_upload_to_s3_no_boto(self):
        """Test S3 upload gracefully fails when boto3 not available."""
        from ingestion.screenshot_capture import ScreenshotCapture
        
        capture = ScreenshotCapture(s3_bucket="test-bucket")
        
        result = capture.upload_to_s3(
            screenshot_bytes=b"fake_png_data",
            url="https://example.com/page",
            run_id="test_run_123",
        )
        
        assert result is None

    def test_get_screenshot_capture_singleton(self):
        """Test singleton instance behavior."""
        from ingestion.screenshot_capture import get_screenshot_capture
        
        instance1 = get_screenshot_capture()
        instance2 = get_screenshot_capture()
        
        assert instance1 is instance2


class TestVisualAnalyzer:
    """Test suite for visual_analyzer.py"""

    def test_import_module(self):
        """Verify module can be imported."""
        from scoring.visual_analyzer import (
            VisualAnalyzer,
            VisualAnalysisResult,
            VisualSignal,
            get_visual_analyzer,
        )
        assert VisualAnalyzer is not None
        assert VisualAnalysisResult is not None
        assert VisualSignal is not None

    def test_visual_signal_dataclass(self):
        """Test VisualSignal dataclass."""
        from scoring.visual_analyzer import VisualSignal
        
        signal = VisualSignal(
            signal_id="vis_design_quality",
            label="Design Quality",
            score=0.85,
            confidence=0.9,
            evidence="Good typography and spacing",
            issues=["Minor contrast issue"],
        )
        
        assert signal.signal_id == "vis_design_quality"
        assert signal.score == 0.85
        assert signal.confidence == 0.9
        assert len(signal.issues) == 1

    def test_visual_analysis_result_to_dict(self):
        """Test VisualAnalysisResult serialization."""
        from scoring.visual_analyzer import VisualAnalysisResult, VisualSignal
        
        result = VisualAnalysisResult(
            url="https://example.com",
            success=True,
            signals={
                "vis_design_quality": VisualSignal(
                    signal_id="vis_design_quality",
                    label="Design Quality",
                    score=0.8,
                    confidence=0.9,
                    evidence="Professional design",
                )
            },
            dark_patterns=[
                {"type": "urgency", "severity": "low", "description": "Mild urgency"}
            ],
            design_assessment="Good overall design",
            overall_visual_score=0.75,
            model="gemini-2.0-flash",
        )
        
        d = result.to_dict()
        
        assert d["url"] == "https://example.com"
        assert d["success"] is True
        assert "vis_design_quality" in d["signals"]
        assert d["signals"]["vis_design_quality"]["score"] == 0.8
        assert len(d["dark_patterns"]) == 1
        assert d["overall_visual_score"] == 0.75

    def test_analyzer_no_screenshot(self):
        """Test analyzer handles missing screenshot gracefully."""
        from scoring.visual_analyzer import VisualAnalyzer
        
        analyzer = VisualAnalyzer(model="gemini-2.0-flash")
        
        result = analyzer.analyze(
            screenshot_bytes=b"",
            url="https://example.com",
        )
        
        assert result.success is False
        assert "No screenshot" in result.error

    def test_analyzer_no_api_key(self):
        """Test analyzer handles missing API key gracefully."""
        from scoring.visual_analyzer import VisualAnalyzer
        
        # Create analyzer without API key
        analyzer = VisualAnalyzer(model="gemini-2.0-flash", api_key=None)
        # Clear environment variable too
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=False):
            analyzer.api_key = None
            result = analyzer.analyze(
                screenshot_bytes=b"fake_png_data",
                url="https://example.com",
            )
        
            # Should fail gracefully
            assert result.success is False
            assert "API key" in result.error or "not configured" in result.error.lower()

    @patch('scoring.visual_analyzer.GOOGLE_AVAILABLE', True)
    @patch('scoring.visual_analyzer.genai')
    def test_analyzer_parse_response(self, mock_genai):
        """Test response parsing from Gemini."""
        from scoring.visual_analyzer import VisualAnalyzer
        
        # Mock the Gemini response
        mock_response = Mock()
        mock_response.text = '''
        {
            "signals": {
                "vis_design_quality": {
                    "score": 0.85,
                    "confidence": 0.9,
                    "evidence": "Professional typography",
                    "issues": []
                },
                "vis_dark_patterns": {
                    "score": 0.95,
                    "confidence": 0.95,
                    "evidence": "No dark patterns detected",
                    "issues": []
                }
            },
            "dark_patterns_detected": [],
            "design_assessment": "Clean, professional design",
            "overall_visual_score": 0.88
        }
        '''
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        analyzer = VisualAnalyzer(model="gemini-2.0-flash", api_key="test-key")
        
        result = analyzer._parse_response(mock_response.text, "https://example.com")
        
        assert result.success is True
        assert "vis_design_quality" in result.signals
        assert result.signals["vis_design_quality"].score == 0.85
        assert result.overall_visual_score == 0.88

    def test_analyzer_parse_response_invalid_json(self):
        """Test response parsing handles invalid JSON."""
        from scoring.visual_analyzer import VisualAnalyzer
        
        analyzer = VisualAnalyzer(model="gemini-2.0-flash")
        
        result = analyzer._parse_response("not valid json", "https://example.com")
        
        assert result.success is False
        assert "Failed to parse" in result.error


class TestTrustSignalsConfig:
    """Test that visual signals are properly configured."""

    def test_visual_signals_in_config(self):
        """Verify visual signals are defined in trust_signals.yml."""
        import yaml
        
        with open("scoring/config/trust_signals.yml", "r") as f:
            config = yaml.safe_load(f)
        
        signals = config.get("signals", {})
        
        # Check all visual signals exist
        visual_signal_ids = [
            "vis_design_quality",
            "vis_dark_patterns",
            "vis_brand_coherence",
            "vis_accessibility",
            "vis_trust_indicators",
            "vis_clutter_score",
        ]
        
        for signal_id in visual_signal_ids:
            assert signal_id in signals, f"Missing visual signal: {signal_id}"
            assert signals[signal_id]["detection"] == "visual"

    def test_dark_patterns_is_knockout(self):
        """Verify vis_dark_patterns is configured as knockout signal."""
        import yaml
        
        with open("scoring/config/trust_signals.yml", "r") as f:
            config = yaml.safe_load(f)
        
        dark_patterns = config["signals"]["vis_dark_patterns"]
        
        assert dark_patterns["knockout_flag"] is True
        assert dark_patterns["knockout_threshold_norm"] == 0.30
        assert dark_patterns["dimension"] == "Transparency"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
