#!/usr/bin/env python3
"""
Phase 2: Replace Playwright usage blocks in fetch_page() with calls to _fetch_with_playwright()
"""

import re

# Read the current file
with open('ingestion/brave_search.py', 'r') as f:
    lines = f.readlines()

content = ''.join(lines)

# Pattern 1: Replace first Playwright block (non-200 status)
# Find the block starting with "with sync_playwright() as pw:" after "Attempting Playwright-rendered fetch"
pattern1_start = "logger.info('Attempting Playwright-rendered fetch for %s (domain config or AR_USE_PLAYWRIGHT)', url)"
pattern1_end = "logger.warning('Playwright fallback failed for %s: %s', url, e)"

# Find the first occurrence
start_idx = content.find(pattern1_start)
if start_idx != -1:
    # Find the end of this block
    end_idx = content.find(pattern1_end, start_idx)
    if end_idx != -1:
        # Extract the section
        before = content[:start_idx]
        after = content[end_idx:]
        
        # Create the replacement
        replacement = """logger.info('Attempting Playwright-rendered fetch for %s (domain config or AR_USE_PLAYWRIGHT)', url)
                        result = _fetch_with_playwright(url, ua, browser_manager)
                        if result.get('body') and len(result.get('body', '')) >= 100:
                            return result
                except Exception as e:
                    """
        
        content = before + replacement + after
        print("✓ Replaced first Playwright usage block (non-200 status)")

# Pattern 2: Replace second Playwright block (thin content)
pattern2_start = "logger.info('Attempting Playwright-rendered fetch for thin content: %s', url)"
pattern2_end_marker = "logger.warning('Playwright fallback for thin content failed for %s: %s', url, e)"

start_idx = content.find(pattern2_start)
if start_idx != -1:
    end_idx = content.find(pattern2_end_marker, start_idx)
    if end_idx != -1:
        before = content[:start_idx]
        after = content[end_idx:]
        
        replacement = """logger.info('Attempting Playwright-rendered fetch for thin content: %s', url)
                        result = _fetch_with_playwright(url, ua, browser_manager)
                        if result.get('body') and len(result.get('body', '')) >= 150:
                            return result
                except Exception as e:
                    """
        
        content = before + replacement + after
        print("✓ Replaced second Playwright usage block (thin content)")

# Write the modified content
with open('ingestion/brave_search.py', 'w') as f:
    f.write(content)

print("\n✅ Phase 2 complete: Replaced Playwright usage blocks with helper function calls")
