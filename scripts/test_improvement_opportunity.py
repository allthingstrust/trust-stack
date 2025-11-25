#!/usr/bin/env python3
"""
Test to verify improvement opportunity recommendations now include specific context
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.utils.recommendations import get_remedy_for_issue

def test_improvement_opportunity_with_aspect():
    """Test that improvement opportunities now show coherence aspects"""
    
    print("Testing Improvement Opportunity with Coherence Aspect...")
    print("=" * 80)
    
    # Test 1: Improvement opportunity with aspect prefix (new format)
    print("\n1. Testing improvement opportunity with aspect prefix:")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Call-to-Action Clarity: The phrase uses generic all-caps text that could be more specific and engaging. Change \'Explore ALL PRODUCTS\' → \'Discover Our Complete Oral Care Collection\'. This enhances coherence by using descriptive, brand-aligned language instead of generic CTAs.',
            'url': 'https://ca.crest.com/en-ca',
            'title': 'Toothpaste, Mouthwash, 3D Whitestrips, Oral Care Tips | Crest',
            'evidence': 'EXACT QUOTE: \'Explore ALL PRODUCTS\'',
            'confidence': 0.75,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    print("\nRecommended Fix:")
    print(remedy_data['recommended_fix'])
    print("\nGeneral Best Practice:")
    print(remedy_data['general_best_practice'])
    
    # Verify the aspect is displayed
    if 'Call-to-Action Clarity' in remedy_data['recommended_fix']:
        print("\n✅ PASS: Coherence aspect (Call-to-Action Clarity) is displayed")
    else:
        print("\n❌ FAIL: Coherence aspect not found in recommendation")
        return False
    
    # Verify the explanation is displayed
    if 'generic all-caps text' in remedy_data['recommended_fix']:
        print("✅ PASS: Explanation is displayed")
    else:
        print("❌ FAIL: Explanation not found in recommendation")
        return False
    
    # Verify the rewrite is displayed
    if 'Discover Our Complete Oral Care Collection' in remedy_data['recommended_fix']:
        print("✅ PASS: Concrete rewrite is displayed")
    else:
        print("❌ FAIL: Concrete rewrite not found in recommendation")
        return False
    
    # Test 2: Improvement opportunity with different aspect
    print("\n\n2. Testing improvement opportunity with different aspect (Tone Optimization):")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Tone Optimization: The phrase could be more conversational and welcoming. Change \'Click here to view products\' → \'Explore our collection\'. This enhances coherence by using a friendlier, more engaging tone.',
            'url': 'https://example.com/products',
            'title': 'Product Page',
            'evidence': 'EXACT QUOTE: \'Click here to view products\'',
            'confidence': 0.72,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    print("\nRecommended Fix:")
    print(remedy_data['recommended_fix'])
    
    if 'Tone Optimization' in remedy_data['recommended_fix']:
        print("\n✅ PASS: Different coherence aspect (Tone Optimization) is displayed")
    else:
        print("\n❌ FAIL: Coherence aspect not found")
        return False
    
    # Test 3: Old format (without aspect prefix) should still work
    print("\n\n3. Testing backward compatibility with old format:")
    print("-" * 80)
    
    issue_items = [
        {
            'suggestion': 'Change \'Learn more\' → \'Discover our story\'. This is a minor optimization to improve engagement.',
            'url': 'https://example.com/about',
            'title': 'About Page',
            'evidence': 'EXACT QUOTE: \'Learn more\'',
            'confidence': 0.70,
            'issue': 'improvement_opportunity'
        }
    ]
    
    remedy_data = get_remedy_for_issue('improvement_opportunity', 'coherence', issue_items)
    print("\nRecommended Fix:")
    print(remedy_data['recommended_fix'])
    
    if 'Discover our story' in remedy_data['recommended_fix']:
        print("\n✅ PASS: Old format still works")
    else:
        print("\n❌ FAIL: Old format broken")
        return False
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED!")
    return True

if __name__ == '__main__':
    success = test_improvement_opportunity_with_aspect()
    sys.exit(0 if success else 1)
