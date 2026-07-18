import json
import os
import sys

if len(sys.argv) != 2:
    print("Usage: python3 verses-trim.py <directory>")
    sys.exit(1)

directory = sys.argv[1]

complete_file = os.path.join(directory, "Complete.json")
chapters_file = os.path.join(directory, "chapters.json")
verses_dir = os.path.join(directory, "verses")

if not os.path.isfile(complete_file):
    print(f"Error: '{complete_file}' not found.")
    sys.exit(1)

if not os.path.isfile(chapters_file):
    print(f"Error: '{chapters_file}' not found.")
    sys.exit(1)

# Load Complete.json
with open(complete_file, "r", encoding="utf-8") as f:
    books = json.load(f)

# Load chapters.json
with open(chapters_file, "r", encoding="utf-8") as f:
    chapters_lookup = json.load(f)

os.makedirs(verses_dir, exist_ok=True)

chapter_count = 0

for book in books:
    book_id = book["id"]
    book_name = book["name"]

    # Create verses/GEN/
    book_dir = os.path.join(verses_dir, book_id)
    os.makedirs(book_dir, exist_ok=True)

    # Lookup chapter references from chapters.json
    chapter_refs = {
        int(c["number"]): c["reference"]
        for c in chapters_lookup.get(book_id, [])
    }

    for chapter_data in book["chapters"]:
        chapter = chapter_data["chapter"]
        chapter_number = chapter["number"]

        content_items = []

        # First paragraph
        current_para = {
            "name": "para",
            "type": "tag",
            "attrs": {
                "style": "p"
            },
            "items": []
        }

        for item in chapter["content"]:
            item_type = item.get("type")

            if item_type == "verse":
                verse_number = str(item["number"])

                # Verse marker
                current_para["items"].append({
                    "name": "verse",
                    "type": "tag",
                    "attrs": {
                        "number": verse_number,
                        "style": "v",
                        "sid": f"{book_id} {chapter_number}:{verse_number}"
                    },
                    "items": [
                        {
                            "text": verse_number,
                            "type": "text"
                        }
                    ]
                })

                # Verse text
                parts = []

                for part in item.get("content", []):
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict):
                        if part.get("lineBreak"):
                            parts.append("\n")

                verse_text = "".join(parts).strip()

                current_para["items"].append({
                    "text": verse_text,
                    "type": "text",
                    "attrs": {
                        "verseId": f"{book_id}.{chapter_number}.{verse_number}",
                        "verseOrgIds": [
                            f"{book_id}.{chapter_number}.{verse_number}"
                        ]
                    }
                })

            elif item_type == "heading":
                # Finish current paragraph
                if current_para["items"]:
                    content_items.append(current_para)

                # Heading
                content_items.append({
                    "name": "para",
                    "type": "tag",
                    "attrs": {
                        "style": "s1"
                    },
                    "items": [
                        {
                            "text": " ".join(item.get("content", [])),
                            "type": "text"
                        }
                    ]
                })

                # Start new paragraph
                current_para = {
                    "name": "para",
                    "type": "tag",
                    "attrs": {
                        "style": "p"
                    },
                    "items": []
                }

            elif item_type == "line_break":
                # Ignore standalone line breaks
                continue

        # Add last paragraph if it contains verses
        if current_para["items"]:
            content_items.append(current_para)

        output = {
            "id": f"{book_id}.{chapter_number}",
            "number": str(chapter_number),
            "bookId": book_id,
            "reference": chapter_refs.get(
                chapter_number,
                f"{book_name} {chapter_number}"
            ),
            "verseCount": chapter_data["numberOfVerses"],
            "content": [
                {
                    "name": "chapter",
                    "type": "tag",
                    "attrs": {
                        "number": str(chapter_number),
                        "style": "c",
                        "sid": f"{book_id} {chapter_number}"
                    },
                    "items": [
                        {
                            "text": str(chapter_number),
                            "type": "text"
                        }
                    ]
                },
                *content_items
            ]
        }

        output_file = os.path.join(
            book_dir,
            f"{chapter_number}.json"
        )

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        chapter_count += 1

print(f"Created {chapter_count} chapter files.")

# Delete Complete.json after successful processing
os.remove(complete_file)
# print(f"Deleted '{complete_file}'.")