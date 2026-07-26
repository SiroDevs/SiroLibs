#!/usr/bin/env python3
"""
Scrape every chapter of a Bible.com version into JSON files, one per chapter,
localizing book names/references from the scraped pages as it goes.

Example:
    python3 scripts/bible.com.py 2138 taita

This will:
  1. Copy swahili/books.json and swahili/chapters.json (the starting template)
     into taita/books.json and taita/chapters.json.
  2. Walk every entry in taita/chapters.json. For each one, build the chapter's
     URL (e.g. https://www.bible.com/bible/2138/GEN.1.TAITA), fetch the page,
     and parse the __NEXT_DATA__ blob into a content tree.
  3. The first time a given book is encountered, read the page's <h1> chapter
     heading (e.g. "KUZOYA 1"), strip the chapter number off it to recover the
     localized book name ("Kuzoya"), and use it to update:
       - taita/books.json:    name / nameLong / abbreviation for that book
       - taita/chapters.json: reference for every chapter of that book
     All later chapters of the same book reuse this cached name.
  4. Save each chapter's content to taita/verses/<BOOK_ID>/<chapter_number>.json,
     e.g. taita/verses/GEN/1.json, with "reference" set to the localized name.

All paths are relative to SCRIPT_ROOT (the project root, one level above
wherever this script file lives), not the current working directory, so
behavior is the same no matter where/how this script is invoked.
"""

import argparse
import json
import re
import shutil
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

DEFAULT_COPYRIGHT = "PUBLIC DOMAIN"

# Root directory that version folders (e.g. "taita/") get created under.
# This script is expected to live in a subfolder (e.g. "scripts/bible.com.py"),
# so we go one level up from the script's own folder to land at the project
# root, sibling to "scripts/". This is anchored to the file's location on
# disk (not the current working directory), so it behaves the same no
# matter what directory you're standing in when you run it.
#
# If you instead keep this script directly at the project root (no
# "scripts/" subfolder), change this to: Path(__file__).resolve().parent
SCRIPT_ROOT = Path(__file__).resolve().parent.parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Source language whose books.json / chapters.json are copied as the starting
# template for a new version folder (see main()). Override with --source.
DEFAULT_SOURCE_NAME = "swahili"


# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------

def build_url(bible_id: int, usfm: str, name: str) -> str:
    return f"https://www.bible.com/bible/{bible_id}/{usfm}.{name.upper()}"


def fetch_page(bible_id: int, usfm: str, name: str):
    """Download the chapter page.

    Returns (next_data, heading_text):
      * next_data    - the embedded __NEXT_DATA__ JSON blob (dict)
      * heading_text - the raw text of the page's <h1> chapter heading,
                       e.g. "KUZOYA 1" (used to derive the localized book name)
    """
    url = build_url(bible_id, usfm, name)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        raise RuntimeError(f"Could not find __NEXT_DATA__ script on {url}")
    next_data = json.loads(script_tag.string)

    h1 = soup.find("h1")
    heading_text = h1.get_text(strip=True) if h1 else ""

    return next_data, heading_text


# --------------------------------------------------------------------------
# HTML -> content-tree parsing
# --------------------------------------------------------------------------

def has_class(tag: Tag, cls: str) -> bool:
    return cls in (tag.get("class") or [])


def parse_note(note_span: Tag) -> dict:
    """Convert a <span class="note x"> ... </span> footnote/cross-reference block."""
    label_span = note_span.find("span", class_="label")
    body_span = note_span.find(lambda t: t.name == "span" and "body" in (t.get("class") or []))

    style = "f" if has_class(note_span, "f") else "x"

    items = []
    if body_span:
        for child in body_span.children:
            if isinstance(child, NavigableString):
                txt = str(child).strip(" ;")
                if txt:
                    items.append({"text": txt, "type": "text"})
            elif isinstance(child, Tag):
                if has_class(child, "ref"):
                    items.append({
                        "name": "ref",
                        "type": "tag",
                        "attrs": {"loc": child.get("data-usfm", "")},
                        "items": [{"text": child.get_text(), "type": "text"}],
                    })
                else:
                    txt = child.get_text().strip()
                    if txt:
                        items.append({"text": txt, "type": "text"})

    return {
        "name": "note",
        "type": "tag",
        "attrs": {
            "style": style,
            "caller": label_span.get_text() if label_span else "",
        },
        "items": items,
    }


