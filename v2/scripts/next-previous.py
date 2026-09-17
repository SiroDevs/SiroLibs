import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def fix_book(lang_book_dir: Path, kjv_book_dir: Path, book_id: str,
             dry_run: bool, stats: dict):
    if not lang_book_dir.is_dir():
        print(f"  [skip] {book_id}: no verses directory at {lang_book_dir}")
        stats["missing_lang_book_dir"] += 1
        return

    if not kjv_book_dir.is_dir():
        print(f"  [skip] {book_id}: no matching KJV directory at {kjv_book_dir}")
        stats["missing_kjv_book_dir"] += 1
        return

    for chapter_file in sorted(lang_book_dir.glob("*.json")):
        kjv_file = kjv_book_dir / chapter_file.name

        if not kjv_file.is_file():
            print(f"    [skip] {book_id}/{chapter_file.name}: "
                  f"no matching KJV file at {kjv_file}")
            stats["missing_kjv_file"] += 1
            continue

        try:
            kjv_data = load_json(kjv_file)
        except json.JSONDecodeError as e:
            print(f"    [error] could not parse {kjv_file}: {e}")
            stats["errors"] += 1
            continue

        kjv_next = kjv_data.get("next")
        kjv_previous = kjv_data.get("previous")

        try:
            lang_data = load_json(chapter_file)
        except json.JSONDecodeError as e:
            print(f"    [error] could not parse {chapter_file}: {e}")
            stats["errors"] += 1
            continue

        # Drop any existing next/previous so we can re-add them in the
        # required order (next, then previous) at the end of the object.
        lang_data.pop("next", None)
        lang_data.pop("previous", None)
        lang_data["next"] = kjv_next
        lang_data["previous"] = kjv_previous

        if dry_run:
            print(f"    [dry-run] would update {chapter_file} "
                  f"(next={kjv_next!r}, previous={kjv_previous!r})")
        else:
            save_json(chapter_file, lang_data)
            print(f"    [ok] updated {chapter_file}")

        stats["updated"] += 1


def main():
    parser = argparse.ArgumentParser(
        description="Fix missing next/previous fields in a translation's "
                    "verse files using the KJV files as the source of truth."
    )
    parser.add_argument("lang", help="Directory name of the translation, e.g. 'kikuyu'")
    parser.add_argument("--root", default=".",
                         help="Root directory containing <lang>/ and the KJV dir "
                              "(default: current directory)")
    parser.add_argument("--kjv-dir-name", default="kjv",
                         help="Name of the KJV reference directory (default: 'kjv')")
    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would change without writing any files")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    lang_dir = root / args.lang
    kjv_dir = root / args.kjv_dir_name

    books_json_path = lang_dir / "books.json"
    if not books_json_path.is_file():
        print(f"books.json not found at {books_json_path}")
        sys.exit(1)

    books = load_json(books_json_path)

    lang_verses_dir = lang_dir / "verses"
    kjv_verses_dir = kjv_dir / "verses"

    stats = {
        "updated": 0,
        "missing_lang_book_dir": 0,
        "missing_kjv_book_dir": 0,
        "missing_kjv_file": 0,
        "errors": 0,
    }

    for book in books:
        book_id = book["id"]
        print(f"Book: {book_id} ({book.get('name', '')})")
        fix_book(
            lang_book_dir=lang_verses_dir / book_id,
            kjv_book_dir=kjv_verses_dir / book_id,
            book_id=book_id,
            dry_run=args.dry_run,
            stats=stats,
        )

    print("\n--- Summary ---")
    print(f"Chapter files updated:            {stats['updated']}")
    print(f"Books missing lang verses dir:     {stats['missing_lang_book_dir']}")
    print(f"Books missing KJV verses dir:      {stats['missing_kjv_book_dir']}")
    print(f"Chapter files missing KJV match:   {stats['missing_kjv_file']}")
    print(f"Errors:                            {stats['errors']}")


if __name__ == "__main__":
    main()