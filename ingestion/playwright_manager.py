import logging
import threading
import queue
from typing import Optional, Dict, Any

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
    
    Uses a dedicated thread to handle all Playwright interactions, ensuring
    thread safety for the synchronous Playwright API.
    """
    
    def __init__(self):
        """Initialize the browser manager."""
        self._request_queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._is_started = False
        self._lock = threading.Lock()
        
    def start(self) -> bool:
        """Launch the browser thread.
        
        Returns:
            True if started successfully (or already started), False otherwise
        """
        if not _PLAYWRIGHT_AVAILABLE:
            logger.warning('Playwright is not available, cannot start browser')
            return False
            
        with self._lock:
            if self._is_started:
                return True
                
            try:
                self._thread = threading.Thread(target=self._run_browser_loop, daemon=True)
                self._thread.start()
                self._is_started = True
                logger.info('Playwright browser thread started')
                return True
            except Exception as e:
                logger.error('Failed to start Playwright thread: %s', e)
                return False

    def _run_browser_loop(self):
        """Internal loop running in a dedicated thread.
        
        Note: We do NOT create a new event loop here because:
        1. sync_playwright() uses synchronous API and doesn't need an event loop
        2. Creating an event loop interferes with Streamlit's event loop management
        3. It causes "Event loop is closed" errors during shutdown
        """
        playwright = None
        browser = None
        
        try:
            logger.info('Initializing Playwright in dedicated thread...')
            playwright = sync_playwright().start()
            
            # Harden browser launch args to prevent crashes on macOS/Headless
            launch_args = [
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-accelerated-2d-canvas',
                '--disable-gl-drawing-for-tests'
            ]
            
            browser = playwright.chromium.launch(
                headless=True,
                args=launch_args,
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False
            )
            logger.info('Playwright browser initialized successfully')
            
            while True:
                item = self._request_queue.get()
                if item is None:
                    break
                    
                url, user_agent, result_queue = item
                
                try:
                    # Check if browser is still connected
                    if not browser.is_connected():
                        logger.warning('Browser disconnected, restarting...')
                        try:
                            browser.close()
                        except: pass
                        browser = playwright.chromium.launch(
                            headless=True,
                            args=launch_args,
                            handle_sigint=False,
                            handle_sigterm=False,
                            handle_sighup=False
                        )
                        
                    result = self._process_fetch(browser, url, user_agent)
                    result_queue.put(result)
                except Exception as e:
                    error_msg = str(e)
                    # If target closed, try one restart
                    if "Target page, context or browser has been closed" in error_msg or "Connection closed" in error_msg:
                        logger.warning('Browser crashed during fetch, restarting and retrying: %s', e)
                        try:
                            try:
                                browser.close()
                            except: pass
                            browser = playwright.chromium.launch(
                                headless=True,
                                args=launch_args,
                                handle_sigint=False,
                                handle_sigterm=False,
                                handle_sighup=False
                            )
                            # Retry fetch once
                            result = self._process_fetch(browser, url, user_agent)
                            result_queue.put(result)
                        except Exception as retry_e:
                            logger.error('Retry failed for %s: %s', url, retry_e)
                            result_queue.put({"title": "", "body": "", "url": url, "error": str(retry_e)})
                    else:
                        logger.error('Error processing fetch for %s: %s', url, e)
                        result_queue.put({"title": "", "body": "", "url": url, "error": str(e)})
                finally:
                    self._request_queue.task_done()
                    
        except Exception as e:
            # Suppress errors during shutdown (like BrokenPipeError, Event loop is closed)
            import sys
            if not sys.is_finalizing():
                # Only log if not shutting down
                if "Broken pipe" not in str(e) and "Event loop is closed" not in str(e):
                    logger.error('Playwright browser loop crashed: %s', e)
        finally:
            import sys # Ensure sys is available in finally block
            # Clean up browser and playwright - suppress all errors during cleanup
            if browser:
                try:
                    if not sys.is_finalizing():
                        browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    if not sys.is_finalizing():
                        playwright.stop()
                except Exception:
                    pass
            
            # Log shutdown only if not finalizing
            if not sys.is_finalizing():
                try:
                    logger.info('Playwright browser thread stopped')
                except Exception:
                    pass
            
            # Ensure we mark as stopped so it can be restarted if needed
            with self._lock:
                self._is_started = False
                self._thread = None

    def _process_fetch(self, browser: Browser, url: str, user_agent: str) -> Dict[str, str]:
        """Perform the actual fetch logic inside the browser thread."""
        page = None
        try:
            page = browser.new_page(user_agent=user_agent)
            page.goto(url, timeout=20000)
            
            try:
                page.wait_for_selector('body', timeout=8000)
            except Exception:
                pass
            
            page_content = page.content()
            page_title = page.title() or ''
            
            # Extraction logic (mirrors _fetch_with_playwright)
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
                page_body = page_content

            return {
                "title": page_title.strip(),
                "body": page_body.strip(),
                "url": url,
                "raw_content": page_content # Return raw content for footer link extraction
            }
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def fetch_page(self, url: str, user_agent: str, timeout: int = 30) -> Dict[str, str]:
        """Submit a fetch request to the browser thread and wait for result."""
        if not self.is_started:
            # Try to auto-restart if not started
            if not self.start():
                return {"title": "", "body": "", "url": url, "error": "Browser not started"}
            
        result_queue = queue.Queue()
        self._request_queue.put((url, user_agent, result_queue))
        
        try:
            return result_queue.get(timeout=timeout)
        except queue.Empty:
            logger.error(f"Timeout waiting for Playwright fetch: {url}")
            return {"title": "", "body": "", "url": url, "error": "Timeout waiting for browser"}

    def close(self):
        """Stop the browser thread."""
        thread_to_join = None
        with self._lock:
            if not self._is_started:
                return
            self._request_queue.put(None)
            thread_to_join = self._thread
            
        # Release lock before joining to avoid deadlock with thread's cleanup
        if thread_to_join:
            thread_to_join.join(timeout=2)
            
        # Ensure state is cleared
        with self._lock:
            self._is_started = False
            self._thread = None
    
    @property
    def is_started(self) -> bool:
        with self._lock:
            return self._is_started and self._thread and self._thread.is_alive()


# Global singleton instance
_GLOBAL_MANAGER = None
_GLOBAL_LOCK = threading.Lock()

def get_browser_manager() -> PlaywrightBrowserManager:
    """Get the global singleton browser manager instance."""
    global _GLOBAL_MANAGER
    with _GLOBAL_LOCK:
        if _GLOBAL_MANAGER is None:
            _GLOBAL_MANAGER = PlaywrightBrowserManager()
            # Register cleanup on exit to ensure terminal is restored
            import atexit
            atexit.register(_cleanup_browser_manager)
    return _GLOBAL_MANAGER

def _cleanup_browser_manager():
    """Cleanup function to close the browser manager on exit."""
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER:
        try:
            # Use a short timeout to avoid hanging if the thread is stuck
            _GLOBAL_MANAGER.close()
        except Exception:
            pass

