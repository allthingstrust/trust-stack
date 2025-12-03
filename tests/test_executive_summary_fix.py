
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

# Mock matplotlib to avoid import error
sys.modules['matplotlib'] = MagicMock()
sys.modules['matplotlib.pyplot'] = MagicMock()

# Mock plotly and its submodules
plotly_mock = MagicMock()
sys.modules['plotly'] = plotly_mock
sys.modules['plotly.express'] = MagicMock()
sys.modules['plotly.graph_objects'] = MagicMock()
sys.modules['plotly.subplots'] = MagicMock()

# Mock boto3
sys.modules['boto3'] = MagicMock()

from reporting.executive_summary import generate_executive_summary

class TestExecutiveSummaryFix(unittest.TestCase):
    @patch('scoring.llm_client.ChatClient')
    def test_prompt_contains_issue_counts(self, MockChatClient):
        # Setup mock
        mock_client_instance = MockChatClient.return_value
        mock_client_instance.chat.return_value = {'content': 'Summary'}
        
        # Create data that reproduces the discrepancy
        # 3 items with low score (< 0.60)
        # 1 item with high score (>= 0.60)
        # All 4 items have a Transparency issue
        items = []
        for i in range(3):
            items.append({
                'final_score': 0.5,
                'meta': {
                    'title': f'Low Score Item {i}',
                    'source_url': f'http://example.com/low/{i}',
                    'detected_attributes': [
                        {
                            'dimension': 'transparency',
                            'label': 'AI-Generated/Assisted Disclosure Present',
                            'value': 0,
                            'evidence': 'No disclosure found'
                        }
                    ]
                }
            })
        
        items.append({
            'final_score': 0.7,
            'meta': {
                'title': 'High Score Item',
                'source_url': 'http://example.com/high',
                'detected_attributes': [
                    {
                        'dimension': 'transparency',
                        'label': 'AI-Generated/Assisted Disclosure Present',
                        'value': 0,
                        'evidence': 'No disclosure found'
                    }
                ]
            }
        })
        
        dimension_breakdown = {
            'transparency': {'average': 0.55},
            'provenance': {'average': 0.8},
            'verification': {'average': 0.8},
            'coherence': {'average': 0.8},
            'resonance': {'average': 0.8}
        }
        
        # Run generation
        generate_executive_summary(
            avg_rating=70.0,
            dimension_breakdown=dimension_breakdown,
            items=items,
            sources=['web'],
            use_llm=True
        )
        
        # Verify prompt content
        call_args = mock_client_instance.chat.call_args
        if not call_args:
            self.fail("ChatClient.chat was not called")
            
        kwargs = call_args[1]
        messages = kwargs.get('messages', [])
        prompt = messages[0]['content']
        
        print("\nChecking Prompt Content...")
        
        # Check for the new section
        self.assertIn("DIMENSION ISSUE COUNTS", prompt)
        
        # Check for the correct count
        # Should say "Transparency: 4 specific issues found"
        # The exact string might vary slightly based on formatting, but "Transparency: 4" is key
        print(f"DEBUG: prompt content:\n{prompt}")
        self.assertTrue("Transparency: 4 specific issues detected" in prompt or "Transparency: 4 issues detected" in prompt)
        
        print("SUCCESS: Prompt contains 'Transparency: 4 specific issues found'")

if __name__ == '__main__':
    unittest.main()
