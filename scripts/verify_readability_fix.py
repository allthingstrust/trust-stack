#!/usr/bin/env python3
"""
Verify the readability fix with the improved detection logic.
This should now properly handle product pages and list content.
"""

from scoring.attribute_detector import TrustStackAttributeDetector
from data.models import NormalizedContent

def test_fixed_readability():
    """Test that the fix properly handles problematic content."""
    
    detector = TrustStackAttributeDetector()
    
    # Example 1: Product page with list items (no periods)
    product_page = """
    Shop Whitestrips, Toothpaste & Mouthwash
    Crest 3D White Whitestrips
    Professional Effects
    Glamorous White
    Gentle Routine
    Crest Pro-Health Toothpaste
    Advanced Deep Clean
    Gum Detoxify
    Sensitive Shield
    Crest Complete Whitening
    Scope Mouthwash
    Outlast
    Classic
    """
    
    # Example 2: Landing page with short headings
    landing_page = """
    Connected for Safety
    CREST provides emergency response services
    Our mission is to protect communities
    We serve Langford and surrounding areas
    24/7 emergency dispatch
    Fire protection services
    Ambulance services
    Police coordination
    """
    
    # Example 3: Normal prose (should still work)
    normal_prose = """
    Our company has been serving customers for over 20 years. We pride ourselves on quality and customer service.
    Every product we offer is carefully tested and vetted by our team. We stand behind everything we sell.
    Visit our website today to learn more about our offerings. We look forward to serving you.
    """
    
    def analyze(text, label):
        content = NormalizedContent(
            content_id="test",
            src="test",
            platform_id="test",
            title="Test",
            body=text,
            author="test",
            published_at="2024-01-01",
            event_ts="2024-01-01T00:00:00"
        )
        result = detector._detect_readability(content)
        
        print(f"\n{'='*60}")
        print(f"{label}")
        print(f"{'='*60}")
        if result:
            print(f"✓ Analysis performed")
            print(f"  Words/sentence: {result.evidence}")
            print(f"  Value: {result.value}")
        else:
            print(f"✓ Skipped (non-prose content)")
        
        return result
    
    result1 = analyze(product_page, "PRODUCT PAGE (List Items)")
    result2 = analyze(landing_page, "LANDING PAGE (Short Lines)")
    result3 = analyze(normal_prose, "NORMAL PROSE")
    
    print(f"\n{'='*60}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*60}")
    
    # Verify expectations
    if result1 is None:
        print("✓ Product page correctly skipped (list content)")
    else:
        print(f"✗ Product page should be skipped but got: {result1.evidence}")
    
    if result2 is None:
        print("✓ Landing page correctly skipped (short lines)")
    else:
        print(f"✗ Landing page should be skipped but got: {result2.evidence}")
    
    if result3 is not None:
        words_per_sent = float(result3.evidence.split()[1])
        if words_per_sent < 50:
            print(f"✓ Normal prose analyzed correctly ({words_per_sent:.1f} words/sentence)")
        else:
            print(f"✗ Normal prose has inflated count: {words_per_sent:.1f} words/sentence")
    else:
        print("✗ Normal prose should be analyzed but was skipped")
    
    print()

if __name__ == '__main__':
    test_fixed_readability()
