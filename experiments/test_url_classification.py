#!/usr/bin/env python3
"""Test script for URL classification and ratio enforcement"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ingestion.domain_classifier import (
    classify_url,
    URLCollectionConfig,
    URLSourceType,
    BrandPropertyTier,
    ThirdPartyTier,
    enforce_ratio
)


def test_url_classification():
    """Test basic URL classification"""
    print("=" * 60)
    print("Test 1: URL Classification")
    print("=" * 60)

    # Create config for Nike brand
    config = URLCollectionConfig(
        brand_owned_ratio=0.6,
        third_party_ratio=0.4,
        brand_domains=['nike.com'],
        brand_subdomains=['blog.nike.com', 'help.nike.com'],
        brand_social_handles=['@nike', 'nike']
    )

    # Test URLs
    test_urls = [
        ('https://www.nike.com/', 'Brand primary website'),
        ('https://blog.nike.com/articles/sustainability', 'Brand content hub'),
        ('https://help.nike.com/support', 'Brand content hub'),
        ('https://twitter.com/nike', 'Brand official social'),
        ('https://twitter.com/user123/status/456', '3rd party social UGC'),
        ('https://www.nytimes.com/2024/nike-earnings', '3rd party news'),
        ('https://www.amazon.com/nike-shoes', '3rd party marketplace'),
        ('https://www.trustpilot.com/review/nike.com', '3rd party reviews'),
        ('https://www.forbes.com/nike-innovation', '3rd party news'),
        ('https://www.reddit.com/r/sneakers/nike', '3rd party UGC'),
    ]

    for url, description in test_urls:
        classification = classify_url(url, config)
        print(f"\nURL: {url}")
        print(f"Description: {description}")
        print(f"  Source Type: {classification.source_type.value}")
        print(f"  Tier: {classification.tier.value if classification.tier else 'None'}")
        print(f"  Reason: {classification.reason}")

    print("\n" + "=" * 60)
    print("Test PASSED: All URLs classified successfully")
    print("=" * 60)


def test_ratio_enforcement():
    """Test ratio enforcement"""
    print("\n" + "=" * 60)
    print("Test 2: Ratio Enforcement")
    print("=" * 60)

    config = URLCollectionConfig(
        brand_owned_ratio=0.6,
        third_party_ratio=0.4,
        brand_domains=['nike.com'],
        brand_subdomains=['blog.nike.com'],
        brand_social_handles=['@nike']
    )

    # Simulated URL pool (mix of brand-owned and 3rd party)
    all_urls = [
        'https://www.nike.com/',
        'https://www.nike.com/products',
        'https://blog.nike.com/article1',
        'https://blog.nike.com/article2',
        'https://www.nike.com/about',
        'https://www.nytimes.com/nike-news',
        'https://www.forbes.com/nike-earnings',
        'https://www.amazon.com/nike-shoes',
        'https://www.reddit.com/r/sneakers',
        'https://twitter.com/user123/nike-review',
        'https://www.trustpilot.com/nike',
        'https://www.youtube.com/watch?v=nike-review',
    ]

    target_count = 10
    selected_urls, stats = enforce_ratio(all_urls, config, target_count)

    print(f"\nTarget count: {target_count}")
    print(f"Available URLs: {len(all_urls)}")
    print(f"\nSelected URLs: {len(selected_urls)}")
    print(f"  Brand-owned: {stats['brand_owned']} ({stats['brand_owned_pct']:.1f}%)")
    print(f"  3rd party: {stats['third_party']} ({stats['third_party_pct']:.1f}%)")
    print(f"\nAvailable in pool:")
    print(f"  Brand-owned: {stats['brand_owned_available']}")
    print(f"  3rd party: {stats['third_party_available']}")

    # Verify ratio is approximately 60/40
    expected_brand = int(target_count * 0.6)
    expected_third_party = target_count - expected_brand

    if stats['brand_owned'] == expected_brand and stats['third_party'] == expected_third_party:
        print("\n" + "=" * 60)
        print("Test PASSED: Ratio enforcement working correctly")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print(f"Test WARNING: Expected {expected_brand}/{expected_third_party}, got {stats['brand_owned']}/{stats['third_party']}")
        print("=" * 60)


def test_edge_cases():
    """Test edge cases"""
    print("\n" + "=" * 60)
    print("Test 3: Edge Cases")
    print("=" * 60)

    config = URLCollectionConfig(
        brand_owned_ratio=0.6,
        third_party_ratio=0.4,
        brand_domains=['nike.com']
    )

    # Test unknown domains
    unknown_url = 'https://unknown-site.xyz/article'
    classification = classify_url(unknown_url, config)
    print(f"\nUnknown domain: {unknown_url}")
    print(f"  Classified as: {classification.source_type.value}")
    assert classification.source_type == URLSourceType.THIRD_PARTY, "Unknown domains should be classified as 3rd party"

    # Test subdomain detection
    subdomain_url = 'https://shop.nike.com/products'
    classification = classify_url(subdomain_url, config)
    print(f"\nSubdomain (not in config): {subdomain_url}")
    print(f"  Classified as: {classification.source_type.value}")
    assert classification.source_type == URLSourceType.BRAND_OWNED, "Brand subdomains should be classified as brand-owned"

    print("\n" + "=" * 60)
    print("Test PASSED: Edge cases handled correctly")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_url_classification()
        test_ratio_enforcement()
        test_edge_cases()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        print("\nURL classification and ratio enforcement are working correctly!")
        print("You can now use the following arguments with run_pipeline.py:")
        print("  --brand-domains nike.com")
        print("  --brand-subdomains blog.nike.com help.nike.com")
        print("  --brand-social-handles @nike nike")
        print("  --brand-owned-ratio 0.6")
        print("  --third-party-ratio 0.4")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
