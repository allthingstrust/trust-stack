"""Brave Search ingestion module

Provides a simple wrapper to query Brave Search (via their search endpoint) and fetch page content for selected URLs.

Note: Brave does not have a public REST API for search results like Google; this module uses the Brave Search HTML endpoint as a lightweight approach. In production, consider using a proper search API or a licensed data provider.
"""
from __future__ import annotations

import logging
import requests
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.parse import urlparse
import urllib.robotparser as robotparser
import os
import json
import time
import threading
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import fetch configuration module
from ingestion.fetch_config import (
    get_domain_config,
    get_random_delay,
    get_realistic_headers,
    should_use_playwright,
    get_retry_config,
)

# Per-domain rate limiting (allows parallel requests to different domains)
from ingestion.rate_limiter import PerDomainRateLimiter
_rate_limiter = PerDomainRateLimiter(
    default_interval=float(os.getenv('BRAVE_REQUEST_INTERVAL', '2.0'))
)

# Import page fetching functions from dedicated module
from ingestion.page_fetcher import fetch_page, _extract_internal_links

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://search.brave.com/search"


def search_brave(query: str, size: int = 10, start_offset: int = 0) -> List[Dict[str, str]]:
    """Search Brave and return a list of result dicts {title, url, snippet}

    For requests larger than the API's per-request limit, this function will
    automatically paginate through multiple requests to collect the desired number of results.
    """
    # If user has provided a Brave API key, prefer the API endpoint
    api_key = os.getenv('BRAVE_API_KEY')
    api_endpoint = os.getenv('BRAVE_API_ENDPOINT', 'https://api.search.brave.com/res/v1/web/search')
    headers = {
        "User-Agent": os.getenv('BRAVE_USER_AGENT', "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        # Default Accept for the module is browser-like; this will be overridden to 'application/json'
        # when calling the Brave API endpoint (the API validates the Accept header strictly).
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    if api_key:
        # Use a single auth method to avoid multiple attempts per logical search.
        # Configure via BRAVE_API_AUTH: 'x-api-key' (default), 'bearer', 'both', 'query-param', or 'subscription-token'
        api_auth = os.getenv('BRAVE_API_AUTH', 'subscription-token')
        # Some Brave API plans limit the maximum 'count' per request. Allow an env override
        # Most Brave API plans have a hard limit of 20 results per request.
        # Default to 20 to maximize results per request while staying within API limits.
        try:
            max_per_request = int(os.getenv('BRAVE_API_MAX_COUNT', '20'))
        except Exception:
            max_per_request = 20

        # If user wants more results than the API allows per request, we'll paginate
        all_results = []
        offset = start_offset
        pagination_attempts = 0
        max_pagination_attempts = 10  # Safety limit

        while len(all_results) < size and pagination_attempts < max_pagination_attempts:
            pagination_attempts += 1
            # Calculate how many results to request in this batch
            remaining = size - len(all_results)
            batch_size = min(remaining, max_per_request)

            params = {"q": query, "count": batch_size}

            # Brave API uses 'offset' parameter for pagination
            # Note: offset is the number of results to skip, not a page number
            if offset > 0:
                params["offset"] = offset

            logger.info('Brave API request: query=%s, batch_size=%s, offset=%s (total collected: %s/%s)',
                       query, batch_size, offset, len(all_results), size)

            # Prepare a results container for this batch
            batch_results = []
            try:
                hdrs = headers.copy()
                if api_auth == 'bearer':
                    hdrs['Authorization'] = f'Bearer {api_key}'
                elif api_auth == 'x-api-key':
                    hdrs['x-api-key'] = api_key
                elif api_auth == 'subscription-token':
                    # Brave uses X-Subscription-Token for the provided key in many cases
                    hdrs['X-Subscription-Token'] = api_key
                elif api_auth == 'both':
                    hdrs['Authorization'] = f'Bearer {api_key}'
                    hdrs['x-api-key'] = api_key

                logger.info('Using Brave API endpoint for query=%s (api_auth=%s)', query, api_auth)
                # Prepare request (if query-param auth, append below)
                _rate_limiter.wait_for_domain(BRAVE_SEARCH_URL)
                # Use helper-style retry for robustness
                # Allow timeout override via environment variable
                api_timeout = int(os.getenv('BRAVE_API_TIMEOUT', '10'))
                if api_auth == 'query-param':
                    params_with_key = params.copy()
                    params_with_key['apikey'] = api_key
                    # API expects JSON response; ensure Accept header is suitable for the API path
                    hdrs['Accept'] = hdrs.get('Accept', '*/*') if hdrs.get('Accept') == '*/*' else 'application/json'
                    resp = requests.get(api_endpoint, params=params_with_key, headers=hdrs, timeout=api_timeout)
                else:
                    hdrs['Accept'] = hdrs.get('Accept', '*/*') if hdrs.get('Accept') == '*/*' else 'application/json'
                    resp = requests.get(api_endpoint, params=params, headers=hdrs, timeout=api_timeout)

                if resp.status_code == 200:
                    try:
                        body = resp.json()
                    except Exception as e:
                        # resp.json() may raise AttributeError if the fake response doesn't implement it
                        logger.warning('Brave API returned non-JSON response: %s; breaking pagination', e)
                        break

                    if isinstance(body, dict):
                        # Log the structure for debugging
                        logger.debug('Brave API response keys: %s', list(body.keys()) if body else 'None')

                        # Preferred: Brave API uses body['web']['results'] for web search results
                        web_results = None
                        if 'web' in body and isinstance(body['web'], dict):
                            web_results = body['web'].get('results')
                            logger.debug('Found web.results with %s items', len(web_results) if isinstance(web_results, list) else 0)

                        if isinstance(web_results, list):
                            for item in web_results:
                                if not isinstance(item, dict):
                                    continue
                                url = item.get('url') or (item.get('meta_url') or {}).get('url') or item.get('link')
                                title = item.get('title') or item.get('name') or item.get('headline') or ''
                                snippet = item.get('description') or item.get('snippet') or ''
                                if url and url.startswith('http'):
                                    batch_results.append({'title': title, 'url': url, 'snippet': snippet})
                            if batch_results:
                                logger.info('Brave API batch returned %s results via web.results', len(batch_results))

                        # Fallback heuristics: look for top-level lists
                        if not batch_results:
                            for key in ('results', 'organic', 'items', 'data'):
                                if key in body and isinstance(body[key], list):
                                    logger.debug('Found results in body[%s] with %s items', key, len(body[key]))
                                    for item in body[key]:
                                        if not isinstance(item, dict):
                                            continue
                                        url = item.get('url') or item.get('link') or item.get('href') or item.get('target')
                                        title = item.get('title') or item.get('name') or ''
                                        snippet = item.get('snippet') or item.get('description') or ''
                                        if url and url.startswith('http'):
                                            batch_results.append({'title': title, 'url': url, 'snippet': snippet})
                                    if batch_results:
                                        logger.info('Brave API batch returned %s results via body[%s]', len(batch_results), key)
                                        break

                    # Log detailed error information if no results in this batch
                    if not batch_results:
                        if isinstance(body, dict):
                            logger.warning('Brave API response did not contain usable results. Response structure: %s', json.dumps(body, indent=2)[:500])
                        else:
                            logger.debug('Brave API response did not contain usable results (body is not a dict)')
                        break  # No more results available
                else:
                    body_text = getattr(resp, 'text', '')[:1000]
                    logger.error('Brave API request failed: HTTP %s. Response: %s', resp.status_code, body_text)
                    # Try to parse error details if it's JSON
                    try:
                        error_body = resp.json()
                        if isinstance(error_body, dict):
                            error_msg = error_body.get('message') or error_body.get('error') or str(error_body)
                            logger.error('Brave API error details: %s', error_msg)
                    except:
                        pass
                    break  # API error, stop pagination

            except Exception as e:
                logger.warning('Brave API request error: %s; stopping pagination', e)
                break

            # Add batch results to total
            all_results.extend(batch_results)
            logger.info('Collected %s/%s total results so far', len(all_results), size)

            # If we got no results in this batch, we've hit the end
            if len(batch_results) == 0:
                logger.info('No results in this batch, stopping pagination')
                break

            # If we got fewer results than requested, we might be near the end
            # But continue trying if we haven't reached our target yet
            if len(batch_results) < batch_size:
                logger.info('Received fewer results than requested (%s < %s), may be reaching end of results', len(batch_results), batch_size)
                # Continue anyway to try to get more results

            # Update offset for next batch
            offset += len(batch_results)

            # Safety check: prevent infinite loops
            if offset > size * 2:
                logger.warning('Offset exceeded safety limit (%s > %s*2), stopping pagination', offset, size)
                break

        # Return collected results
        if all_results:
            logger.info('Brave API pagination complete: collected %s results total (requested %s) after %s attempts',
                       len(all_results), size, pagination_attempts)
            return all_results[:size]  # Trim to exact size requested

        logger.warning('Brave API pagination complete but no results collected after %s attempts', pagination_attempts)

        # If no results via pagination, fall through to HTML scraping
        logger.warning('Brave API pagination returned no results')
        # If API key exists, do not fallback to HTML scraping unless explicitly enabled
        # This enforces an API-only flow when a subscription key is configured.
        allow_html = os.getenv('BRAVE_ALLOW_HTML_FALLBACK', '0') == '1'
        if not allow_html:
            # Return whatever results we have (possibly empty) and avoid HTML scraping
            return all_results

    logger.info('Falling back to Brave HTML scraping for query=%s', query)
    # Fallback to HTML scraping (only when API key is not present or fallback explicitly enabled)
    params = {"q": query, "source": "web", "count": size}
    _rate_limiter.wait_for_domain(BRAVE_SEARCH_URL)
    # Use simple retries/backoff for the public HTML scrape path
    # Allow timeout override via environment variable
    html_timeout = int(os.getenv('BRAVE_API_TIMEOUT', '10'))
    def _http_get_with_retries(url, params=None, headers=None, timeout=10, retries=3, backoff_factor=0.7):
        attempt = 0
        while attempt < retries:
            attempt += 1
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
                return resp
            except requests.RequestException as e:
                logger.debug('Brave HTML fetch attempt %s/%s failed: %s', attempt, retries, e)
                if attempt >= retries:
                    raise
                time.sleep(backoff_factor * (2 ** (attempt - 1)))

    try:
        resp = _http_get_with_retries(BRAVE_SEARCH_URL, params=params, headers=headers, timeout=html_timeout, retries=int(os.getenv('BRAVE_HTML_RETRIES','3')))
    except Exception as e:
        logger.error('Brave Search request failed after retries: %s', e)
        return []
    if resp.status_code != 200:
        logger.error("Brave Search request failed: %s %s", resp.status_code, getattr(resp, 'text', '')[:400])
        # Dump raw HTML for debugging
        try:
            dump_dir = Path(os.getenv('AR_FETCH_DEBUG_DIR', '/tmp/ar_fetch_debug'))
            dump_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', query)[:80]
            (dump_dir / f'brave_search_{safe}.html').write_text(resp.text or '', encoding='utf-8')
            logger.debug('Wrote Brave search raw HTML to %s', dump_dir)
        except Exception:
            pass
        return []

    # Parse HTML results (best-effort)
    soup = BeautifulSoup(resp.text, "lxml")
    results = []

    # Try multiple selectors to be robust against layout changes
    candidate_selectors = [
        ".result",
        "div[data-test=search-result]",
        "div.result__body",
        "div.result__content",
        "li.result",
        "article",
    ]

    for sel in candidate_selectors:
        for item in soup.select(sel)[:size]:
            # Several possible title anchor selectors
            a = (
                item.select_one("a.result-title")
                or item.select_one("a.result__title")
                or item.select_one("h3 a")
                or item.select_one("a")
            )
            if not a:
                continue
            title = a.get_text(separator=" ", strip=True)
            url = a.get("href")

            # Try alternate attributes that some search UIs use to store real target
            if (not url or url in ("/", "/settings")):
                url = a.get('data-href') or a.get('data-url') or a.get('data-redirect') or url

            # If still not a valid http URL, attempt to parse onclick handlers
            if not url or not url.startswith('http'):
                onclick = a.get('onclick')
                if onclick:
                    import re

                    m = re.search(r"location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", onclick)
                    if m:
                        url = m.group(1)

            # Normalize relative URLs
            snippet_el = item.select_one("p.snippet") or item.select_one("div.result__snippet")
            snippet = snippet_el.get_text(separator=" ", strip=True) if snippet_el else ""

            # Resolve relative URLs against Brave search base
            if url and url.startswith("/"):
                url = urljoin(BRAVE_SEARCH_URL, url)

            # Log suspicious or internal-only hrefs for debugging
            if url in ("/", "/settings") or not url:
                logger.debug("Brave result had internal href or missing URL: title=%s href=%s html_snippet=%s", title, url, str(item)[:400])

            # Skip anchors that are not HTTP(S)
            if not url or not url.startswith("http"):
                logger.debug("Skipping non-http href: %s (title=%s)", url, title)
                continue

            results.append({"title": title, "url": url, "snippet": snippet})

        if results:
            break

    # Fallback: look for simple anchors (filtering non-http links)
    if not results:
        for a in soup.find_all("a", href=True)[:size * 3]:
            href = a.get('href')
            if not href:
                continue
            if href.startswith("/"):
                href = urljoin(BRAVE_SEARCH_URL, href)
            if not href.startswith("http"):
                continue
            title = a.get_text(separator=" ", strip=True) or href
            results.append({"title": title, "url": href, "snippet": ""})

    # If still no results, dump a short snippet of HTML into the logs to help debugging
    if not results:
        snippet = resp.text[:1000].replace("\n", " ")
        logger.debug("Brave search returned status %s but parsing found no results. HTML snippet: %s", resp.status_code, snippet)

    return results

    # Optional Playwright fallback: render the page with a headless browser and extract links
    use_playwright = os.getenv('AR_USE_PLAYWRIGHT', '0') == '1'
    if not results and use_playwright:
        if not _PLAYWRIGHT_AVAILABLE:
            logger.warning('Playwright fallback requested (AR_USE_PLAYWRIGHT=1) but Playwright is not installed.')
        else:
            logger.info('Attempting Playwright-rendered Brave search (AR_USE_PLAYWRIGHT=1)')
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(user_agent=headers.get('User-Agent'))
                    # Build URL explicitly to avoid double-encoding
                    search_url = f"{BRAVE_SEARCH_URL}?q={query}&source=web&count={size}"
                    page.goto(search_url, timeout=20000)
                    # Wait for anchors to appear
                    page.wait_for_selector('a', timeout=8000)
                    anchors = page.query_selector_all('a')
                    for a in anchors:
                        try:
                            href = a.get_attribute('href')
                            text = a.inner_text().strip()
                            if href and href.startswith('/'):
                                href = urljoin(BRAVE_SEARCH_URL, href)
                            if href and href.startswith('http'):
                                results.append({'title': text or href, 'url': href, 'snippet': ''})
                                if len(results) >= size:
                                    break
                        except Exception:
                            continue
                    browser.close()
            except Exception as e:
                logger.warning('Playwright-based fetch failed: %s', e)

    return results


def collect_brave_pages(
    query: str,
    target_count: int = 10,
    pool_size: int | None = None,
    min_body_length: int = 200,
    min_brand_body_length: int | None = None,
    url_collection_config: 'URLCollectionConfig' | None = None
) -> List[Dict[str, str]]:
    """Collect up to `target_count` successfully fetched pages for a Brave search query.

    Behavior:
    - Request `pool_size` search results (defaults to max(30, target_count*3)).
    - If url_collection_config is provided, enforces brand-owned vs 3rd party ratio
    - Iterate results in order, skip URLs disallowed by robots.txt.
    - Attempt to fetch each allowed URL via `fetch_page` and only count pages whose
      `body` length >= min_body_length as successful.
    - Brand-owned URLs can use a lower threshold (min_brand_body_length) if specified
    - Stop once `target_count` successful pages are collected or the pool is exhausted.

    This function honors robots.txt directives and will not fetch pages explicitly
    disallowed for the configured user-agent.

    Args:
        query: Search query
        target_count: Target number of pages to collect
        pool_size: Number of search results to request
        min_body_length: Minimum body length for third-party pages (default: 200)
        min_brand_body_length: Minimum body length for brand-owned pages (default: 75, filters error pages)
        url_collection_config: Optional ratio enforcement configuration
    """
    # Dynamic Pool Sizing Configuration
    initial_multiplier = 2
    max_total_results = pool_size if pool_size is not None else max(30, target_count * 5)
    current_batch_size = target_count * initial_multiplier
    
    total_processed = 0
    total_fetched = 0
    total_processed = 0
    total_fetched = 0
    current_offset = 0
    
    # Initialize persistent Playwright browser if available
    browser_manager = None
    try:
        from ingestion.playwright_manager import PlaywrightBrowserManager
        browser_manager = PlaywrightBrowserManager()
        if browser_manager.start():
            logger.info('[BRAVE] Persistent Playwright browser started for collection')
        else:
            browser_manager = None
    except Exception as e:
        logger.debug('[BRAVE] Could not start persistent browser: %s', e)
        browser_manager = None

    # Collections
    brand_owned_collected: List[Dict[str, str]] = []
    third_party_collected: List[Dict[str, str]] = []
    
    # Domain diversity tracking
    domain_counts: Dict[str, int] = {}
    max_per_domain = max(1, int(target_count * 0.2))
    
    # Track skip reasons for debugging
    skip_stats = {
        'no_url': 0,
        'robots_txt': 0,
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

        logger.info('[BRAVE] Collecting with ratio enforcement: %d brand-owned (%.0f%%) + %d 3rd party (%.0f%%) from %d search results',
                   target_brand_owned, url_collection_config.brand_owned_ratio * 100,
                   target_third_party, url_collection_config.third_party_ratio * 100,
                   max_total_results)

    logger.info('[BRAVE] Starting dynamic collection for query=%s (target=%d)', query, target_count)

    while len(brand_owned_collected) + len(third_party_collected) < target_count:
        if total_processed >= max_total_results:
            logger.info('[BRAVE] Reached max total results (%d), stopping', max_total_results)
            break

        logger.info('[BRAVE] Fetching search batch: size=%d, offset=%d', current_batch_size, current_offset)
        try:
            search_results = search_brave(query, size=current_batch_size, start_offset=current_offset)
        except Exception as e:
            logger.warning('Brave search failed: %s', e)
            break
            
        if not search_results:
            logger.info('[BRAVE] No more search results available')
            break
            
        current_offset += len(search_results)
        
        # Filter out already processed URLs? 
        # Brave search results might overlap if we are not careful, but offset should handle it.
        
        batch_fetched_count = 0
        batch_valid_count = 0
        
        for item in search_results:
            skip_stats['processed'] += 1
            total_processed += 1
            
            url = item.get('url')
            if not url:
                skip_stats['no_url'] += 1
                continue

            # Classify
            is_brand_owned = False
            classification = None
            if url_collection_config:
                classification = classify_url(url, url_collection_config)
                is_brand_owned = classification.source_type == URLSourceType.BRAND_OWNED

            # Robots check
            try:
                allowed = is_allowed_by_robots(url)
            except Exception:
                allowed = True
            if not allowed:
                skip_stats['robots_txt'] += 1
                continue

            # Fetch
            batch_fetched_count += 1
            content = fetch_page(url, browser_manager=browser_manager)
            body = content.get('body') or ''
            required_length = min_brand_body_length if is_brand_owned else min_body_length
            
            if body and len(body) >= required_length:
                # Check error page
                title = content.get('title', '').lower()
                error_indicators = ['access denied', 'forbidden', '403', '401', 'error', 'not found', '404']
                if any(indicator in title for indicator in error_indicators):
                    skip_stats['error_page'] += 1
                    continue

                # Check pools
                if url_collection_config:
                    if is_brand_owned and len(brand_owned_collected) >= target_brand_owned:
                        skip_stats['brand_owned_pool_full'] += 1
                        continue
                    if not is_brand_owned and len(third_party_collected) >= target_third_party:
                        skip_stats['third_party_pool_full'] += 1
                        continue
                elif len(brand_owned_collected) + len(third_party_collected) >= target_count:
                    break

                # Check diversity
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
                if domain_counts.get(domain, 0) >= max_per_domain:
                    skip_stats['domain_limit_reached'] += 1
                    continue

                # Add
                if url_collection_config:
                    content['source_type'] = classification.source_type.value
                    content['source_tier'] = classification.tier.value if classification.tier else 'unknown'
                    if is_brand_owned:
                        brand_owned_collected.append(content)
                        # Subpage logic omitted for brevity
                    else:
                        third_party_collected.append(content)
                else:
                    brand_owned_collected.append(content)

                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                batch_valid_count += 1
                
            else:
                skip_stats['thin_content'] += 1

            if len(brand_owned_collected) + len(third_party_collected) >= target_count:
                break
        
        total_fetched += batch_fetched_count
        success_rate = batch_valid_count / batch_fetched_count if batch_fetched_count > 0 else 0
        
        logger.info('[BRAVE] Batch finished. Valid: %d/%d (Rate: %.2f). Total: %d/%d', 
                   batch_valid_count, batch_fetched_count, success_rate,
                   len(brand_owned_collected) + len(third_party_collected), target_count)

        if len(brand_owned_collected) + len(third_party_collected) >= target_count:
            break
            
        # Dynamic Sizing
        if success_rate < 0.3:
            current_batch_size = target_count * 2
        elif success_rate > 0.6:
            needed = target_count - (len(brand_owned_collected) + len(third_party_collected))
            current_batch_size = max(10, int(needed / success_rate) + 5)
        else:
            current_batch_size = target_count

    collected = brand_owned_collected + third_party_collected
    
    # Clean up browser manager
    if browser_manager:
        browser_manager.close()
        logger.info('[BRAVE] Persistent Playwright browser closed')
    
    return collected
