import pytest


def test_collect_skips_thin_and_reaches_target(monkeypatch):
    """collect_brave_pages should skip thin/empty fetches and keep trying until it
    collects the requested number of successful pages (or exhausts pool)."""
    from ingestion import brave_search

    # Prepare fake search results (5 URLs)
    urls = [f"https://site{i}.com/page{i}" for i in range(5)]
    monkeypatch.setattr(brave_search, 'search_brave', lambda q, size: [{'url': u, 'title': f't{i}'} for i, u in enumerate(urls)])

    # Fake fetch_page: first two are thin (simulate 403/blocked body), later ones are full
    def fake_fetch(url, browser_manager=None):
        if url.endswith('page0') or url.endswith('page1'):
            return {'title': '', 'body': '', 'url': url}
        return {'title': 'Good', 'body': 'x' * 500, 'url': url}

    monkeypatch.setattr(brave_search, 'fetch_page', fake_fetch)

    # Mock robots.txt fetch to be permissive (200 but empty body -> treated permissive by code)
    class FakeResp:
        def __init__(self, status=200, text=''):
            self.status_code = status
            self.text = text

    monkeypatch.setattr('ingestion.brave_search.requests.get', lambda url, headers=None, timeout=None: FakeResp(200, ''))

    collected = brave_search.collect_brave_pages('query', target_count=2, pool_size=5, min_body_length=200)
    assert isinstance(collected, list)
    assert len(collected) == 2
    # Ensure we skipped the thin ones and returned later ones
    assert collected[0]['url'].endswith('page2')


def test_collect_respects_robots_disallow(monkeypatch):
    """collect_brave_pages should skip URLs disallowed by robots.txt and fetch allowed ones."""
    from ingestion import brave_search

    urls = ['https://example.com/blocked', 'https://example.com/allowed']
    monkeypatch.setattr(brave_search, 'search_brave', lambda q, size: [{'url': u} for u in urls])

    called = []
    def fake_fetch(url, browser_manager=None):
        called.append(url)
        return {'title': 'OK', 'body': 'x' * 300, 'url': url}

    monkeypatch.setattr(brave_search, 'fetch_page', fake_fetch)

    # robots.txt returns a Disallow for /blocked path
    def fake_requests_get(url, headers=None, timeout=None):
        class R:
            pass
        r = R()
        r.status_code = 200
        r.text = "User-agent: *\nDisallow: /blocked\n"
        return r

    monkeypatch.setattr('ingestion.brave_search.requests.get', fake_requests_get)

    collected = brave_search.collect_brave_pages('query', target_count=1, pool_size=2, min_body_length=100)
    assert len(collected) == 1
    assert collected[0]['url'] == 'https://example.com/allowed'
    # Ensure fetch_page was only called for the allowed URL
    assert called == ['https://example.com/allowed']
