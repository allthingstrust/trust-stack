#!/usr/bin/env python3
"""
Test script to verify metadata is being collected from web pages.

This script:
1. Fetches a real URL (or uses mock HTML)
2. Extracts metadata using both page_fetcher and MetadataExtractor
3. Reports which metadata fields were successfully collected

Usage:
    python scripts/test_metadata_collection.py [--url URL] [--verbose]
"""

import sys
import os
import argparse
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.page_fetcher import fetch_page
from ingestion.metadata_extractor import MetadataExtractor
from data.models import NormalizedContent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


# Sample HTML with rich metadata for offline testing
SAMPLE_HTML_WITH_METADATA = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sample Brand Page - Premium Products</title>
    
    <!-- Standard Meta Tags -->
    <meta name="description" content="Discover premium products from Sample Brand. Quality you can trust.">
    <meta name="keywords" content="sample, brand, premium, quality, products">
    <meta name="author" content="Sample Brand Team">
    <meta name="robots" content="index, follow">
    
    <!-- Open Graph Tags -->
    <meta property="og:title" content="Sample Brand - Premium Products">
    <meta property="og:description" content="Discover premium products from Sample Brand">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://sample-brand.com/products">
    <meta property="og:image" content="https://sample-brand.com/images/og-image.jpg">
    <meta property="og:site_name" content="Sample Brand">
    
    <!-- Twitter Card Tags -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Sample Brand - Premium Products">
    <meta name="twitter:description" content="Discover premium products from Sample Brand">
    
    <!-- Canonical URL -->
    <link rel="canonical" href="https://sample-brand.com/products">
    
    <!-- Schema.org JSON-LD -->
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Sample Brand",
        "url": "https://sample-brand.com",
        "logo": "https://sample-brand.com/logo.png",
        "sameAs": [
            "https://twitter.com/samplebrand",
            "https://facebook.com/samplebrand"
        ]
    }
    </script>
</head>
<body>
    <header>
        <nav><a href="/">Home</a> | <a href="/products">Products</a></nav>
    </header>
    
    <main role="main">
        <article>
            <h1>Welcome to Sample Brand</h1>
            <p>We are committed to providing the highest quality products to our customers. 
            Our dedication to excellence has made us a trusted name in the industry.</p>
            
            <h2>Our Products</h2>
            <ul>
                <li>Premium Product A - $99.99</li>
                <li>Premium Product B - $149.99</li>
                <li>Premium Product C - $199.99</li>
            </ul>
            
            <p>Contact us at support@sample-brand.com for more information.</p>
        </article>
    </main>
    
    <footer>
        <a href="/terms">Terms of Service</a>
        <a href="/privacy">Privacy Policy</a>
        <p>&copy; 2024 Sample Brand. All rights reserved.</p>
    </footer>
