"""Search provider interface for unified page collection.

Provides an abstract interface for search providers (Brave, Serper, etc.)
to enable unified collection logic with provider-specific search implementations.
"""
from abc import ABC, abstractmethod
from typing import List, Dict


class SearchProvider(ABC):
    """Abstract interface for search providers.
    
    Implementations must provide a search method that returns standardized
    search results with url, title, and snippet fields.
    """
    
    @abstractmethod
    def search(self, query: str, size: int) -> List[Dict[str, str]]:
        """Execute search and return results.
        
        Args:
            query: Search query string
            size: Number of results to retrieve
            
        Returns:
            List of dicts with keys: url, title, snippet
            
        Raises:
            Exception: If search fails or API is unavailable
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging (e.g., 'BRAVE', 'SERPER')."""
        pass


class BraveSearchProvider(SearchProvider):
    """Brave Search API provider."""
    
    def search(self, query: str, size: int) -> List[Dict[str, str]]:
        """Execute Brave search and return standardized results."""
        from ingestion.brave_search import search_brave
        return search_brave(query, size)
    
    @property
    def name(self) -> str:
        return "BRAVE"


class SerperSearchProvider(SearchProvider):
    """Serper (Google Search) API provider."""
    
    def search(self, query: str, size: int) -> List[Dict[str, str]]:
        """Execute Serper search and return standardized results."""
        from ingestion.serper_search import search_serper
        return search_serper(query, size)
    
    @property
    def name(self) -> str:
        return "SERPER"
