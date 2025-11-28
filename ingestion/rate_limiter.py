"""Per-domain rate limiter for web scraping.

Provides thread-safe rate limiting on a per-domain basis to avoid overwhelming
individual servers while allowing parallel requests to different domains.
"""
import time
import threading
from urllib.parse import urlparse
from typing import Dict


class PerDomainRateLimiter:
    """Thread-safe per-domain rate limiter.
    
    Tracks the last request time for each domain and enforces a minimum
    interval between requests to the same domain. Requests to different
    domains can proceed in parallel without waiting.
    
    Usage:
        limiter = PerDomainRateLimiter(default_interval=2.0)
        limiter.wait_for_domain('https://example.com/page1')  # No wait (first request)
        limiter.wait_for_domain('https://other.com/page')     # No wait (different domain)
        limiter.wait_for_domain('https://example.com/page2')  # Waits if < 2s since last example.com request
    """
    
    def __init__(self, default_interval: float = 2.0):
        """Initialize the rate limiter.
        
        Args:
            default_interval: Minimum seconds between requests to the same domain
        """
        self._domain_last_request: Dict[str, float] = {}
        self._domain_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # Lock for managing the locks dictionary
        self._default_interval = default_interval
    
    def wait_for_domain(self, url: str) -> None:
        """Wait if necessary before making a request to this URL's domain.
        
        Args:
            url: The URL to be requested. Domain is extracted from this URL.
        """
        if self._default_interval <= 0:
            return
        
        # Extract domain from URL
        try:
            domain = urlparse(url).netloc
            if not domain:
                return  # Invalid URL, no rate limiting
        except Exception:
            return  # Failed to parse URL, no rate limiting
        
        # Get or create a lock for this specific domain
        with self._locks_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = threading.Lock()
            domain_lock = self._domain_locks[domain]
        
        # Acquire the domain-specific lock and calculate sleep time
        with domain_lock:
            last_time = self._domain_last_request.get(domain, 0)
            now = time.monotonic()
            elapsed = now - last_time
            
            if elapsed < self._default_interval:
                sleep_time = self._default_interval - elapsed
            else:
                sleep_time = 0
            
            # Update timestamp BEFORE sleeping (reserve this slot)
            self._domain_last_request[domain] = now + sleep_time
        
        # Sleep OUTSIDE the lock to allow other domains to proceed in parallel
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    def reset(self) -> None:
        """Clear all domain tracking. Useful for testing."""
        with self._locks_lock:
            self._domain_last_request.clear()
            self._domain_locks.clear()
