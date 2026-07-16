#!/usr/bin/env python3
"""
split_json.py

Iterates over all .json files in a given directory. For each file (e.g. RUT.json),
creates a subdirectory named after the file's base name (e.g. RUT/), and inside it
writes one JSON file per item found in the source file's top-level object, named
after that item's "number" attribute (e.g. 4.json).

Usage:
    python split_json.py /path/to/source_dir [-o /path/to/output_dir] [--indent 2]

If -o/--output is not given, the per-book folders are created inside the source
directory itself.
"""

import argparse
import json
import sys
from pathlib import Path


def process_file(json_path: Path, output_root: Path, indent: int) -> None:
    """Process a single JSON file, splitting its items into individual files."""
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  [SKIP] Could not parse {json_path.name}: {e}")
        return

    if not isinstance(data, dict):
        print(f"  [SKIP] {json_path.name}: top-level JSON is not an object, cannot split into items")
        return

    book_name = json_path.stem  # e.g. "RUT" from "RUT.json"
    book_dir = output_root / book_name
    book_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0

    for key, item in data.items():
        if not isinstance(item, dict) or "number" not in item:
            print(f"  [WARN] Item '{key}' has no 'number' attribute, skipping")
            skipped += 1
            continue

        number = item["number"]
        out_path = book_dir / f"{number}.json"

        try:
            with out_path.open("w", encoding="utf-8") as out_f:
                json.dump(item, out_f, indent=indent, ensure_ascii=False)
        except OSError as e:
            print(f"  [ERROR] Failed to write {out_path}: {e}")
            skipped += 1
            continue

        written += 1

    print(f"  -> {book_dir} : {written} file(s) written" + (f", {skipped} skipped" if skipped else ""))

    if written > 0:
        try:
            json_path.unlink()
            print(f"  -> Deleted original {json_path.name}")
        except OSError as e:
            print(f"  [ERROR] Failed to delete {json_path}: {e}")
    else:
        print(f"  [SKIP] No files written, keeping original {json_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split JSON files into per-item files by 'number' attribute.")
    parser.add_argument("source_dir", type=str, help="Directory containing the .json files to process")
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Directory in which to create the per-file output folders (default: same as source_dir)",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentation level for output JSON files (default: 2)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"Error: '{source_dir}' is not a valid directory")
        sys.exit(1)

    verses_dir = source_dir / "verses"
    if not verses_dir.is_dir():
        print(f"Error: expected a 'verses' subdirectory inside '{source_dir}', found none")
        sys.exit(1)

    output_root = Path(args.output).expanduser().resolve() if args.output else verses_dir
    output_root.mkdir(parents=True, exist_ok=True)

    json_files = sorted(verses_dir.glob("*.json"))
    if not json_files:
        print(f"No .json files found in '{verses_dir}'")
        return

    print(f"Found {len(json_files)} JSON file(s) in '{verses_dir}'")
    for json_path in json_files:
        print(f"Processing {json_path.name}...")
        process_file(json_path, output_root, args.indent)

    print("Done.")


if __name__ == "__main__":
    main()