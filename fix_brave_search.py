"""Script to fix brave_search.py by removing leftover lines and restoring search_brave"""

# Read the original file to find search_brave function
with open('ingestion/brave_search.py', 'r') as f:
    lines = f.readlines()

# Remove lines 47-48 which are leftover code fragments
# Lines 47-48 contain:
#             pass
#         return {"title": "", "body": "", "url": url}

# Create new content
new_lines = lines[:46] + lines[49:]

# Write back
with open('ingestion/brave_search.py', 'w') as f:
    f.writelines(new_lines)

print(f"Removed leftover lines from brave_search.py")
print(f"Old line count: {len(lines)}")
print(f"New line count: {len(new_lines)}")

# Now we need to check if search_brave function exists
# Let's search for it
has_search_brave = any('def search_brave' in line for line in new_lines)
print(f"Has search_brave function: {has_search_brave}")
