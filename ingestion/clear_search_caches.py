#!/usr/bin/env python3
"""
Utility to clear all search-related caches for accurate performance testing.

This clears:
- HTTP session cache (connection pooling)
- Robots.txt cache
- Domain configuration cache (Playwright requirements)
- Streamlit session state (if running in Streamlit context)
"""

def clear_all_search_caches():
    """Clear all caches used by the search system."""
    
    print("Clearing all search-related caches...")
    
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
    
    # 3. Clear domain config cache (Playwright requirements)
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
    
    # 5. Clear Streamlit session state (if in Streamlit context)
    try:
        import streamlit as st
        # Clear brand domain cache
        keys_to_clear = [k for k in st.session_state.keys() if k.startswith('brand_domains_')]
        for key in keys_to_clear:
            del st.session_state[key]
        if keys_to_clear:
            print(f"✓ Cleared {len(keys_to_clear)} Streamlit session cache(s)")
    except ImportError:
        # Not in Streamlit context, skip
        pass
    except Exception as e:
        print(f"⚠ Could not clear Streamlit session state: {e}")
    
    print("\n✅ Cache clearing complete!")
    print("Note: This only clears in-memory caches. Persistent browser state is not affected.")


if __name__ == '__main__':
    clear_all_search_caches()
