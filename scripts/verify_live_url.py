
import sys
import os
import requests
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion.metadata_extractor import MetadataExtractor

@dataclass
class MockNormalizedContent:
    content_id: str = "live-test"
    src: str = "test"
    url: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    published_at: Optional[str] = None
    # Add other fields to satisfy usage
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

def verify_live_url(url: str):
    print(f"Fetching {url }...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        html = resp.text
        print(f"Fetched {len(html)} bytes.")
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return

    extractor = MetadataExtractor()
    content = MockNormalizedContent(url=url)
    
    # Run extraction
    extractor.enrich_content_metadata(content, html)
    
    print("\n--- Extraction Results ---")
    print(f"URL: {content.url}")
    print(f"Published At: {content.published_at}")
    print(f"Meta 'published_at': {content.meta.get('published_at')}")
    print(f"Canonical: {content.meta.get('canonical')}")
    
    # Print Schema dates if found
    if 'schema_org' in content.meta:
        print("\n--- Schema.org Data ---")
        try:
            data = json.loads(content.meta['schema_org'])
            candidates = []
            if isinstance(data, dict):
                if 'json_ld' in data and isinstance(data['json_ld'], list):
                    candidates.extend(data['json_ld'])
                else:
                    candidates.append(data)
            elif isinstance(data, list):
                candidates.extend(data)
                
            for item in candidates:
                type_ = item.get('@type')
                date_pub = item.get('datePublished')
                date_mod = item.get('dateModified')
                date_created = item.get('dateCreated')
                if date_pub or date_mod or date_created:
                    print(f"Type: {type_}")
                    print(f"  datePublished: {date_pub}")
                    print(f"  dateModified:  {date_mod}")
                    print(f"  dateCreated:   {date_created}")
        except Exception as e:
            print(f"Error parsing schema debugging: {e}")

    # Print OpenGraph dates if found
    print("\n--- OpenGraph Data ---")
    for k, v in content.meta.items():
        if k.startswith('og_'):
            print(f"{k}: {v}")
            
    # Print other date meta
    print("\n--- Date Meta Tags ---")
    for k, v in content.meta.items():
        if 'date' in k.lower() or 'time' in k.lower():
            if not k.startswith('og_') and k != 'published_at':
                print(f"{k}: {v}")

    # Verify Provenance Impact Prediction
    if content.published_at:
        from datetime import datetime
        from dateutil import parser
        try:
            pub_date = parser.parse(content.published_at)
            # Naive freshnes check
            now = datetime.now(pub_date.tzinfo)
            age_days = (now - pub_date).days
            print(f"\n--- Analysis ---")
            print(f"Content Age: {age_days} days")
            if age_days < 30: score = 1.0
            elif age_days < 90: score = 0.9
            elif age_days < 180: score = 0.8
            elif age_days < 365: score = 0.6
            else: score = 0.4
            print(f"Predicted Freshness Score: {score}/1.0")
        except Exception as e:
            print(f"Could not parse date for analysis: {e}")
    else:
        print(f"\n--- Analysis ---")
        print("No date found. Predicted Freshness Score: 0.5/1.0 (Default)")

if __name__ == "__main__":
    url = "https://allthingstrust.com"
    if len(sys.argv) > 1:
        url = sys.argv[1]
    verify_live_url(url)
