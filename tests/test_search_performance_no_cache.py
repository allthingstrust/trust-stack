#!/usr/bin/env python3
"""End-to-end test to verify search performance WITHOUT caching.

This test clears all caches before running to get accurate performance metrics.
It is marked as an integration test and requires explicit opt-in plus a valid
SERPER_API_KEY to avoid accidental live calls in CI.
"""
import os
import time

import pytest

from ingestion.serper_search import collect_serper_pages

def clear_all_caches():
    """Clear all search-related caches for accurate testing."""
    print("\n" + "=" * 60)
    print("CLEARING ALL CACHES")
    print("=" * 60)
    
    # 1. Clear HTTP session cache
    try:
        from ingestion import page_fetcher
        with page_fetcher._SESSIONS_LOCK:
            count = len(page_fetcher._SESSIONS_CACHE)
            page_fetcher._SESSIONS_CACHE.clear()
            print(f"✓ Cleared {count} HTTP session(s)")
    except Exception as e:
        print(f"⚠ Could not clear HTTP sessions: {e}")
    
    # 2. Clear robots.txt cache
    try:
        from ingestion import page_fetcher
        count = len(page_fetcher._ROBOTS_CACHE)
        page_fetcher._ROBOTS_CACHE.clear()
        print(f"✓ Cleared {count} robots.txt cache(s)")
    except Exception as e:
        print(f"⚠ Could not clear robots.txt cache: {e}")
    
    # 3. Clear domain config cache
    try:
        from ingestion.page_fetcher import DomainConfigCache
        cache = DomainConfigCache.get_instance()
        count = len(cache._requires_playwright)
        cache._requires_playwright.clear()
        print(f"✓ Cleared {count} domain config(s)")
    except Exception as e:
        print(f"⚠ Could not clear domain config cache: {e}")
    
    # 4. Clear rate limiter state
    try:
        from ingestion import serper_search
        serper_search._rate_limiter.reset()
        print(f"✓ Reset rate limiter state")
    except Exception as e:
        print(f"⚠ Could not reset rate limiter: {e}")
    
    print("=" * 60 + "\n")


@pytest.mark.integration
@pytest.mark.skipif(
    not (os.getenv("SERPER_API_KEY") and os.getenv("RUN_SERPER_LIVE_TESTS") == "1"),
    reason="Requires RUN_SERPER_LIVE_TESTS=1 and SERPER_API_KEY for live Serper calls",
)
def test_search_performance_no_cache():
    """Test search performance with all caches cleared."""
    
    # Clear all caches first
    clear_all_caches()
    
    print("=" * 60)
    print("SEARCH PERFORMANCE TEST (NO CACHE)")
    print("=" * 60)
    print(f"Query: 'Nike running shoes'")
    print(f"Target: 10 pages")
    print(f"Pool size: 50 pages")
    print(f"Rate limit: 1.0s per domain")
    print(f"Caches: CLEARED (fresh start)")
    print("=" * 60)
    
    start = time.time()
    
    try:
        pages = collect_serper_pages(
            query='Nike running shoes',
            target_count=10,
            pool_size=50
        )
        
        duration = time.time() - start
        
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"✓ Collected: {len(pages)} pages")
        print(f"✓ Duration: {duration:.2f} seconds")
        print(f"✓ Throughput: {len(pages) / duration:.2f} pages/second")
        print("=" * 60)
        
        # Performance expectations (without caching):
        # - Should be slower than cached version
        # - But still much faster than the old global-lock version (128s)
        # - Expected: 40-60s (includes robots.txt fetches, session setup, etc.)
        
        print(f"\n📊 PERFORMANCE ANALYSIS:")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Previous (with cache): ~34.47s")
        print(f"   Previous (broken): 128.76s")
        
        if duration < 80:
            print(f"\n✅ SUCCESS: Search completed in {duration:.2f}s")
            print(f"   Still much faster than broken version (128.76s)")
            print(f"   Improvement: {((128.76 - duration) / 128.76 * 100):.1f}% faster")
            
            # Show cache impact
            cache_overhead = duration - 34.47
            if cache_overhead > 0:
                print(f"\n💡 Cache overhead: ~{cache_overhead:.2f}s")
                print(f"   This is the time saved by caching:")
                print(f"   - HTTP session pooling")
                print(f"   - Robots.txt caching")
                print(f"   - Domain config learning")
            
            return True
        else:
            print(f"\n⚠️  WARNING: Search took {duration:.2f}s")
            print(f"   Expected < 80s without caching")
            print(f"   May indicate performance regression")
            return False
            
    except Exception as e:
        duration = time.time() - start
        print(f"\n❌ FAILURE: Search failed after {duration:.2f}s")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_search_performance_no_cache()
    exit(0 if success else 1)
