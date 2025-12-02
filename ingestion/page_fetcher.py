"""Page fetching module

Provides unified page fetching logic for all search providers.
Handles HTTP requests, Playwright rendering, content extraction, and robots.txt compliance.
"""
from __future__ import annotations

import logging
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import urllib.robotparser as robotparser
import os
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

# Per-domain rate limiting (allows parallel requests to different domains)
from ingestion.rate_limiter import PerDomainRateLimiter
_rate_limiter = PerDomainRateLimiter(
    default_interval=float(os.getenv('BRAVE_REQUEST_INTERVAL', '2.0'))
)

# Session management for connection pooling and cookie handling
_SESSIONS_CACHE: Dict[str, requests.Session] = {}
_SESSIONS_LOCK = threading.Lock()


class DomainConfigCache:
    """Cache for domain-specific configuration and behavior learning."""
    _instance = None
    _lock = threading.Lock()
    _requires_playwright: Dict[str, bool] = {}  # domain -> bool

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def mark_requires_playwright(self, url: str):
        """Mark a domain as requiring Playwright."""
        domain = urlparse(url).netloc
        with self._lock:
            self._requires_playwright[domain] = True
            logger.info(f"Marked domain {domain} as requiring Playwright for future requests")

    def requires_playwright(self, url: str) -> bool:
        """Check if a domain is known to require Playwright."""
        domain = urlparse(url).netloc
        with self._lock:
            return self._requires_playwright.get(domain, False)

_domain_config = DomainConfigCache.get_instance()


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
            _rate_limiter.wait_for_domain(robots_url)
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


def _extract_footer_links(html: str, base_url: str) -> Dict[str, str]:
    """Parse HTML and attempt to find Terms and Privacy links.

    Returns a dict with keys 'terms' and 'privacy' whose values are absolute URLs or
    empty strings when not found.
    """
    terms_url = ""
    privacy_url = ""
    try:
        s = BeautifulSoup(html or "", "lxml")
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
        soup = BeautifulSoup(html_content, "lxml")
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


def _infer_semantic_role(element, element_type: str) -> str:
    """
    Infer semantic role of an HTML element based on its type and context.
    
    Args:
        element: BeautifulSoup element
        element_type: HTML tag name (h1, p, div, etc.)
    
    Returns:
        Semantic role string (headline, subheadline, body_text, etc.)
    """
    # Heading hierarchy
    if element_type in ['h1', 'h2']:
        return 'headline'
    elif element_type in ['h3', 'h4']:
        return 'subheadline'
    elif element_type in ['h5', 'h6']:
        return 'minor_heading'
    
    # Check for common class patterns
    if hasattr(element, 'get'):
        classes = element.get('class', [])
        class_str = ' '.join(classes).lower() if classes else ''
        
        # Product/pricing related
        if any(term in class_str for term in ['price', 'product', 'item', 'card']):
            return 'product_info'
        
        # Hero/banner content
        if any(term in class_str for term in ['hero', 'banner', 'jumbotron', 'headline']):
            return 'headline'
        
        # Subtext/tagline
        if any(term in class_str for term in ['subtext', 'tagline', 'subtitle', 'subheading']):
            return 'subheadline'
        
        # Footer content
        if any(term in class_str for term in ['footer', 'copyright', 'legal']):
            return 'footer_text'
    
    # List items
    if element_type == 'li':
        return 'list_item'
    
    # Paragraphs and divs default to body text
    if element_type in ['p', 'div', 'span']:
        return 'body_text'
    
    return 'body_text'


def _extract_elements_with_structure(container) -> List[Dict[str, str]]:
    """
    Extract text elements from a container while preserving structure.
    
    Args:
        container: BeautifulSoup element to extract from
    
    Returns:
        List of structured text segments
    """
    segments = []
    
    # Extract headings and paragraphs with their types
    for element in container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']):
        text = element.get_text(separator=" ", strip=True)
        if text and len(text) > 5:  # Skip very short text
            element_type = element.name
            semantic_role = _infer_semantic_role(element, element_type)
            
            segments.append({
                "text": text,
                "element_type": element_type,
                "semantic_role": semantic_role
            })
    
    # If no structured elements found, try divs with meaningful classes
    if not segments:
        for div in container.find_all('div', recursive=False):
            text = div.get_text(separator=" ", strip=True)
            if text and len(text) > 10:
                semantic_role = _infer_semantic_role(div, 'div')
                segments.append({
                    "text": text,
                    "element_type": "div",
                    "semantic_role": semantic_role
                })
    
    return segments


