"""Unified page collection logic for search providers.

This module provides a unified interface for collecting pages from different
search providers (Brave, Serper, etc.) with shared optimization logic.
"""
import logging
from typing import List, Dict, Optional

from ingestion.search_provider import SearchProvider

logger = logging.getLogger(__name__)


def collect_pages(
    provider: SearchProvider,
    query: str,
    target_count: int = 10,
    pool_size: Optional[int] = None,
    min_body_length: int = 200,
    min_brand_body_length: Optional[int] = None,
    url_collection_config: Optional['URLCollectionConfig'] = None
) -> List[Dict[str, str]]:
    """Unified page collection with provider-agnostic logic.
    
    This function provides a single entry point for page collection across
    different search providers. It delegates to provider-specific collection
    functions while ensuring consistent behavior.
    
    Args:
        provider: Search provider implementation (Brave, Serper, etc.)
        query: Search query string
        target_count: Target number of pages to collect
        pool_size: Number of search results to request (defaults to target_count * 5)
        min_body_length: Minimum body length for third-party pages (default: 200)
        min_brand_body_length: Minimum body length for brand-owned pages (default: 75)
        url_collection_config: Optional ratio enforcement configuration
        
    Returns:
        List of dicts with page content {title, body, url, source_type, source_tier, ...}
        
    Note:
        Currently delegates to provider-specific implementations. Future versions
        will extract shared logic into this function for better code reuse.
    """
    # Delegate to provider-specific implementation
    # TODO: Extract shared logic from provider-specific functions into this unified function
    
    if provider.name == "BRAVE":
        from ingestion.brave_search import collect_brave_pages
        return collect_brave_pages(
            query=query,
            target_count=target_count,
            pool_size=pool_size,
            min_body_length=min_body_length,
            min_brand_body_length=min_brand_body_length,
            url_collection_config=url_collection_config
        )
    elif provider.name == "SERPER":
        from ingestion.serper_search import collect_serper_pages
        return collect_serper_pages(
            query=query,
            target_count=target_count,
            pool_size=pool_size,
            min_body_length=min_body_length,
            min_brand_body_length=min_brand_body_length,
            url_collection_config=url_collection_config
        )
    else:
        raise ValueError(f"Unknown search provider: {provider.name}")
