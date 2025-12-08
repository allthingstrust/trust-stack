"""Unified search interface for multiple search providers

This module provides a single search() function that routes to different search providers
based on the SEARCH_PROVIDER environment variable. This allows easy switching between
search APIs without changing application code.

Supported Providers:
- brave: Brave Search API
- serper: Serper (Google Search API wrapper)

Usage:
    from ingestion.search_unified import search

    # Uses provider specified in SEARCH_PROVIDER env var
    results = search("your query", size=20)

Configuration:
    Set SEARCH_PROVIDER=brave or SEARCH_PROVIDER=serper in your .env file
"""
from __future__ import annotations

import logging
import os
from typing import List, Dict
from config.settings import get_secret

logger = logging.getLogger(__name__)

# Import both search modules with aliases to avoid naming conflicts
try:
    from ingestion.brave_search import search_brave as _brave_search_impl
    _BRAVE_AVAILABLE = True
except ImportError as e:
    logger.warning('Brave search not available: %s', e)
    _BRAVE_AVAILABLE = False
    _brave_search_impl = None

try:
    from ingestion.serper_search import search_serper as _serper_search_impl
    _SERPER_AVAILABLE = True
except ImportError as e:
    logger.warning('Serper search not available: %s', e)
    _SERPER_AVAILABLE = False
    _serper_search_impl = None


def search(query: str, size: int = 10, provider: str | None = None) -> List[Dict[str, str]]:
    """Unified search interface that routes to the configured search provider.

    Args:
        query: Search query string
        size: Number of results to retrieve
        provider: Optional provider override ('brave' or 'serper').
                 If None, uses SEARCH_PROVIDER environment variable.

    Returns:
        List of dicts with keys: title, url, snippet

    Raises:
        ValueError: If provider is not configured or not available
        Exception: If search fails
    """
    # Determine which provider to use
    if provider is None:
        provider = get_secret('SEARCH_PROVIDER', 'brave').lower()

    logger.info('Using search provider: %s for query: %s', provider, query)

    if provider == 'brave':
        if not _BRAVE_AVAILABLE:
            raise ValueError(
                'Brave search is not available. Check brave_search.py import.'
            )
        return _brave_search_impl(query, size=size)

    elif provider == 'serper':
        if not _SERPER_AVAILABLE:
            raise ValueError(
                'Serper search is not available. Check serper_search.py import.'
            )
        return _serper_search_impl(query, size=size)

    else:
        raise ValueError(
            f"Unknown search provider: {provider}. "
            f"Valid options are: 'brave', 'serper'"
        )


def get_available_providers() -> List[str]:
    """Get list of available search providers.

    Returns:
        List of provider names that are currently available
    """
    providers = []
    if _BRAVE_AVAILABLE:
        providers.append('brave')
    if _SERPER_AVAILABLE:
        providers.append('serper')
    return providers


def get_current_provider() -> str:
    """Get the currently configured search provider.

    Returns:
        Name of the current provider from SEARCH_PROVIDER env var
    """
    return get_secret('SEARCH_PROVIDER', 'brave').lower()


def validate_provider_config() -> Dict[str, any]:
    """Validate the current provider configuration.

    Returns:
        Dict with validation results:
        - provider: Current provider name
        - available: Whether the provider is available
        - configured: Whether required API keys are set
        - ready: Whether provider is ready to use
        - message: Status message
    """
    provider = get_current_provider()
    available_providers = get_available_providers()

    result = {
        'provider': provider,
        'available': provider in available_providers,
        'configured': False,
        'ready': False,
        'message': ''
    }

    if not result['available']:
        result['message'] = f"Provider '{provider}' is not available. Available: {available_providers}"
        return result

    # Check if API keys are configured
    if provider == 'brave':
        api_key = get_secret('BRAVE_API_KEY')
        if api_key:
            result['configured'] = True
            result['ready'] = True
            result['message'] = 'Brave Search is configured and ready'
        else:
            result['message'] = 'BRAVE_API_KEY not found in environment'

    elif provider == 'serper':
        api_key = get_secret('SERPER_API_KEY')
        if api_key:
            result['configured'] = True
            result['ready'] = True
            result['message'] = 'Serper API is configured and ready'
        else:
            result['message'] = 'SERPER_API_KEY not found in environment'

    return result


# Backward compatibility: allow direct import of search_brave
# This ensures existing code continues to work
def search_brave(query: str, size: int = 10) -> List[Dict[str, str]]:
    """Backward compatibility wrapper for search_brave.

    Delegates to the unified search interface with provider='brave'.
    """
    return search(query, size=size, provider='brave')


# Convenience function for serper
def search_serper(query: str, size: int = 10) -> List[Dict[str, str]]:
    """Convenience wrapper for search_serper.

    Delegates to the unified search interface with provider='serper'.
    """
    return search(query, size=size, provider='serper')
