"""
Social Media Search Service

This module handles the discovery and validation of brand social media channels
across Instagram, LinkedIn, and X.
"""
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def search_social_media_channels(brand_id: str, search_provider: str, progress_animator, logger) -> List[Dict[str, Any]]:
    """
    Search for official brand social media channels on Instagram, LinkedIn, and X.

    Args:
        brand_id: The brand identifier (e.g., "Mastercard")
        search_provider: The search provider to use ('brave' or 'serper')
        progress_animator: Progress animator instance
        logger: Logger instance

    Returns:
        List of social media channel results
    """
    social_results = []

    # Social media platforms to search
    social_platforms = [
        # {
        #     'name': 'Instagram',
        #     'site': 'instagram.com',
        #     'emoji': '📸',
        #     'tier': 'brand_social'
        # },
        # {
        #     'name': 'LinkedIn',
        #     'site': 'linkedin.com',
        #     'emoji': '💼',
        #     'tier': 'brand_social'
        # },
        # {
        #     'name': 'X (Twitter)',
        #     'site': 'x.com',
        #     'emoji': '✖️',
        #     'tier': 'brand_social'
        # }
    ]

    for platform in social_platforms:
        try:
            # Build site-specific query
            query = f"{brand_id} official site:{platform['site']}"

            progress_animator.show(
                f"Searching {platform['name']} for official {brand_id} channel...",
                platform['emoji']
            )

            logger.info(f"Searching {platform['name']}: {query}")

            # Use the appropriate search provider
            search_results = []

            if search_provider == 'brave':
                from ingestion.brave_search import search_brave
                # Get top 3 results from this platform
                results = search_brave(query, size=3)
                if results:
                    for result in results:
                        search_results.append({
                            'url': result.get('url', ''),
                            'title': result.get('title', f'{brand_id} on {platform["name"]}'),
                            'snippet': result.get('snippet', result.get('description', ''))
                        })
            else:  # serper
                from ingestion.serper_search import search_serper
                # Get top 3 results from this platform
                results = search_serper(query, size=3)
                if results:
                    for result in results:
                        search_results.append({
                            'url': result.get('url', ''),
                            'title': result.get('title', f'{brand_id} on {platform["name"]}'),
                            'snippet': result.get('snippet', result.get('description', ''))
                        })

            # Filter to only actual social media profile URLs (not just mentions)
            for result in search_results:
                url = result.get('url', '')
                if url and _is_valid_social_profile(url, platform['site'], brand_id):
                    social_results.append({
                        'url': url,
                        'title': result.get('title', f'{brand_id} on {platform["name"]}'),
                        'description': result.get('snippet', ''),
                        'is_brand_owned': True,
                        'is_core_domain': False,
                        'source_type': 'brand_owned',
                        'source_tier': platform['tier'],
                        'classification_reason': f'Official {platform["name"]} channel',
                        'selected': True,
                        'source': f'{search_provider}_social',
                        'platform': platform['name']
                    })
                    logger.info(f"Found {platform['name']} channel: {url}")
                    # Only take the first valid profile per platform
                    break

        except Exception as e:
            logger.warning(f"Error searching {platform['name']}: {e}")
            continue

    return social_results


def _is_valid_social_profile(url: str, platform_site: str, brand_id: str) -> bool:
    """
    Validate that a URL is an actual social media profile page.

    Args:
        url: The URL to validate
        platform_site: The social media site (e.g., 'instagram.com')
        brand_id: The brand identifier

    Returns:
        True if this is a valid profile URL, False otherwise
    """
    try:
        parsed = urlparse(url.lower())

        # Must be on the correct domain
        if platform_site not in parsed.netloc:
            return False

        path = parsed.path.lower()

        # Instagram profiles
        if 'instagram.com' in platform_site:
            # Valid: /username or /username/
            # Invalid: /p/, /tv/, /explore/, /accounts/
            invalid_patterns = ['/p/', '/tv/', '/explore/', '/accounts/', '/reels/', '/stories/']
            if any(pattern in path for pattern in invalid_patterns):
                return False
            # Should have a username path (starts with /)
            if not path or path == '/' or len(path.split('/')) < 2:
                return False
            return True

        # LinkedIn profiles
        elif 'linkedin.com' in platform_site:
            # Valid: /company/name or /in/name
            # Invalid: /posts/, /feed/, /search/
            if '/company/' in path or '/showcase/' in path:
                return True
            invalid_patterns = ['/posts/', '/feed/', '/search/', '/in/', '/pulse/']
            if any(pattern in path for pattern in invalid_patterns):
                return False
            return '/company/' in path or '/showcase/' in path

        # Twitter/X profiles
        elif 'twitter.com' in platform_site or 'x.com' in platform_site:
            # Valid: /username or /username/
            # Invalid: /i/, /search/, /hashtag/, /status/
            invalid_patterns = ['/i/', '/search/', '/hashtag/', '/status/', '/explore/', '/notifications/']
            if any(pattern in path for pattern in invalid_patterns):
                return False
            # Should have a username path
            if not path or path == '/' or len(path.split('/')) < 2:
                return False
            return True

        return False

    except Exception:
        return False
