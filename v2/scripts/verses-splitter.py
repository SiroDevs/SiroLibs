#!/usr/bin/env python3
"""
split_verses.py

Reads `books.json` and `verses.json` from a given directory, and for every
book listed in books.json, writes/updates a per-book JSON file
`<path>/verses/<BOOK_ID>.json` containing that book's verse data pulled
out of verses.json.

Usage:
    python3 split_verses.py /path/to/translation/folder

Expected input layout (inside the given path):
    books.json   -> { "data": [ { "id": "GEN", ... }, { "id": "EXO", ... }, ... ] }
    verses.json  -> { "GEN": { "GEN.1": {...}, "GEN.2": {...}, ... },
                       "EXO": { "EXO.1": {...}, ... }, ... }

Output:
    <path>/verses/GEN.json
    <path>/verses/EXO.json
    ...

If an output file for a book already exists, its existing chapter entries
are merged with (and overwritten by) the new data rather than being
clobbered, so re-running the script is safe and additive.
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(file_path: Path):
    if not file_path.is_file():
        sys.exit(f"Error: expected file not found: {file_path}")
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: failed to parse JSON in {file_path}: {e}")


def get_book_ids(books_data) -> list:
    """Extract the list of book ids from the parsed books.json content."""
    if isinstance(books_data, dict) and "data" in books_data:
        entries = books_data["data"]
    elif isinstance(books_data, list):
        entries = books_data
    else:
        sys.exit("Error: unrecognized books.json structure (expected a 'data' list).")

    book_ids = []
    for entry in entries:
        book_id = entry.get("id")
        if not book_id:
            print(f"Warning: skipping book entry without an 'id': {entry}", file=sys.stderr)
            continue
        book_ids.append(book_id)
    return book_ids


def main():
    parser = argparse.ArgumentParser(
        description="Split verses.json into per-book files under a 'verses' subdirectory."
    )
    parser.add_argument(
        "path",
        help="Directory containing books.json and verses.json",
    )
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="Do not delete verses.json after successfully splitting it (deleted by default).",
    )
    args = parser.parse_args()

    base_path = Path(args.path).expanduser().resolve()
    if not base_path.is_dir():
        sys.exit(f"Error: path is not a directory: {base_path}")

    books_path = base_path / "books.json"
    verses_path = base_path / "verses.json"

    books_data = load_json(books_path)
    verses_data = load_json(verses_path)

    if not isinstance(verses_data, dict):
        sys.exit("Error: unrecognized verses.json structure (expected an object keyed by book id).")

    book_ids = get_book_ids(books_data)
    if not book_ids:
        sys.exit("Error: no book ids found in books.json.")

    output_dir = base_path / "verses"
    output_dir.mkdir(parents=True, exist_ok=True)

    created, updated, missing = 0, 0, []

    for book_id in book_ids:
        book_verses = verses_data.get(book_id)
        if book_verses is None:
            missing.append(book_id)
            continue

        out_file = output_dir / f"{book_id}.json"

        # Merge with any existing content so re-runs are additive, not destructive.
        if out_file.is_file():
            try:
                with out_file.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError):
                existing = {}
            existing.update(book_verses)
            merged = existing
            updated += 1
        else:
            merged = book_verses
            created += 1

        with out_file.open("w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Done. {created} file(s) created, {updated} file(s) updated in: {output_dir}")
    if missing:
        print(
            f"Warning: {len(missing)} book id(s) from books.json had no matching "
            f"entry in verses.json: {', '.join(missing)}",
            file=sys.stderr,
        )

    # Only delete the source verses.json if at least one output file was
    # successfully written and the user didn't ask to keep it.
    if not args.keep_source:
        if created or updated:
            try:
                verses_path.unlink()
                print(f"Deleted source file: {verses_path}")
            except OSError as e:
                print(f"Warning: could not delete {verses_path}: {e}", file=sys.stderr)
        else:
            print(
                f"Note: no output files were written, so {verses_path} was left in place.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()