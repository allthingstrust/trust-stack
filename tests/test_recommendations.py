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


def test_filtered_suggestions_show_urls():
    """Verify that items with filtered suggestions still show their URLs in fallback."""
    
    # Create items with suggestions that will be filtered out (low confidence)
    issue_items = [
        {
            'title': 'Page with Missing Privacy Policy',
            'url': 'https://example.com/page1',
            'evidence': 'No privacy policy link found',
            'language': 'en',
            'issue': 'missing_privacy_policy',
            'suggestion': 'Add a privacy policy link',  # Has suggestion
            'confidence': 0.5  # Low confidence - will be filtered
        },
        {
            'title': 'Another Page Missing Privacy Policy',
            'url': 'https://example.com/page2',
            'evidence': 'No privacy policy link found',
            'language': 'en',
            'issue': 'missing_privacy_policy',
            'suggestion': 'Add a privacy policy link',  # Has suggestion
            'confidence': 0.6  # Low confidence - will be filtered
        }
    ]
    
    # Call the function
    result = get_remedy_for_issue(
        issue_type='Missing Privacy Policy',
        dimension='transparency',
        issue_items=issue_items
    )
    
    # Assertions
    # Even though suggestions were filtered, URLs should still appear
    assert 'https://example.com/page1' in result, "URL 1 missing from result"
    assert 'https://example.com/page2' in result, "URL 2 missing from result"
    
    # Should NOT show the generic fallback
    assert "Review content for this issue" not in result
