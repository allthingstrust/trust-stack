#!/usr/bin/env python3
"""
Reproduce the readability issue where sentences are flagged with hundreds of words.
This typically happens with product pages, navigation content, or list-heavy pages.
"""

import re

def test_sentence_splitting():
    """Test the current sentence splitting logic with problematic content."""
    
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
    
    # Current logic from attribute_detector.py
    def analyze_readability(text):
        sentence_list = re.split(r'(?<=[\.\!\?])\s+', text)
        sentence_list = [s.strip() for s in sentence_list if len(s.strip()) > 10]
        
        if len(sentence_list) == 0:
            return None
        
        words = len(text.split())
        words_per_sentence = words / len(sentence_list)
        
        return {
            'total_words': words,
            'num_sentences': len(sentence_list),
            'words_per_sentence': words_per_sentence,
            'sentences': sentence_list[:3]  # Show first 3
        }
    
    print("=" * 60)
    print("PRODUCT PAGE ANALYSIS")
    print("=" * 60)
    result1 = analyze_readability(product_page)
    if result1:
        print(f"Total words: {result1['total_words']}")
        print(f"Detected sentences: {result1['num_sentences']}")
        print(f"Words/sentence: {result1['words_per_sentence']:.1f}")
        print(f"\nFirst detected 'sentence':")
        for i, sent in enumerate(result1['sentences'], 1):
            print(f"  {i}. {sent[:100]}...")
    
    print("\n" + "=" * 60)
    print("LANDING PAGE ANALYSIS")
    print("=" * 60)
    result2 = analyze_readability(landing_page)
    if result2:
        print(f"Total words: {result2['total_words']}")
        print(f"Detected sentences: {result2['num_sentences']}")
        print(f"Words/sentence: {result2['words_per_sentence']:.1f}")
        print(f"\nFirst detected 'sentence':")
        for i, sent in enumerate(result2['sentences'], 1):
            print(f"  {i}. {sent[:100]}...")

if __name__ == '__main__':
    test_sentence_splitting()
