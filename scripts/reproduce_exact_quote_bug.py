
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.utils.recommendations import get_remedy_for_issue

def test_exact_quote_bug():
    print("Testing Exact Quote Bug...")
    
    # Simulate the issue reported by the user
    issue_items = [
        {
            'suggestion': "EXACT QUOTE: 'SHOP NOW HOLIDAY CHEESE CLASSES ARE IN SESSION'",
            'url': 'https://www.murrayscheese.com/',
            'title': "Murray's Cheese",
            'evidence': "EXACT QUOTE: 'SHOP NOW HOLIDAY CHEESE CLASSES ARE IN SESSION'",
            'confidence': 0.9,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    print("\nRecommended Fix:")
    print(remedy_data['recommended_fix'])
    
    # Check if it was filtered or formatted incorrectly
    if "EXACT QUOTE: 'SHOP NOW HOLIDAY CHEESE CLASSES ARE IN SESSION'" in remedy_data['recommended_fix']:
        print("\n⚠️  Reproduced: The exact quote is shown as the recommendation description.")
        # Check if it was treated as an aspect (which we suspect it is)
        # If it was treated as an aspect, it might be formatted in a specific way, 
        # but since there is no "Change '", it falls through to default description.
    else:
        print("\n✅ Not Reproduced: The exact quote was filtered or formatted differently.")

if __name__ == '__main__':
    test_exact_quote_bug()
