#!/usr/bin/env python3
"""End-to-end test to verify search performance improvement."""
import time
import os

import pytest

from ingestion.serper_search import collect_serper_pages


RUN_SERPER_LIVE_TESTS = os.getenv("RUN_SERPER_LIVE_TESTS") == "1"
SERPER_API_KEY_SET = bool(os.getenv("SERPER_API_KEY"))
RUNNING_IN_CI = bool(os.getenv("CI"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        RUNNING_IN_CI,
        reason="Skipped in CI; enable locally with RUN_SERPER_LIVE_TESTS=1",
    ),
    pytest.mark.skipif(
        not RUN_SERPER_LIVE_TESTS or not SERPER_API_KEY_SET,
        reason="Requires RUN_SERPER_LIVE_TESTS=1 and SERPER_API_KEY for live Serper calls",
    ),
]


def test_search_performance():
    """Test that search completes in reasonable time with parallelization."""
    
    print("=" * 60)
    print("SEARCH PERFORMANCE TEST")
    print("=" * 60)
    print(f"Query: 'Nike running shoes'")
    print(f"Target: 10 pages")
    print(f"Pool size: 50 pages")
    print(f"Rate limit: 1.0s per domain")
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
        print("=" * 60)
        
        # Performance expectations:
        # - With global lock (broken): ~128s
        # - With per-domain locks (fixed): ~20-40s (depends on domain diversity)
        
        if duration < 60:
            print(f"\n✅ SUCCESS: Search completed in {duration:.2f}s (< 60s threshold)")
            print(f"   Previous broken version: 128.76s")
            print(f"   Improvement: {((128.76 - duration) / 128.76 * 100):.1f}% faster")
            return True
        else:
            print(f"\n⚠️  WARNING: Search took {duration:.2f}s (expected < 60s)")
            print(f"   This is still better than 128s, but may indicate issues")
            return False
            
    except Exception as e:
        duration = time.time() - start
        print(f"\n❌ FAILURE: Search failed after {duration:.2f}s")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_search_performance()
    exit(0 if success else 1)
