import json
import os
import sys

if len(sys.argv) != 2:
    print("Usage: python3 books-strip.py <directory>")
    sys.exit(1)

directory = sys.argv[1]

source_file = os.path.join(directory, "bookz.json")
books_file = os.path.join(directory, "books.json")
chapters_file = os.path.join(directory, "chapters.json")

if not os.path.isfile(source_file):
    print(f"Error: '{source_file}' not found.")
    sys.exit(1)

# Load source JSON
with open(source_file, "r", encoding="utf-8") as f:
    books = json.load(f)

books_output = []
chapters_output = {}

for book in books:
    book_id = book["id"]
    name = book["name"]
    last_chapter = int(book.get("lastChapterNumber", 0))

    # books.json
    books_output.append({
        "id": book_id,
        "abbreviation": name[:3],
        "name": name,
        "nameLong": book.get("commonName")
    })

    # chapters.json
    chapters = []

    for chapter in range(1, last_chapter + 1):
        chapters.append({
            "id": f"{book_id}.{chapter}",
            "bookId": book_id,
            "number": str(chapter),
            "reference": f"{name} {chapter}"
        })

    chapters_output[book_id] = chapters

# Save books.json
with open(books_file, "w", encoding="utf-8") as f:
    json.dump(books_output, f, ensure_ascii=False, indent=2)

# Save chapters.json
with open(chapters_file, "w", encoding="utf-8") as f:
    json.dump(chapters_output, f, ensure_ascii=False, indent=2)

# Delete the original source file only after successful creation
try:
    os.remove(source_file)
    print(f"Deleted '{source_file}'")
except OSError as e:
    print(f"Warning: Could not delete '{source_file}': {e}")

print(f"Created '{books_file}'")
print(f"Created '{chapters_file}'")
print(f"Processed {len(books_output)} books.")