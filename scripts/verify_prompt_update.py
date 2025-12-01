
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring.key_signal_evaluator import KeySignalEvaluator

def test_prompt_generation():
    evaluator = KeySignalEvaluator()
    
    # Mock items with specific details
    items = [
        {
            'meta': {
                'title': 'About Us',
                'source_url': 'https://example.com/about',
                'detected_attributes': [
                    {'dimension': 'provenance', 'label': 'Author Identity', 'value': 8}
                ]
            }
        },
        {
            'meta': {
                'title': 'Blog Post by Jane Doe',
                'source_url': 'https://example.com/blog/post1',
                'detected_attributes': [
                    {'dimension': 'provenance', 'label': 'Author Identity', 'value': 10}
                ]
            }
        }
    ]
    
    # Generate prompt
    context = evaluator._prepare_context_for_signal(items, 'provenance', 'Authorship & Attribution')
    prompt = evaluator._create_signal_evaluation_prompt(
        dimension='provenance',
        signal_name='Authorship & Attribution',
        context=context,
        dimension_score=0.85
    )
    
    print("\n--- Generated Prompt ---\n")
    print(prompt)
    print("\n------------------------\n")
    
    # Check for key phrases
    if "CRITICAL: You MUST include concrete details" in prompt:
        print("✅ Prompt contains specific instructions for details.")
    else:
        print("❌ Prompt missing specific instructions.")

    if "Direct quotes" in prompt or "direct quotes" in prompt:
        print("✅ Prompt requests direct quotes.")
    else:
        print("❌ Prompt missing quote request.")

if __name__ == "__main__":
    test_prompt_generation()
