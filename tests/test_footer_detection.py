import pytest
from ingestion import brave_search, page_fetcher


def test_extract_footer_links_footer_present():
    html = """
    <html>
      <body>
        <footer>
          <a href="/terms">Terms of Service</a>
          <a href="/privacy">Privacy Policy</a>
        </footer>
      </body>
    </html>
    """
    links = page_fetcher._extract_footer_links(html, "https://example.com")
    assert links["terms"].endswith('/terms')
    assert links["privacy"].endswith('/privacy')


def test_extract_footer_links_footer_absent_body_links():
    html = """
    <html>
      <body>
        <p>Some text</p>
        <a href="https://example.com/privacy-policy">Privacy Policy</a>
      </body>
    </html>
    """
    links = page_fetcher._extract_footer_links(html, "https://example.com")
    assert links["terms"] == ""
    assert 'privacy' in links["privacy"].lower()


def test_extract_footer_links_no_links():
    html = """
    <html>
      <body>
        <h1>Hello</h1>
        <p>No relevant links here</p>
      </body>
    </html>
    """
    links = page_fetcher._extract_footer_links(html, "https://example.com")
    assert links["terms"] == ""
    assert links["privacy"] == ""
