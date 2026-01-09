"""
URL verification and title extraction utilities.
"""
import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from ingestion.fetch_config import get_realistic_headers, get_random_delay
from webapp.utils.url_utils import normalize_international_url, _fallback_title, extract_hostname

logger = logging.getLogger(__name__)

def fetch_page_title(url: str, brand_id: str = '', timeout: float = 5.0) -> str:
    """Retrieve a human-readable title for a given URL, fallback to hostname, and handle hostname mismatches."""
    # Use realistic browser headers from the start
    headers = get_realistic_headers(url)

    try:
        # Use realistic headers with full browser simulation
        response = requests.get(url, timeout=timeout, headers=headers)
        status = getattr(response, 'status_code', None)
        if status and 200 <= status < 400:
            soup = BeautifulSoup(response.text, 'html.parser')
            title_tag = soup.title
            if title_tag and title_tag.string:
                title = title_tag.string.strip()
                if title:
                    return title
        # If we get a 403, add a random delay and retry with fresh headers
        if status == 403:
            logger.debug('Received 403 fetching title for %s; retrying with delay and fresh headers', url)
            try:
                delay = get_random_delay(url)
                time.sleep(delay)
                # Get fresh headers with potentially different UA
                fresh_headers = get_realistic_headers(url)
                resp2 = requests.get(url, timeout=max(timeout, 6.0), headers=fresh_headers)
                if getattr(resp2, 'status_code', None) and 200 <= resp2.status_code < 400:
                    soup = BeautifulSoup(resp2.text, 'html.parser')
                    title_tag = soup.title
                    if title_tag and title_tag.string:
                        return title_tag.string.strip()
            except Exception as e:
                logger.debug('Retry with fresh headers failed for %s: %s', url, e)
    except requests.exceptions.SSLError as exc:
        logger.debug('SSL error fetching %s: %s', url, exc)
        normalized_url = normalize_international_url(url, brand_id)
        if normalized_url and normalized_url != url:
            logger.info('Retrying with normalized host: %s', normalized_url)
            return fetch_page_title(normalized_url, brand_id, timeout)
        return _fallback_title(url)
    except Exception as exc:
        logger.debug('Unable to fetch title for %s: %s', url, exc)
        return _fallback_title(url)

    parsed = urlparse(url)
    hostname = parsed.hostname or url
    return hostname


def verify_url(url: str, brand_id: str = '', timeout: float = 5.0) -> bool:
    """Verify that a URL is reachable (2xx or 3xx).

    Returns a dict: {'ok': bool, 'status': int|None, 'final_url': str|None}

    Retries with normalized host on SSL errors.
    """
    # Use realistic browser headers
    headers = get_realistic_headers(url)
    try:
        # Prefer HEAD for lightweight check
        resp = requests.head(url, timeout=timeout, headers=headers, allow_redirects=True)
        status = getattr(resp, 'status_code', None)
        final = getattr(resp, 'url', url)
        if status and 200 <= status < 400:
            return {'ok': True, 'status': status, 'final_url': final}
        # If forbidden (403), try again with a browser UA via GET
        if status == 403:
            logger.debug('HEAD returned 403 for %s; retrying GET with browser UA', url)
            try:
                browser_headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                resp2 = requests.get(url, timeout=max(timeout, 6.0), headers=browser_headers, allow_redirects=True)
                status2 = getattr(resp2, 'status_code', None)
                final2 = getattr(resp2, 'url', url)
                if status2 and 200 <= status2 < 400:
                    return {'ok': True, 'status': status2, 'final_url': final2}
                # If still forbidden, attempt DNS resolution as a soft-verification
                try:
                    from socket import getaddrinfo
                    host = extract_hostname(url)
                    if host:
                        addrs = getaddrinfo(host, None)
                        if addrs:
                            logger.info('Host %s resolves via DNS; marking soft-verified', host)
                            return {'ok': True, 'status': status2, 'final_url': final2, 'soft_verified': True, 'method': 'dns_resolution'}
                except Exception as _:
                    pass
                return {'ok': False, 'status': status2, 'final_url': final2}
            except Exception as e:
                logger.debug('Browser-UA GET retry failed for %s: %s', url, e)
                return {'ok': False, 'status': status, 'final_url': final}
        # Some servers don't like HEAD; fall back to GET for verification
        if status in (405, 501) or status is None:
            try:
                resp = requests.get(url, timeout=max(timeout, 6.0), headers=headers, allow_redirects=True)
                status = getattr(resp, 'status_code', None)
                final = getattr(resp, 'url', url)
                return {'ok': bool(status and 200 <= status < 400), 'status': status, 'final_url': final}
            except Exception as e:
                logger.debug('GET fallback failed for %s after HEAD status=%s: %s', url, status, e)
                return {'ok': False, 'status': status, 'final_url': final}
        return {'ok': False, 'status': status, 'final_url': final}
    except requests.exceptions.SSLError as exc:
        logger.debug('SSL error verifying %s: %s', url, exc)
        normalized = normalize_international_url(url, brand_id)
        if normalized and normalized != url:
            logger.info('Retrying verification with normalized host: %s', normalized)
            return verify_url(normalized, brand_id, timeout)
        return {'ok': False, 'status': None, 'final_url': None}
    except Exception as exc:
        # Some network/HEAD-specific errors can be resolved by trying GET once
        logger.debug('HEAD request failed for %s: %s -- attempting GET fallback', url, exc)
        try:
            resp = requests.get(url, timeout=max(timeout, 6.0), headers=headers, allow_redirects=True)
            status = getattr(resp, 'status_code', None)
            final = getattr(resp, 'url', url)
            return {'ok': bool(status and 200 <= status < 400), 'status': status, 'final_url': final}
        except requests.exceptions.SSLError as exc2:
            logger.debug('SSL error on GET fallback for %s: %s', url, exc2)
            normalized = normalize_international_url(url, brand_id)
            if normalized and normalized != url:
                logger.info('Retrying verification with normalized host (GET fallback): %s', normalized)
                return verify_url(normalized, brand_id, timeout)
            return {'ok': False, 'status': None, 'final_url': None}
        except Exception as exc2:
            logger.debug('GET fallback also failed for %s: %s', url, exc2)
            return {'ok': False, 'status': None, 'final_url': None}
