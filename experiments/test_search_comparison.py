#!/usr/bin/env python3
"""Search Provider Comparison Tool

Compares search results between Brave and Serper to help you make an informed
decision about which provider to use for your Authenticity Ratio project.

Usage:
    python test_search_comparison.py "brand name" --queries 3 --results 10
    python test_search_comparison.py "Nike" --queries 5
    python test_search_comparison.py "Tesla review" --results 20

This will:
- Test both Brave and Serper with the same queries
- Compare performance (response time)
- Analyze result quality (URL overlap, diversity)
- Show side-by-side comparison
- Provide migration recommendation
"""
from __future__ import annotations

import sys
import os
import time
import argparse
from typing import List, Dict, Set
from collections import Counter

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv not available, try manual loading
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from ingestion.search_unified import search

try:
    import pytest
    pytestmark = pytest.mark.skip(reason="Script for manual provider comparison — skip during automated pytest runs")
except Exception:
    pass


def test_provider(provider: str, query: str, size: int) -> tuple[List[Dict[str, str]], float]:
    """Test a single provider and measure response time.

    Returns:
        Tuple of (results, elapsed_time_seconds)
    """
    print(f"  Testing {provider}...", end=" ", flush=True)

    start = time.time()
    try:
        results = search(query, size=size, provider=provider)
        elapsed = time.time() - start
        print(f"✓ {len(results)} results in {elapsed:.2f}s")
        return results, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ Failed: {e}")
        return [], elapsed


def extract_domains(results: List[Dict[str, str]]) -> List[str]:
    """Extract domains from result URLs."""
    from urllib.parse import urlparse
    domains = []
    for r in results:
        try:
            parsed = urlparse(r['url'])
            domain = parsed.netloc.lower()
            # Remove www. prefix for comparison
            if domain.startswith('www.'):
                domain = domain[4:]
            domains.append(domain)
        except:
            pass
    return domains


def analyze_url_overlap(brave_results: List[Dict[str, str]], serper_results: List[Dict[str, str]]) -> Dict:
    """Analyze URL overlap between providers."""
    brave_urls = {r['url'].lower() for r in brave_results}
    serper_urls = {r['url'].lower() for r in serper_results}

    overlap = brave_urls & serper_urls
    brave_only = brave_urls - serper_urls
    serper_only = serper_urls - brave_urls

    return {
        'overlap_count': len(overlap),
        'overlap_percent': (len(overlap) / max(len(brave_urls), 1)) * 100,
        'brave_only': len(brave_only),
        'serper_only': len(serper_only),
        'overlap_urls': list(overlap),
        'total_unique': len(brave_urls | serper_urls)
    }


def analyze_domain_diversity(brave_results: List[Dict[str, str]], serper_results: List[Dict[str, str]]) -> Dict:
    """Analyze domain diversity between providers."""
    brave_domains = extract_domains(brave_results)
    serper_domains = extract_domains(serper_results)

    brave_counter = Counter(brave_domains)
    serper_counter = Counter(serper_domains)

    return {
        'brave_unique_domains': len(brave_counter),
        'serper_unique_domains': len(serper_counter),
        'brave_top_domains': brave_counter.most_common(5),
        'serper_top_domains': serper_counter.most_common(5),
    }


