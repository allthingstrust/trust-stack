import os
import types
import pytest
from ingestion import page_fetcher


class DummyResponse:
    def __init__(self, status_code=200, text='', json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError('No JSON')
        return self._json


def test_fetch_page_http_success(monkeypatch, tmp_path):
    url = 'https://example.com/article'
    html = '<html><head><title>Test Title</title></head><body><article><p>Paragraph one.</p><p>Paragraph two.</p></article><footer><a href="/terms">Terms</a><a href="/privacy">Privacy</a></footer></body></html>'

    def fake_get(u, headers=None, timeout=None):
        assert u == url
        return DummyResponse(status_code=200, text=html)

    # Mock both requests.get and requests.Session
    class FakeSession:
        def __init__(self):
            self.max_redirects = 10
        def get(self, *args, **kwargs):
            return fake_get(*args, **kwargs)
    
    monkeypatch.setattr(page_fetcher, 'requests', types.SimpleNamespace(get=fake_get, Session=FakeSession))

    result = page_fetcher.fetch_page(url)
    assert result['title'] == 'Test Title'
    assert 'Paragraph one' in result['body']
    assert result['url'] == url
    assert result.get('terms') == 'https://example.com/terms'
    assert result.get('privacy') == 'https://example.com/privacy'


def test_fetch_page_playwright_fallback(monkeypatch, tmp_path):
    # Simulate initial HTTP 403, then Playwright rendering returns body
    url = 'https://example.com/protected'
    http_resp = DummyResponse(status_code=403, text='<html><body>Forbidden</body></html>')

    def fake_get(u, headers=None, timeout=None):
        return http_resp

    # Fake playwright objects to mimic the sync_playwright context used in the module
    class FakePage:
        def __init__(self):
            self._html = '<html><head><title>Rendered Title</title></head><body><article><p>Rendered paragraph.</p></article><footer><a href="/privacy">Privacy</a></footer></body></html>'

        def goto(self, url, timeout=None):
            pass

        def wait_for_selector(self, sel, timeout=None):
            return True

        def content(self):
            return self._html

        def title(self):
            return 'Rendered Title'

        def query_selector(self, sel):
            # return a truthy object to represent article existing
            return True

        def query_selector_all(self, sel):
            class P:
                def inner_text(self):
                    return 'Rendered paragraph.'
            return [P()]

    class FakeBrowser:
        def __init__(self):
            pass

        def new_page(self, user_agent=None):
            return FakePage()

        def close(self):
            pass

    class FakePW:
        def __init__(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @property
        def chromium(self):
            class C:
                def launch(self, headless=True):
                    return FakeBrowser()

            return C()

    # Monkeypatch requests
    # Mock both requests.get and requests.Session
    class FakeSession:
        def __init__(self):
            self.max_redirects = 10
        def get(self, *args, **kwargs):
            return fake_get(*args, **kwargs)
    
    monkeypatch.setattr(page_fetcher, 'requests', types.SimpleNamespace(get=fake_get, Session=FakeSession))

    # Ensure Playwright is considered available
    monkeypatch.setattr(page_fetcher, '_PLAYWRIGHT_AVAILABLE', True)

    # Monkeypatch sync_playwright in the module to return FakePW
    monkeypatch.setattr(page_fetcher, 'sync_playwright', lambda: FakePW())

    # Enable Playwright via env var
    monkeypatch.setenv('AR_USE_PLAYWRIGHT', '1')

    result = page_fetcher.fetch_page(url)
    assert result['title'] == 'Rendered Title'
    assert 'Rendered paragraph' in result['body']
    assert result['url'] == url
    # Privacy link should be absolute
    assert result.get('privacy') == 'https://example.com/privacy'


def test_fetch_page_respects_robots(monkeypatch, tmp_path):
    # Simulate HTTP 403, but robots.txt disallows the agent, so Playwright should not be used
    url = 'https://blocked.example.com/secret'
    http_resp = DummyResponse(status_code=403, text='<html><body>Forbidden</body></html>')

    def fake_get(u, headers=None, timeout=None):
        # First call for the page
        if u == url:
            return http_resp
        # For robots.txt fetching
        if u.endswith('/robots.txt'):
            return DummyResponse(status_code=200, text='User-agent: *\nDisallow: /')
        return DummyResponse(status_code=404, text='')

    # Mock both requests.get and requests.Session
    class FakeSession:
        def __init__(self):
            self.max_redirects = 10
        def get(self, *args, **kwargs):
            return fake_get(*args, **kwargs)
    
    monkeypatch.setattr(page_fetcher, 'requests', types.SimpleNamespace(get=fake_get, Session=FakeSession))

    # Even if Playwright is available, it should not be used because robots disallow
    monkeypatch.setattr(page_fetcher, '_PLAYWRIGHT_AVAILABLE', True)
    monkeypatch.setenv('AR_USE_PLAYWRIGHT', '1')

    result = page_fetcher.fetch_page(url)
    # Since robots disallow, fetch_page should not use Playwright and should return empty body
    assert result['body'] == ''
    assert result['terms'] == ''
    assert result['privacy'] == ''


if __name__ == '__main__':
    pytest.main([__file__])
