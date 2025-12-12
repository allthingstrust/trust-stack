import pytest
from unittest.mock import MagicMock, patch
from scoring.visual_analyzer import VisualAnalyzer

class TestVisualAnalyzerCost:
    """Tests for VisualAnalyzer cost recording."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton instance before each test."""
        from scoring.visual_analyzer import _VISUAL_ANALYZER
        _VISUAL_ANALYZER = None
        
        # Reset cost tracker singleton
        from scoring.cost_tracker import CostTracker
        CostTracker._instance = None
        
        yield
        
        _VISUAL_ANALYZER = None
        CostTracker._instance = None

    @patch('scoring.visual_analyzer.genai.GenerativeModel')
    def test_visual_analysis_records_cost(self, mock_model_cls):
        """Test that visual analysis records cost correctly."""
        from scoring.cost_tracker import CostTracker
        
        # Setup mocks
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        
        # Create a mock response with usage metadata
        mock_response = MagicMock()
        mock_response.text = '{"signals": {}}'
        mock_response.usage_metadata = MagicMock(
            prompt_token_count=100,
            candidates_token_count=50
        )
        mock_model.generate_content.return_value = mock_response
        
        # Create cost tracker instance
        tracker = CostTracker()
        
        # Initialize analyzer with a specific model and fake API key
        analyzer = VisualAnalyzer(model="gemini-2.0-flash", api_key="fake_key")
        
        # Patch cost_tracker global at source
        with patch('scoring.cost_tracker.cost_tracker', tracker):
            # Run analysis
            analyzer.analyze(b"fake_image_bytes", "http://example.com")
            
            # Verify usage was recorded
            summary = tracker.get_summary()
            assert "gemini-2.0-flash" in summary["models"]
            assert summary["models"]["gemini-2.0-flash"]["prompt_tokens"] == 100
            assert summary["models"]["gemini-2.0-flash"]["completion_tokens"] == 50

    @patch('scoring.visual_analyzer.genai.GenerativeModel')
    def test_visual_analysis_records_estimated_cost_fallback(self, mock_model_cls):
        """Test fallback cost estimation when usage metadata is missing."""
        from scoring.cost_tracker import CostTracker
        
        # Setup mocks
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        
        # Response WITHOUT usage metadata
        mock_response = MagicMock()
        mock_response.text = '{"signals": {}}'
        mock_response.usage_metadata = None  # Missing usage
        mock_model.generate_content.return_value = mock_response
        
        tracker = CostTracker()
        analyzer = VisualAnalyzer(model="gemini-2.0-flash", api_key="fake_key")
        
        with patch('scoring.cost_tracker.cost_tracker', tracker):
            analyzer.analyze(b"fake_image_bytes", "http://example.com")
            
            # Verify usage was recorded (fallback values)
            summary = tracker.get_summary()
            assert "gemini-2.0-flash" in summary["models"]
            # Fallback logic: 258 (image) + len(prompt)//4
            assert summary["models"]["gemini-2.0-flash"]["prompt_tokens"] > 258
            assert summary["models"]["gemini-2.0-flash"]["completion_tokens"] > 0
