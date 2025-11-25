
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from webapp.utils.recommendations import get_remedy_for_issue

# Configure logging to see debug output
logging.basicConfig(level=logging.DEBUG)

def test_recommendation_filtering():
    print("Testing Recommendation Filtering...")
    
    # Sample issue items that might be filtered
    issue_items = [
        {
            'title': 'Test Page 1',
            'url': 'https://example.com/1',
            'evidence': 'Claim: "We are the best."',
            'suggestion': 'Remove this claim as it is unsubstantiated.',
            'confidence': 0.9,
            'language': 'en'
        },
        {
            'title': 'Test Page 2',
            'url': 'https://example.com/2',
            'evidence': 'Passive voice detected.',
            'suggestion': 'Change "Mistakes were made" -> "We made mistakes"',
            'confidence': 0.85,
            'language': 'en'
        },
        {
            'title': 'Test Page 3',
            'url': 'https://example.com/3',
            'evidence': 'Complex sentence.',
            'suggestion': 'Simplify the sentence structure.',
            'confidence': 0.9,
            'language': 'en'
        }
    ]
    
    print("\n--- Input Items ---")
    for item in issue_items:
        print(f"- {item['suggestion']}")
        
    print("\n--- Generated Output ---")
    output = get_remedy_for_issue('Coherence', 'coherence', issue_items)
    print(f"Recommended Fix:\n{output['recommended_fix']}")
    print(f"\nGeneral Best Practice:\n{output['general_best_practice']}")

if __name__ == "__main__":
    test_recommendation_filtering()
