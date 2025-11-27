"""Script to remove extracted functions from brave_search.py"""

# Read the file
with open('ingestion/brave_search.py', 'r') as f:
    lines = f.readlines()

# Find the line numbers to remove
# We need to remove from line 47 (old _get_session) to line 1300 (end of fetch_page)
# But keep everything after line 1300

# The new file should have:
# - Lines 1-46 (imports and setup)
# - Lines 1301-end (collect_brave_pages and other Brave-specific functions)

new_lines = lines[:46] + lines[1300:]

# Write the cleaned file
with open('ingestion/brave_search.py', 'w') as f:
    f.writelines(new_lines)

print(f"Removed lines 47-1300 from brave_search.py")
print(f"Old line count: {len(lines)}")
print(f"New line count: {len(new_lines)}")
