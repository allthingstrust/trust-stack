
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp.utils.recommendations import get_remedy_for_issue

def test_bad_improvement_opportunity():
    print("Testing Bad Improvement Opportunity Format...")
    
    # Simulate the bad output the user is seeing
    issue_items = [
        {
            'suggestion': "EXACT QUOTE: 'Exceptional food makes the best gift, and Murray's has something special for every cheese lover and every holiday and occasion.'",
            'url': 'https://www.murrayscheese.com/lp/all-gifts',
            'title': 'Shop All Gifts | Murray\'s Cheese',
            'evidence': "EXACT QUOTE: 'Exceptional food makes the best gift, and Murray's has something special for every cheese lover and every holiday and occasion.'",
            'confidence': 0.95,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    print("\nRecommended Fix:")
    print(remedy_data['recommended_fix'])
    
    # Check if it displays the bad format
    if "1. EXACT QUOTE:" in remedy_data['recommended_fix'] and "Change '" not in remedy_data['recommended_fix']:
        print("\n❌ REPRODUCED: Displaying bare quote without explanation")
        return True
    else:
        print("\n✅ NOT REPRODUCED: Output seems okay or filtered")
        return False

if __name__ == '__main__':
    test_bad_improvement_opportunity()
