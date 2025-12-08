"""Serper API search module

Provides a wrapper to query Serper's Google Search API and return structured results.
Serper offers a cost-effective alternative to direct Google Search API with generous rate limits.

API Documentation: https://serper.dev/
Pricing: ~$0.30 per 1,000 searches (free tier: 2,500 searches)
"""
from __future__ import annotations

import logging
import requests
import os
import time
import threading
from typing import List, Dict, Optional
from config.settings import get_secret

logger = logging.getLogger(__name__)

# Per-domain rate limiting (allows parallel requests to different domains)
from ingestion.rate_limiter import PerDomainRateLimiter
_rate_limiter = PerDomainRateLimiter(
    default_interval=float(os.getenv('SERPER_REQUEST_INTERVAL', '1.0'))
)


def search_serper(query: str, size: int = 10, start_page: int = 1) -> List[Dict[str, str]]:
    """Search using Serper API and return a list of result dicts {title, url, snippet}

    Args:
        query: Search query string
        size: Number of results to retrieve (max 100 per request)

    Returns:
        List of dicts with keys: title, url, snippet

    Raises:
        ValueError: If SERPER_API_KEY is not configured
        requests.exceptions.RequestException: If API request fails
    """
    api_key = get_secret('SERPER_API_KEY')
    if not api_key:
        raise ValueError(
            "SERPER_API_KEY not found in environment. "
            "Get your key at https://serper.dev/ and add it to .env"
        )

    # Serper API endpoint
    endpoint = "https://google.serper.dev/search"

    # Serper's actual per-page limit is 10 results (despite documentation suggesting 100)
    # To get more results, we need to paginate through multiple pages
    results_per_page = 10
    max_per_request = min(int(os.getenv('SERPER_MAX_PER_REQUEST', '100')), 100)

    all_results = []
    page = start_page
    max_pages = start_page + (size + results_per_page - 1) // results_per_page  # Calculate pages needed
    max_pages = min(max_pages, start_page + 10)  # Safety limit for pagination

    while len(all_results) < size and page <= max_pages:
        # Calculate how many results we still need
        remaining = size - len(all_results)
        # Request 10 results per page (Serper's page size)
        batch_size = min(remaining, results_per_page)

        # Prepare request payload
        payload = {
            "q": query,
            "num": results_per_page,  # Always request 10 per page
        }

        # Add pagination if not the first page
        if page > 1:
            # Serper uses page number for pagination
            payload["page"] = page

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }

        logger.info(
            'Serper API request: query=%s, batch_size=%s, page=%s (collected: %s/%s)',
            query, batch_size, page, len(all_results), size
        )

        try:
            # Apply rate limiting
            _rate_limiter.wait_for_domain(endpoint)

            # Make API request
            timeout = int(os.getenv('SERPER_API_TIMEOUT', '30'))
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()

                # Serper returns results in 'organic' field
                organic_results = data.get('organic', [])

                if not organic_results:
                    logger.warning('Serper API returned no organic results for query: %s', query)
                    break

                # Extract results in the expected format
                for item in organic_results:
                    title = item.get('title', '')
                    url = item.get('link', '')
                    snippet = item.get('snippet', '')

                    if url and url.startswith('http'):
                        all_results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet
                        })

                logger.info('Serper API batch returned %s results', len(organic_results))

                # Stop if we have enough results
                if len(all_results) >= size:
                    logger.info('Collected enough results: %s/%s', len(all_results), size)
                    break

                # Only stop if we got zero results (no more results available)
                if len(organic_results) == 0:
                    logger.info('Serper API returned zero results - no more results available')
                    break

            elif response.status_code == 401:
                logger.error('Serper API authentication failed - check your SERPER_API_KEY')
                raise ValueError('Invalid Serper API key')

            elif response.status_code == 429:
                logger.error('Serper API rate limit exceeded')
                raise requests.exceptions.RequestException('Serper API rate limit exceeded')

            else:
                logger.error('Serper API request failed: HTTP %s. Response: %s',
                           response.status_code, response.text[:500])
                break

        except requests.exceptions.Timeout:
            logger.error('Serper API request timed out for query: %s', query)
            break

        except requests.exceptions.RequestException as e:
            logger.error('Serper API request failed: %s', str(e))
            raise

        except Exception as e:
            logger.error('Unexpected error during Serper API request: %s', str(e))
            break

        page += 1

    logger.info('Serper search completed: collected %s results for query: %s', len(all_results), query)
    return all_results[:size]  # Ensure we don't return more than requested


