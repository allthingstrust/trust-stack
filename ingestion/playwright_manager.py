import logging
import os
import threading
import queue
import time
import asyncio
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from ingestion.screenshot_capture import get_screenshot_capture, should_capture_screenshot
from config.settings import SETTINGS

logger = logging.getLogger(__name__)

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
                self._thread = threading.Thread(target=self._run_browser_loop, daemon=True, name="PlaywrightBrowserThread")
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
            # --disable-http2 fixes ERR_HTTP2_PROTOCOL_ERROR from CDNs/WAFs (e.g., Akamai on adidas.com)
            launch_args = [
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-accelerated-2d-canvas',
                '--disable-gl-drawing-for-tests',
                '--disable-http2',
                # Stealth additions
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--ignore-certificate-errors',
            ]
            
            # Default to Headed mode (false) to bypass bot detection on sites like Costco
            headless_mode = os.environ.get('HEADLESS_MODE', 'false').lower() == 'true'
            browser = playwright.chromium.launch(
                headless=headless_mode,
                args=launch_args,
                ignore_default_args=['--enable-automation'],
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False
            )
            logger.info(f'Playwright browser initialized successfully (Headless: {headless_mode})')
            
            while True:
                task = self._request_queue.get()
                if task is None:
                    break
                    
                task_type = task.get("type")
                if task_type == "fetch":
                    url = task.get("url")
                    user_agent = task.get("user_agent")
                    
                    # Update to modern Chrome 131 User Agent if generic/older one provided
                    if "HeadlessChrome" in user_agent or "Playwright" in user_agent:
                        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                        
                    capture_screenshot = task.get("capture_screenshot", False)
                    result_queue = task.get("result_queue")
                    logger.debug(f'Browser thread processing fetch request for: {url}')
                    
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
                            
                        data = self._process_fetch(browser, url, user_agent, capture_screenshot)
                        result_queue.put(data)
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
                                data = self._process_fetch(browser, url, user_agent, capture_screenshot)
                                result_queue.put(data)
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
                    # Check if logger is still valid (not None) during interpreter shutdown
                    if logger and hasattr(logger, 'info'):
                        logger.info('Playwright browser thread stopped')
                except Exception:
                    pass
            
            # Ensure we mark as stopped so it can be restarted if needed
            with self._lock:
                self._is_started = False
                self._thread = None

    def _process_fetch(self, browser: Browser, url: str, user_agent: str, capture_screenshot: bool = False) -> Dict[str, str]:
        """Perform the actual fetch logic inside the browser thread."""
        page = None
        screenshot_key = None
        try:
            logger.debug(f'[PLAYWRIGHT] Creating new page for: {url}')
            
            # Add extra HTTP headers for realism
            extra_headers = {
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            }
            
            context = browser.new_context(
                user_agent=user_agent,
                extra_http_headers=extra_headers
            )
            page = context.new_page()
            
            logger.debug(f'[PLAYWRIGHT] Page created, navigating to: {url}')
            # Stealth: Inject scripts to mask automation
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Pass Chrome test
                window.chrome = {
                    runtime: {}
                };
                
                // Pass Permissions test
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
                
                // Pass Plugins length test
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Pass Languages test
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)

            # Use domcontentloaded instead of 'load' - faster and more reliable for SPAs
            # 'load' waits for all resources which can timeout on heavy sites
            # Log failed requests for debugging
            page.on("requestfailed", lambda request: logger.debug(f"[PLAYWRIGHT] Request failed: {request.url} - {request.failure}"))

            # Use 'commit' to avoid hanging on heavy sites (like Winn-Dixie)
            # Then rely on wait_for_selector to ensure body is present
            page.goto(url, timeout=60000, wait_until='commit')
            logger.debug(f'[PLAYWRIGHT] Navigation "commit" complete for: {url}')
            
            try:
                # Increased timeout for body selector to allow content to load after commit
                page.wait_for_selector('body', timeout=15000)
            except Exception as wait_e:
                logger.warning(f"[PLAYWRIGHT] Timeout waiting for body selector: {wait_e}")
                pass
            
            logger.debug(f'[PLAYWRIGHT] Extracting content from: {url}')
            page_content = page.content()
            page_title = page.title() or ''
            logger.debug(f'[PLAYWRIGHT] Content extracted, title="{page_title[:50]}..." for: {url}')
            
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

            # Capture screenshot if requested
            if capture_screenshot:
                try:
                    capture_tool = get_screenshot_capture()
                    # Capture above fold
                    png_bytes, meta = capture_tool.capture_above_fold(page, url)
                    
                    if meta.get('success'):
                        run_id = f"fetch_{datetime.now().strftime('%Y%m%d')}"
                        screenshot_key = capture_tool.store_screenshot(png_bytes, url, run_id)
                        if screenshot_key:
                            logger.info(f"[PLAYWRIGHT] Screenshot stored: {screenshot_key}")
                except Exception as e:
                    logger.warning(f"[PLAYWRIGHT] Screenshot capture failed for {url}: {e}")

            # Check for Access Denied / Blocked content
            access_denied = False
            lower_title = page_title.lower()
            lower_content = page_content.lower()[:5000] # Check first 5kb
            
            # Common WAF/Block pages
            if "access denied" in lower_title or "access denied" in lower_content:
                if "website" not in lower_title: # Avoid false positives like "Access Denied: The Movie"
                    access_denied = True
            elif "403 forbidden" in lower_title or "403 forbidden" in lower_content:
                access_denied = True
            elif "cloudflare" in lower_title and "security" in lower_title:
                access_denied = True
            
            if access_denied:
                logger.warning(f"[PLAYWRIGHT] Detected Access Denied content for {url}")

            return {
                "title": page_title.strip(),
                "body": page_body.strip(),
                "url": url,
                "raw_content": page_content, # Return raw content for footer link extraction
                "screenshot_path": screenshot_key,
                "access_denied": access_denied
            }
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def fetch_page(self, url: str, user_agent: str, capture_screenshot: bool = False) -> Dict[str, Any]:
        """
        Fetch a page using the background browser.
        Returns a dict with title, body, etc.
        """
        if not self.is_started:
            raise RuntimeError("Browser not started")

        result_queue = queue.Queue()
        self._request_queue.put({
            "type": "fetch",
            "url": url,
            "user_agent": user_agent,
            "capture_screenshot": capture_screenshot,
            "result_queue": result_queue
        })
        
        try:
            # Wait indefinitely for the result
            # The background thread guarantees a result (success or error) because of the try/finally block
            result = result_queue.get()
            if isinstance(result, Exception):
                raise result
            return result
        # queue.Empty is no longer possible without a timeout, but keeping generic error handling is fine
        except Exception as e:
            raise e

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
            # Check if global manager is still valid
            if _GLOBAL_MANAGER:
                _GLOBAL_MANAGER.close()
        except Exception:
            pass

