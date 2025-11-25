
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from webapp.utils.recommendations import extract_issues_from_items

def test_readability_threshold():
    # Create a mock item with readability score of 7.0
    item = {
        'meta': {
            'title': 'Test Content',
            'url': 'http://example.com',
            'detected_attributes': [
                {
                    'attribute_id': 'readability_grade_level_fit',
                    'dimension': 'resonance',
                    'label': 'Readability Grade Level Fit',
                    'value': 7.0,
                    'evidence': 'Acceptable: 25.2 words/sentence',
                    'confidence': 0.7
                }
            ]
        }
    }

    # Extract issues
    issues = extract_issues_from_items([item])

    # Check if readability is flagged as an issue
    resonance_issues = issues.get('resonance', [])
    readability_issues = [i for i in resonance_issues if i['issue'] == 'Readability Grade Level Fit']

    if not readability_issues:
        print("SUCCESS: Readability score of 7.0 was NOT flagged as an issue.")
    else:
        print("FAILURE: Readability score of 7.0 WAS flagged as an issue.")
        print(json.dumps(readability_issues, indent=2))

if __name__ == "__main__":
    test_readability_threshold()
