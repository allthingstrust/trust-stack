
import sys
import os
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion.metadata_extractor import MetadataExtractor

# Mock NormalizedContent since we can't import the full model easily without SQLAlchemy setup issues in some envs
# Just a simple class that mimics the structure needed
@dataclass
class MockNormalizedContent:
    content_id: str = "test-1"
    src: str = "test"
    url: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    published_at: Optional[str] = None
    # Add other fields to satisfy type hints if needed (though Python is dynamic)
    platform_id: str = "test"
    author: str = "test"
    title: str = "test"
    body: str = "test"
    rating: Optional[float] = None
    upvotes: Optional[int] = None
    helpful_count: Optional[float] = None
    event_ts: str = ""
    run_id: str = ""
    modality: str = "text"
    channel: str = "unknown"
    platform_type: str = "unknown"
    source_type: str = "unknown"
    source_tier: str = "unknown"
    language: str = "en"
    structured_body: Optional[Any] = None
    screenshot_path: Optional[str] = None
    visual_analysis: Optional[Dict[str, Any]] = None

def test_og_date():
    print("Testing OpenGraph date extraction...")
    html = """
    <html>
        <head>
            <meta property="article:published_time" content="2023-10-27T10:00:00Z" />
        </head>
        <body></body>
    </html>
    """
    extractor = MetadataExtractor()
    content = MockNormalizedContent()
    
    result = extractor.enrich_content_metadata(content, html)
    
    print(f"Result published_at: {result.published_at}")
    assert result.published_at == "2023-10-27T10:00:00Z"
    print("PASS: OpenGraph date extracted correctly.\n")

def test_schema_date():
    print("Testing Schema.org date extraction...")
    html = """
    <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": "Test Article",
                "datePublished": "2023-11-15T08:30:00Z"
            }
            </script>
        </head>
        <body></body>
    </html>
    """
    extractor = MetadataExtractor()
    content = MockNormalizedContent()
    
    result = extractor.enrich_content_metadata(content, html)
    
    print(f"Result published_at: {result.published_at}")
    assert result.published_at == "2023-11-15T08:30:00Z"
    print("PASS: Schema.org date extracted correctly.\n")

def test_meta_date():
    print("Testing standard meta date extraction...")
    html = """
    <html>
        <head>
            <meta name="pubdate" content="2023-01-01" />
        </head>
        <body></body>
    </html>
    """
    extractor = MetadataExtractor()
    content = MockNormalizedContent()
    
    result = extractor.enrich_content_metadata(content, html)
    
    print(f"Result published_at: {result.published_at}")
    assert result.published_at == "2023-01-01"
    print("PASS: Meta pubdate extracted correctly.\n")

def test_itemprop_date():
    print("Testing itemprop date extraction...")
    html = """
    <html>
        <head></head>
        <body>
            <div itemscope itemtype="http://schema.org/Article">
                <span itemprop="datePublished" content="2022-12-25">December 25, 2022</span>
            </div>
        </body>
    </html>
    """
    extractor = MetadataExtractor()
    content = MockNormalizedContent()
    
    result = extractor.enrich_content_metadata(content, html)
    
    print(f"Result published_at: {result.published_at}")
    assert result.published_at == "2022-12-25"
    print("PASS: Microdata itemprop date extracted correctly.\n")

def test_priority():
    print("Testing priority (OG > Schema > Meta)...")
    html = """
    <html>
        <head>
            <meta property="article:published_time" content="2024-01-01T00:00:00Z" /> <!-- Should win -->
            <meta name="pubdate" content="2020-01-01" />
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "datePublished": "2022-01-01"
            }
            </script>
        </head>
        <body></body>
    </html>
    """
    extractor = MetadataExtractor()
    content = MockNormalizedContent()
    
    result = extractor.enrich_content_metadata(content, html)
    
    print(f"Result published_at: {result.published_at}")
    assert result.published_at == "2024-01-01T00:00:00Z"
    print("PASS: Priority logic respected (OG preferred).\n")

if __name__ == "__main__":
    try:
        test_og_date()
        test_schema_date()
        test_meta_date()
        test_itemprop_date()
        test_priority()
        print("ALL TESTS PASSED!")
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
