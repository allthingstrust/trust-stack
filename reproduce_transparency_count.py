
import json
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from webapp.utils.recommendations import extract_issues_from_items

def reproduce_discrepancy():
    # Create 4 items
    # 3 items with low score (< 0.60)
    # 1 item with high score (>= 0.60)
    # All 4 items have a Transparency issue
    
    items = []
    
    # 3 Low scoring items
    for i in range(3):
        items.append({
            'final_score': 0.5,
            'meta': {
                'title': f'Low Score Item {i}',
                'source_url': f'http://example.com/low/{i}',
                'detected_attributes': [
                    {
                        'dimension': 'transparency',
                        'label': 'AI-Generated/Assisted Disclosure Present',
                        'value': 0, # Low value = issue
                        'evidence': 'No disclosure found'
                    }
                ]
            }
        })
        
    # 1 High scoring item (but still has the issue)
    items.append({
        'final_score': 0.7,
        'meta': {
            'title': 'High Score Item',
            'source_url': 'http://example.com/high',
            'detected_attributes': [
                {
                    'dimension': 'transparency',
                    'label': 'AI-Generated/Assisted Disclosure Present',
                    'value': 0, # Low value = issue
                    'evidence': 'No disclosure found'
                }
            ]
        }
    })
    
    # 1. Check extract_issues_from_items count
    dimension_issues = extract_issues_from_items(items)
    transparency_issues = dimension_issues.get('transparency', [])
    print(f"Total Transparency Issues Found: {len(transparency_issues)}")
    
    # 2. Check what the LLM prompt logic sees
    # Logic from reporting/executive_summary.py
    low_scoring_items = sorted(
        [item for item in items if item.get('final_score', 1.0) < 0.60],
        key=lambda x: x.get('final_score', 0)
    )[:5]
    
    print(f"Items passed to LLM as 'PROBLEMATIC CONTENT EXAMPLES': {len(low_scoring_items)}")
    for item in low_scoring_items:
        print(f" - {item['meta']['title']} (Score: {item['final_score']})")
        
    if len(transparency_issues) == 4 and len(low_scoring_items) == 3:
        print("\nSUCCESS: Reproduction confirmed.")
        print("The detailed list shows 4 issues, but the LLM only sees 3 problematic items.")
        print("This explains why the LLM might write 'three out of four' in the summary.")
    else:
        print("\nFAILURE: Could not reproduce the discrepancy.")

if __name__ == "__main__":
    reproduce_discrepancy()
