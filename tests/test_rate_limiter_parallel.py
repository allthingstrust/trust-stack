#!/usr/bin/env python3
"""Quick test to verify the rate limiter fix allows parallel requests"""
import time
import threading
from ingestion.rate_limiter import PerDomainRateLimiter

def test_parallel_domains():
    """Test that different domains can be fetched in parallel"""
    limiter = PerDomainRateLimiter(default_interval=2.0)
    
    results = []
    
    def fetch_domain(domain_url, delay=0):
        time.sleep(delay)  # Stagger the starts
        start = time.time()
        limiter.wait_for_domain(domain_url)
        elapsed = time.time() - start
        results.append({
            'domain': domain_url,
            'wait_time': elapsed,
            'timestamp': time.time()
        })
        print(f"✓ {domain_url}: waited {elapsed:.2f}s")
    
    # Test 1: Same domain should be rate limited (sequential)
    print("\n=== Test 1: Same domain (should be sequential) ===")
    results.clear()
    start = time.time()
    
    threads = [
        threading.Thread(target=fetch_domain, args=('https://example.com/page1',)),
        threading.Thread(target=fetch_domain, args=('https://example.com/page2', 0.1)),
        threading.Thread(target=fetch_domain, args=('https://example.com/page3', 0.2)),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    total_time = time.time() - start
    print(f"Total time for 3 requests to same domain: {total_time:.2f}s")
    print(f"Expected: ~4s (0s + 2s + 2s), Actual: {total_time:.2f}s")
    
    # Test 2: Different domains should be parallel (no waiting)
    print("\n=== Test 2: Different domains (should be parallel) ===")
    results.clear()
    start = time.time()
    
    threads = [
        threading.Thread(target=fetch_domain, args=('https://domain1.com/page',)),
        threading.Thread(target=fetch_domain, args=('https://domain2.com/page',)),
        threading.Thread(target=fetch_domain, args=('https://domain3.com/page',)),
        threading.Thread(target=fetch_domain, args=('https://domain4.com/page',)),
        threading.Thread(target=fetch_domain, args=('https://domain5.com/page',)),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    total_time = time.time() - start
    print(f"Total time for 5 requests to different domains: {total_time:.2f}s")
    print(f"Expected: <0.5s (parallel), Actual: {total_time:.2f}s")
    
    if total_time < 1.0:
        print("\n✅ SUCCESS: Different domains are being fetched in parallel!")
        return True
    else:
        print(f"\n❌ FAILURE: Different domains took {total_time:.2f}s (should be <1s)")
        return False

if __name__ == '__main__':
    success = test_parallel_domains()
    exit(0 if success else 1)
