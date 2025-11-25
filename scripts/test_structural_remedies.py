#!/usr/bin/env python3
"""
Test to verify structural issue remedies are now displayed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.utils.recommendations import get_remedy_for_issue

def test_structural_issue_remedies():
    """Test that structural issues now show remedies"""
    
    print("Testing Structural Issue Remedies...")
    print("=" * 80)
    
    # Test 1: Transparency structural issue
    print("\n1. Testing 'missing_privacy_policy' (Transparency):")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Add a privacy policy link to your website footer and navigation.',
            'url': 'http://example.com/homepage',
            'title': 'Homepage',
            'evidence': 'No privacy policy link found',
            'confidence': 0.85,
            'issue': 'missing_privacy_policy'
        }
    ]
    
    remedy_data = get_remedy_for_issue('missing_privacy_policy', 'transparency', issue_items)
    print(remedy_data)
    
    # Check that both the LLM suggestion AND the predefined remedy are shown
    if remedy_data and 'privacy policy' in remedy_data['recommended_fix'].lower() and remedy_data['general_best_practice']:
        print("\n✅ PASS: Structural transparency issue shows remedy")
    else:
        print("\n❌ FAIL: No remedy shown")
        return False
    
    # Test 2: Provenance structural issue
    print("\n\n2. Testing 'unclear_authorship' (Provenance):")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Add author attribution to blog posts and articles.',
            'url': 'http://example.com/blog/post',
            'title': 'Blog Post',
            'evidence': 'No author information found',
            'confidence': 0.9,
            'issue': 'unclear_authorship'
        }
    ]
    
    remedy_data = get_remedy_for_issue('unclear_authorship', 'provenance', issue_items)
    print(remedy_data)
    
    if remedy_data and 'author' in remedy_data['recommended_fix'].lower() and remedy_data['general_best_practice']:
        print("\n✅ PASS: Structural provenance issue shows remedy")
    else:
        print("\n❌ FAIL: No remedy shown")
        return False
    
    # Test 3: Predefined remedy fallback
    print("\n\n3. Testing predefined remedy fallback (no LLM suggestions):")
    print("-" * 80)
    
    remedy_data = get_remedy_for_issue('no_schema_markup', 'provenance', issue_items=[])
    print(remedy_data)
    
    if remedy_data and 'schema' in remedy_data['general_best_practice'].lower():
        print("\n✅ PASS: Predefined remedy displayed")
    else:
        print("\n❌ FAIL: No predefined remedy")
        return False
    
    # Test 4: Verification pattern analysis
    print("\n\n4. Testing 'fake_engagement' (Verification):")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Monitor engagement patterns for suspicious bot activity.',
            'url': 'http://example.com/social',
            'title': 'Social Media Post',
            'evidence': 'Unusual engagement spike detected',
            'confidence': 0.8,
            'issue': 'fake_engagement'
        }
    ]
    
    remedy_data = get_remedy_for_issue('fake_engagement', 'verification', issue_items)
    print(remedy_data)
    
    if remedy_data and ('monitor' in remedy_data['recommended_fix'].lower() or 'engagement' in remedy_data['recommended_fix'].lower()):
        print("\n✅ PASS: Pattern analysis issue shows remedy")
    else:
        print("\n❌ FAIL: No remedy shown")
        return False
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED!")
    return True

if __name__ == '__main__':
    success = test_structural_issue_remedies()
    sys.exit(0 if success else 1)
