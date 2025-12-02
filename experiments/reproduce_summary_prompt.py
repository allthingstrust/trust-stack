
import sys
import os
import logging
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock matplotlib before importing reporting modules
sys.modules['matplotlib'] = MagicMock()
sys.modules['matplotlib.pyplot'] = MagicMock()
sys.modules['matplotlib.use'] = MagicMock()
sys.modules['plotly'] = MagicMock()
sys.modules['plotly.express'] = MagicMock()
sys.modules['plotly.graph_objects'] = MagicMock()
sys.modules['plotly.subplots'] = MagicMock()
sys.modules['boto3'] = MagicMock()
sys.modules['botocore'] = MagicMock()
sys.modules['botocore.exceptions'] = MagicMock()

from reporting.executive_summary import _generate_llm_summary

# Mock the ChatClient to capture the prompt
class MockChatClient:
    def chat(self, messages, **kwargs):
        # Return the prompt so we can inspect it
        return {'content': messages[0]['content']}

def test_prompt_generation():
    # Setup mock data
    avg_rating = 75.0
    dimension_breakdown = {
        'provenance': {'average': 0.7},
        'verification': {'average': 0.8},
        'transparency': {'average': 0.6},
        'coherence': {'average': 0.9},
        'resonance': {'average': 0.75}
    }
    
    # Create 7 items, but generate 10 issues across them
    items = []
    for i in range(7):
        items.append({
            'title': f'Item {i}',
            'final_score': 0.7,
            'meta': {
                'url': f'http://example.com/{i}',
                'detected_attributes': [
                    # Add some issues
                    {'dimension': 'transparency', 'label': 'Missing Data Source Citations', 'value': 0, 'attribute_id': 'missing_data_source_citations'},
                    # Add a second issue to some items to create the "more issues than items" scenario
                    {'dimension': 'transparency', 'label': 'No AI Disclosure', 'value': 0, 'attribute_id': 'no_ai_disclosure'} if i < 3 else {}
                ]
            }
        })
        
    sources = ['web']
    
    # Patch ChatClient
    with patch('scoring.llm_client.ChatClient', MockChatClient):
        # Generate summary (which will actually return the prompt due to our mock)
        prompt = _generate_llm_summary(avg_rating, dimension_breakdown, items, sources, model='test')
        
        print("\n--- Generated Prompt Snippet (Transparency Section) ---")
        # Find the transparency section in the prompt
        if "Transparency:" in prompt:
            start = prompt.find("Transparency:")
            end = prompt.find("\n", start)
            print(prompt[start:end])
        else:
            print("Transparency section not found in prompt")
            
        print("\n--- Full Prompt for Inspection ---")
        # Print relevant parts of the prompt
        print(prompt)

if __name__ == "__main__":
    test_prompt_generation()
