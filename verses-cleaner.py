import sys
import json
import gzip
import re
from pathlib import Path
from collections import Counter

INPUT_FILE = "bible-verses.json"
OUTPUT_FILE = "bible-verses.cleaned.json"

# Unicode spaces that commonly cause issues
UNICODE_SPACES = {
    "\u2000",  # EN QUAD
    "\u2001",  # EM QUAD
    "\u2002",  # EN SPACE
    "\u2003",  # EM SPACE
    "\u2004",  # THREE-PER-EM SPACE
    "\u2005",  # FOUR-PER-EM SPACE
    "\u2006",  # SIX-PER-EM SPACE
    "\u2007",  # FIGURE SPACE
    "\u2008",  # PUNCTUATION SPACE
    "\u2009",  # THIN SPACE
    "\u200A",  # HAIR SPACE
    "\u202F",  # NARROW NO-BREAK SPACE
    "\u205F",  # MEDIUM MATHEMATICAL SPACE
    "\u3000",  # IDEOGRAPHIC SPACE
}

# Smart quote replacements
SMART_QUOTES = {
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}

stats = Counter()


def clean_string(text):
    original = text

    # Replace strange spaces
    for space in UNICODE_SPACES:
        if space in text:
            stats[f"space_{ord(space):04X}"] += text.count(space)
            text = text.replace(space, " ")

    # Replace smart quotes
    for old, new in SMART_QUOTES.items():
        if old in text:
            stats[f"quote_{old}"] += text.count(old)
            text = text.replace(old, new)

    # Collapse whitespace
    collapsed = re.sub(r"\s+", " ", text)

    if collapsed != text:
        stats["collapsed_whitespace"] += 1

    text = collapsed.strip()

    if text != original:
        stats["modified_strings"] += 1

    return text


def recursively_clean(obj):
    if isinstance(obj, str):
        return clean_string(obj)

    if isinstance(obj, list):
        return [recursively_clean(item) for item in obj]

    if isinstance(obj, dict):
        return {
            key: recursively_clean(value)
            for key, value in obj.items()
        }

    return obj


def split_books(data):
    """
    Attempts to split into one file per book.

    Adjust this section if your JSON structure differs.
    """

    output_dir = Path("books")
    output_dir.mkdir(exist_ok=True)

    if not isinstance(data, dict):
        print("Cannot split books automatically.")
        return

    books = data.get("books")

    if not isinstance(books, list):
        print("No books array found.")
        return

    for book in books:
        name = book.get("name", "unknown")

        safe_name = (
            name.lower()
            .replace(" ", "_")
            .replace("/", "_")
        )

        path = output_dir / f"{safe_name}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                book,
                f,
                ensure_ascii=False,
                separators=(",", ":"),
            )

    print(f"Split {len(books)} books into {output_dir}/")


def create_gzip(json_path):
    gz_path = json_path + ".gz"

    with open(json_path, "rb") as fin:
        with gzip.open(gz_path, "wb") as fout:
            fout.writelines(fin)

    print(f"Created {gz_path}")


def main():
    if len(sys.argv) != 2:
        print(
            "missing arguments"
        )
        sys.exit(1)

    source_dir = Path(sys.argv[1]).resolve()

    if not source_dir.exists():
        print(f"Input directory does not exist: {source_dir}")
        sys.exit(1)

    source_dir.mkdir(parents=True, exist_ok=True)

    input_file = source_dir / "bible-verses.json"

    if not input_file.exists():
        print(f"File not found: {input_file}")
        sys.exit(1)

    output_file = source_dir / "bible-verses-new.json"

    print(f"Loading {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Cleaning content...")

    cleaned = recursively_clean(data)

    print(f"Writing cleaned file to {output_file}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            cleaned,
            f,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    print("\nStatistics:")
    for key, value in stats.most_common():
        print(f"{key}: {value}")

    # create_gzip(str(output_file))

    # try:
    #     split_books(
    #         cleaned,
    #         output_dir / "books"
    #     )
    # except Exception as e:
    #     print(f"Book splitting skipped: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()