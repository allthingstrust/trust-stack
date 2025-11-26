
import sys
import os
import json

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from webapp.utils.recommendations import extract_issues_from_items, get_remedy_for_issue

def reproduce_verification_remedy():
    print("--- Reproducing Verification Remedy Issue ---")

    # Simulate an item with a verification issue
    # We use the ID 'claim_to_source_traceability' and see what happens
    # We assume the label might be 'Claim-to-source traceability' or 'Claim traceability'
    
    # Scenario 1: Old Label
    items_old = [
        {
            "meta": {
                "detected_attributes": [
                    {
                        "dimension": "verification",
                        "value": 1,
                        "label": "Claim-to-source traceability",
                        "id": "claim_to_source_traceability",
                        "evidence": "No citations found"
                    }
                ],
                "title": "Page 1",
                "url": "http://example.com/1"
            }
        }
    ]

    print("\nScenario 1: Old Label 'Claim-to-source traceability'")
    issues_old = extract_issues_from_items(items_old)
    verification_issues_old = issues_old.get('verification', [])
    if verification_issues_old:
        issue_type = verification_issues_old[0]['issue']
        print(f"Extracted Issue Type: {issue_type}")
        remedy = get_remedy_for_issue(issue_type, 'verification', verification_issues_old)
        print(f"Remedy Found: {bool(remedy.get('recommended_fix'))}")
        print(f"General Practice: {bool(remedy.get('general_best_practice'))}")
        print(f"Remedy Content: {remedy}")
    else:
        print("No issues extracted.")

    # Scenario 2: New Label
    items_new = [
        {
            "meta": {
                "detected_attributes": [
                    {
                        "dimension": "verification",
                        "value": 1,
                        "label": "Claim traceability",
                        "id": "claim_to_source_traceability",
                        "evidence": "No citations found"
                    }
                ],
                "title": "Page 2",
                "url": "http://example.com/2"
            }
        }
    ]

    print("\nScenario 2: New Label 'Claim traceability'")
    issues_new = extract_issues_from_items(items_new)
    verification_issues_new = issues_new.get('verification', [])
    if verification_issues_new:
        issue_type = verification_issues_new[0]['issue']
        print(f"Extracted Issue Type: {issue_type}")
        remedy = get_remedy_for_issue(issue_type, 'verification', verification_issues_new)
        print(f"Remedy Found: {bool(remedy.get('recommended_fix'))}")
        print(f"General Practice: {bool(remedy.get('general_best_practice'))}")
        print(f"Remedy Content: {remedy}")
    else:
        print("No issues extracted.")

if __name__ == "__main__":
    reproduce_verification_remedy()
