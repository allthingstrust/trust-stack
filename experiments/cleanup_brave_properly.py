"""Script to properly clean up brave_search.py"""

# Read the file
with open('ingestion/brave_search.py', 'r') as f:
    lines = f.readlines()

# We need to:
# 1. Keep lines 1-42 (imports and rate limiter setup)
# 2. Add import from page_fetcher
# 3. Add logger and BRAVE_SEARCH_URL
# 4. Keep search_brave function (starts at line 165)
# 5. Remove lines 44-164 (extracted functions: _get_session, _is_allowed_by_robots, _extract_footer_links)
# 6. Remove lines 516-1299 (extracted functions: _extract_internal_links through fetch_page)
# 7. Keep collect_brave_pages and everything after (line 1302+)

# Build the new file
new_lines = []

# Part 1: Lines 1-37 (up to and including rate limiter)
new_lines.extend(lines[:37])

# Part 2: Add new imports and setup
new_lines.append('\n')
new_lines.append('# Import page fetching functions from dedicated module\n')
new_lines.append('from ingestion.page_fetcher import fetch_page, _extract_internal_links\n')
new_lines.append('\n')
new_lines.append('logger = logging.getLogger(__name__)\n')
new_lines.append('\n')
new_lines.append('BRAVE_SEARCH_URL = "https://search.brave.com/search"\n')
new_lines.append('\n')
new_lines.append('\n')

# Part 3: search_brave function (lines 165-515)
new_lines.extend(lines[164:515])

# Part 4: collect_brave_pages and rest (line 1302+)
new_lines.extend(lines[1301:])

# Write the cleaned file
with open('ingestion/brave_search.py', 'w') as f:
    f.writelines(new_lines)

print(f"Cleaned brave_search.py successfully")
print(f"Old line count: {len(lines)}")
print(f"New line count: {len(new_lines)}")

# Verify search_brave exists
has_search_brave = any('def search_brave' in line for line in new_lines)
has_collect_brave = any('def collect_brave_pages' in line for line in new_lines)
print(f"Has search_brave: {has_search_brave}")
print(f"Has collect_brave_pages: {has_collect_brave}")