def _extract_structured_body_text(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Extract body text with HTML structure metadata preserved.
    
    Returns list of text segments with metadata:
    [
        {
            "text": "UP TO 70% OFF",
            "element_type": "h1",
            "semantic_role": "headline"
        },
        {
            "text": "Plus, buy two and get an extra 10% off!",
            "element_type": "p",
            "semantic_role": "subheadline"
        }
    ]
    
    This enables structure-aware scoring that can distinguish intentional
    visual hierarchy from actual tone inconsistencies.
    """
    structured_segments = []
    
    # Strategy 0: Check for product grids first
    try:
        product_cards = _detect_product_grid(soup)
        if product_cards:
            for card in product_cards[:20]:  # Limit to 20 products
                # Extract product name
                name = card.select_one('h1, h2, h3, h4, h5, strong, .product-name, .title, [class*="name"], [class*="title"]')
                name_text = name.get_text(separator=" ", strip=True) if name else ""
                
                # Extract price
                price = card.select_one('[class*="price"], .price, [class*="cost"]')
                price_text = price.get_text(separator=" ", strip=True) if price else ""
                
                if name_text:
                    product_text = name_text
                    if price_text:
                        product_text += f" ({price_text})"
                    
                    structured_segments.append({
                        "text": product_text,
                        "element_type": "product_card",
                        "semantic_role": "product_listing"
                    })
            
            if structured_segments:
                logger.debug(f"Extracted {len(structured_segments)} product cards with structure")
                return structured_segments
    except Exception as e:
        logger.debug(f"Structured product extraction failed: {e}")
    
    # Strategy 1: Try <article> tag
    article = soup.find("article")
    if article:
        segments = _extract_elements_with_structure(article)
        if segments and len(''.join(s['text'] for s in segments)) >= 100:
            logger.debug(f"Extracted {len(segments)} segments from <article>")
            return segments
    
    # Strategy 2: Try <main> tag or [role="main"]
    main = soup.find("main") or soup.select_one('[role="main"]')
    if main:
        segments = _extract_elements_with_structure(main)
        if segments and len(''.join(s['text'] for s in segments)) >= 100:
            logger.debug(f"Extracted {len(segments)} segments from <main>")
            return segments
    
    # Strategy 3: Try <div> with content-related class names
    content_class_patterns = [
        'content', 'post-content', 'article-body', 'article', 'entry',
        'post', 'body-text', 'post-body', 'main-content', 'page-content',
        'story-body', 'article-text', 'article-content', 'text-content'
    ]
    for pattern in content_class_patterns:
        divs = soup.find_all('div', class_=lambda x: x and pattern in x.lower())
        for div in divs:
            segments = _extract_elements_with_structure(div)
            if segments and len(''.join(s['text'] for s in segments)) >= 150:
                logger.debug(f"Extracted {len(segments)} segments from content div")
                return segments
    
    # Strategy 4: Try all <p> tags combined
    paragraphs = soup.find_all("p")
    if paragraphs:
        segments = []
        for p in paragraphs:
            text = p.get_text(separator=" ", strip=True)
            if text:
                segments.append({
                    "text": text,
                    "element_type": "p",
                    "semantic_role": "body_text"
                })
        if segments and len(''.join(s['text'] for s in segments)) >= 100:
            logger.debug(f"Extracted {len(segments)} paragraph segments")
            return segments
    
    # Strategy 5: Find longest <div> by text length
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
        segments = _extract_elements_with_structure(longest_div)
        if segments:
            logger.debug(f"Extracted {len(segments)} segments from longest div")
            return segments
    
    # Strategy 6: Fall back to entire body
    if soup.body:
        segments = _extract_elements_with_structure(soup.body)
        if segments:
            logger.debug(f"Extracted {len(segments)} segments from <body>")
            return segments
    
    return []


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


def _fetch_with_playwright(url: str, user_agent: str, browser_manager=None) -> Dict[str, str]:
    """Fetch a URL using Playwright and extract content.
    
    Args:
        url: URL to fetch
        user_agent: User agent string
        browser_manager: Optional PlaywrightBrowserManager instance for persistent browser
        
    Returns:
        Dict with title, body, url, terms, and privacy keys
    """
    page = None
    browser = None
    pw_context = None
    pw_cleanup = None
    
    try:
        # Use persistent browser if available
        if browser_manager and browser_manager.is_started:
            result = browser_manager.fetch_page(url, user_agent)
            
            # Extract footer links from raw_content if available
            if 'raw_content' in result:
                try:
                    links = _extract_footer_links(result['raw_content'], url)
                    result['terms'] = links.get('terms', '')
                    result['privacy'] = links.get('privacy', '')
                    del result['raw_content']  # Clean up
                except Exception:
                    result['terms'] = ""
                    result['privacy'] = ""
            return result
        else:
            # Fallback to per-page browser launch
            if not _PLAYWRIGHT_AVAILABLE:
                return {"title": "", "body": "", "url": url, "terms": "", "privacy": ""}

            pw_context = sync_playwright()

            # Support both context-manager style and explicit .start() to remain
            # compatible with tests that monkeypatch sync_playwright.
            if hasattr(pw_context, '__enter__'):
                pw = pw_context.__enter__()

                def _cleanup():
                    try:
                        pw_context.__exit__(None, None, None)
                    except Exception:
                        pass

                pw_cleanup = _cleanup
            else:
                pw = pw_context.start()

                def _cleanup():
                    try:
                        pw_context.stop()
                    except Exception:
                        pass

                pw_cleanup = _cleanup

            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=user_agent)
        
        # Navigate to page
        page.goto(url, timeout=20000)
        
        # Wait for body
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
            # Fallback to raw HTML if inner_text extraction fails
            page_body = page_content
        
        # Extract footer links
        try:
            links = _extract_footer_links(page_content, url)
        except Exception:
            links = {"terms": "", "privacy": ""}
        
        return {
            "title": page_title.strip(),
            "body": page_body.strip(),
            "url": url,
            "terms": links.get("terms", ""),
            "privacy": links.get("privacy", "")
        }
        
    except Exception as e:
        logger.warning('Playwright fetch failed for %s: %s', url, e)
        return {"title": "", "body": "", "url": url, "terms": "", "privacy": ""}
    finally:
        # Clean up
        if page:
            try:
                page.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw_cleanup:
            pw_cleanup()


def fetch_page(url: str, timeout: int = 10, browser_manager=None) -> Dict[str, str]:
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

    # Smart Fallback: Check if we already know this domain needs Playwright
    # But only if Playwright is available and enabled
    use_pw_config = should_use_playwright(url)
    if _PLAYWRIGHT_AVAILABLE and (use_pw_config or _domain_config.requires_playwright(url)):
        logger.info('Smart Fallback: Skipping lxml fetch for %s (known to require Playwright)', url)
        # Use realistic browser headers for Playwright too
        pw_headers = get_realistic_headers(url)
        ua = pw_headers['User-Agent']
        # Respect robots.txt before attempting a headful fetch
        try:
            allowed = _is_allowed_by_robots(url, ua)
        except Exception:
            allowed = True
        if allowed:
            return _fetch_with_playwright(url, ua, browser_manager)

    resp = None
    last_status_code = None

    for attempt in range(1, retries + 1):
        try:
            # Use randomized delay instead of fixed rate limit
            if attempt == 1:
                # First attempt: use configured rate limit
                _rate_limiter.wait_for_domain(url)
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
                        result = _fetch_with_playwright(url, ua, browser_manager)
                        if result.get('body') and len(result.get('body', '')) >= 100:
                            # Success! Mark this domain as requiring Playwright for future
                            _domain_config.mark_requires_playwright(url)
                            return result
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

        soup = BeautifulSoup(resp.text, "lxml")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # Try OpenGraph / Twitter meta fallbacks for title/description
        if not title:
            og_title = soup.select_one('meta[property="og:title"]') or soup.select_one('meta[name="twitter:title"]')
            if og_title and og_title.get('content'):
                title = og_title.get('content').strip()

        # Extract body using multiple strategies (plain text for backward compatibility)
        body = _extract_body_text(soup)
        
        # Also extract structured body text with HTML metadata
        structured_body = _extract_structured_body_text(soup)

        # If body or title are thin, try OG/Twitter description and dump for debugging
        if (not body or len(body) < 200) and soup.select_one('meta[property="og:description"]'):
            og_desc = soup.select_one('meta[property="og:description"]') or soup.select_one('meta[name="twitter:description"]')
            if og_desc and og_desc.get('content'):
                body = og_desc.get('content').strip()
        if (not title or not body or len(body) < 200):
            # Attempt Playwright fallback for thin content if enabled and allowed
            # Force Playwright if content is thin, even if not explicitly configured for this domain
            try_playwright = _PLAYWRIGHT_AVAILABLE
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
                        result = _fetch_with_playwright(url, ua, browser_manager)
                        if result.get('body') and len(result.get('body', '')) >= 150:
                            # Success! Mark this domain as requiring Playwright for future
                            _domain_config.mark_requires_playwright(url)
                            return result
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
        return {
            "title": title, 
            "body": body, 
            "structured_body": structured_body,
            "url": url, 
            "terms": links.get("terms", ""), 
            "privacy": links.get("privacy", "")
        }
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


def fetch_pages_parallel(
    urls: List[str],
    max_workers: int = None,
    browser_manager=None
) -> List[Dict[str, str]]:
    """Fetch multiple pages in parallel using ThreadPoolExecutor.
    
    This function significantly improves performance when fetching multiple pages,
    especially for JavaScript-heavy pages that require Playwright rendering.
    
    Args:
        urls: List of URLs to fetch
        max_workers: Maximum number of concurrent fetches (default: from env or 5)
        browser_manager: Optional PlaywrightBrowserManager for persistent browser
        
    Returns:
        List of dicts with page content {title, body, url, ...}
        Results are returned in the same order as input URLs.
        
    Example:
        >>> urls = ['https://example.com/page1', 'https://example.com/page2']
        >>> results = fetch_pages_parallel(urls, max_workers=5)
        >>> # Results returned in same order as input URLs
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Try to import Streamlit context utilities to suppress threading warnings
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx, add_script_run_ctx
        streamlit_ctx = get_script_run_ctx()
    except ImportError:
        streamlit_ctx = None
    
    if not urls:
        return []
    
    # Get max_workers from environment or use default
    if max_workers is None:
        max_workers = int(os.getenv('AR_PARALLEL_FETCH_WORKERS', '5'))
    
    # Limit max_workers to avoid overwhelming the system
    max_workers = min(max_workers, len(urls), 10)
    
    logger.info('[PARALLEL] Fetching %d pages with %d workers', len(urls), max_workers)
    
    results = {}
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Define the function to submit
        if streamlit_ctx:
            def fetch_task(url, browser_manager=None):
                # Re-attach context in the new thread
                add_script_run_ctx(threading.current_thread(), streamlit_ctx)
                return fetch_page(url, browser_manager=browser_manager)
        else:
            fetch_task = fetch_page

        # Submit all fetch tasks exactly once
        future_to_url = {
            executor.submit(fetch_task, url, browser_manager=browser_manager): url
            for url in urls
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            completed += 1
            try:
                result = future.result()
                results[url] = result
                body_len = len(result.get('body', ''))
                logger.debug('[PARALLEL] ✓ Fetched %s [%d/%d] [len=%d]', 
                           url, completed, len(urls), body_len)
            except Exception as e:
                logger.warning('[PARALLEL] ✗ Failed to fetch %s [%d/%d]: %s', 
                             url, completed, len(urls), e)
                results[url] = {"title": "", "body": "", "url": url}
    
    elapsed = time.time() - start_time
    logger.info('[PARALLEL] Completed fetching %d pages in %.2f seconds (avg: %.2f s/page)',
               len(urls), elapsed, elapsed / len(urls) if urls else 0)
    
    # Return results in original order
    return [results[url] for url in urls]

