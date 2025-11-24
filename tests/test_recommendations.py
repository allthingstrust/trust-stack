import pytest
from webapp.utils.recommendations import get_remedy_for_issue

def test_get_remedy_for_issue_no_truncation():
    """Verify that all issue items are displayed and no truncation message appears."""
    
    # Create 5 dummy issue items (more than the previous default of 3)
    issue_items = []
    for i in range(5):
        issue_items.append({
            'title': f'Page {i}',
            'url': f'https://example.com/{i}',
            'evidence': f'Issue evidence {i}',
            'language': 'en'
        })
        
    # Call the function
    result = get_remedy_for_issue(
        issue_type='Generic Issue',
        dimension='transparency',
        issue_items=issue_items
    )
    
    # Assertions
    # 1. Check that all 5 URLs are present in the output
    for i in range(5):
        assert f'https://example.com/{i}' in result, f"URL {i} missing from result"
        
    # 2. Check that the truncation message is NOT present
    assert "...and" not in result
    assert "more instance" not in result
