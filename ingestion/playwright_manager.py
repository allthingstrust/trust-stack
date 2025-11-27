"""Playwright browser manager for persistent browser instance.

Provides thread-safe management of a persistent Playwright browser instance
to avoid the overhead of launching and closing the browser for each page fetch.
"""
import logging
import threading
from typing import Optional

logger = logging.getLogger('ingestion.playwright_manager')

# Optional Playwright import
try:
    from playwright.sync_api import sync_playwright, Browser, Page, Playwright
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False
    Browser = None
    Page = None
    Playwright = None


class PlaywrightBrowserManager:
    """Thread-safe manager for persistent Playwright browser instance.
    
    Usage:
        manager = PlaywrightBrowserManager()
        manager.start()
        try:
            page = manager.get_page(user_agent='...')
            # ... use page ...
            page.close()
        finally:
            manager.close()
    """
    
    def __init__(self):
        """Initialize the browser manager."""
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = threading.Lock()
        self._is_started = False
        
    def start(self) -> bool:
        """Launch the browser instance.
        
        Should be called once at the start of a collection run.
        
        Returns:
            True if browser was started successfully, False otherwise
        """
        if not _PLAYWRIGHT_AVAILABLE:
            logger.warning('Playwright is not available, cannot start browser')
            return False
            
        with self._lock:
            if self._is_started:
                logger.debug('Browser already started')
                return True
                
            try:
                logger.info('Starting persistent Playwright browser...')
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=True)
                self._is_started = True
                logger.info('Playwright browser started successfully')
                return True
            except Exception as e:
                logger.error('Failed to start Playwright browser: %s', e)
                self._playwright = None
                self._browser = None
                self._is_started = False
                return False
    
    def get_page(self, user_agent: str) -> Optional[Page]:
        """Get a new browser page/context.
        
        Thread-safe method to create a new page with the specified user agent.
        Each page should be closed by the caller when done.
        
        Args:
            user_agent: User agent string for the page
            
        Returns:
            A new Page object, or None if browser is not started
        """
        with self._lock:
            if not self._is_started or not self._browser:
                logger.warning('Browser not started, cannot create page')
                return None
                
            try:
                page = self._browser.new_page(user_agent=user_agent)
                return page
            except Exception as e:
                logger.error('Failed to create new page: %s', e)
                return None
    
    def close(self):
        """Close the browser instance.
        
        Should be called once at the end of a collection run.
        Safe to call multiple times.
        """
        with self._lock:
            if not self._is_started:
                return
                
            try:
                logger.info('Closing persistent Playwright browser...')
                if self._browser:
                    self._browser.close()
                if self._playwright:
                    self._playwright.stop()
                logger.info('Playwright browser closed successfully')
            except Exception as e:
                logger.error('Error closing Playwright browser: %s', e)
            finally:
                self._browser = None
                self._playwright = None
                self._is_started = False
    
    @property
    def is_started(self) -> bool:
        """Check if the browser is currently started."""
        with self._lock:
            return self._is_started