def verse_number_from_classes(verse_span: Tag) -> str:
    for c in verse_span.get("class", []):
        m = re.match(r"^v(\d+)$", c)
        if m:
            return m.group(1)
    label = verse_span.find("span", class_="label")
    return label.get_text().strip() if label else ""


def parse_verse_span(verse_span: Tag, book_id: str, chapter_number: str) -> list:
    """Convert a <span class="verse vN" data-usfm="..."> into [verse-marker, text..., note...]."""
    items = []

    usfm = verse_span.get("data-usfm", "")
    vnum = verse_number_from_classes(verse_span)
    sid = f"{book_id} {chapter_number}:{vnum}"

    items.append({
        "name": "verse",
        "type": "tag",
        "attrs": {"number": vnum, "style": "v", "sid": sid},
        "items": [{"text": vnum, "type": "text"}],
    })

    verse_ids = usfm.split("+") if usfm else [f"{book_id}.{chapter_number}.{vnum}"]
    verse_id = usfm or verse_ids[0]

    for child in verse_span.children:
        if isinstance(child, Tag) and has_class(child, "label"):
            continue  # already emitted as the verse marker above
        elif isinstance(child, Tag) and has_class(child, "content"):
            txt = child.get_text()
            items.append({
                "text": txt,
                "type": "text",
                "attrs": {"verseId": verse_id, "verseOrgIds": verse_ids},
            })
        elif isinstance(child, Tag) and "note" in (child.get("class") or []):
            items.append(parse_note(child))
        elif isinstance(child, NavigableString):
            txt = str(child)
            if txt.strip():
                items.append({
                    "text": txt,
                    "type": "text",
                    "attrs": {"verseId": verse_id, "verseOrgIds": verse_ids},
                })

    return items


def paragraph_style(p_div: Tag) -> str:
    classes = p_div.get("class", [])
    for candidate in ("q1", "q2", "q3", "m", "pi", "li1", "li2", "b"):
        if candidate in classes:
            return candidate
    return "p"


def parse_paragraph(p_div: Tag, book_id: str, chapter_number: str) -> dict:
    items = []
    for child in p_div.children:
        if isinstance(child, Tag):
            classes = child.get("class", [])
            if "verse" in classes:
                items.extend(parse_verse_span(child, book_id, chapter_number))
            elif "content" in classes:
                txt = child.get_text()
                if txt.strip():
                    items.append({"text": txt, "type": "text"})
            elif "note" in classes:
                items.append(parse_note(child))
        elif isinstance(child, NavigableString):
            txt = str(child)
            if txt.strip():
                items.append({"text": txt, "type": "text"})

    return {"name": "para", "type": "tag", "attrs": {"style": paragraph_style(p_div)}, "items": items}


def parse_heading(s_div: Tag) -> dict:
    heading_span = s_div.find("span", class_="heading")
    text = heading_span.get_text() if heading_span else s_div.get_text()
    return {
        "name": "para",
        "type": "tag",
        "attrs": {"style": "s1"},
        "items": [{"text": text, "type": "text"}],
    }


def parse_chapter_html(chapter_html: str, book_id: str, chapter_number: str) -> list:
    """Parse the chapterInfo.content HTML fragment into a list of content blocks."""
    soup = BeautifulSoup(chapter_html, "html.parser")

    chapter_div = soup.find("div", class_="chapter")
    if chapter_div is None:
        chapter_div = soup

    content = [{
        "name": "chapter",
        "type": "tag",
        "attrs": {"number": chapter_number, "style": "c", "sid": f"{book_id} {chapter_number}"},
        "items": [{"text": chapter_number, "type": "text"}],
    }]

    for child in chapter_div.children:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class", [])
        if "label" in classes:
            continue  # the chapter-number label div; already represented above
        elif "s" in classes:
            content.append(parse_heading(child))
        elif "p" in classes:
            content.append(parse_paragraph(child, book_id, chapter_number))

    return content


