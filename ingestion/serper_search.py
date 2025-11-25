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

logger = logging.getLogger(__name__)

# Rate limiting: minimum interval (seconds) between Serper API requests
_SERPER_REQUEST_INTERVAL = float(os.getenv('SERPER_REQUEST_INTERVAL', '1.0'))
_LAST_SERPER_REQUEST_TS = 0.0
_SERPER_RATE_LOCK = threading.Lock()


def _wait_for_rate_limit():
    """Ensure at least _SERPER_REQUEST_INTERVAL seconds between requests."""
    global _LAST_SERPER_REQUEST_TS
    if _SERPER_REQUEST_INTERVAL <= 0:
        return
    with _SERPER_RATE_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_SERPER_REQUEST_TS
        if elapsed < _SERPER_REQUEST_INTERVAL:
            to_sleep = _SERPER_REQUEST_INTERVAL - elapsed
            time.sleep(to_sleep)
        _LAST_SERPER_REQUEST_TS = time.monotonic()


def search_serper(query: str, size: int = 10) -> List[Dict[str, str]]:
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
    api_key = os.getenv('SERPER_API_KEY')
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
    page = 1
    max_pages = (size + results_per_page - 1) // results_per_page  # Calculate pages needed
    max_pages = min(max_pages, 10)  # Safety limit for pagination

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
            _wait_for_rate_limit()

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

    Behavior:
    - Request `pool_size` search results (defaults to max(30, target_count*3)).
    - If url_collection_config is provided, enforces brand-owned vs 3rd party ratio
    - Iterate results in order and fetch page content
    - Only count pages whose `body` length >= min_body_length as successful
    - Brand-owned URLs can use a lower threshold (min_brand_body_length) if specified
    - Stop once `target_count` successful pages are collected or the pool is exhausted

    Args:
        query: Search query
        target_count: Target number of pages to collect
        pool_size: Number of search results to request
        min_body_length: Minimum body length for third-party pages (default: 200)
        min_brand_body_length: Minimum body length for brand-owned pages (default: 75, filters error pages)
        url_collection_config: Optional ratio enforcement configuration

    Returns:
        List of dicts with page content {title, body, url, ...}
    """
    # Import fetch_page from brave_search module
    from ingestion.brave_search import fetch_page

    if pool_size is None:
        # Use 5x multiplier to account for access-denied URLs and content filtering
        pool_size = max(30, target_count * 5)

    # Default brand threshold to 75 bytes if not specified
    # This filters out error pages while allowing landing pages with minimal text
    if min_brand_body_length is None:
        min_brand_body_length = 75

    # Import classifier here to avoid circular imports
    if url_collection_config:
        from ingestion.domain_classifier import classify_url, URLSourceType

    # Let exceptions bubble up so the caller knows if configuration is wrong
    search_results = search_serper(query, size=pool_size)
    logger.info('[SERPER] Requested pool_size=%d, received %d search results for query=%s',
               pool_size, len(search_results), query)

    if not search_results:
        logger.warning('[SERPER] No search results returned, returning empty list')
        return []

    # Ratio enforcement: track separate pools if config provided
    if url_collection_config:
        target_brand_owned = int(target_count * url_collection_config.brand_owned_ratio)
        target_third_party = int(target_count * url_collection_config.third_party_ratio)

        # Handle rounding to ensure we hit exact target_count
        if target_brand_owned + target_third_party < target_count:
            if url_collection_config.brand_owned_ratio >= url_collection_config.third_party_ratio:
                target_brand_owned += (target_count - target_brand_owned - target_third_party)
            else:
                target_third_party += (target_count - target_brand_owned - target_third_party)

        brand_owned_collected: List[Dict[str, str]] = []
        third_party_collected: List[Dict[str, str]] = []

        # Track URLs per domain to enforce diversity (max 20% per domain)
        from urllib.parse import urlparse
        domain_counts: Dict[str, int] = {}
        max_per_domain = max(1, int(target_count * 0.2))  # 20% of target, minimum 1

        # Track skip reasons for debugging
        skip_stats = {
            'no_url': 0,
            'thin_content': 0,
            'brand_owned_pool_full': 0,
            'third_party_pool_full': 0,
            'domain_limit_reached': 0,
            'error_page': 0,
            'processed': 0
        }

        logger.info('[SERPER] Collecting with ratio enforcement: %d brand-owned (%.0f%%) + %d 3rd party (%.0f%%) from %d search results',
                   target_brand_owned, url_collection_config.brand_owned_ratio * 100,
                   target_third_party, url_collection_config.third_party_ratio * 100,
                   len(search_results))

        for item in search_results:
            skip_stats['processed'] += 1

            # Periodic progress update (every 50 URLs)
            if skip_stats['processed'] % 50 == 0:
                logger.info('[SERPER] Progress: Processed %d/%d results, collected %d/%d URLs (%d brand-owned, %d 3rd party)',
                           skip_stats['processed'], len(search_results),
                           len(brand_owned_collected) + len(third_party_collected), target_count,
                           len(brand_owned_collected), len(third_party_collected))

            # Stop if both pools are full
            if len(brand_owned_collected) >= target_brand_owned and len(third_party_collected) >= target_third_party:
                logger.info('[SERPER] Both pools full, breaking early at result %d/%d',
                           skip_stats['processed'], len(search_results))
                break

            url = item.get('url')
            if not url:
                skip_stats['no_url'] += 1
                continue

            # Classify the URL
            classification = classify_url(url, url_collection_config)
            is_brand_owned = classification.source_type == URLSourceType.BRAND_OWNED

            # Attempt to fetch and only count if body meets minimum length
            # Use lower threshold for brand-owned URLs (landing pages often have less text)
            content = fetch_page(url)
            body = content.get('body') or ''
            required_length = min_brand_body_length if is_brand_owned else min_body_length
            if body and len(body) >= required_length:
                # Filter out error pages based on title
                title = content.get('title', '').lower()
                error_indicators = ['access denied', 'forbidden', '403', '401', 'error', 'not found', '404']
                if any(indicator in title for indicator in error_indicators):
                    skip_stats['error_page'] += 1
                    logger.debug('[SERPER] Skipping %s - error page detected (title: "%s")',
                               url, content.get('title', '')[:50])
                    continue

                # Check if pools are full AFTER validating content.
                # Skip a URL if its specific pool is full.
                # This ensures proper filtering based on collection strategy:
                # - Brand-Controlled only: skips all 3rd party URLs (target_third_party=0)
                # - 3rd Party only: skips all brand-owned URLs (target_brand_owned=0)
                # - Balanced: allows both until their respective targets are met
                if is_brand_owned:
                    if len(brand_owned_collected) >= target_brand_owned:
                        skip_stats['brand_owned_pool_full'] += 1
                        logger.debug('[SERPER] Skipping brand-owned URL %s - pool full',
                                   url)
                        continue
                else:
                    if len(third_party_collected) >= target_third_party:
                        skip_stats['third_party_pool_full'] += 1
                        logger.debug('[SERPER] Skipping 3rd party URL %s - pool full',
                                   url)
                        continue

                # Check domain diversity limit (max 20% per domain)
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
                if domain_counts.get(domain, 0) >= max_per_domain:
                    skip_stats['domain_limit_reached'] += 1
                    logger.debug('[SERPER] Skipping %s - domain limit reached (%d/%d URLs from %s)',
                               url, domain_counts[domain], max_per_domain, domain)
                    continue

                # Add source type metadata
                content['source_type'] = classification.source_type.value
                content['source_tier'] = classification.tier.value if classification.tier else 'unknown'

                if is_brand_owned:
                    brand_owned_collected.append(content)
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                    logger.debug('[SERPER] ✓ Collected brand-owned page (%d/%d): %s [len=%d]',
                               len(brand_owned_collected), target_brand_owned, url, len(body))

                    # If we still need more brand-owned URLs, try extracting subpages
                    if len(brand_owned_collected) < target_brand_owned:
                        try:
                            from ingestion.brave_search import _extract_internal_links

                            # Get the raw HTML for link extraction
                            resp = requests.get(url, headers={
                                'User-Agent': os.getenv('AR_USER_AGENT',
                                    'Mozilla/5.0 (compatible; ar-bot/1.0)')
                            }, timeout=10)

                            if resp.status_code == 200:
                                subpage_urls = _extract_internal_links(url, resp.text, max_links=15)
                                logger.debug('[SERPER] Extracted %d internal links from %s',
                                           len(subpage_urls), url)

                                # Fetch and add subpages as brand-owned URLs
                                for subpage_url in subpage_urls:
                                    if len(brand_owned_collected) >= target_brand_owned:
                                        break

                                    try:
                                        # Check domain limit for subpage
                                        subpage_parsed = urlparse(subpage_url)
                                        subpage_domain = subpage_parsed.netloc.lower()
                                        if domain_counts.get(subpage_domain, 0) >= max_per_domain:
                                            logger.debug('[SERPER] Skipping subpage %s - domain limit reached', subpage_url)
                                            continue

                                        subpage_content = fetch_page(subpage_url)
                                        subpage_body = subpage_content.get('body') or ''

                                        # Subpages are brand-owned, use lower threshold
                                        if subpage_body and len(subpage_body) >= min_brand_body_length:
                                            subpage_content['source_type'] = 'brand_owned'
                                            subpage_content['source_tier'] = 'brand_subpage'
                                            brand_owned_collected.append(subpage_content)
                                            domain_counts[subpage_domain] = domain_counts.get(subpage_domain, 0) + 1
                                            logger.debug('[SERPER] ✓ Collected brand subpage (%d/%d): %s [len=%d]',
                                                       len(brand_owned_collected), target_brand_owned,
                                                       subpage_url, len(subpage_body))
                                        else:
                                            logger.debug('[SERPER] Skipping subpage %s - thin content', subpage_url)
                                    except Exception as e:
                                        logger.debug('[SERPER] Failed to fetch subpage %s: %s', subpage_url, e)
                        except Exception as e:
                            logger.debug('[SERPER] Failed to extract subpages from %s: %s', url, e)
                else:
                    third_party_collected.append(content)
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                    logger.debug('[SERPER] ✓ Collected 3rd party page (%d/%d): %s [len=%d]',
                               len(third_party_collected), target_third_party, url, len(body))
            else:
                skip_stats['thin_content'] += 1
                logger.debug('[SERPER] Skipping %s - thin/empty content (len=%s, min=%d) [%s]',
                           url, len(body), required_length,
                           'brand-owned' if is_brand_owned else '3rd party')

        # Combine results
        collected = brand_owned_collected + third_party_collected

        logger.info('[SERPER] ═══════════════════════════════════════════════════════════')
        logger.info('[SERPER] COLLECTION SUMMARY for query=%s', query)
        logger.info('[SERPER] ───────────────────────────────────────────────────────────')
        logger.info('[SERPER] Search results received: %d (requested pool_size: %d)',
                   len(search_results), pool_size)
        logger.info('[SERPER] Results processed: %d', skip_stats['processed'])
        logger.info('[SERPER] Target: %d total (%d brand-owned + %d 3rd party)',
                   target_count, target_brand_owned, target_third_party)
        logger.info('[SERPER] Collected: %d total (%d brand-owned + %d 3rd party)',
                   len(collected), len(brand_owned_collected), len(third_party_collected))
        logger.info('[SERPER] Domain diversity: %d unique domains (max %d URLs per domain)',
                   len(domain_counts), max_per_domain)
        logger.info('[SERPER] ───────────────────────────────────────────────────────────')
        logger.info('[SERPER] Skip reasons:')
        logger.info('[SERPER]   - No URL: %d', skip_stats['no_url'])
        logger.info('[SERPER]   - Thin/empty content (brand <%d bytes, 3rd party <%d bytes): %d',
                   min_brand_body_length, min_body_length, skip_stats['thin_content'])
        logger.info('[SERPER]   - Error page (Access Denied, 403, etc.): %d', skip_stats['error_page'])
        logger.info('[SERPER]   - Domain limit reached (max %d per domain): %d', max_per_domain, skip_stats['domain_limit_reached'])
        logger.info('[SERPER]   - Brand-owned pool full: %d', skip_stats['brand_owned_pool_full'])
        logger.info('[SERPER]   - 3rd party pool full: %d', skip_stats['third_party_pool_full'])
        logger.info('[SERPER] ═══════════════════════════════════════════════════════════')

    else:
        # Original behavior: no ratio enforcement
        collected: List[Dict[str, str]] = []
        for item in search_results:
            if len(collected) >= target_count:
                break
            url = item.get('url')
            if not url:
                continue

            # Attempt to fetch and only count if body meets minimum length
            content = fetch_page(url)
            body = content.get('body') or ''
            if body and len(body) >= min_body_length:
                collected.append(content)
            else:
                logger.debug('Skipping %s because content is thin or empty (len=%s)', url, len(body))

        if collected:
            logger.info('Collected %s/%s successful pages for query=%s', len(collected), target_count, query)
        else:
            logger.info('No usable pages collected for query=%s', query)

    return collected


def get_serper_stats() -> Dict[str, any]:
    """Get current Serper API usage statistics.

    Returns:
        Dict with usage statistics from Serper API

    Note: This requires a valid API key and may not be available on all plans.
    """
    api_key = os.getenv('SERPER_API_KEY')
    if not api_key:
        return {"error": "SERPER_API_KEY not configured"}

    try:
        _wait_for_rate_limit()
        response = requests.get(
            "https://google.serper.dev/account",
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
