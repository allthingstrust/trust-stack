import pytest
from webapp.utils.recommendations import get_remedy_for_issue


def test_vocabulary_issue_with_problem_description():
    """Verify that vocabulary issues display problem descriptions explaining why text is problematic."""
    
    # Create vocabulary issue with problem description before quote
    issue_items = [
        {
            'suggestion': "Jargon mismatch: The phrase 'Zone Enhancement Information' is technical jargon that doesn't match the plain-language style used elsewhere. EXACT QUOTE: 'Zone Enhancement Information'",
            'url': 'https://crest.ca/',
            'title': 'Connected for Safety – CREST',
            'evidence': "EXACT QUOTE: 'Zone Enhancement Information'",
            'confidence': 0.85,
            'issue': 'vocabulary',
            'language': 'en'
        },
        {
            'suggestion': "Inconsistent terminology: The site uses both 'customer' and 'client' interchangeably, which can confuse readers. EXACT QUOTE: 'Our clients receive premium service'",
            'url': 'https://example.com/services',
            'title': 'Our Services',
            'evidence': "EXACT QUOTE: 'Our clients receive premium service'",
            'confidence': 0.88,
            'issue': 'vocabulary',
            'language': 'en'
        }
    ]
    
    # Call the function
    result = get_remedy_for_issue(
        issue_type='Vocabulary',
        dimension='coherence',
        issue_items=issue_items
    )
    
    # Assertions
    recommended_fix = result['recommended_fix']
    
    # 1. Check that problem descriptions are present
    assert 'Jargon mismatch' in recommended_fix, "Missing 'Jargon mismatch' problem type"
    assert 'Inconsistent terminology' in recommended_fix, "Missing 'Inconsistent terminology' problem type"
    
    # 2. Check that explanations are present
    assert "technical jargon that doesn't match" in recommended_fix, "Missing explanation for jargon issue"
    assert "uses both 'customer' and 'client' interchangeably" in recommended_fix, "Missing explanation for terminology issue"
    
    # 3. Check that quotes are present
    assert "Zone Enhancement Information" in recommended_fix, "Missing first quote"
    assert "Our clients receive premium service" in recommended_fix, "Missing second quote"
    
    # 4. Check that URLs are present
    assert 'https://crest.ca/' in recommended_fix, "Missing first URL"
    assert 'https://example.com/services' in recommended_fix, "Missing second URL"
    
    # 5. Check that titles are present
    assert 'Connected for Safety' in recommended_fix or 'CREST' in recommended_fix, "Missing first title"
    assert 'Our Services' in recommended_fix, "Missing second title"
    
    # 6. Verify the format includes numbered items
    assert '1.' in recommended_fix, "Missing first numbered item"
    assert '2.' in recommended_fix, "Missing second numbered item"
    
    print("✅ All vocabulary issue formatting tests passed!")
    print("\nFormatted output:")
    print(recommended_fix)


def test_vocabulary_issue_without_description_filtered():
    """Verify that vocabulary issues without problem descriptions are filtered out."""
    
    # Create vocabulary issue WITHOUT problem description (just a quote)
    issue_items = [
        {
            'suggestion': "'Zone Enhancement Information'",  # No explanation
            'url': 'https://crest.ca/',
            'title': 'Connected for Safety – CREST',
            'evidence': "EXACT QUOTE: 'Zone Enhancement Information'",
            'confidence': 0.85,
            'issue': 'vocabulary',
            'language': 'en'
        }
    ]
    
    # Call the function
    result = get_remedy_for_issue(
        issue_type='Vocabulary',
        dimension='coherence',
        issue_items=issue_items
    )
    
    # This should fall back to general best practice since the suggestion lacks explanation
    # The URL should still appear in fallback format
    recommended_fix = result['recommended_fix']
    
    # Should show the URL even if suggestion was filtered
    assert 'https://crest.ca/' in recommended_fix, "URL should appear even when suggestion filtered"
    
    print("✅ Vocabulary issue without description correctly handled!")


def test_vocabulary_vs_concrete_rewrite():
    """Verify that vocabulary issues with descriptions are handled differently from concrete rewrites."""
    
    # Vocabulary issue (general guidance)
    vocab_items = [
        {
            'suggestion': "Brand voice deviation: This formal phrasing doesn't match the conversational tone used throughout the site. EXACT QUOTE: 'Utilize our comprehensive solutions'",
            'url': 'https://example.com/page1',
            'title': 'Solutions Page',
            'evidence': "EXACT QUOTE: 'Utilize our comprehensive solutions'",
            'confidence': 0.87,
            'issue': 'vocabulary',
            'language': 'en'
        }
    ]
    
    # Concrete rewrite issue
    rewrite_items = [
        {
            'suggestion': "Change 'click here' → 'learn more about our services'. This improves coherence by providing specific, descriptive CTAs.",
            'url': 'https://example.com/page2',
            'title': 'Services Page',
            'evidence': "EXACT QUOTE: 'click here'",
            'confidence': 0.9,
            'issue': 'Brand Voice Consistency Score',
            'language': 'en'
        }
    ]
    
    # Test vocabulary issue
    vocab_result = get_remedy_for_issue('Vocabulary', 'coherence', vocab_items)
    vocab_fix = vocab_result['recommended_fix']
    
    # Should show description without "Change" format
    assert 'Brand voice deviation' in vocab_fix, "Missing problem type"
    assert "doesn't match the conversational tone" in vocab_fix, "Missing explanation"
    assert 'Change' not in vocab_fix, "Should not have 'Change' format for vocabulary"
    
    # Test concrete rewrite issue
    rewrite_result = get_remedy_for_issue('Brand Voice Consistency Score', 'coherence', rewrite_items)
    rewrite_fix = rewrite_result['recommended_fix']
    
    # Should show "Change X → Y" format
    assert "Change 'click here'" in rewrite_fix, "Missing 'Change' format for rewrite"
    assert "learn more about our services" in rewrite_fix, "Missing rewrite suggestion"
    
    print("✅ Vocabulary vs concrete rewrite formatting correctly differentiated!")


if __name__ == '__main__':
    test_vocabulary_issue_with_problem_description()
    print("\n" + "="*80 + "\n")
    test_vocabulary_issue_without_description_filtered()
    print("\n" + "="*80 + "\n")
    test_vocabulary_vs_concrete_rewrite()
    print("\n" + "="*80)
    print("✅ ALL VOCABULARY TESTS PASSED!")