</body>
</html>
"""


def test_metadata_extraction_offline(verbose: bool = False):
    """Test metadata extraction using sample HTML (no network required)."""
    print("\n" + "=" * 60)
    print("OFFLINE METADATA EXTRACTION TEST")
    print("=" * 60)
    
    extractor = MetadataExtractor()
    
    # Test each extraction method individually
    results = {}
    
    # 1. Test OG metadata extraction
    print("\n[1] Testing Open Graph (OG) Metadata Extraction...")
    og_data = extractor.extract_og_metadata(SAMPLE_HTML_WITH_METADATA)
    results['og_metadata'] = og_data
    if og_data:
        print(f"    ✅ Extracted {len(og_data)} OG fields")
        if verbose:
            for key, value in og_data.items():
                print(f"       - {key}: {value[:50]}..." if len(value) > 50 else f"       - {key}: {value}")
    else:
        print("    ❌ No OG metadata found")
    
    # 2. Test standard meta tags extraction
    print("\n[2] Testing Standard Meta Tags Extraction...")
    meta_tags = extractor.extract_meta_tags(SAMPLE_HTML_WITH_METADATA)
    results['meta_tags'] = meta_tags
    if meta_tags:
        print(f"    ✅ Extracted {len(meta_tags)} meta tags")
        if verbose:
            for key, value in meta_tags.items():
                print(f"       - {key}: {value[:50]}..." if len(str(value)) > 50 else f"       - {key}: {value}")
    else:
        print("    ❌ No standard meta tags found")
    
    # 3. Test canonical URL extraction
    print("\n[3] Testing Canonical URL Extraction...")
    canonical_url = extractor.extract_canonical_url(SAMPLE_HTML_WITH_METADATA)
    results['canonical_url'] = canonical_url
    if canonical_url:
        print(f"    ✅ Canonical URL: {canonical_url}")
    else:
        print("    ❌ No canonical URL found")
    
    # 4. Test schema.org extraction
    print("\n[4] Testing Schema.org Structured Data Extraction...")
    schema_data = extractor.parse_schema_org(SAMPLE_HTML_WITH_METADATA)
    results['schema_org'] = schema_data
    if schema_data:
        print(f"    ✅ Extracted schema.org data")
        if verbose:
            import json
            print(f"       {json.dumps(schema_data, indent=8)[:200]}...")
    else:
        print("    ❌ No schema.org data found")
    
    # 5. Test modality detection
    print("\n[5] Testing Modality Detection...")
    modality = extractor.detect_modality(
        url="https://sample-brand.com/products",
        content_type="text/html",
        html=SAMPLE_HTML_WITH_METADATA
    )
    results['modality'] = modality
    print(f"    ✅ Detected modality: {modality}")
    
    # 6. Test channel info extraction
    print("\n[6] Testing Channel/Platform Detection...")
    channel, platform_type = extractor.extract_channel_info("https://sample-brand.com/products")
    results['channel'] = channel
    results['platform_type'] = platform_type
    print(f"    ✅ Channel: {channel}, Platform Type: {platform_type}")
    
    # Summary
    print("\n" + "-" * 60)
    print("SUMMARY: Offline Metadata Extraction")
    print("-" * 60)
    
    collected_count = 0
    total_fields = 0
    
    for category, data in results.items():
        if isinstance(data, dict):
            total_fields += len(data)
            collected_count += len(data)
        elif data:
            total_fields += 1
            collected_count += 1
        else:
            total_fields += 1
    
    print(f"Total metadata fields collected: {collected_count}")
    print(f"Metadata extraction is WORKING ✅" if collected_count > 5 else "Metadata extraction may have issues ⚠️")
    
    return results


def test_metadata_extraction_online(url: str, verbose: bool = False):
    """Test metadata extraction from a live URL."""
    print("\n" + "=" * 60)
    print(f"ONLINE METADATA EXTRACTION TEST")
    print(f"URL: {url}")
    print("=" * 60)
    
    # 1. Fetch the page
    print("\n[1] Fetching page...")
    result = fetch_page(url)
    
    if not result.get('body'):
        print(f"    ⚠️ Warning: No body content extracted from {url}")
        print("    This could indicate the page requires JavaScript rendering")
        return None
    
    print(f"    ✅ Fetched page: {len(result.get('body', ''))} chars")
    print(f"    ✅ Title: {result.get('title', 'N/A')[:50]}...")
    
    # Check for structured body (HTML structure metadata)
    if 'structured_body' in result and result['structured_body']:
        print(f"    ✅ Structured body segments: {len(result['structured_body'])}")
        if verbose:
            for i, segment in enumerate(result['structured_body'][:3]):
                print(f"       [{i}] {segment.get('semantic_role')}: {segment.get('text', '')[:40]}...")
    
    # Check for footer links (terms/privacy)
    if result.get('terms'):
        print(f"    ✅ Terms link found: {result['terms']}")
    else:
        print(f"    ⚠️ No Terms link found")
    
    if result.get('privacy'):
        print(f"    ✅ Privacy link found: {result['privacy']}")
    else:
        print(f"    ⚠️ No Privacy link found")
    
    # 2. Create a NormalizedContent object and enrich it
    print("\n[2] Enriching with MetadataExtractor...")
    
    extractor = MetadataExtractor()
    
    # Create a basic NormalizedContent object
    content = NormalizedContent(
        content_id="test_" + url.replace('https://', '').replace('/', '_')[:30],
        src="web",
        platform_id="test",
        author="",
        title=result.get('title', ''),
        body=result.get('body', ''),
        rating=None,
        upvotes=None,
        helpful_count=None,
        event_ts="2024-01-01T00:00:00",
        run_id="test_run",
        meta={},
        url=url
    )
    
    # We don't have raw HTML from fetch_page, but we can show what's in the result
    # In a real flow, the MetadataExtractor would be called with raw HTML
    
    # Show channel/platform detection
    channel, platform_type = extractor.extract_channel_info(url)
    print(f"    ✅ Channel: {channel}")
    print(f"    ✅ Platform Type: {platform_type}")
    
    # Show modality detection
    modality = extractor.detect_modality(url=url, src="web")
    print(f"    ✅ Modality: {modality}")
    
    print("\n" + "-" * 60)
    print("SUMMARY: Online Metadata Extraction")
    print("-" * 60)
    
    summary = {
        'url': url,
        'title': result.get('title', ''),
        'body_length': len(result.get('body', '')),
        'has_structured_body': 'structured_body' in result and bool(result['structured_body']),
        'structured_segments': len(result.get('structured_body', [])),
        'terms_link': result.get('terms', ''),
        'privacy_link': result.get('privacy', ''),
        'channel': channel,
        'platform_type': platform_type,
        'modality': modality
    }
    
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    metadata_collected = bool(
        result.get('title') or 
        result.get('terms') or 
        result.get('privacy') or
        result.get('structured_body')
    )
    
    print(f"\nMetadata collection is WORKING ✅" if metadata_collected else "\nMetadata collection may have issues ⚠️")
    
    return summary


def run_all_tests(url: str = None, verbose: bool = False):
    """Run all metadata collection tests."""
    print("\n" + "=" * 70)
    print("          METADATA COLLECTION VERIFICATION TEST SUITE")
    print("=" * 70)
    
    # Always run offline test first
    offline_results = test_metadata_extraction_offline(verbose)
    
    # Run online test if URL provided
    online_results = None
    if url:
        online_results = test_metadata_extraction_online(url, verbose)
    else:
        print("\n" + "-" * 60)
        print("SKIPPED: Online test (no URL provided)")
        print("Use --url https://example.com to test live metadata extraction")
        print("-" * 60)
    
    # Final summary
    print("\n" + "=" * 70)
    print("                    FINAL TEST RESULTS")
    print("=" * 70)
    
    offline_pass = bool(offline_results and len(offline_results.get('og_metadata', {})) > 0)
    print(f"Offline metadata extraction: {'✅ PASS' if offline_pass else '❌ FAIL'}")
    
    if online_results:
        online_pass = online_results['body_length'] > 100
        print(f"Online page fetch: {'✅ PASS' if online_pass else '❌ FAIL'}")
    
    print("\nKey metadata fields that SHOULD be collected:")
    print("  - Page title")
    print("  - Body content (text extracted from page)")
    print("  - Structured body (HTML structure + semantic roles)")
    print("  - Open Graph tags (og:title, og:description, etc.)")
    print("  - Standard meta tags (description, keywords, author)")
    print("  - Canonical URL")
    print("  - Schema.org structured data (JSON-LD)")
    print("  - Footer links (terms, privacy)")
    print("  - Channel/platform detection")
    print("  - Modality detection (text/image/video/audio)")
    
    return offline_pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test metadata collection from web pages')
    parser.add_argument('--url', type=str, help='URL to test (optional, for live testing)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    args = parser.parse_args()
    
    success = run_all_tests(url=args.url, verbose=args.verbose)
    sys.exit(0 if success else 1)
