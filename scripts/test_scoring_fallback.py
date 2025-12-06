#!/usr/bin/env python3
"""Test script to verify scoring fallback when pages have no content."""

import sys
sys.path.insert(0, '.')

from unittest.mock import MagicMock
from core.run_manager import RunManager
from scoring.scorer import ContentScorer

def test_scoring_with_empty_content():
    """Test that assets with 0-char content still get scores (not 0.0)."""
    
    # Create mock assets that simulate what happens when Playwright can't fetch content
    mock_assets = []
    for i in range(5):
        asset = MagicMock()
        asset.id = i + 1
        asset.run_id = 1
        asset.title = f"Test Page {i+1}"
        asset.url = f"https://example.com/page{i+1}"
        asset.source_type = "web"
        asset.normalized_content = ""  # Empty - simulates failed fetch
        asset.raw_content = ""
        asset.meta_info = {}
        asset.modality = "text"
        asset.channel = "web"
        mock_assets.append(asset)
    
    run_config = {
        "brand_name": "TestBrand",
        "keywords": ["test"],
        "sources": ["web"],
    }
    
    # Test 1: With ContentScorer (which will filter out all items due to insufficient content)
    print("=" * 60)
    print("TEST 1: ContentScorer with empty content (should fallback to heuristic)")
    print("=" * 60)
    
    scorer = ContentScorer(use_attribute_detection=False)  # Disable to speed up
    manager = RunManager(scoring_pipeline=scorer)
    
    scores = manager._score_assets(mock_assets, run_config)
    
    print(f"\nReturned {len(scores)} scores for {len(mock_assets)} assets")
    
    all_passed = True
    for score in scores:
        prov = score.get('score_provenance', 0)
        res = score.get('score_resonance', 0)
        overall = score.get('overall_score', 0)
        
        print(f"  Asset {score['asset_id']}: provenance={prov:.2f}, resonance={res:.2f}, overall={overall:.2f}")
        
        if prov == 0.0 or res == 0.0 or overall == 0.0:
            print(f"    ❌ FAIL: Score is 0.0!")
            all_passed = False
        elif prov == 0.5 and res == 0.5:
            print(f"    ✅ PASS: Heuristic baseline (0.5) applied correctly")
        else:
            print(f"    ⚠️  Score is not 0.5, but also not 0")
    
    # Test 2: With NO scoring pipeline (pure heuristic fallback)
    print("\n" + "=" * 60)
    print("TEST 2: No scoring pipeline (pure heuristic)")
    print("=" * 60)
    
    manager_no_scorer = RunManager(scoring_pipeline=None)
    scores2 = manager_no_scorer._score_assets(mock_assets, run_config)
    
    print(f"\nReturned {len(scores2)} scores for {len(mock_assets)} assets")
    
    for score in scores2:
        prov = score.get('score_provenance', 0)
        overall = score.get('overall_score', 0)
        
        print(f"  Asset {score['asset_id']}: provenance={prov:.2f}, overall={overall:.2f}")
        
        if prov == 0.0 or overall == 0.0:
            print(f"    ❌ FAIL: Score is 0.0!")
            all_passed = False
        else:
            print(f"    ✅ PASS: Score is {prov:.2f}")
    
    # Test 3: Mixed content (some empty, some with content)
    print("\n" + "=" * 60)
    print("TEST 3: Mixed content (some empty, some with content)")
    print("=" * 60)
    
    mock_assets[0].normalized_content = "This is some real content about the brand. " * 50  # 2200 chars
    mock_assets[1].normalized_content = "Short content"  # 13 chars
    # Assets 2,3,4 remain empty
    
    scores3 = manager._score_assets(mock_assets, run_config)
    
    print(f"\nReturned {len(scores3)} scores for {len(mock_assets)} assets")
    
    for i, score in enumerate(scores3):
        content_len = len(mock_assets[i].normalized_content or "")
        prov = score.get('score_provenance', 0)
        overall = score.get('overall_score', 0)
        classification = score.get('classification', 'Unknown')
        
        print(f"  Asset {score['asset_id']} ({content_len} chars): provenance={prov:.2f}, overall={overall:.2f}, class={classification}")
        
        if prov == 0.0 or overall == 0.0:
            print(f"    ❌ FAIL: Score is 0.0!")
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - No 0.0 scores!")
    else:
        print("❌ SOME TESTS FAILED - There are still 0.0 scores")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = test_scoring_with_empty_content()
    sys.exit(0 if success else 1)
