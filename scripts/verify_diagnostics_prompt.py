
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reporting.trust_stack_report import generate_trust_stack_report

def test_prompt_generation():
    # Mock data
    report_data = {
        'brand_id': 'Test Brand',
        'generated_at': '2025-12-03',
        'dimension_breakdown': {
            'provenance': {'average': 0.8},
            'resonance': {'average': 0.7},
            'coherence': {'average': 0.9},
            'transparency': {'average': 0.6},
            'verification': {'average': 0.5}
        },
        'items': [],
        'sources': ['web']
    }

    # Mock ChatClient to capture prompt
    with patch('reporting.trust_stack_report.ChatClient') as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.return_value = {'content': 'Mock Analysis'}
        
        generate_trust_stack_report(report_data)
        
        # Check calls
        print(f"Total calls to chat: {mock_instance.chat.call_count}")
        
        # Inspect the prompt for 'coherence' dimension (index 2 in the loop of 5 dims)
        # The order is ['provenance', 'resonance', 'coherence', 'transparency', 'verification']
        # So coherence is the 3rd call (index 2)
        
        if mock_instance.chat.call_count >= 3:
            call_args = mock_instance.chat.call_args_list[2]
            prompt = call_args[1]['messages'][0]['content']
            
            print("\n--- Generated Prompt for Coherence ---")
            print(prompt)
            
            # Verify specific metrics are present
            expected_metrics = [
                "Content Narrative Alignment",
                "Audience Engagement Clarity",
                "Brand Messaging Consistency",
                "Product Relevance Connection",
                "Overall Content Cohesion"
            ]
            
            missing = [m for m in expected_metrics if m not in prompt]
            if missing:
                print(f"\n❌ FAILED: Missing metrics in prompt: {missing}")
            else:
                print("\n✅ SUCCESS: All expected metrics found in prompt.")
                
            # Verify table instruction
            if "Score each of the following specific metrics on a 1/10 scale" in prompt:
                print("✅ SUCCESS: Table instruction found.")
            else:
                print("❌ FAILED: Table instruction missing.")

if __name__ == "__main__":
    test_prompt_generation()