def count_verses(content: list) -> int:
    verse_numbers = set()
    for block in content:
        for item in block.get("items", []):
            if item.get("type") == "tag" and item.get("name") == "verse":
                verse_numbers.add(item["attrs"]["number"])
    return len(verse_numbers)


# --------------------------------------------------------------------------
# next / previous references
# --------------------------------------------------------------------------

def normalize_ref(usfm_token: str) -> dict:
    """Turn a raw usfm token like 'GEN.2' or 'GEN.INTRO1' into {id, number, bookId}."""
    parts = usfm_token.split(".")
    book_id = parts[0]
    raw_number = parts[1] if len(parts) > 1 else ""
    number = "intro" if raw_number.upper().startswith("INTRO") else raw_number
    return {"id": f"{book_id}.{number}", "number": number, "bookId": book_id}


# --------------------------------------------------------------------------
# Localized book name (from the page's <h1>, e.g. "KUZOYA 1" -> "Kuzoya")
# --------------------------------------------------------------------------

def extract_book_name_from_heading(heading_text: str, chapter_number: str) -> str:
    """'KUZOYA 1' + chapter_number='1' -> 'Kuzoya'.

    Strips the trailing chapter number off the page's <h1> text to recover
    just the localized book title, then title-cases it.
    """
    text = heading_text.strip()

    # Prefer stripping the exact chapter number we requested...
    stripped = re.sub(r"\s*" + re.escape(chapter_number) + r"\s*$", "", text)
    if stripped == text:
        # ...fall back to stripping any trailing digits, in case of a mismatch.
        stripped = re.sub(r"\s*\d+\s*$", "", text)

    return stripped.strip().title()


# --------------------------------------------------------------------------
# Top-level chapter build
# --------------------------------------------------------------------------

def build_chapter_json(bible_id: int, usfm: str, name: str, copyright_text: str,
                        book_name_cache: dict) -> tuple:
    """Fetch + parse a single chapter.

    book_name_cache maps bookId -> localized book name (e.g. {"GEN": "Kuzoya"}).
    It's read/written in place: the first time a given bookId is seen, the
    localized name is derived from this page's <h1> and cached; subsequent
    chapters of the same book reuse the cached name instead of re-deriving it.

    Returns (result_dict, local_book_name, is_newly_resolved).
    """
    next_data, heading_text = fetch_page(bible_id, usfm, name)
    page_props = next_data["props"]["pageProps"]
    chapter_info = page_props["chapterInfo"]

    ref_usfm = chapter_info["reference"]["usfm"][0]
    book_id, chapter_number = ref_usfm.split(".")

    is_newly_resolved = book_id not in book_name_cache
    if is_newly_resolved:
        book_name_cache[book_id] = extract_book_name_from_heading(heading_text, chapter_number)
    local_book_name = book_name_cache[book_id]

    content = parse_chapter_html(chapter_info["content"], book_id, chapter_number)

    result = {
        "id": f"{book_id}.{chapter_number}",
        "number": chapter_number,
        "bookId": book_id,
        "reference": f"{local_book_name} {chapter_number}",
        "copyright": copyright_text,
        "verseCount": count_verses(content),
        "content": content,
    }

    if chapter_info.get("next"):
        result["next"] = normalize_ref(chapter_info["next"]["usfm"][0])
    if chapter_info.get("previous"):
        result["previous"] = normalize_ref(chapter_info["previous"]["usfm"][0])

    return result, local_book_name, is_newly_resolved


