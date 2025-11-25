
import sys
import os
import json

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp.utils.recommendations import extract_issues_from_items

def reproduce():
    # Mock item as produced by scorer.py
    # Note: scorer.py uses "id" for the attribute ID in the meta.detected_attributes list
    mock_item = {
        "meta": {
            "title": "Test Page",
            "url": "https://example.com",
            "detected_attributes": [
                {
                    "id": "author_brand_identity_verified", # This is how scorer.py saves it
                    "dimension": "provenance",
                    "label": "Author/Brand Identity Verified",
                    "value": 7.0,
                    "evidence": "Author attribution present: web",
                    "confidence": 0.85
                }
            ]
        }
    }

    print("Testing extract_issues_from_items with score 7.0...")
    issues = extract_issues_from_items([mock_item])
    
    provenance_issues = issues.get('provenance', [])
    found = False
    for issue in provenance_issues:
        if issue['issue'] == "Author/Brand Identity Verified":
            found = True
            print("ISSUE FOUND: Author/Brand Identity Verified was flagged as an issue.")
            print(f"Value: {issue['value']}")
            print("This confirms the bug (7.0 should pass because threshold is 6.0).")
            break
            
    if not found:
        print("ISSUE NOT FOUND: Author/Brand Identity Verified was NOT flagged.")
        print("This means the fix is working (or the test is wrong).")

if __name__ == "__main__":
    reproduce()
