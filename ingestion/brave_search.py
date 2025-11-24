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

# Import fetch configuration module
from ingestion.fetch_config import (
    get_domain_config,
    get_random_delay,
    get_realistic_headers,
    should_use_playwright,
    get_retry_config,
)

# Rate limiting: minimum interval (seconds) between outbound Brave requests
_BRAVE_REQUEST_INTERVAL = float(os.getenv('BRAVE_REQUEST_INTERVAL', '1.2'))
_LAST_BRAVE_REQUEST_TS = 0.0
_BRAVE_RATE_LOCK = threading.Lock()

# Session management for connection pooling and cookie handling
_SESSIONS_CACHE: Dict[str, requests.Session] = {}
_SESSIONS_LOCK = threading.Lock()


def _wait_for_rate_limit():
    """Ensure at least _BRAVE_REQUEST_INTERVAL seconds between requests."""
    global _LAST_BRAVE_REQUEST_TS
    if _BRAVE_REQUEST_INTERVAL <= 0:
        return
    with _BRAVE_RATE_LOCK:
        now = time.monotonic()
        elapsed = now - _LAST_BRAVE_REQUEST_TS
        if elapsed < _BRAVE_REQUEST_INTERVAL:
            to_sleep = _BRAVE_REQUEST_INTERVAL - elapsed
            time.sleep(to_sleep)
        # Update the timestamp to now after sleeping
        _LAST_BRAVE_REQUEST_TS = time.monotonic()
    # end _wait_for_rate_limit


def _get_session(domain: str) -> requests.Session:
    """
    Get or create a requests.Session for the given domain.

    Sessions provide connection pooling and automatic cookie handling,
    making scraping more efficient and realistic.

    Args:
        domain: The domain (netloc) for which to get a session

    Returns:
        A requests.Session object
    """
    with _SESSIONS_LOCK:
        if domain not in _SESSIONS_CACHE:
            session = requests.Session()
            # Configure session for better compatibility
            session.max_redirects = 10
            _SESSIONS_CACHE[domain] = session
        return _SESSIONS_CACHE[domain]


# Module-level robots.txt cache to share across functions
_ROBOTS_CACHE: Dict[str, robotparser.RobotFileParser] = {}


def _is_allowed_by_robots(url: str, user_agent: str | None = None) -> bool:
    """Check robots.txt for the given URL and user agent. Returns True if fetching is allowed.

    Uses a module-level cache to avoid repeated robots.txt fetches. If robots.txt cannot be
    fetched or parsed, defaults to permissive (True).
    """
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc
        scheme = parsed.scheme or 'https'
        key = f"{scheme}://{netloc}"
        ua = user_agent or os.getenv('AR_USER_AGENT', 'Mozilla/5.0 (compatible; ar-bot/1.0)')
        if key in _ROBOTS_CACHE:
            rp = _ROBOTS_CACHE[key]
            try:
                return rp.can_fetch(ua, parsed.path or '/')
            except Exception:
                return True

        robots_url = f"{key}/robots.txt"
        rp = robotparser.RobotFileParser()
        try:
            _wait_for_rate_limit()
            r = requests.get(robots_url, headers={'User-Agent': ua}, timeout=5)
            if r.status_code == 200 and r.text:
                rp.parse(r.text.splitlines())
            else:
                rp.parse([])
        except Exception:
            try:
                rp.parse([])
            except Exception:
                pass
        _ROBOTS_CACHE[key] = rp
        try:
            return rp.can_fetch(ua, parsed.path or '/')
        except Exception:
            return True
    except Exception:
        return True

# Optional Playwright import (used only if the environment opts in)
try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger('ingestion.page_fetcher')

BRAVE_SEARCH_URL = "https://search.brave.com/search"


