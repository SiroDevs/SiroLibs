import json
from collections import Counter

INPUT_FILE = "words.json"
OUTPUT_FILE = "similar_words.txt"

# Load the JSON
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Collect all titles
titles = [
    item["title"].strip()
    for item in data
    if item.get("title") and item["title"].strip()
]

# Count occurrences
counts = Counter(titles)

# Keep only duplicates
duplicates = {
    title: count
    for title, count in counts.items()
    if count > 1
}

# Write to file
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for title in sorted(duplicates):
        f.write(f"{title} ({duplicates[title]})\n")

print(f"Found {len(duplicates)} duplicated titles.")
print(f"Results written to {OUTPUT_FILE}")