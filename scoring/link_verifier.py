"""
Link verifier for validating LLM-reported broken links
Checks actual HTTP status codes to prevent hallucinations
"""

import re
import logging
from typing import List, Set
import requests
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# Timeout for HTTP requests (seconds)
# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 10

# Default headers to mimic a real browser
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def extract_urls(text: str) -> Set[str]:
    """
    Extract URLs from text content
    
    Args:
        text: Content text to extract URLs from
    
    Returns:
        Set of unique URLs found in text
    """
    # Regex pattern for URLs
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    
    urls = set(re.findall(url_pattern, text))
    return urls


def check_link_status(url: str) -> dict:
    """
    Check HTTP status of a single URL
    
    Args:
        url: URL to check
    
    Returns:
        Dict with 'url', 'status_code', 'is_broken', 'error'
    """
    try:
        # First try HEAD request with headers
        try:
            response = requests.head(
                url, 
                headers=DEFAULT_HEADERS, 
                timeout=REQUEST_TIMEOUT, 
                allow_redirects=True
            )
            status_code = response.status_code
        except requests.exceptions.RequestException:
            # If HEAD fails (connection error etc), force a retry with GET below
            status_code = None

        # If HEAD failed or returned 403/404/405/503, try GET as fallback
        # (Some servers block HEAD or return 403 for it)
        if status_code is None or status_code in [403, 404, 405, 503]:
            try:
                response = requests.get(
                    url, 
                    headers=DEFAULT_HEADERS, 
                    timeout=REQUEST_TIMEOUT, 
                    allow_redirects=True, 
                    stream=True
                )
                status_code = response.status_code
                response.close() # Close immediately, we just need the status
            except requests.exceptions.RequestException:
                pass # use the previous status_code or None

        # Determine if broken
        # 403 Forbidden is treated as NOT BROKEN because it usually means the link exists
        # but the server is blocking our bot/crawler.
        if status_code == 403:
            is_broken = False
            logger.info(f"URL {url} returned 403 (Forbidden). Treating as valid (anti-bot protection).")
        else:
            is_broken = status_code is not None and status_code >= 400

        return {
            'url': url,
            'status_code': status_code,
            'is_broken': is_broken,
            'error': None
        }
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout checking URL: {url}")
        return {
            'url': url,
            'status_code': None,
            'is_broken': True,
            'error': 'timeout'
        }
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error checking URL {url}: {e}")
        return {
            'url': url,
            'status_code': None,
            'is_broken': True,
            'error': str(e)
        }


def verify_broken_links(content_text: str, content_url: str = None) -> List[dict]:
    """
    Verify which links in content are actually broken
    
    Args:
        content_text: Text content to check for links
        content_url: Base URL for resolving relative links (optional)
    
    Returns:
        List of broken link dicts with url, status_code, error
    """
    urls = extract_urls(content_text)
    
    if not urls:
        logger.debug("No URLs found in content")
        return []
    
    logger.info(f"Checking {len(urls)} URLs for broken links")
    
    broken_links = []
    for url in urls:
        # Resolve relative URLs if base URL provided
        if content_url and not urlparse(url).netloc:
            url = urljoin(content_url, url)
        
        result = check_link_status(url)
        if result['is_broken']:
            broken_links.append(result)
            logger.info(f"Found broken link: {url} (status={result['status_code']})")
    
    return broken_links
