
import sys
import os
import json

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp.utils.recommendations import extract_issues_from_items

def reproduce_consolidation():
    print("--- Reproducing Issue Consolidation ---")

    # Simulate items with different issue labels for the same underlying problem
    items = [
        {
            "meta": {
                "detected_attributes": [
                    {
                        "dimension": "transparency",
                        "value": 1,
                        "label": "Missing Data Source Citations",
                        "id": "missing_data_source_citations",
                        "evidence": "No citations found"
                    }
                ],
                "title": "Page 1",
                "url": "http://example.com/1"
            }
        },
        {
            "meta": {
                "detected_attributes": [
                    {
                        "dimension": "transparency",
                        "value": 1,
                        "label": "Data Source Citations for Claims",
                        "id": "data_source_citations_for_claims",
                        "evidence": "Claims without citations"
                    }
                ],
                "title": "Page 2",
                "url": "http://example.com/2"
            }
        }
    ]

    print("Extracting issues...")
    issues = extract_issues_from_items(items)
    
    transparency_issues = issues.get('transparency', [])
    print(f"Found {len(transparency_issues)} transparency issues.")
    
    issue_labels = [i['issue'] for i in transparency_issues]
    print(f"Issue labels: {issue_labels}")
    
    if len(set(issue_labels)) > 1:
        print("FAIL: Issues are NOT consolidated.")
    else:
        print("SUCCESS: Issues are consolidated.")

if __name__ == "__main__":
    reproduce_consolidation()
