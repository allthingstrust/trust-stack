
import unittest
from reporting.trust_stack_report import _generate_visual_snapshot

class TestVisualScoreReporting(unittest.TestCase):
    
    def test_visual_scores_populated(self):
        """Test that Visual Score fields are correctly populated in the report snapshot."""
        
        # simulated "existing data" structure matches what comes from db/normalizer
        items = [{
            'title': 'Test Page Success',
            'url': 'http://example.com/success',
            'screenshot_path': '/tmp/screenshot.png',
            'visual_analysis': {
                'success': True,
                'overall_visual_score': 0.88,
                'signals': {
                    'vis_design_quality': {'score': 0.85},
                    'vis_brand_coherence': {'score': 0.92},
                    'vis_dark_patterns': {'score': 0.95},
                    'vis_trust_indicators': {'score': 0.70}
                },
                'design_assessment': 'Excellent design with high brand coherence.'
            }
        }]
        
        # Generate the snapshot section
        output = _generate_visual_snapshot(items, "run_test_123")
        
        print("\n--- Generated Output ---")
        print(output)
        print("------------------------\n")
        
        # Verify the section header
        self.assertIn("🎨 **Visual Analysis Snapshot**", output)
        
        # Verify the item title and URL
        self.assertIn("**Test Page Success**", output)
        self.assertIn("URL: http://example.com/success", output)
        
        # Verify specific Visual Score fields
        # Note: Code formats as float(val)*10 :.1f
        # 0.85 -> 8.5
        # 0.92 -> 9.2
        # 0.95 -> 9.5
        self.assertIn("Design Quality: 8.5/10", output)
        self.assertIn("Brand Coherence: 9.2/10", output)
        self.assertIn("Dark Pattern Prevention: 9.5/10", output)
        
        # Verify design assessment
        self.assertIn("Excellent design with high brand coherence.", output)

    def test_visual_scores_partial_data(self):
        """Test partial visual analysis data."""
        items = [{
            'title': 'Partial Data Page',
            'url': 'http://example.com/partial',
            'screenshot_path': '/tmp/screenshot2.png',
            'visual_analysis': {
                'success': True,
                # Missing signals
                 'signals': {
                    'vis_design_quality': {'score': 0.4},
                    # brand coherence missing
                    # dark patterns missing
                },
                'design_assessment': 'Poor design.'
            }
        }]

        output = _generate_visual_snapshot(items, "run_test_456")
        
        print("\n--- Generated Output (Partial) ---")
        print(output)
        print("----------------------------------\n")

        self.assertIn("Design Quality: 4.0/10", output)
        # Should NOT contain others
        self.assertNotIn("Brand Coherence:", output)
        self.assertNotIn("Dark Patterns Risk:", output)

if __name__ == '__main__':
    unittest.main()
