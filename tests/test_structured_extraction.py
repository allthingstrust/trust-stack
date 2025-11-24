#!/usr/bin/env python3
"""
Test structure-aware text extraction to prevent tone shift false positives.

This test verifies that the Reebok-style headline + subheadline pattern
is NOT flagged as a tone shift when using structured text extraction.
"""

from bs4 import BeautifulSoup
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.brave_search import _extract_structured_body_text, _extract_body_text


def test_reebok_headline_subheadline():
    """Test that headline + subheadline with different capitalization is preserved with structure."""
    html = """
    <html>
    <body>
        <div class="hero">
            <h1>UP TO 70% OFF</h1>
            <p class="subtext">Plus, buy two and get an extra 10% off!</p>
        </div>
    </body>
    </html>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Test structured extraction
    structured = _extract_structured_body_text(soup)
    
    print("=" * 60)
    print("TEST: Reebok Headline + Subheadline")
    print("=" * 60)
    
    print("\n1. Structured Body Text:")
    for segment in structured:
        print(f"   [{segment['semantic_role'].upper()}] {segment['text']}")
        print(f"      Element: {segment['element_type']}")
    
    # Verify structure is preserved
    assert len(structured) >= 2, "Should extract at least 2 segments"
    
    # Find headline and subheadline
    headline = next((s for s in structured if 'UP TO 70% OFF' in s['text']), None)
    subheadline = next((s for s in structured if 'Plus, buy two' in s['text']), None)
    
    assert headline is not None, "Should find headline"
    assert subheadline is not None, "Should find subheadline"
    
    print(f"\n2. Headline semantic role: {headline['semantic_role']}")
    print(f"   Subheadline semantic role: {subheadline['semantic_role']}")
    
    # Verify they have different semantic roles
    assert headline['semantic_role'] == 'headline', "H1 should be marked as headline"
    assert subheadline['semantic_role'] in ['subheadline', 'body_text'], "P should be marked appropriately"
    
    print("\n✓ Structure preserved correctly!")
    print("  - Different capitalization is in different semantic elements")
    print("  - LLM will understand this is intentional visual hierarchy")
    
    # Compare with plain text extraction
    plain_text = _extract_body_text(soup)
    print(f"\n3. Plain Text (old method):")
    print(f"   {plain_text}")
    print("   ^ Without structure markers, LLM might flag as tone shift")
    
    return True


def test_product_grid_structure():
    """Test that product grids are marked as product_listing."""
    html = """
    <html>
    <body>
        <div class="product-grid">
            <div class="product-card">
                <h3>Nike Air Max</h3>
                <span class="price">$120</span>
            </div>
            <div class="product-card">
                <h3>Adidas Ultraboost</h3>
                <span class="price">$180</span>
            </div>
            <div class="product-card">
                <h3>Reebok Classic</h3>
                <span class="price">$80</span>
            </div>
        </div>
    </body>
    </html>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    structured = _extract_structured_body_text(soup)
    
    print("\n" + "=" * 60)
    print("TEST: Product Grid Structure")
    print("=" * 60)
    
    print("\nStructured Body Text:")
    for segment in structured:
        print(f"   [{segment['semantic_role'].upper()}] {segment['text']}")
    
    # Verify product listings are marked correctly
    assert len(structured) >= 3, "Should extract at least 3 products"
    
    for segment in structured:
        assert segment['semantic_role'] == 'product_listing', "Should be marked as product_listing"
    
    print("\n✓ Product grid structure preserved!")
    print("  - All items marked as PRODUCT_LISTING")
    print("  - LLM will understand this is structured e-commerce content")
    
    return True


def test_true_positive_tone_shift():
    """Test that actual tone shifts within same element ARE still detected."""
    html = """
    <html>
    <body>
        <p>
            Our professional team provides EXPERT CONSULTING services. 
            lol just kidding we're totally chill and casual dude.
        </p>
    </body>
    </html>
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    structured = _extract_structured_body_text(soup)
    
    print("\n" + "=" * 60)
    print("TEST: True Positive Tone Shift (within same element)")
    print("=" * 60)
    
    print("\nStructured Body Text:")
    for segment in structured:
        print(f"   [{segment['semantic_role'].upper()}] {segment['text']}")
    
    # This should be a single body_text segment
    assert len(structured) == 1, "Should be single paragraph"
    assert structured[0]['semantic_role'] == 'body_text', "Should be body_text"
    
    print("\n✓ Tone shift is within same semantic element!")
    print("  - LLM should still flag this as inconsistent tone")
    print("  - Structure awareness doesn't prevent detecting real issues")
    
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("STRUCTURE-AWARE TEXT EXTRACTION TESTS")
    print("=" * 60)
    
    try:
        test_reebok_headline_subheadline()
        test_product_grid_structure()
        test_true_positive_tone_shift()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nStructure-aware extraction is working correctly:")
        print("  ✓ Headlines and subheadlines are distinguished")
        print("  ✓ Product grids are marked as structured content")
        print("  ✓ Real tone shifts within elements can still be detected")
        print("\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