def _extract_footer_links(html: str, base_url: str) -> Dict[str, str]:
    """Parse HTML and attempt to find Terms and Privacy links.

    Returns a dict with keys 'terms' and 'privacy' whose values are absolute URLs or
    empty strings when not found.
    """
    terms_url = ""
    privacy_url = ""
    try:
        s = BeautifulSoup(html or "", "html.parser")
        footer = s.find('footer')
        anchors = footer.find_all('a', href=True) if footer else []
        # If footer anchors are not present, fall back to scanning all anchors
        if not anchors:
            anchors = s.find_all('a', href=True)

        for a in anchors:
            try:
                href = a.get('href', '').strip()
                if not href:
                    continue
                text = (a.get_text(" ", strip=True) or "").lower()
                href_l = href.lower()
                full = urljoin(base_url, href)

                # Common heuristics for privacy/terms links
                if ('privacy' in href_l) or ('privacy' in text) or ('cookie' in text):
                    if not privacy_url:
                        privacy_url = full
                if ('term' in href_l) or ('term' in text) or ('conditions' in text):
                    if not terms_url:
                        terms_url = full

                if terms_url and privacy_url:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return {"terms": terms_url, "privacy": privacy_url}


def search_brave(query: str, size: int = 10) -> List[Dict[str, str]]:
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
        offset = 0
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
                _wait_for_rate_limit()
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
    _wait_for_rate_limit()
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
    soup = BeautifulSoup(resp.text, "html.parser")
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


def _extract_internal_links(url: str, html_content: str, max_links: int = 15) -> List[str]:
    """Extract internal links from a brand domain page.

    Useful for collecting subpages from brand homepages (e.g., product pages,
    category pages, about pages from nike.com).

    Args:
        url: The parent URL (used to determine internal links)
        html_content: HTML content of the page
        max_links: Maximum number of links to extract

    Returns:
        List of internal URLs (subpages on the same domain)
    """
    try:
        from urllib.parse import urlparse, urljoin

        soup = BeautifulSoup(html_content, "html.parser")
        parent_domain = urlparse(url).netloc

        internal_links = []
        seen = set([url])  # Avoid duplicates

        for link in soup.find_all('a', href=True):
            try:
                href = link.get('href', '').strip()
                if not href:
                    continue

                # Skip anchors and javascript
                if href.startswith('#') or href.startswith('javascript:'):
                    continue

                # Resolve relative URLs
                full_url = urljoin(url, href)

                # Only include internal links (same domain)
                link_domain = urlparse(full_url).netloc
                if link_domain != parent_domain:
                    continue

                # Skip common non-content pages
                path = urlparse(full_url).path.lower()
                if any(skip in path for skip in ['/search', '/login', '/cart', '/checkout',
                                                   '/account', '/privacy', '/terms', '/contact']):
                    continue

                # Skip duplicate fragments
                if full_url in seen:
                    continue

                seen.add(full_url)
                internal_links.append(full_url)

                if len(internal_links) >= max_links:
                    break
            except Exception:
                continue

        logger.debug('[INTERNAL_LINKS] Extracted %d internal links from %s', len(internal_links), url)
        return internal_links
    except Exception as e:
        logger.debug('Failed to extract internal links from %s: %s', url, e)
        return []


def _detect_product_grid(soup: BeautifulSoup) -> Optional[list]:
    """
    Detect if page contains a product grid/listing.
    
    Returns list of product card elements if found, None otherwise.
    """
    # Look for repeated card/item patterns
    card_selectors = [
        '.product-card', '.product-item', '.item-card', '.card',
        '[class*="product"]', '[class*="card"]', '[class*="item"]'
    ]
    
    for selector in card_selectors:
        try:
            cards = soup.select(selector)
            # Need at least 3 similar items to consider it a grid
            if len(cards) >= 3:
                # Verify they have similar structure (name/title + price/button)
                valid_cards = []
                for card in cards:
                    # Check if card has typical product elements
                    has_title = card.select_one('h1, h2, h3, h4, h5, strong, .title, .name, [class*="title"], [class*="name"]')
                    has_price_or_button = card.select_one('[class*="price"], button, a[class*="shop"], a[class*="buy"]')
                    if has_title or has_price_or_button:
                        valid_cards.append(card)
                
                if len(valid_cards) >= 3:
                    logger.debug(f"Detected product grid with {len(valid_cards)} items using selector: {selector}")
                    return valid_cards
        except Exception:
            continue
    
    return None


