#!/usr/bin/env python3
"""
Debug script to check appendix data structure
Run this after the pipeline to inspect what's in the scoring report
"""

import json
import sys

# This would be populated by the pipeline - for testing we'll create a minimal version
def check_appendix_structure(appendix_items):
    """Check structure of appendix items"""
    if not appendix_items:
        print("❌ Appendix is empty!")
        return

    print(f"✓ Appendix has {len(appendix_items)} items\n")

    # Check first item structure
    first_item = appendix_items[0]
    print("First item keys:", list(first_item.keys()))
    print()

    # Check if dimensions exist
    if 'dimensions' in first_item:
        print("✓ 'dimensions' key exists")
        dims = first_item['dimensions']
        print(f"  Dimensions type: {type(dims)}")
        if isinstance(dims, dict):
            print(f"  Dimension keys: {list(dims.keys())}")
            for dim, score in dims.items():
                print(f"    {dim}: {score} (type: {type(score)})")
        print()
    else:
        print("❌ 'dimensions' key NOT found")
        print()

    # Check if dimension_scores exists
    if 'dimension_scores' in first_item:
        print("✓ 'dimension_scores' key exists")
        dims = first_item['dimension_scores']
        print(f"  Type: {type(dims)}")
        if isinstance(dims, dict):
            print(f"  Keys: {list(dims.keys())}")
        print()
    else:
        print("❌ 'dimension_scores' key NOT found")
        print()

    # Check meta structure
    if 'meta' in first_item:
        print("✓ 'meta' key exists")
        meta = first_item['meta']
        print(f"  Meta type: {type(meta)}")

        if isinstance(meta, str):
            try:
                meta_parsed = json.loads(meta)
                print(f"  Meta parsed keys: {list(meta_parsed.keys())}")
                print(f"  modality: {meta_parsed.get('modality', 'NOT FOUND')}")
                print(f"  channel: {meta_parsed.get('channel', 'NOT FOUND')}")
                print(f"  platform_type: {meta_parsed.get('platform_type', 'NOT FOUND')}")
            except:
                print("  ⚠ Meta is string but not valid JSON")
        elif isinstance(meta, dict):
            print(f"  Meta keys: {list(meta.keys())}")
            print(f"  modality: {meta.get('modality', 'NOT FOUND')}")
            print(f"  channel: {meta.get('channel', 'NOT FOUND')}")
            print(f"  platform_type: {meta.get('platform_type', 'NOT FOUND')}")
        print()
    else:
        print("❌ 'meta' key NOT found")
        print()

    print("="*60)
    print("Full first item:")
    print(json.dumps(first_item, indent=2, default=str))

if __name__ == "__main__":
    print("This is a debug helper.")
    print("To use: import this in your pipeline and call check_appendix_structure(appendix)")
