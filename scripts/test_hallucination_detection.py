#!/usr/bin/env python3
"""
Test to verify hallucination detection and aspect context validation
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.utils.recommendations import get_remedy_for_issue

def test_hallucination_detection():
    """Test that prompt text hallucinations are filtered out"""
    
    print("Testing Hallucination Detection and Aspect Validation...")
    print("=" * 80)
    
    # Test 1: Hallucination - LLM quoting the prompt text
    print("\n1. Testing hallucination detection (prompt text quote):")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Why didn\'t I get 100%? What specific thing could make this even better?',
            'url': 'https://ca.crest.com/en-ca/oral-care-products/toothpaste',
            'title': 'Shop Toothpaste for Best Oral Hygiene | Crest CA',
            'evidence': 'EXACT QUOTE: \'some text\'',
            'confidence': 0.75,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    
    # Should be filtered out, so recommended_fix should be fallback text
    if 'Why didn\'t I get 100%' not in remedy_data['recommended_fix']:
        print("✅ PASS: Hallucination (prompt quote) was filtered out")
    else:
        print("❌ FAIL: Hallucination was NOT filtered out")
        print(f"Got: {remedy_data['recommended_fix']}")
        return False
    
    # Test 2: Bare quote without aspect context
    print("\n\n2. Testing bare quote without aspect context:")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Explore ALL PRODUCTS',
            'url': 'https://ca.crest.com/en-ca',
            'title': 'Toothpaste, Mouthwash, 3D Whitestrips | Crest',
            'evidence': 'EXACT QUOTE: \'Explore ALL PRODUCTS\'',
            'confidence': 0.75,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    
    # Should be filtered out
    if 'Explore ALL PRODUCTS' not in remedy_data['recommended_fix'] or 'Review content' in remedy_data['recommended_fix']:
        print("✅ PASS: Bare quote without aspect was filtered out")
    else:
        print("❌ FAIL: Bare quote was NOT filtered out")
        print(f"Got: {remedy_data['recommended_fix']}")
        return False
    
    # Test 3: Quote without explanation (just content text)
    print("\n\n3. Testing content quote without explanation:")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Teeth Whitening Remove surface stains and maintain a bright smile.',
            'url': 'https://crest.com/en-us/oral-care-products/toothpaste',
            'title': 'Shop our Best Toothpastes | Crest US',
            'evidence': 'EXACT QUOTE: \'Teeth Whitening Remove surface stains and maintain a bright smile.\'',
            'confidence': 0.75,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    
    # Should be filtered out (no aspect prefix, no "Change" statement)
    if 'Teeth Whitening Remove surface' not in remedy_data['recommended_fix'] or 'Review content' in remedy_data['recommended_fix']:
        print("✅ PASS: Content quote without explanation was filtered out")
    else:
        print("❌ FAIL: Content quote was NOT filtered out")
        print(f"Got: {remedy_data['recommended_fix']}")
        return False
    
    # Test 4: Valid suggestion with aspect prefix (should NOT be filtered)
    print("\n\n4. Testing valid suggestion with aspect prefix:")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Call-to-Action Clarity: The phrase uses generic all-caps text that could be more specific and engaging. Change \'Explore ALL PRODUCTS\' → \'Discover Our Complete Oral Care Collection\'. This enhances coherence by using descriptive, brand-aligned language instead of generic CTAs.',
            'url': 'https://ca.crest.com/en-ca',
            'title': 'Toothpaste, Mouthwash, 3D Whitestrips | Crest',
            'evidence': 'EXACT QUOTE: \'Explore ALL PRODUCTS\'',
            'confidence': 0.75,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    
    # Should NOT be filtered out
    if 'Call-to-Action Clarity' in remedy_data['recommended_fix']:
        print("✅ PASS: Valid suggestion with aspect prefix was NOT filtered")
        print(f"\nRecommendation:\n{remedy_data['recommended_fix']}")
    else:
        print("❌ FAIL: Valid suggestion was incorrectly filtered out")
        print(f"Got: {remedy_data['recommended_fix']}")
        return False
    
    # Test 5: Another hallucination variant
    print("\n\n5. Testing another hallucination variant:")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'The client wants to know what is one small thing I could do to make this perfect',
            'url': 'https://example.com',
            'title': 'Example Page',
            'evidence': 'EXACT QUOTE: \'some text\'',
            'confidence': 0.75,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    
    if 'client wants to know' not in remedy_data['recommended_fix']:
        print("✅ PASS: Hallucination variant was filtered out")
    else:
        print("❌ FAIL: Hallucination variant was NOT filtered out")
        print(f"Got: {remedy_data['recommended_fix']}")
        return False
    
    print("\n" + "=" * 80)
    print("✅ ALL HALLUCINATION DETECTION TESTS PASSED!")
    return True

if __name__ == '__main__':
    success = test_hallucination_detection()
    sys.exit(0 if success else 1)