def categorize_urls(results: List[Dict[str, str]]) -> Dict[str, int]:
    """Categorize URLs by type (social media, reviews, news, etc)."""
    categories = {
        'social': 0,
        'review': 0,
        'news': 0,
        'ecommerce': 0,
        'forum': 0,
        'video': 0,
        'other': 0
    }

    social_domains = {'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'tiktok.com', 'x.com'}
    review_domains = {'yelp.com', 'trustpilot.com', 'glassdoor.com', 'g2.com', 'capterra.com', 'consumeraffairs.com'}
    news_domains = {'cnn.com', 'bbc.com', 'nytimes.com', 'forbes.com', 'bloomberg.com', 'reuters.com'}
    ecommerce_domains = {'amazon.com', 'ebay.com', 'walmart.com', 'target.com', 'shopify.com'}
    forum_domains = {'reddit.com', 'quora.com', 'stackexchange.com', 'stackoverflow.com'}
    video_domains = {'youtube.com', 'vimeo.com', 'dailymotion.com'}

    for r in results:
        domain = extract_domains([r])
        if not domain:
            categories['other'] += 1
            continue

        d = domain[0]
        if any(social in d for social in social_domains):
            categories['social'] += 1
        elif any(review in d for review in review_domains):
            categories['review'] += 1
        elif any(news in d for news in news_domains):
            categories['news'] += 1
        elif any(ecom in d for ecom in ecommerce_domains):
            categories['ecommerce'] += 1
        elif any(forum in d for forum in forum_domains):
            categories['forum'] += 1
        elif any(video in d for video in video_domains):
            categories['video'] += 1
        else:
            categories['other'] += 1

    return categories


def print_comparison_table(brave_results: List[Dict[str, str]], serper_results: List[Dict[str, str]], max_show: int = 10):
    """Print side-by-side comparison of results."""
    print("\n" + "="*100)
    print("SIDE-BY-SIDE COMPARISON (Top Results)")
    print("="*100)

    print(f"\n{'#':<3} {'BRAVE':<45} {'SERPER':<45}")
    print("-" * 100)

    max_results = max(len(brave_results), len(serper_results))
    for i in range(min(max_results, max_show)):
        brave_title = brave_results[i]['title'][:42] + "..." if i < len(brave_results) else ""
        serper_title = serper_results[i]['title'][:42] + "..." if i < len(serper_results) else ""

        # Check if same URL
        same_url = ""
        if (i < len(brave_results) and i < len(serper_results) and
            brave_results[i]['url'].lower() == serper_results[i]['url'].lower()):
            same_url = " [SAME]"

        print(f"{i+1:<3} {brave_title:<45} {serper_title:<45}{same_url}")


def run_comparison(brand: str, num_queries: int = 3, results_per_query: int = 10):
    """Run complete comparison between Brave and Serper."""

    # Generate test queries
    queries = [
        f"{brand}",
        f"{brand} review",
        f"{brand} customer reviews",
        f"{brand} complaints",
        f"{brand} reddit",
    ][:num_queries]

    print("="*100)
    print(f"SEARCH PROVIDER COMPARISON: {brand}")
    print("="*100)
    print(f"\nTest Configuration:")
    print(f"  Brand: {brand}")
    print(f"  Queries: {num_queries}")
    print(f"  Results per query: {results_per_query}")
    print(f"  Total API calls: {num_queries * 2} ({num_queries} per provider)")
    print()

    all_brave_results = []
    all_serper_results = []
    brave_times = []
    serper_times = []

    for i, query in enumerate(queries, 1):
        print(f"\nQuery {i}/{num_queries}: \"{query}\"")

        # Test Brave
        brave_results, brave_time = test_provider('brave', query, results_per_query)
        all_brave_results.extend(brave_results)
        brave_times.append(brave_time)

        # Test Serper
        serper_results, serper_time = test_provider('serper', query, results_per_query)
        all_serper_results.extend(serper_results)
        serper_times.append(serper_time)

        # Quick comparison for this query
        if brave_results and serper_results:
            overlap = analyze_url_overlap(brave_results, serper_results)
            print(f"  → URL Overlap: {overlap['overlap_count']}/{len(brave_results)} ({overlap['overlap_percent']:.1f}%)")

    # Overall performance comparison
    print("\n" + "="*100)
    print("PERFORMANCE COMPARISON")
    print("="*100)

    avg_brave_time = sum(brave_times) / len(brave_times) if brave_times else 0
    avg_serper_time = sum(serper_times) / len(serper_times) if serper_times else 0

    print(f"\nAverage Response Time:")
    print(f"  Brave:  {avg_brave_time:.2f}s per query")
    print(f"  Serper: {avg_serper_time:.2f}s per query")

    if avg_brave_time > 0 and avg_serper_time > 0:
        if avg_serper_time < avg_brave_time:
            speedup = ((avg_brave_time - avg_serper_time) / avg_brave_time) * 100
            print(f"  → Serper is {speedup:.1f}% faster")
        else:
            slowdown = ((avg_serper_time - avg_brave_time) / avg_serper_time) * 100
            print(f"  → Brave is {slowdown:.1f}% faster")

    # URL overlap analysis
    if all_brave_results and all_serper_results:
        print("\n" + "="*100)
        print("QUALITY COMPARISON")
        print("="*100)

        overlap = analyze_url_overlap(all_brave_results, all_serper_results)
        print(f"\nURL Coverage:")
        print(f"  Total Brave results:  {len(all_brave_results)}")
        print(f"  Total Serper results: {len(all_serper_results)}")
        print(f"  Overlapping URLs:     {overlap['overlap_count']} ({overlap['overlap_percent']:.1f}%)")
        print(f"  Brave-only URLs:      {overlap['brave_only']}")
        print(f"  Serper-only URLs:     {overlap['serper_only']}")
        print(f"  Total unique URLs:    {overlap['total_unique']}")

        # Domain diversity
        diversity = analyze_domain_diversity(all_brave_results, all_serper_results)
        print(f"\nDomain Diversity:")
        print(f"  Brave unique domains:  {diversity['brave_unique_domains']}")
        print(f"  Serper unique domains: {diversity['serper_unique_domains']}")

        # Content categories
        brave_categories = categorize_urls(all_brave_results)
        serper_categories = categorize_urls(all_serper_results)

        print(f"\nContent Categories (Brave):")
        for cat, count in brave_categories.items():
            if count > 0:
                print(f"  {cat.capitalize()}: {count}")

        print(f"\nContent Categories (Serper):")
        for cat, count in serper_categories.items():
            if count > 0:
                print(f"  {cat.capitalize()}: {count}")

        # Show first query comparison
        if queries:
            first_brave = [r for r in all_brave_results[:results_per_query]]
            first_serper = [r for r in all_serper_results[:results_per_query]]
            if first_brave and first_serper:
                print_comparison_table(first_brave, first_serper, max_show=5)

    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)

    if not all_serper_results:
        print("\n⚠️  Serper API failed - check your SERPER_API_KEY")
        print("→ Stay with Brave for now")
    elif not all_brave_results:
        print("\n⚠️  Brave API failed - check your BRAVE_API_KEY")
        print("→ Consider switching to Serper")
    else:
        print("\n✓ Both providers working correctly")

        # Decision factors
        factors = []

        if avg_serper_time < avg_brave_time * 0.8:
            factors.append("Serper is significantly faster")
        elif avg_brave_time < avg_serper_time * 0.8:
            factors.append("Brave is significantly faster")

        if overlap['overlap_percent'] > 70:
            factors.append("High result overlap - similar quality")
        elif overlap['overlap_percent'] < 40:
            factors.append("Low result overlap - different perspectives")

        if len(all_serper_results) > len(all_brave_results) * 1.2:
            factors.append("Serper returns more results")

        print("\nKey Findings:")
        for factor in factors:
            print(f"  • {factor}")

        print("\n💡 Recommendation:")
        if avg_serper_time < avg_brave_time and overlap['overlap_percent'] > 60:
            print("  → SWITCH TO SERPER - Faster with comparable quality")
        elif overlap['overlap_percent'] > 80:
            print("  → EITHER PROVIDER - Nearly identical results")
        else:
            print("  → TEST MORE - Results differ significantly, try more queries")

        print("\nCost Consideration:")
        print("  Brave: ~$0.50-1.00 per 1,000 searches (varies by plan)")
        print("  Serper: ~$0.30 per 1,000 searches")
        print("  → Serper is typically 40-70% cheaper")

    print("\n" + "="*100)


def main():
    parser = argparse.ArgumentParser(
        description='Compare Brave and Serper search providers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_search_comparison.py "Nike"
  python test_search_comparison.py "Tesla" --queries 5 --results 20
  python test_search_comparison.py "Apple iPhone" --queries 3
        """
    )

    parser.add_argument('brand', help='Brand name to search for')
    parser.add_argument('--queries', type=int, default=3,
                       help='Number of test queries (default: 3)')
    parser.add_argument('--results', type=int, default=10,
                       help='Results per query (default: 10)')

    args = parser.parse_args()

    # Validate environment
    if not os.getenv('SERPER_API_KEY'):
        print("⚠️  SERPER_API_KEY not found in environment")
        print("   Add it to your .env file to test Serper")
        print()

    if not os.getenv('BRAVE_API_KEY'):
        print("⚠️  BRAVE_API_KEY not found in environment")
        print("   Brave tests may fail")
        print()

    try:
        run_comparison(args.brand, args.queries, args.results)
    except KeyboardInterrupt:
        print("\n\nComparison interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
