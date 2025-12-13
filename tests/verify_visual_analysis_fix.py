
import unittest
from unittest.mock import MagicMock, patch
import json
from data.models import NormalizedContent, ContentScores
from scoring.scorer import ContentScorer
from core.run_manager import RunManager
from reporting.trust_stack_report import _generate_visual_snapshot

class TestVisualAnalysisFix(unittest.TestCase):
    
    def setUp(self):
        self.scorer = ContentScorer(use_attribute_detection=False)
        self.run_manager = RunManager()

    def test_visual_analysis_persistence_success(self):
        """Test that successful visual analysis is persisted by RunManager"""
        # Mock ContentScores with visual_analysis in meta
        cs = ContentScores(
            content_id="1", brand="brand", src="web", event_ts="now",
            score_provenance=0, score_resonance=0, score_coherence=0, 
            score_transparency=0, score_verification=0
        )
        cs.meta = json.dumps({
            'visual_analysis': {'success': True, 'score': 0.9},
            'dimensions': {}
        })
        
        # Test persistence extraction
        rationale = self.run_manager._extract_rationale_from_content_scores(cs)
        
        self.assertIn('visual_analysis', rationale)
        self.assertTrue(rationale['visual_analysis']['success'])
        self.assertEqual(rationale['visual_analysis']['score'], 0.9)

    def test_visual_analysis_persistence_failure(self):
        """Test that FAILED visual analysis is persisted by RunManager"""
        # Mock ContentScores with failed visual_analysis in meta
        cs = ContentScores(
            content_id="2", brand="brand", src="web", event_ts="now",
            score_provenance=0, score_resonance=0, score_coherence=0, 
            score_transparency=0, score_verification=0
        )
        cs.meta = json.dumps({
            'visual_analysis': {'success': False, 'error': 'Image too large'},
            'dimensions': {}
        })
        
        # Test persistence extraction
        rationale = self.run_manager._extract_rationale_from_content_scores(cs)
        
        self.assertIn('visual_analysis', rationale)
        self.assertFalse(rationale['visual_analysis']['success'])
        self.assertEqual(rationale['visual_analysis']['error'], 'Image too large')

    @patch('scoring.visual_analyzer.get_visual_analyzer')
    @patch('ingestion.screenshot_capture.get_screenshot_capture')
    def test_scorer_preserves_failure(self, mock_capture, mock_analyzer):
        """Test that Scorer persists failure result instead of returning early"""
        # Mock analyzer to return failure
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Mock Error"
        mock_result.to_dict.return_value = {'success': False, 'error': "Mock Error"}
        
        mock_instance = MagicMock()
        mock_instance.analyze.return_value = mock_result
        mock_analyzer.return_value = mock_instance
        
        # Mock capture
        mock_capture_instance = MagicMock()
        mock_capture_instance.get_screenshot_bytes.return_value = b"fake_bytes"
        mock_capture.return_value = mock_capture_instance
        
        content = NormalizedContent(
            content_id="123", src="web", platform_id="http://example.com",
            author="test", title="Test", body="body", screenshot_path="path/to/img.png"
        )
        signals = []
        
        # Run scoring
        self.scorer._score_visual_signals(content, signals)
        
        # Check that meta was updated despite failure
        self.assertIsNotNone(content.meta)
        self.assertIn('visual_analysis', content.meta)
        self.assertFalse(content.meta['visual_analysis']['success'])
        self.assertEqual(content.meta['visual_analysis']['error'], "Mock Error")

    def test_report_displays_error(self):
        """Test that report generator displays the error message"""
        items = [{
            'title': 'Test Page',
            'url': 'http://example.com',
            'screenshot_path': 'path.png',
            'visual_analysis': {'success': False, 'error': 'Safety Block'}
        }]
        
        # Generate snapshot
        output = _generate_visual_snapshot(items, "run_123")
        
        self.assertIn("Test Page", output)
        self.assertIn("⚠️ Analysis Failed: Safety Block", output)

if __name__ == '__main__':
    unittest.main()
