"""Fix test_fetch_page.py to properly mock requests.Session"""

# Read the file
with open('tests/test_fetch_page.py', 'r') as f:
    content = f.read()

# Replace the monkeypatch.setattr lines to also include Session
# The issue is that we're replacing requests with a SimpleNamespace that only has 'get'
# But _get_session needs requests.Session()

# We need to create a proper mock that includes both get and Session
new_content = content.replace(
    "monkeypatch.setattr(page_fetcher, 'requests', types.SimpleNamespace(get=fake_get))",
    """# Mock both requests.get and requests.Session
    class FakeSession:
        def __init__(self):
            self.max_redirects = 10
        def get(self, *args, **kwargs):
            return fake_get(*args, **kwargs)
    
    monkeypatch.setattr(page_fetcher, 'requests', types.SimpleNamespace(get=fake_get, Session=FakeSession))"""
)

# Write back
with open('tests/test_fetch_page.py', 'w') as f:
    f.write(new_content)

print("Fixed test_fetch_page.py to properly mock requests.Session")