def collect_serper_pages(
    query: str,
    target_count: int = 10,
    pool_size: int | None = None,
    min_body_length: int = 200,
    min_brand_body_length: int | None = None,
    url_collection_config: 'URLCollectionConfig' | None = None
) -> List[Dict[str, str]]:
    """Collect up to `target_count` successfully fetched pages from Serper search.

    Uses a Producer-Consumer pattern:
    - Main thread (Producer): Fetches search results and pushes them to a queue.
    - Worker threads (Consumers): Fetch page content and process results.
    """
    import queue
    import threading
    from concurrent.futures import ThreadPoolExecutor
    
    # Import fetch_page from page_fetcher module
    from ingestion.page_fetcher import fetch_page

    # Dynamic Pool Sizing Configuration
    initial_multiplier = 2
    max_total_results = pool_size if pool_size is not None else max(30, target_count * 5)
    current_batch_size = target_count * initial_multiplier
    
    current_page = 1
    
    # Shared state
    # Use bounded queue to prevent producer from flooding memory if consumers are slow
    url_queue = queue.Queue(maxsize=max_total_results if max_total_results < 100 else 50)
    results_lock = threading.Lock()
    stop_event = threading.Event()
    seen_urls = set()
    
    # Collections
    brand_owned_collected: List[Dict[str, str]] = []
    third_party_collected: List[Dict[str, str]] = []
    
    # Domain diversity tracking
    from urllib.parse import urlparse
    domain_counts: Dict[str, int] = {}
    
    # Adjust domain limits based on collection strategy
    if url_collection_config and url_collection_config.brand_owned_ratio >= 0.8:
        # Brand-controlled search: allow many pages per domain
        # We WANT multiple pages from the brand's domains (nike.com, about.nike.com, etc.)
        max_per_domain = target_count  # No effective limit
        logger.info('[SERPER] Brand-controlled search: disabled domain diversity limits (max_per_domain=%d)', max_per_domain)
    else:
        # Third-party or mixed search: enforce diversity to avoid over-sampling one domain
        max_per_domain = max(1, int(target_count * 0.2))
        logger.info('[SERPER] Mixed search: enforcing domain diversity (max_per_domain=%d)', max_per_domain)

    
    # Stats
    stats = {
        'total_processed': 0,
        'total_fetched': 0,
        'total_valid': 0,
        'no_url': 0,
        'thin_content': 0,
        'brand_owned_pool_full': 0,
        'third_party_pool_full': 0,
        'domain_limit_reached': 0,
        'error_page': 0,
        'processed': 0
    }
    
    # Ratio targets
    target_brand_owned = target_count
    target_third_party = 0
    if url_collection_config:
        target_brand_owned = int(target_count * url_collection_config.brand_owned_ratio)
        target_third_party = int(target_count * url_collection_config.third_party_ratio)
        if target_brand_owned + target_third_party < target_count:
            if url_collection_config.brand_owned_ratio >= url_collection_config.third_party_ratio:
                target_brand_owned += (target_count - target_brand_owned - target_third_party)
            else:
                target_third_party += (target_count - target_brand_owned - target_third_party)
    
    # Default brand threshold
    if min_brand_body_length is None:
        min_brand_body_length = 75

    if url_collection_config:
        from ingestion.domain_classifier import classify_url, URLSourceType

    logger.info('[SERPER] Starting concurrent collection for query=%s (target=%d)', query, target_count)

    # Capture Streamlit context in main thread BEFORE workers start
    # (get_script_run_ctx() only works in the main thread, not in workers)
    streamlit_ctx = None
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
        streamlit_ctx = get_script_run_ctx()
    except ImportError:
        pass
    except Exception:
        pass

    def worker():
        """Worker function that processes URLs from the queue.
        
        Attaches Streamlit context to suppress warnings in worker threads.
        """
        # Attach Streamlit context to this worker thread to suppress warnings
        # Context was captured in main thread and is available via closure
        if streamlit_ctx:
            try:
                from streamlit.runtime.scriptrunner_utils.script_run_context import add_script_run_ctx
                add_script_run_ctx(threading.current_thread(), streamlit_ctx)
            except Exception:
                # Context attachment failed, continue without it
                pass
        
        while True:
            try:
                item = url_queue.get(timeout=0.5)
            except queue.Empty:
                if stop_event.is_set():
                    break
                continue
            
            try:
                with results_lock:
                    if len(brand_owned_collected) + len(third_party_collected) >= target_count:
                        continue
                    stats['processed'] += 1
                    stats['total_processed'] += 1

                url = item.get('url')
                if not url:
                    with results_lock: stats['no_url'] += 1
                    continue

                # Classify
                is_brand_owned = False
                classification = None
                if url_collection_config:
                    classification = classify_url(url, url_collection_config)
                    is_brand_owned = classification.source_type == URLSourceType.BRAND_OWNED

                # Fetch
                with results_lock: stats['total_fetched'] += 1
                content = fetch_page(url, browser_manager=browser_manager)
                body = content.get('body') or ''
                required_length = min_brand_body_length if is_brand_owned else min_body_length
                
                if body and len(body) >= required_length:
                    # Check error page
                    title = content.get('title', '').lower()
                    error_indicators = ['access denied', 'forbidden', '403', '401', 'error', 'not found', '404']
                    if any(indicator in title for indicator in error_indicators):
                        with results_lock: stats['error_page'] += 1
                        continue

                    with results_lock:
                        # Re-check limits
                        if len(brand_owned_collected) + len(third_party_collected) >= target_count:
                            continue

                        # Check pools
                        if url_collection_config:
                            if is_brand_owned and len(brand_owned_collected) >= target_brand_owned:
                                stats['brand_owned_pool_full'] += 1
                                continue
                            if not is_brand_owned and len(third_party_collected) >= target_third_party:
                                stats['third_party_pool_full'] += 1
                                continue
                        elif len(brand_owned_collected) + len(third_party_collected) >= target_count:
                            continue

                        # Check diversity
                        parsed_url = urlparse(url)
                        domain = parsed_url.netloc.lower()
                        if domain_counts.get(domain, 0) >= max_per_domain:
                            stats['domain_limit_reached'] += 1
                            continue

                        # Add
                        if url_collection_config:
                            content['source_type'] = classification.source_type.value
                            content['source_tier'] = classification.tier.value if classification.tier else 'unknown'
                            if is_brand_owned:
                                brand_owned_collected.append(content)
                            else:
                                third_party_collected.append(content)
                        else:
                            brand_owned_collected.append(content)

                        domain_counts[domain] = domain_counts.get(domain, 0) + 1
                        stats['total_valid'] += 1
                        
                        logger.info('[SERPER] Collected page %d/%d: %s', 
                                   len(brand_owned_collected) + len(third_party_collected), 
                                   target_count, url)
                else:
                    with results_lock: stats['thin_content'] += 1

            except Exception as e:
                logger.error('Worker error processing %s: %s', url, e)
            finally:
                url_queue.task_done()

    # Initialize persistent Playwright browser if available
    browser_manager = None
    try:
        from ingestion.playwright_manager import get_browser_manager
        browser_manager = get_browser_manager()
        if browser_manager.start():
            logger.info('[SERPER] Initialized persistent Playwright browser')
        else:
            browser_manager = None
    except Exception as e:
        logger.debug('[SERPER] Could not start persistent browser: %s', e)
        browser_manager = None
    except ImportError:
        logger.debug('[SERPER] PlaywrightBrowserManager not available')

    try:
        # Start workers - context is attached inside worker function
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit worker tasks directly (context attachment happens inside worker)
            futures = [executor.submit(worker) for _ in range(5)]
            
            # Producer Loop
            while not stop_event.is_set():
                # Check if done
                with results_lock:
                    if len(brand_owned_collected) + len(third_party_collected) >= target_count:
                        logger.info('[SERPER] Target reached, stopping producer')
                        stop_event.set()
                        break
                    if stats['total_processed'] >= max_total_results:
                        logger.info('[SERPER] Max total results reached, stopping producer')
                        stop_event.set()
                        break

                logger.info('[SERPER] Fetching search batch: size=%d, start_page=%d', current_batch_size, current_page)
                try:
                    search_results = search_serper(query, size=current_batch_size, start_page=current_page)
                except Exception as e:
                    logger.warning('Serper search failed: %s', e)
                    break
                    
                if not search_results:
                    logger.info('[SERPER] No more search results available')
                    break
                    
                # Update pagination
                pages_in_batch = (len(search_results) + 9) // 10
                current_page += pages_in_batch
                
                # Push to queue
                for item in search_results:
                    url = item.get('url')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        url_queue.put(item)
                
                # Dynamic Sizing
                with results_lock:
                    success_rate = stats['total_valid'] / stats['total_fetched'] if stats['total_fetched'] > 0 else 0
                
                if success_rate < 0.3 and stats['total_fetched'] > 5:
                    current_batch_size = target_count * 2
                elif success_rate > 0.6 and stats['total_fetched'] > 5:
                    with results_lock:
                        needed = target_count - (len(brand_owned_collected) + len(third_party_collected))
                    current_batch_size = max(10, int(needed / (success_rate or 0.1)) + 5)
                else:
                    current_batch_size = target_count
                
                time.sleep(0.1)

            stop_event.set()

        collected = brand_owned_collected + third_party_collected
        logger.info('[SERPER] Collection complete. Collected: %d. Stats: %s', len(collected), stats)
        return collected
    finally:
        # Do NOT close the singleton browser manager here. Let it persist.
        # if browser_manager:
        #     try:
        #         browser_manager.close()
        #         logger.info('[SERPER] Stopped persistent Playwright browser')
        #     except Exception as e:
        #         logger.warning('[SERPER] Error stopping browser: %s', e)
        pass


def get_serper_stats() -> Dict[str, any]:
    """Get current Serper API usage statistics.

    Returns:
        Dict with usage statistics from Serper API

    Note: This requires a valid API key and may not be available on all plans.
    """
    api_key = get_secret('SERPER_API_KEY')
    if not api_key:
        return {"error": "SERPER_API_KEY not configured"}

    try:
        account_url = "https://google.serper.dev/account"
        _rate_limiter.wait_for_domain(account_url)
        response = requests.get(
            account_url,
            headers={"X-API-KEY": api_key},
            timeout=10
        )

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error('Failed to get Serper stats: %s', str(e))
        return {"error": str(e)}
