#!/usr/bin/env python3
"""
Phase 3: Add browser manager initialization and integration to collect_brave_pages()
"""

import re

# Read the current file
with open('ingestion/brave_search.py', 'r') as f:
    content = f.read()

# Step 1: Add browser manager initialization after url_collection_config import
init_code = """
    # Initialize persistent Playwright browser if available
    browser_manager = None
    try:
        from ingestion.playwright_manager import PlaywrightBrowserManager
        browser_manager = PlaywrightBrowserManager()
        if browser_manager.start():
            logger.info('[BRAVE] Persistent Playwright browser started for collection')
        else:
            browser_manager = None
    except Exception as e:
        logger.debug('[BRAVE] Could not start persistent browser: %s', e)
        browser_manager = None
"""

# Find the location after url_collection_config import
marker = "    if url_collection_config:\n        from ingestion.domain_classifier import classify_url, URLSourceType\n"
if marker in content and 'browser_manager = None' not in content:
    content = content.replace(marker, marker + init_code)
    print("✓ Added browser manager initialization")

# Step 2: Add browser cleanup to early return
early_return_marker = "    if not search_results:\n        logger.warning('[BRAVE] No search results returned, returning empty list')\n        return []"
early_return_replacement = """    if not search_results:
        logger.warning('[BRAVE] No search results returned, returning empty list')
        if browser_manager:
            browser_manager.close()
        return []"""

if early_return_marker in content:
    content = content.replace(early_return_marker, early_return_replacement)
    print("✓ Added browser cleanup to early return")

# Step 3: Update process_url to pass browser_manager to fetch_page
old_fetch = "        content = fetch_page(url)"
new_fetch = "        content = fetch_page(url, browser_manager=browser_manager)"

if old_fetch in content:
    content = content.replace(old_fetch, new_fetch)
    print("✓ Updated process_url to pass browser_manager")

# Step 4: Add browser cleanup before final return
# Find the last "return collected" and add cleanup before it
lines = content.split('\n')
for i in range(len(lines) - 1, -1, -1):
    if lines[i].strip() == 'return collected':
        # Insert cleanup before return
        indent = len(lines[i]) - len(lines[i].lstrip())
        cleanup_lines = [
            ' ' * indent + '# Clean up browser manager',
            ' ' * indent + 'if browser_manager:',
            ' ' * indent + '    browser_manager.close()',
            ' ' * indent + '    logger.info(\'[BRAVE] Persistent Playwright browser closed\')',
            ' ' * indent + ''
        ]
        lines = lines[:i] + cleanup_lines + lines[i:]
        break

content = '\n'.join(lines)
print("✓ Added browser cleanup before final return")

# Write the modified content
with open('ingestion/brave_search.py', 'w') as f:
    f.write(content)

print("\n✅ Phase 3 complete: Browser manager integrated with collect_brave_pages()")
