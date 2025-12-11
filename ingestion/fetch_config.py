"""
Domain-specific fetch configuration for web scraping.

This module provides configurations for different types of domains to improve
scraping success rates for legitimate, authorized scraping scenarios.
"""

import os
import random
from typing import Dict, Any, Optional
from urllib.parse import urlparse


# Domain-specific configurations
DOMAIN_CONFIGS = {
    # Social media platforms - require JS rendering for verification badges
    "instagram.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "twitter.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "x.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "linkedin.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    # Enterprise financial/banking sites - often have sophisticated anti-bot protection
    "mastercard.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "visa.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "americanexpress.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "discover.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    # Add more enterprise domains as needed
    "chase.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
    "bankofamerica.com": {
        "use_playwright": True,
        "min_delay": 2.0,
        "max_delay": 4.0,
        "timeout": 15,
        "max_retries": 3,
    },
}

# Default configuration for domains not in DOMAIN_CONFIGS
DEFAULT_CONFIG = {
    "use_playwright": False,
    "min_delay": 1.0,
    "max_delay": 2.5,
    "timeout": 10,
    "max_retries": 3,
}

# Pool of realistic User-Agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def get_domain_config(url: str) -> Dict[str, Any]:
    """
    Get configuration for a specific domain.

    Args:
        url: The URL to fetch

    Returns:
        Dictionary with configuration parameters
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www. prefix for matching
        if domain.startswith('www.'):
            domain = domain[4:]

        # Check for exact domain match
        if domain in DOMAIN_CONFIGS:
            return DOMAIN_CONFIGS[domain].copy()

        # Check for parent domain match (e.g., blog.mastercard.com -> mastercard.com)
        parts = domain.split('.')
        if len(parts) >= 2:
            parent_domain = '.'.join(parts[-2:])
            if parent_domain in DOMAIN_CONFIGS:
                return DOMAIN_CONFIGS[parent_domain].copy()

        return DEFAULT_CONFIG.copy()
    except Exception:
        return DEFAULT_CONFIG.copy()


def get_random_delay(url: str) -> float:
    """
    Get a randomized delay for the given URL based on domain configuration.

    Args:
        url: The URL to fetch

    Returns:
        Random delay in seconds
    """
    config = get_domain_config(url)
    min_delay = config.get('min_delay', 1.0)
    max_delay = config.get('max_delay', 2.5)

    # Check if randomization is enabled via environment variable
    if os.getenv('AR_RANDOMIZE_DELAYS', '1') == '1':
        return random.uniform(min_delay, max_delay)
    else:
        # Use average of min and max if randomization is disabled
        return (min_delay + max_delay) / 2


def get_realistic_headers(url: str = '', referer: Optional[str] = None) -> Dict[str, str]:
    """
    Get realistic browser headers for the given URL.

    Args:
        url: The URL being fetched (optional, for future domain-specific headers)
        referer: The referer URL to include (optional)

    Returns:
        Dictionary of HTTP headers
    """
    # Get user agent from environment or use random from pool
    user_agent = os.getenv('AR_USER_AGENT')
    if not user_agent or 'bot' in user_agent.lower():
        # Use random UA from pool if env var is not set or is a bot UA
        user_agent = random.choice(USER_AGENTS)

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }

    # Add referer if provided
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "cross-site"

    return headers


def should_use_playwright(url: str) -> bool:
    """
    Determine if Playwright should be used for the given URL.

    Args:
        url: The URL to fetch

    Returns:
        True if Playwright should be used, False otherwise
    """
    # Check global override first
    if os.getenv('AR_USE_PLAYWRIGHT', '0') == '1':
        return True

    # Check domain-specific configuration
    config = get_domain_config(url)
    return config.get('use_playwright', False)


def get_retry_config(url: str, status_code: Optional[int] = None) -> Dict[str, Any]:
    """
    Get retry configuration for a given URL and response status.

    Args:
        url: The URL being fetched
        status_code: HTTP status code of the response (if available)

    Returns:
        Dictionary with retry configuration
    """
    config = get_domain_config(url)
    base_backoff = float(os.getenv('AR_FETCH_BACKOFF', '0.6'))

    # Increase backoff for certain status codes
    if status_code == 403:
        # Access forbidden - back off more aggressively
        backoff_multiplier = 3.0
    elif status_code == 429:
        # Rate limited - back off significantly
        backoff_multiplier = 5.0
    elif status_code and 500 <= status_code < 600:
        # Server error - moderate backoff
        backoff_multiplier = 2.0
    else:
        backoff_multiplier = 1.0

    return {
        'max_retries': config.get('max_retries', 3),
        'base_backoff': base_backoff * backoff_multiplier,
        'timeout': config.get('timeout', 10),
    }