def _format_product_grid(cards: list) -> str:
    """Format product cards as bulleted list."""
    items = []
    
    for card in cards:
        try:
            # Extract product name (h2, h3, h4, strong, or class with "name"/"title")
            name = card.select_one('h1, h2, h3, h4, h5, strong, .product-name, .title, [class*="name"], [class*="title"]')
            name_text = name.get_text(separator=" ", strip=True) if name else ""
            
            # Extract price
            price = card.select_one('[class*="price"], .price, [class*="cost"]')
            price_text = price.get_text(separator=" ", strip=True) if price else ""
            
            # Build item text
            if name_text:
                item = f"- {name_text}"
                if price_text:
                    item += f" ({price_text})"
                items.append(item)
        except Exception:
            continue
    
    if items:
        result = "\n".join(items)
        logger.debug(f"Formatted product grid: {len(items)} items")
        return result
    return ""


def _format_html_lists(soup: BeautifulSoup) -> str:
    """Convert HTML lists to formatted text."""
    text_parts = []
    
    try:
        for ul in soup.find_all(['ul', 'ol']):
            items = []
            for li in ul.find_all('li', recursive=False):
                item_text = li.get_text(separator=" ", strip=True)
                if item_text and len(item_text) > 5:  # Skip very short items
                    items.append(f"- {item_text}")
            
            if items and len(items) >= 2:  # At least 2 items to be meaningful
                text_parts.append("\n".join(items))
        
        if text_parts:
            result = "\n\n".join(text_parts)
            logger.debug(f"Formatted HTML lists: {len(text_parts)} lists")
            return result
    except Exception:
        pass
    
    return ""


def _format_tables(soup: BeautifulSoup) -> str:
    """Convert HTML tables to formatted text."""
    text_parts = []
    
    try:
        for table in soup.find_all('table'):
            rows = []
            for tr in table.find_all('tr'):
                cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(['td', 'th'])]
                cells = [c for c in cells if c]  # Remove empty cells
                if cells:
                    rows.append(" | ".join(cells))
            
            if rows and len(rows) >= 2:  # At least header + 1 row
                text_parts.append("\n".join(rows))
        
        if text_parts:
            result = "\n\n".join(text_parts)
            logger.debug(f"Formatted tables: {len(text_parts)} tables")
            return result
    except Exception:
        pass
    
    return ""


def _extract_body_text(soup: BeautifulSoup) -> str:
    """Extract body text using multiple strategies in order of preference.
    
    Tries extraction from:
    0. Structured content (product grids, lists, tables) - NEW
    1. <article> tag
    2. <main> tag or [role="main"]
    3. <div> with content-related class names
    4. All <p> tags combined
    5. Longest <div> by text length
    6. Entire <body> as fallback

    Returns the extracted text using the first strategy that yields content.
    """
    # NEW: Strategy 0 - Try structured content extraction first
    try:
        # Check for product grids
        product_cards = _detect_product_grid(soup)
        if product_cards:
            grid_text = _format_product_grid(product_cards)
            if grid_text and len(grid_text) >= 100:
                logger.debug("Extracted product grid with %d items", len(product_cards))
                return grid_text
        
        # Check for HTML lists (if no product grid found)
        list_text = _format_html_lists(soup)
        if list_text and len(list_text) >= 150:
            logger.debug("Extracted formatted HTML lists")
            return list_text
        
        # Check for tables (if no lists found)
        table_text = _format_tables(soup)
        if table_text and len(table_text) >= 150:
            logger.debug("Extracted formatted tables")
            return table_text
    except Exception as e:
        logger.debug("Structured extraction failed, falling back to generic: %s", e)
    
    # EXISTING: Strategy 1: Try <article> tag
    article = soup.find("article")
    if article:
        body = article.get_text(separator=" \n ", strip=True)
        if body and len(body) >= 100:
            return body

    # Strategy 2: Try <main> tag or [role="main"]
    main = soup.find("main") or soup.select_one('[role="main"]')
    if main:
        body = main.get_text(separator=" \n ", strip=True)
        if body and len(body) >= 100:
            return body

    # Strategy 3: Try <div> with content-related class names
    content_class_patterns = [
        'content', 'post-content', 'article-body', 'article', 'entry',
        'post', 'body-text', 'post-body', 'main-content', 'page-content',
        'story-body', 'article-text', 'article-content', 'text-content'
    ]
    for pattern in content_class_patterns:
        divs = soup.find_all('div', class_=lambda x: x and pattern in x.lower())
        for div in divs:
            body = div.get_text(separator=" \n ", strip=True)
            if body and len(body) >= 150:
                return body

    # Strategy 4: Try all <p> tags combined
    paragraphs = soup.find_all("p")
    if paragraphs:
        body = "\n\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs if p.get_text(separator=" ", strip=True))
        if body and len(body) >= 100:
            return body

    # Strategy 5: Try to find the longest <div> by text length
    divs = soup.find_all('div')
    longest_div = None
    longest_length = 0
    for div in divs:
        # Skip divs that are likely navigation or headers
        div_class = div.get('class', [])
        div_id = div.get('id', '')
        if any(skip in str(div_class).lower() + div_id.lower()
               for skip in ['nav', 'header', 'footer', 'menu', 'sidebar', 'widget', 'ad']):
            continue
        text = div.get_text(separator=" \n ", strip=True)
        if len(text) > longest_length:
            longest_length = len(text)
            longest_div = div

    if longest_div and longest_length >= 100:
        return longest_div.get_text(separator=" \n ", strip=True)

    # Strategy 6: Fall back to entire body text
    body = soup.body.get_text(separator=" \n ", strip=True) if soup.body else ""
    return body


