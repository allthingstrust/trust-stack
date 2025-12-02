
import sys
import os
import json

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from webapp.utils.recommendations import extract_successes_from_items

def reproduce_success_extraction():
    print("--- Reproducing Success Extraction ---")

    # Simulate items with high-scoring attributes
    items = [
        {
            "meta": {
                "detected_attributes": [
                    {
                        "dimension": "provenance",
                        "value": 10,
                        "label": "Author/Brand Identity Verified",
                        "id": "author_brand_identity_verified",
                        "evidence": "Byline found: John Doe"
                    },
                    {
                        "dimension": "provenance",
                        "value": 5,
                        "label": "Some Low Score Attribute",
                        "id": "low_score_attr",
                        "evidence": "Not good"
                    }
                ],
                "title": "High Quality Page",
                "url": "http://example.com/high"
            },
            "applied_rules": [
                {
                    "dimension": "provenance",
                    "value": 10,
                    "label": "Schema Compliance",
                    "reason": "Valid JSON-LD found"
                }
            ]
        }
    ]

    print("Extracting successes...")
    successes = extract_successes_from_items(items)
    
    provenance_successes = successes.get('provenance', [])
    print(f"Found {len(provenance_successes)} provenance successes.")
    
    for s in provenance_successes:
        print(f" - {s['success']} (Value: {s['value']})")
        
    # Verification
    expected_successes = ["Author/Brand Identity Verified", "Schema Compliance"]
    found_successes = [s['success'] for s in provenance_successes]
    
    if all(expected in found_successes for expected in expected_successes):
        print("SUCCESS: All expected successes found.")
    else:
        print(f"FAIL: Expected {expected_successes}, found {found_successes}")

if __name__ == "__main__":
    reproduce_success_extraction()
