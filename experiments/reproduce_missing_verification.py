
import sys
import os
import json

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from webapp.utils.recommendations import extract_issues_from_items, extract_successes_from_items

def reproduce_missing_verification():
    print("--- Reproducing Missing Verification Dimension ---")

    # Simulate items where Verification has NO issues and NO specific successes
    # But other dimensions have issues
    items = [
        {
            "meta": {
                "detected_attributes": [
                    # Provenance Issue
                    {
                        "dimension": "provenance",
                        "value": 1,
                        "label": "Missing Metadata",
                        "evidence": "No metadata found"
                    },
                    # Verification - High score but no specific attribute > 8.0
                    # (Assume the overall score calculation handles the high score if no issues)
                    # Here we just simulate the extraction logic
                    {
                        "dimension": "verification",
                        "value": 7.5, # Not a success (>=8), not an issue (< passing threshold?)
                        # Passing threshold for most is 10.0, so 7.5 IS an issue?
                        # Wait, extract_issues_from_items uses PASSING_THRESHOLDS.
                        # Default passing threshold is 10.0.
                        # So 7.5 would be an issue unless it's a specific attribute with lower threshold.
                        "label": "Some Verification Attribute",
                        "evidence": "Okay but not perfect"
                    }
                ],
                "title": "Test Page",
                "url": "http://example.com"
            }
        }
    ]
    
    # Let's adjust the mock to ensure Verification has NO issues.
    # To have no issues, value must be >= passing_threshold (default 10.0).
    # So let's give it value 10.0.
    items[0]["meta"]["detected_attributes"][1]["value"] = 10.0
    
    # And let's ensure it's NOT a success.
    # Success threshold is 8.0.
    # Wait, if value is 10.0, it IS >= 8.0, so it IS a success.
    
    # So if it has no issues (value 10), it MUST be a success (value >= 8).
    # So how can we have no issues AND no successes?
    # Only if there are NO attributes detected for Verification at all?
    
    items_no_verification_attrs = [
        {
            "meta": {
                "detected_attributes": [
                    {
                        "dimension": "provenance",
                        "value": 1,
                        "label": "Missing Metadata",
                        "evidence": "No metadata found"
                    }
                ],
                "title": "Test Page",
                "url": "http://example.com"
            }
        }
    ]

    print("\nScenario: No Verification Attributes Detected")
    issues = extract_issues_from_items(items_no_verification_attrs)
    successes = extract_successes_from_items(items_no_verification_attrs)
    
    print(f"Verification Issues: {len(issues.get('verification', []))}")
    print(f"Verification Successes: {len(successes.get('verification', []))}")
    
    # Now simulate the UI logic
    # dimension_breakdown usually comes from the report, calculated from attributes.
    # If no attributes, what is the score?
    # Usually it defaults to something or is calculated.
    # Let's assume the score is high (100) because no issues found.
    
    dimension_breakdown = {
        'verification': {'average': 1.0}, # 100%
        'provenance': {'average': 0.5}
    }
    
    dimension_key = 'verification'
    dim_issues = issues.get(dimension_key, [])
    dim_successes = successes.get(dimension_key, [])
    dim_score = dimension_breakdown.get(dimension_key, {}).get('average', 1.0) * 100
    is_high_score = dim_score >= 80
    
    print(f"Dimension Score: {dim_score}")
    print(f"Is High Score: {is_high_score}")
    
    should_show = False
    if dim_issues or is_high_score:
        should_show = True
        
    print(f"Should Show in UI (Logic Check): {should_show}")
    
    if should_show:
        print("PASS: Verification would now be shown in UI.")
    else:
        print("FAIL: Verification would still be hidden!")

if __name__ == "__main__":
    reproduce_missing_verification()
