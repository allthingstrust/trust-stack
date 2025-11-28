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
        """Internal loop running in a dedicated thread."""
        # Create a new event loop for this thread to isolate it from Streamlit's loop
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception as e:
            logger.warning('Failed to set new event loop for Playwright thread: %s', e)

        playwright = None
        browser = None
        
        try:
            logger.info('Initializing Playwright in dedicated thread...')
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            logger.info('Playwright browser initialized successfully')
            
            while True:
                item = self._request_queue.get()
                if item is None:
                    break
                    
                url, user_agent, result_queue = item
                
                try:
                    result = self._process_fetch(browser, url, user_agent)
                    result_queue.put(result)
                except Exception as e:
                    logger.error('Error processing fetch for %s: %s', url, e)
                    result_queue.put({"title": "", "body": "", "url": url, "error": str(e)})
                finally:
                    self._request_queue.task_done()
                    
        except Exception as e:
            # Suppress errors during shutdown (like BrokenPipeError)
            if "Broken pipe" not in str(e) and "Event loop is closed" not in str(e):
                logger.error('Playwright browser loop crashed: %s', e)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass
            try:
                logger.info('Playwright browser thread stopped')
            except Exception:
                pass

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

    def fetch_page(self, url: str, user_agent: str) -> Dict[str, str]:
        """Submit a fetch request to the browser thread and wait for result."""
        if not self._is_started:
            return {"title": "", "body": "", "url": url, "error": "Browser not started"}
            
        result_queue = queue.Queue()
        self._request_queue.put((url, user_agent, result_queue))
        return result_queue.get()
    
    def close(self):
        """Stop the browser thread."""
        with self._lock:
            if not self._is_started:
                return
            self._request_queue.put(None)
            if self._thread:
                self._thread.join(timeout=5)
            self._is_started = False
    
    @property
    def is_started(self) -> bool:
        with self._lock:
            return self._is_started
