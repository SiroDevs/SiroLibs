#!/usr/bin/env python3
"""
Scrape a chapter from Bible.com and save it as a structured JSON file
(a simplified USX-style tag tree, similar to YouVersion's own chapter JSON).

Example:
    python scrape_bible_chapter.py --bible-id 2138 --name taita --usfm GEN.1

This will:
  * request https://www.bible.com/bible/2138/GEN.1.TAITA
  * pull the embedded __NEXT_DATA__ blob out of the page
  * convert the chapter's HTML into a content tree
  * write the result to taita/verses/GEN/1.json (relative to the project
    root, i.e. one level above wherever this script file lives)
"""

import argparse
import json
import re
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

# Standard USFM book code -> English book name, used to build the
# "reference" field (e.g. "Genesis 1"). Extend / edit as needed.
BOOK_NAMES = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
    "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
    "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
    "EST": "Esther", "JOB": "Job", "PSA": "Psalm", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "Song of Solomon", "ISA": "Isaiah",
    "JER": "Jeremiah", "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel",
    "HOS": "Hosea", "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah",
    "JON": "Jonah", "MIC": "Micah", "NAM": "Nahum", "HAB": "Habakkuk",
    "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi",
    "MAT": "Matthew", "MRK": "Mark", "LUK": "Luke", "JHN": "John",
    "ACT": "Acts", "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
    "GAL": "Galatians", "EPH": "Ephesians", "PHP": "Philippians", "COL": "Colossians",
    "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy",
    "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John",
    "2JN": "2 John", "3JN": "3 John", "JUD": "Jude", "REV": "Revelation",
}


# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------

def build_url(bible_id: int, usfm: str, name: str) -> str:
    return f"https://www.bible.com/bible/{bible_id}/{usfm}.{name.upper()}"


def fetch_next_data(bible_id: int, usfm: str, name: str) -> dict:
    """Download the chapter page and pull out the embedded __NEXT_DATA__ JSON blob."""
    url = build_url(bible_id, usfm, name)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        raise RuntimeError(f"Could not find __NEXT_DATA__ script on {url}")

    return json.loads(script_tag.string)


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
# Top-level chapter build
# --------------------------------------------------------------------------

def build_chapter_json(bible_id: int, usfm: str, name: str, copyright_text: str) -> dict:
    data = fetch_next_data(bible_id, usfm, name)
    page_props = data["props"]["pageProps"]
    chapter_info = page_props["chapterInfo"]

    ref_usfm = chapter_info["reference"]["usfm"][0]
    book_id, chapter_number = ref_usfm.split(".")

    content = parse_chapter_html(chapter_info["content"], book_id, chapter_number)

    result = {
        "id": f"{book_id}.{chapter_number}",
        "number": chapter_number,
        "bookId": book_id,
        "reference": f"{BOOK_NAMES.get(book_id, book_id)} {chapter_number}",
        "copyright": copyright_text,
        "verseCount": count_verses(content),
        "content": content,
    }

    if chapter_info.get("next"):
        result["next"] = normalize_ref(chapter_info["next"]["usfm"][0])
    if chapter_info.get("previous"):
        result["previous"] = normalize_ref(chapter_info["previous"]["usfm"][0])

    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_chapter_range(book: str, chapters: str):
    """'1-5' or '1,3,7' or '1' -> ['GEN.1', 'GEN.2', ...]"""
    usfms = []
    for piece in chapters.split(","):
        piece = piece.strip()
        if "-" in piece:
            start, end = piece.split("-")
            for n in range(int(start), int(end) + 1):
                usfms.append(f"{book}.{n}")
        else:
            usfms.append(f"{book}.{piece}")
    return usfms


def main():
    parser = argparse.ArgumentParser(description="Scrape Bible.com chapter(s) into JSON files.")
    parser.add_argument("--bible-id", type=int, required=True, help="Bible version ID, e.g. 2138")
    parser.add_argument("--name", required=True,
                         help="Version short name, e.g. taita. Used lower-case for the "
                              "output folder and upper-case in the URL.")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--usfm", help="Single chapter usfm, e.g. GEN.1")
    group.add_argument("--book", help="Book code to use with --chapters, e.g. GEN")

    parser.add_argument("--chapters", help="Chapter number/range/list, e.g. '1-50' or '1,2,5' "
                                            "(required if --book is used)")
    parser.add_argument("--copyright", default=DEFAULT_COPYRIGHT,
                         help=f"Copyright string to embed in the JSON (default: '{DEFAULT_COPYRIGHT}')")
    parser.add_argument("--sleep", type=float, default=1.0,
                         help="Seconds to sleep between requests when scraping multiple chapters")
    args = parser.parse_args()

    if args.book and not args.chapters:
        parser.error("--chapters is required when using --book")

    # <name>/verses/ folder, anchored to SCRIPT_ROOT (the project root, one level
    # above this script's own folder) rather than the current working directory,
    # so behavior is stable no matter where/how this script is invoked.
    verses_dir = SCRIPT_ROOT / args.name.lower() / "verses"

    usfms = [args.usfm] if args.usfm else parse_chapter_range(args.book, args.chapters)

    for i, usfm in enumerate(usfms):
        try:
            result = build_chapter_json(args.bible_id, usfm, args.name, args.copyright)
        except Exception as exc:
            print(f"FAILED {usfm}: {exc}")
            continue

        # <name>/verses/<BOOK_ID>/<chapter_number>.json, e.g. taita/verses/GEN/1.json
        book_dir = verses_dir / result["bookId"]
        book_dir.mkdir(parents=True, exist_ok=True)

        out_path = book_dir / f"{result['number']}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved {out_path}")

        if i < len(usfms) - 1:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()