def fetch_page(url: str, timeout: int = 10) -> Dict[str, str]:
    """Fetch a URL and return a simple content dict {title, body, url}"""
    # Get realistic headers for this URL
    headers = get_realistic_headers(url)

    # Get retry configuration
    retry_config = get_retry_config(url)
    retries = retry_config['max_retries']
    timeout = retry_config['timeout']

    # Get session for this domain (for connection pooling and cookie handling)
    parsed = urlparse(url)
    domain = parsed.netloc
    session = _get_session(domain)

    resp = None
    last_status_code = None

    for attempt in range(1, retries + 1):
        try:
            # Use randomized delay instead of fixed rate limit
            if attempt == 1:
                # First attempt: use configured rate limit
                _wait_for_rate_limit()
            else:
                # Retry attempts: use randomized delay
                delay = get_random_delay(url)
                logger.debug('Retry attempt %s/%s for %s - waiting %.2fs', attempt, retries, url, delay)
                time.sleep(delay)

            # Use session.get instead of requests.get for better session management
            resp = session.get(url, headers=headers, timeout=timeout)
            last_status_code = resp.status_code
            break
        except Exception as e:
            # Handle both requests.RequestException and generic exceptions from monkeypatches
            logger.debug('Fetch attempt %s/%s for %s failed: %s', attempt, retries, url, e)
            if attempt == retries:
                logger.error('Error fetching page %s after %s attempts: %s', url, retries, e)
                # No resp to dump; just return empty
                return {"title": "", "body": "", "url": url}
            # Get smarter backoff based on status code if available
            retry_config_updated = get_retry_config(url, last_status_code)
            backoff = retry_config_updated['base_backoff']
            time.sleep(backoff * (2 ** (attempt - 1)))

    try:
        if resp is None:
            return {"title": "", "body": "", "url": url}

        if resp.status_code != 200:
            logger.warning("Fetching %s returned %s", url, resp.status_code)
            # Check if Playwright should be used (global override or domain-specific config)
            use_pw = should_use_playwright(url)
            try_playwright = use_pw and _PLAYWRIGHT_AVAILABLE
            if try_playwright:
                try:
                    # Use realistic browser headers for Playwright too
                    pw_headers = get_realistic_headers(url)
                    ua = pw_headers['User-Agent']
                    # Respect robots.txt before attempting a headful fetch
                    try:
                        allowed = _is_allowed_by_robots(url, ua)
                    except Exception:
                        allowed = True
                    if allowed:
                        logger.info('Attempting Playwright-rendered fetch for %s (domain config or AR_USE_PLAYWRIGHT)', url)
                        with sync_playwright() as pw:
                            browser = pw.chromium.launch(headless=True)
                            page = browser.new_page(user_agent=ua)
                            page.goto(url, timeout=20000)
                            # wait for body
                            try:
                                page.wait_for_selector('body', timeout=8000)
                            except Exception:
                                pass
                            page_content = page.content()
                            page_title = page.title() or ''
                            # Try multiple extraction strategies for rendered content
                            page_body = ""
                            try:
                                # Strategy 1: article tag
                                article = page.query_selector('article')
                                if article:
                                    page_body = article.inner_text()

                                # Strategy 2: main tag or role="main"
                                if not page_body or len(page_body) < 150:
                                    main = page.query_selector('main') or page.query_selector('[role="main"]')
                                    if main:
                                        page_body = main.inner_text()

                                # Strategy 3: divs with content-related class names
                                if not page_body or len(page_body) < 150:
                                    content_patterns = ['content', 'post-content', 'article-body', 'article', 'entry', 'post', 'story-body']
                                    for pattern in content_patterns:
                                        divs = page.query_selector_all(f'div[class*="{pattern}"]')
                                        for div in divs:
                                            div_text = div.inner_text()
                                            if div_text and len(div_text) >= 150:
                                                page_body = div_text
                                                break
                                        if page_body:
                                            break

                                # Strategy 4: all paragraphs
                                if not page_body or len(page_body) < 150:
                                    paragraphs = page.query_selector_all('p')
                                    texts = [p.inner_text() for p in paragraphs if p]
                                    page_body = "\n\n".join(texts)

                                # Strategy 5: fall back to entire body content
                                if not page_body or len(page_body) < 100:
                                    body_elem = page.query_selector('body')
                                    if body_elem:
                                        page_body = body_elem.inner_text()
                            except Exception:
                                page_body = page_content
                            browser.close()
                            if page_body and len(page_body) >= 100:
                                links = _extract_footer_links(page_content, url)
                                return {"title": page_title.strip(), "body": page_body.strip(), "url": url, "terms": links.get("terms", ""), "privacy": links.get("privacy", "")}
                except Exception as e:
                    logger.warning('Playwright fallback failed for %s: %s', url, e)

            # Dump raw response for debugging
            try:
                dump_dir = Path(os.getenv('AR_FETCH_DEBUG_DIR', '/tmp/ar_fetch_debug'))
                dump_dir.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', url)[:120]
                (dump_dir / f'{safe}_status_{resp.status_code}.html').write_text(resp.text or '', encoding='utf-8')
                logger.debug('Wrote raw fetch output to %s', dump_dir)
            except Exception:
                pass
            try:
                links = _extract_footer_links(getattr(resp, 'text', '') or '', url)
            except Exception:
                links = {"terms": "", "privacy": ""}
            return {"title": "", "body": "", "url": url, "terms": links.get("terms", ""), "privacy": links.get("privacy", "")}

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # Try OpenGraph / Twitter meta fallbacks for title/description
        if not title:
            og_title = soup.select_one('meta[property="og:title"]') or soup.select_one('meta[name="twitter:title"]')
            if og_title and og_title.get('content'):
                title = og_title.get('content').strip()

        # Extract body using multiple strategies
        body = _extract_body_text(soup)

        # If body or title are thin, try OG/Twitter description and dump for debugging
        if (not body or len(body) < 200) and soup.select_one('meta[property="og:description"]'):
            og_desc = soup.select_one('meta[property="og:description"]') or soup.select_one('meta[name="twitter:description"]')
            if og_desc and og_desc.get('content'):
                body = og_desc.get('content').strip()
        if (not title or not body or len(body) < 200):
            # Attempt Playwright fallback for thin content if enabled and allowed
            use_pw = should_use_playwright(url)
            try_playwright = use_pw and _PLAYWRIGHT_AVAILABLE
            if try_playwright:
                try:
                    # Use realistic browser headers for Playwright too
                    pw_headers = get_realistic_headers(url)
                    ua = pw_headers['User-Agent']
                    allowed = True
                    try:
                        allowed = _is_allowed_by_robots(url, ua)
                    except Exception:
                        allowed = True
                    if allowed:
                        logger.info('Attempting Playwright-rendered fetch for thin content: %s', url)
                        with sync_playwright() as pw:
                            browser = pw.chromium.launch(headless=True)
                            page = browser.new_page(user_agent=ua)
                            page.goto(url, timeout=20000)
                            try:
                                page.wait_for_selector('body', timeout=8000)
                            except Exception:
                                pass
                            page_html = page.content()
                            page_title = page.title() or ''
                            # Try multiple extraction strategies for rendered content
                            page_body = ""
                            try:
                                # Strategy 1: article tag
                                article = page.query_selector('article')
                                if article:
                                    page_body = article.inner_text()

                                # Strategy 2: main tag or role="main"
                                if not page_body or len(page_body) < 150:
                                    main = page.query_selector('main') or page.query_selector('[role="main"]')
                                    if main:
                                        page_body = main.inner_text()

                                # Strategy 3: divs with content-related class names
                                if not page_body or len(page_body) < 150:
                                    content_patterns = ['content', 'post-content', 'article-body', 'article', 'entry', 'post', 'story-body']
                                    for pattern in content_patterns:
                                        divs = page.query_selector_all(f'div[class*="{pattern}"]')
                                        for div in divs:
                                            div_text = div.inner_text()
                                            if div_text and len(div_text) >= 150:
                                                page_body = div_text
                                                break
                                        if page_body:
                                            break

                                # Strategy 4: all paragraphs
                                if not page_body or len(page_body) < 150:
                                    paragraphs = page.query_selector_all('p')
                                    texts = [p.inner_text() for p in paragraphs if p]
                                    page_body = "\n\n".join(texts)

                                # Strategy 5: fall back to entire body content
                                if not page_body or len(page_body) < 150:
                                    body_elem = page.query_selector('body')
                                    if body_elem:
                                        page_body = body_elem.inner_text()
                            except Exception:
                                # fallback to raw HTML if inner_text extraction fails
                                page_body = page_html
                            browser.close()
                            if page_body and len(page_body) >= 150:
                                try:
                                    links = _extract_footer_links(page_html, url)
                                except Exception:
                                    links = {"terms": "", "privacy": ""}
                                return {"title": page_title.strip(), "body": page_body.strip(), "url": url, "terms": links.get("terms", ""), "privacy": links.get("privacy", "")}
                except Exception as e:
                    logger.warning('Playwright fallback for thin content failed for %s: %s', url, e)

            try:
                dump_dir = Path(os.getenv('AR_FETCH_DEBUG_DIR', '/tmp/ar_fetch_debug'))
                dump_dir.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', url)[:120]
                (dump_dir / f'{safe}_thin.html').write_text(resp.text or '', encoding='utf-8')
                logger.debug('Wrote thin-content raw fetch output to %s', dump_dir)
            except Exception:
                pass

        try:
            links = _extract_footer_links(getattr(resp, 'text', '') or '', url)
        except Exception:
            links = {"terms": "", "privacy": ""}
        return {"title": title, "body": body, "url": url, "terms": links.get("terms", ""), "privacy": links.get("privacy", "")}
    except Exception as e:
        logger.error("Error fetching page %s: %s", url, e)
        # Attempt to dump whatever we have for debugging
        try:
            dump_dir = Path(os.getenv('AR_FETCH_DEBUG_DIR', '/tmp/ar_fetch_debug'))
            dump_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[^a-zA-Z0-9_.-]', '_', url)[:120]
            if resp is not None:
                (dump_dir / f'{safe}_exception.html').write_text(getattr(resp, 'text', '') or '', encoding='utf-8')
        except Exception:
            pass
        return {"title": "", "body": "", "url": url}


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

    results = []
    try:
        search_results = search_brave(query, size=pool_size)
        logger.info('[BRAVE] Requested pool_size=%d, received %d search results for query=%s',
                   pool_size, len(search_results), query)
    except Exception as e:
        logger.warning('Brave search failed while collecting pages: %s', e)
        search_results = []

    if not search_results:
        logger.warning('[BRAVE] No search results returned, returning empty list')
        return []

    # robots.txt cache per netloc
    robots_cache: Dict[str, robotparser.RobotFileParser] = {}
    ua = headers = {
        'User-Agent': os.getenv('AR_USER_AGENT', 'Mozilla/5.0 (compatible; ar-bot/1.0)')
    }

    def is_allowed_by_robots(url: str) -> bool:
        parsed = urlparse(url)
        netloc = parsed.netloc
        scheme = parsed.scheme or 'https'
        key = f"{scheme}://{netloc}"
        if key in robots_cache:
            rp = robots_cache[key]
            try:
                return rp.can_fetch(ua['User-Agent'], parsed.path or '/')
            except Exception:
                return True

        robots_url = f"{key}/robots.txt"
        rp = robotparser.RobotFileParser()
        try:
            # Fetch robots.txt using requests so we can set headers and timeouts
            _wait_for_rate_limit()
            r = requests.get(robots_url, headers=ua, timeout=5)
            if r.status_code == 200 and r.text:
                rp.parse(r.text.splitlines())
            else:
                # No robots.txt or non-200: treat as permissive
                rp.parse([])
        except Exception:
            # If robots fetch fails, prefer permissive to avoid blocking useful fetches
            try:
                rp.parse([])
            except Exception:
                pass
        robots_cache[key] = rp
        try:
            return rp.can_fetch(ua['User-Agent'], parsed.path or '/')
        except Exception:
            return True

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
        domain_counts: Dict[str, int] = {}
        max_per_domain = max(1, int(target_count * 0.2))  # 20% of target, minimum 1

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

        logger.info('[BRAVE] Collecting with ratio enforcement: %d brand-owned (%.0f%%) + %d 3rd party (%.0f%%) from %d search results',
                   target_brand_owned, url_collection_config.brand_owned_ratio * 100,
                   target_third_party, url_collection_config.third_party_ratio * 100,
                   len(search_results))

        for item in search_results:
            skip_stats['processed'] += 1

            # Periodic progress update (every 50 URLs)
            if skip_stats['processed'] % 50 == 0:
                logger.info('[BRAVE] Progress: Processed %d/%d results, collected %d/%d URLs (%d brand-owned, %d 3rd party)',
                           skip_stats['processed'], len(search_results),
                           len(brand_owned_collected) + len(third_party_collected), target_count,
                           len(brand_owned_collected), len(third_party_collected))

            # Stop if both pools are full
            if len(brand_owned_collected) >= target_brand_owned and len(third_party_collected) >= target_third_party:
                logger.info('[BRAVE] Both pools full, breaking early at result %d/%d',
                           skip_stats['processed'], len(search_results))
                break

            url = item.get('url')
            if not url:
                skip_stats['no_url'] += 1
                continue

            # Classify the URL
            classification = classify_url(url, url_collection_config)
            is_brand_owned = classification.source_type == URLSourceType.BRAND_OWNED

            # Respect robots.txt
            try:
                allowed = is_allowed_by_robots(url)
            except Exception:
                allowed = True

            if not allowed:
                skip_stats['robots_txt'] += 1
                logger.info('[BRAVE] Skipping %s due to robots.txt disallow', url)
                continue

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
                    logger.debug('[BRAVE] Skipping %s - error page detected (title: "%s")',
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
                        logger.debug('[BRAVE] Skipping brand-owned URL %s - pool full',
                                   url)
                        continue
                else:
                    if len(third_party_collected) >= target_third_party:
                        skip_stats['third_party_pool_full'] += 1
                        logger.debug('[BRAVE] Skipping 3rd party URL %s - pool full',
                                   url)
                        continue

                # Check domain diversity limit (max 20% per domain)
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.lower()
                if domain_counts.get(domain, 0) >= max_per_domain:
                    skip_stats['domain_limit_reached'] += 1
                    logger.debug('[BRAVE] Skipping %s - domain limit reached (%d/%d URLs from %s)',
                               url, domain_counts[domain], max_per_domain, domain)
                    continue

                # Add source type metadata
                content['source_type'] = classification.source_type.value
                content['source_tier'] = classification.tier.value if classification.tier else 'unknown'

                if is_brand_owned:
                    brand_owned_collected.append(content)
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                    logger.debug('[BRAVE] ✓ Collected brand-owned page (%d/%d): %s [len=%d]',
                               len(brand_owned_collected), target_brand_owned, url, len(body))

                    # If we still need more brand-owned URLs, try extracting subpages
                    if len(brand_owned_collected) < target_brand_owned:
                        try:
                            # Get the raw HTML for link extraction
                            resp = requests.get(url, headers={
                                'User-Agent': os.getenv('AR_USER_AGENT',
                                    'Mozilla/5.0 (compatible; ar-bot/1.0)')
                            }, timeout=10)

                            if resp.status_code == 200:
                                subpage_urls = _extract_internal_links(url, resp.text, max_links=15)
                                logger.debug('[BRAVE] Extracted %d internal links from %s',
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
                                            logger.debug('[BRAVE] Skipping subpage %s - domain limit reached', subpage_url)
                                            continue

                                        subpage_content = fetch_page(subpage_url)
                                        subpage_body = subpage_content.get('body') or ''

                                        # Subpages are brand-owned, use lower threshold
                                        if subpage_body and len(subpage_body) >= min_brand_body_length:
                                            subpage_content['source_type'] = 'brand_owned'
                                            subpage_content['source_tier'] = 'brand_subpage'
                                            brand_owned_collected.append(subpage_content)
                                            domain_counts[subpage_domain] = domain_counts.get(subpage_domain, 0) + 1
                                            logger.debug('[BRAVE] ✓ Collected brand subpage (%d/%d): %s [len=%d]',
                                                       len(brand_owned_collected), target_brand_owned,
                                                       subpage_url, len(subpage_body))
                                        else:
                                            logger.debug('[BRAVE] Skipping subpage %s - thin content', subpage_url)
                                    except Exception as e:
                                        logger.debug('[BRAVE] Failed to fetch subpage %s: %s', subpage_url, e)
                        except Exception as e:
                            logger.debug('[BRAVE] Failed to extract subpages from %s: %s', url, e)
                else:
                    third_party_collected.append(content)
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                    logger.debug('[BRAVE] ✓ Collected 3rd party page (%d/%d): %s [len=%d]',
                               len(third_party_collected), target_third_party, url, len(body))
            else:
                skip_stats['thin_content'] += 1
                logger.debug('[BRAVE] Skipping %s - thin/empty content (len=%s, min=%d) [%s]',
                           url, len(body), min_body_length,
                           'brand-owned' if is_brand_owned else '3rd party')

        # Combine results
        collected = brand_owned_collected + third_party_collected

        logger.info('[BRAVE] ═══════════════════════════════════════════════════════════')
        logger.info('[BRAVE] COLLECTION SUMMARY for query=%s', query)
        logger.info('[BRAVE] ───────────────────────────────────────────────────────────')
        logger.info('[BRAVE] Search results received: %d (requested pool_size: %d)',
                   len(search_results), pool_size)
        logger.info('[BRAVE] Results processed: %d', skip_stats['processed'])
        logger.info('[BRAVE] Target: %d total (%d brand-owned + %d 3rd party)',
                   target_count, target_brand_owned, target_third_party)
        logger.info('[BRAVE] Collected: %d total (%d brand-owned + %d 3rd party)',
                   len(collected), len(brand_owned_collected), len(third_party_collected))
        logger.info('[BRAVE] Domain diversity: %d unique domains (max %d URLs per domain)',
                   len(domain_counts), max_per_domain)
        logger.info('[BRAVE] ───────────────────────────────────────────────────────────')
        logger.info('[BRAVE] Skip reasons:')
        logger.info('[BRAVE]   - No URL: %d', skip_stats['no_url'])
        logger.info('[BRAVE]   - Robots.txt blocked: %d', skip_stats['robots_txt'])
        logger.info('[BRAVE]   - Thin/empty content (brand <%d bytes, 3rd party <%d bytes): %d',
                   min_brand_body_length, min_body_length, skip_stats['thin_content'])
        logger.info('[BRAVE]   - Error page (Access Denied, 403, etc.): %d', skip_stats['error_page'])
        logger.info('[BRAVE]   - Domain limit reached (max %d per domain): %d', max_per_domain, skip_stats['domain_limit_reached'])
        logger.info('[BRAVE]   - Brand-owned pool full: %d', skip_stats['brand_owned_pool_full'])
        logger.info('[BRAVE]   - 3rd party pool full: %d', skip_stats['third_party_pool_full'])
        logger.info('[BRAVE] ═══════════════════════════════════════════════════════════')

    else:
        # Original behavior: no ratio enforcement
        collected: List[Dict[str, str]] = []
        for item in search_results:
            if len(collected) >= target_count:
                break
            url = item.get('url')
            if not url:
                continue

            # Respect robots.txt
            try:
                allowed = is_allowed_by_robots(url)
            except Exception:
                allowed = True

            if not allowed:
                logger.info('Skipping %s due to robots.txt disallow', url)
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
