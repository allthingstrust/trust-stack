import pytest
from unittest import mock

from ingestion import brave_search, page_fetcher


def test_fetch_page_handles_invalid_url(monkeypatch):
    # Simulate requests.get raising an exception
    class DummyResp:
        status_code = 500

    def fake_get(*args, **kwargs):
        raise Exception("network error")

    monkeypatch.setattr('ingestion.brave_search.requests.get', fake_get)
    res = page_fetcher.fetch_page('http://invalid.local')
    assert isinstance(res, dict)
    assert res.get('url') == 'http://invalid.local'


def test_search_brave_returns_list(monkeypatch):
    # Ensure the code uses the HTML scraping path for this test by unsetting BRAVE_API_KEY
    import os
    if 'BRAVE_API_KEY' in os.environ:
        del os.environ['BRAVE_API_KEY']
    html = '<html><body><div class="result"><a class="result-title" href="http://example.com">Example</a><p class="snippet">Snippet</p></div></body></html>'
    class DummyResp:
        status_code = 200
        text = html

    def fake_get(*args, **kwargs):
        return DummyResp()

    monkeypatch.setattr('ingestion.brave_search.requests.get', fake_get)
    res = brave_search.search_brave('query', size=5)
    assert isinstance(res, list)
    assert len(res) >= 1
    assert res[0]['url'] == 'http://example.com'
