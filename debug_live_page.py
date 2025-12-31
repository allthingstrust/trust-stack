
import sys
import logging
import json
from ingestion.page_fetcher import fetch_page
from ingestion.metadata_extractor import MetadataExtractor
from ingestion.playwright_manager import get_browser_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_page(url):
    print(f"Fetching {url}...")
    browser_manager = get_browser_manager()
    browser_manager.start()
    
    try:
        content = fetch_page(url, browser_manager=browser_manager)
        
        print(f"Fetched {len(content['body'])} bytes")
        print(f"Content Keys: {list(content.keys())}")
        
        # Use full HTML for metadata extraction if available, otherwise body
        raw_html = content.get('html')
        if not raw_html:
            print("WARNING: No 'html' field in content. Using 'body' (might be plain text).")
            raw_html = content['body']
        else:
            print(f"Found 'html' content ({len(raw_html)} bytes)")

        # Parse metadata
        extractor = MetadataExtractor()
        
        # Manually extract pieces to see raw data
        schema_data = extractor.parse_schema_org(raw_html)
        meta_tags = extractor.extract_meta_tags(raw_html)
        og_tags = extractor.extract_og_metadata(raw_html)
        
        meta = {
            'schema_org': json.dumps(schema_data) if schema_data else None,
            'meta_tags': meta_tags,
            'og_tags': og_tags
        }
        
        print("\n--- Extracted Metadata (Summary) ---")
        print(f"Meta Tags Found: {len(meta_tags)}")
        print(f"OG Tags Found: {len(og_tags)}")
        print(f"Schema.org Found: {bool(schema_data)}")
        
        # Specific check for schema.org
        schema_org = meta.get('schema_org')
        if schema_org:
            print("\n--- Schema.org Data ---")
            if isinstance(schema_org, str):
                try:
                    schema_data_loaded = json.loads(schema_org)
                except:
                    print(f"Raw string (failed to parse): {schema_org}")
                    schema_data_loaded = None
            else:
                schema_data_loaded = schema_org
                
            if schema_data_loaded:
                print(json.dumps(schema_data_loaded, indent=2))
                
                # Test the flattening logic directly here
                from scoring.attribute_detector import TrustStackAttributeDetector
                detector = TrustStackAttributeDetector()
                flattened = detector._flatten_json_ld(schema_data_loaded)
                print(f"\n--- Flattened Objects ({len(flattened)}) ---")
                for i, item in enumerate(flattened):
                    print(f"[{i}] Type: {item.get('@type')}, ID: {item.get('@id')}")
                    if 'author' in item:
                        print(f"    -> FOUND AUTHOR: {item['author']}")
                    if 'publisher' in item:
                        print(f"    -> FOUND PUBLISHER: {item['publisher']}")
                    if 'name' in item:
                        print(f"    -> NAME: {item['name']}")
        else:
            print("WARNING: No schema_org found in metadata")

        # Test attribute detection
        from data.models import NormalizedContent
        from scoring.attribute_detector import TrustStackAttributeDetector
        
        norm_content = NormalizedContent(
            content_id="debug",
            src=url,
            platform_id="web",
            author="unknown", # Default
            title=content.get('title', ''),
            body=content.get('body', ''),
            url=url,
            meta=meta,
            channel='web'
        )
        
        print("\n--- Page Body Preview (First 1000 chars) ---")
        print(content.get('body', '')[:1000])
        
        detector = TrustStackAttributeDetector()
        result = detector._detect_author_verified(norm_content)
        print(f"\n--- Detection Result ---")
        print(f"Score: {result.value}")
        print(f"Evidence: {result.evidence}")

    finally:
        browser_manager.close()

if __name__ == "__main__":
    debug_page("https://allthingstrust.com/trust-stack")
