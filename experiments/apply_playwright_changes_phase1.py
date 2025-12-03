#!/usr/bin/env python3
"""
Script to apply Playwright browser manager integration to brave_search.py
This applies the changes systematically to avoid indentation errors.
"""

import re

# Read the current file
with open('ingestion/brave_search.py', 'r') as f:
    content = f.read()

# 1. Add concurrent.futures import (after line 21)
if 'from concurrent.futures import ThreadPoolExecutor, as_completed' not in content:
    content = content.replace(
        'from pathlib import Path',
        'from pathlib import Path\nfrom concurrent.futures import ThreadPoolExecutor, as_completed'
    )
    print("✓ Added concurrent.futures import")

# 2. Add _fetch_with_playwright helper function before fetch_page
helper_function = '''
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
    
    try:
        # Use persistent browser if available, otherwise launch new browser
        if browser_manager and browser_manager.is_started:
            page = browser_manager.get_page(user_agent=user_agent)
            if not page:
                logger.warning('Failed to get page from browser manager for %s', url)
                return {"title": "", "body": "", "url": url, "terms": "", "privacy": ""}
        else:
            # Fallback to per-page browser launch
            if not _PLAYWRIGHT_AVAILABLE:
                return {"title": "", "body": "", "url": url, "terms": "", "privacy": ""}
            pw_context = sync_playwright().start()
            browser = pw_context.chromium.launch(headless=True)
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
                page_body = "\\n\\n".join(texts)

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
        if pw_context:
            try:
                pw_context.stop()
            except Exception:
                pass


'''

if '_fetch_with_playwright' not in content:
    # Find the line before fetch_page definition
    content = content.replace(
        '\ndef fetch_page(url: str, timeout: int = 10) -> Dict[str, str]:',
        helper_function + 'def fetch_page(url: str, timeout: int = 10, browser_manager=None) -> Dict[str, str]:'
    )
    print("✓ Added _fetch_with_playwright helper function")
    print("✓ Updated fetch_page signature")
else:
    # Just update the signature
    content = content.replace(
        'def fetch_page(url: str, timeout: int = 10) -> Dict[str, str]:',
        'def fetch_page(url: str, timeout: int = 10, browser_manager=None) -> Dict[str, str]:'
    )
    print("✓ Updated fetch_page signature")

# Write the modified content
with open('ingestion/brave_search.py', 'w') as f:
    f.write(content)

print("\n✅ Phase 1 complete: Added imports, helper function, and updated fetch_page signature")