# --------------------------------------------------------------------------
# books.json / chapters.json helpers
# --------------------------------------------------------------------------

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def copy_template_files(source_dir: Path, dest_dir: Path) -> tuple:
    """Copy books.json and chapters.json from source_dir into dest_dir.

    Returns (books_path, chapters_path) inside dest_dir.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    src_books = source_dir / "books.json"
    src_chapters = source_dir / "chapters.json"
    if not src_books.exists() or not src_chapters.exists():
        raise FileNotFoundError(
            f"Expected books.json and chapters.json in {source_dir}, "
            f"found books.json={src_books.exists()} chapters.json={src_chapters.exists()}"
        )

    dest_books = dest_dir / "books.json"
    dest_chapters = dest_dir / "chapters.json"
    shutil.copy2(src_books, dest_books)
    shutil.copy2(src_chapters, dest_chapters)

    return dest_books, dest_chapters


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape every chapter of a Bible.com version into JSON files, "
                    "localizing book names/references as it goes."
    )
    parser.add_argument("bible_id", type=int, help="Bible version ID, e.g. 2138")
    parser.add_argument("name",
                         help="Version short name, e.g. taita. Used lower-case for the "
                              "output folder and upper-case in the URL.")
    parser.add_argument("--source", default=DEFAULT_SOURCE_NAME,
                         help=f"Folder to copy books.json/chapters.json from as the starting "
                              f"template (default: '{DEFAULT_SOURCE_NAME}')")
    parser.add_argument("--copyright", default=DEFAULT_COPYRIGHT,
                         help=f"Copyright string to embed in each chapter JSON "
                              f"(default: '{DEFAULT_COPYRIGHT}')")
    parser.add_argument("--sleep", type=float, default=1.0,
                         help="Seconds to sleep between requests")
    args = parser.parse_args()

    dest_dir = SCRIPT_ROOT / args.name.lower()
    source_dir = SCRIPT_ROOT / args.source.lower()
    verses_dir = dest_dir / "verses"

    books_path, chapters_path = copy_template_files(source_dir, dest_dir)
    print(f"Copied templates from {source_dir} to {dest_dir}")

    books = load_json(books_path)
    # chapters.json is a dict keyed by bookId, e.g. {"GEN": [ {...}, {...} ], "EXO": [...]}
    chapters_by_book = load_json(chapters_path)

    books_by_id = {b["id"]: b for b in books}

    # Flatten into a single ordered list of (book_id, chapter_entry) so we can
    # walk them in document order while still updating chapters_by_book in place.
    flat_entries = [
        (book_id, entry)
        for book_id, entries in chapters_by_book.items()
        for entry in entries
    ]

    book_name_cache = {}  # bookId -> localized name, e.g. {"GEN": "Kuzoya"}
    total = len(flat_entries)

    for i, (book_id, entry) in enumerate(flat_entries):
        number = entry["number"]
        usfm = f"{book_id}.{number}"

        try:
            result, local_name, is_newly_resolved = build_chapter_json(
                args.bible_id, usfm, args.name, args.copyright, book_name_cache
            )
        except Exception as exc:
            print(f"FAILED {usfm}: {exc}")
            continue

        if is_newly_resolved:
            print(f"Resolved book name for {book_id}: '{local_name}'")

            book_entry = books_by_id.get(book_id)
            if book_entry:
                book_entry["name"] = local_name
                book_entry["nameLong"] = local_name
                book_entry["abbreviation"] = local_name[:3]

            for ch in chapters_by_book.get(book_id, []):
                ch["reference"] = f"{local_name} {ch['number']}"

            # Persist immediately so a partial/interrupted run still leaves
            # books.json and chapters.json in a consistent, up-to-date state.
            save_json(books_path, books)
            save_json(chapters_path, chapters_by_book)

        book_dir = verses_dir / book_id
        book_dir.mkdir(parents=True, exist_ok=True)
        out_path = book_dir / f"{result['number']}.json"
        save_json(out_path, result)
        print(f"[{i + 1}/{total}] Saved {out_path}")

        if i < total - 1:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()