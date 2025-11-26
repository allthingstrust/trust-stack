
import sys
import os

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp.utils.recommendations import get_remedy_for_issue

def reproduce_issue():
    print("--- Reproducing Transparency Formatting Issue ---")

    # Case 1: Missing Data Source Citations (Currently Structural)
    print("\n1. Testing 'Missing Data Source Citations'...")
    issue_type_1 = "Missing Data Source Citations"
    dimension_1 = "Transparency"
    items_1 = [
        {
            "url": "https://b2b.mastercard.com/news-and-insights/success-stories/",
            "evidence": "No data source citations",
            "title": "Success Stories"
        },
        {
            "url": "https://careers.mastercard.com/us/en/search-results",
            "evidence": "No data source citations",
            "title": "Careers"
        }
    ]
    
    remedy_1 = get_remedy_for_issue(issue_type_1, dimension_1, items_1)
    print("Recommended Fix Output:")
    print(remedy_1['recommended_fix'])

    # Case 2: Data Source Citations for Claims (Standard)
    print("\n2. Testing 'Data Source Citations for Claims'...")
    issue_type_2 = "Data Source Citations for Claims"
    dimension_2 = "Transparency"
    items_2 = [
        {
            "url": "https://investor.mastercard.com/overview/default.aspx",
            "evidence": "Data claims detected but no citations provided",
            "title": "Investor Relations"
        }
    ]

    remedy_2 = get_remedy_for_issue(issue_type_2, dimension_2, items_2)
    print("Recommended Fix Output:")
    print(remedy_2['recommended_fix'])

if __name__ == "__main__":
    reproduce_issue()
