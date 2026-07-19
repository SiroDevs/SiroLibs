import argparse
import json
import os
import re
import sys
from bs4 import BeautifulSoup, NavigableString, Tag

_COMPACT_TO_CLASSIC = {
    "\u2160": "I", "\u2161": "II", "\u2162": "III", "\u2163": "IV",
    "\u2164": "V", "\u2165": "VI", "\u2166": "VII", "\u2167": "VIII",
    "\u2168": "IX", "\u2169": "X", "\u216A": "XI", "\u216B": "XII",
    "\u216C": "L", "\u216D": "C", "\u216E": "D", "\u216F": "M",
    "\u2170": "I", "\u2171": "II", "\u2172": "III", "\u2173": "IV",
    "\u2174": "V", "\u2175": "VI", "\u2176": "VII", "\u2177": "VIII",
    "\u2178": "IX", "\u2179": "X", "\u217A": "XI", "\u217B": "XII",
    "\u217C": "L", "\u217D": "C", "\u217E": "D", "\u217F": "M",
}

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(text):
    """Convert a (possibly compact-Unicode) Roman numeral string to an int.

    Returns None if the string has no usable numeral content.
    """
    if text is None:
        return None
    cleaned = text.replace("\xa0", "").strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        return None

    classic = "".join(_COMPACT_TO_CLASSIC.get(ch, ch) for ch in cleaned).upper()

    if classic.isdigit():
        return int(classic)

    total = 0
    prev_value = 0
    for ch in reversed(classic):
        value = _ROMAN_VALUES.get(ch)
        if value is None:
            continue
        if value < prev_value:
            total -= value
        else:
            total += value
            prev_value = value
    return total if total else None

_NON_VERSE_STYLES = {
    "s", "s1", "s2", "s3", "sr", "r", "d", "sp",
    "mt", "mt1", "mt2", "mt3", "imt", "imt1", "imt2",
    "is", "is1", "iot", "io", "io1", "io2", "ip", "ipi",
    "rem", "restore",
}


CHAPTERLABEL_RE = re.compile(r"<div\s+class=['\"]chapterlabel['\"][^>]*>", re.IGNORECASE)
TNAV_RE = re.compile(r"<ul\s+class=['\"]tnav['\"]\s*>", re.IGNORECASE)
COPYRIGHT_RE = re.compile(
    r"<div\s+class=['\"]copyright['\"][^>]*>(.*?)</div>", re.IGNORECASE | re.DOTALL
)
CHAPTER_FILE_RE_TEMPLATE = r"^{book_id}(\d+)\.html?$"


def extract_copyright(full_html):
    """Best-effort extraction of the copyright notice from a chapter file."""
    match = COPYRIGHT_RE.search(full_html)
    if not match:
        return None
    text = BeautifulSoup(match.group(1), "html.parser").get_text()
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def slice_chapter_html(full_html):
    """Return the substring of full_html from the chapterlabel div (inclusive)
    up to the following <ul class='tnav'> (exclusive). Returns None if the
    markers aren't found (e.g. an intro / index page with no chapter content).
    """
    start_match = CHAPTERLABEL_RE.search(full_html)
    if not start_match:
        return None
    start = start_match.start()
    end_match = TNAV_RE.search(full_html, start_match.end())
    if not end_match:
        return None
    end = end_match.start()
    return full_html[start:end]


def clean_text(text):
    """Collapse internal whitespace/newlines to single spaces and trim ends."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_chapter(full_html, book_id, book_name, filename):
    """Parse a single chapter HTML file into the JSON structure."""
    chapter_html = slice_chapter_html(full_html)
    if chapter_html is None:
        return None

    soup = BeautifulSoup(chapter_html, "html.parser")
    top_level = [node for node in soup.contents
                 if isinstance(node, Tag) or
                 (isinstance(node, NavigableString) and node.strip())]

    if not top_level or not isinstance(top_level[0], Tag):
        return None

    chapterlabel_div = top_level[0]
    chapter_num = roman_to_int(chapterlabel_div.get_text())
    if chapter_num is None:
        print(f"  ! Could not determine chapter number in {filename}; skipping",
              file=sys.stderr)
        return None

    content = [{
        "name": "chapter",
        "type": "tag",
        "attrs": {
            "number": str(chapter_num),
            "style": "c",
            "sid": f"{book_id} {chapter_num}",
        },
        "items": [{"text": str(chapter_num), "type": "text"}],
    }]

    current_verse = None
    max_verse = 0

    for div in top_level[1:]:
        if not isinstance(div, Tag):
            continue

        classes = div.get("class") or ["p"]
        style = classes[0]
        items = []

        for child in div.children:
            if isinstance(child, NavigableString):
                text = clean_text(str(child))
                if not text:
                    continue
                block = {"text": text, "type": "text"}
                if current_verse is not None and style not in _NON_VERSE_STYLES:
                    verse_id = f"{book_id}.{chapter_num}.{current_verse}"
                    block["attrs"] = {"verseId": verse_id, "verseOrgIds": [verse_id]}
                items.append(block)
                continue

            if not isinstance(child, Tag):
                continue

            child_classes = child.get("class") or []

            if child.name == "span" and "verse" in child_classes:
                verse_num = roman_to_int(child.get_text())
                if verse_num is None:
                    continue
                current_verse = verse_num
                max_verse = max(max_verse, verse_num)
                items.append({
                    "name": "verse",
                    "type": "tag",
                    "attrs": {
                        "number": str(verse_num),
                        "style": "v",
                        "sid": f"{book_id} {chapter_num}:{verse_num}",
                    },
                    "items": [{"text": str(verse_num), "type": "text"}],
                })
                continue

            if child.name == "a" and "notemark" in child_classes:
                continue

            text = clean_text(child.get_text())
            if text:
                block = {"text": text, "type": "text"}
                if current_verse is not None and style not in _NON_VERSE_STYLES:
                    verse_id = f"{book_id}.{chapter_num}.{current_verse}"
                    block["attrs"] = {"verseId": verse_id, "verseOrgIds": [verse_id]}
                items.append(block)

        if items:
            content.append({
                "name": "para",
                "type": "tag",
                "attrs": {"style": style},
                "items": items,
            })

    copyright_text = extract_copyright(full_html)

    return {
        "id": f"{book_id}.{chapter_num}",
        "number": str(chapter_num),
        "bookId": book_id,
        "reference": f"{book_name} {chapter_num}",
        "copyright": copyright_text,
        "verseCount": max_verse,
        "content": content,
        "chapterNumber": chapter_num,  # kept for internal sorting/linking use
    }

def find_chapter_files(vs_dir, book_id):
    """Return a sorted list of (chapter_number, filepath) for a book,
    skipping the "00" intro file. Falls back to treating the bare
    "<id>.htm" file as a single chapter 1 if no numbered files exist.
    """
    pattern = re.compile(CHAPTER_FILE_RE_TEMPLATE.format(book_id=re.escape(book_id)),
                          re.IGNORECASE)
    found = []
    try:
        entries = os.listdir(vs_dir)
    except FileNotFoundError:
        return []

    for entry in entries:
        m = pattern.match(entry)
        if not m:
            continue
        num = int(m.group(1))
        if num == 0:
            continue  # intro / book-info page, not a chapter
        found.append((num, os.path.join(vs_dir, entry)))

    found.sort(key=lambda pair: pair[0])

    if found:
        return found

    # Single-chapter book fallback: bare "<id>.htm" holds the chapter itself
    bare_path = os.path.join(vs_dir, f"{book_id}.htm")
    if not os.path.exists(bare_path):
        bare_path = os.path.join(vs_dir, f"{book_id}.html")
    if os.path.exists(bare_path):
        with open(bare_path, encoding="utf-8-sig") as fh:
            if CHAPTERLABEL_RE.search(fh.read()):
                return [(1, bare_path)]

    return []


def process_book(book, vs_dir, out_dir, verbose=False):
    book_id = book["id"]
    book_name = book.get("name") or book.get("nameLong") or book_id

    chapter_files = find_chapter_files(vs_dir, book_id)
    if not chapter_files:
        if verbose:
            print(f"[{book_id}] no chapter files found in {vs_dir}; skipping")
        return 0

    chapters = []
    for chapter_num, path in chapter_files:
        with open(path, encoding="utf-8-sig") as fh:
            full_html = fh.read()
        filename = os.path.basename(path)
        chapter_json = parse_chapter(full_html, book_id, book_name, filename)
        if chapter_json is None:
            if verbose:
                print(f"  ! Skipped {filename} (no chapter content found)")
            continue
        chapters.append(chapter_json)

    if not chapters:
        return 0

    chapters.sort(key=lambda c: c["chapterNumber"])

    book_out_dir = os.path.join(out_dir, book_id)
    os.makedirs(book_out_dir, exist_ok=True)

    chapter_numbers = [c["chapterNumber"] for c in chapters]

    for i, chapter in enumerate(chapters):
        this_num = chapter_numbers[i]

        if i == 0:
            previous = {"id": f"{book_id}.intro", "number": "intro", "bookId": book_id}
        else:
            prev_num = chapter_numbers[i - 1]
            previous = {"id": f"{book_id}.{prev_num}", "number": str(prev_num), "bookId": book_id}

        if i < len(chapters) - 1:
            next_num = chapter_numbers[i + 1]
            nxt = {"id": f"{book_id}.{next_num}", "number": str(next_num), "bookId": book_id}
        else:
            nxt = None

        chapter["previous"] = previous
        chapter["next"] = nxt
        del chapter["chapterNumber"]  # internal-only field

        out_path = os.path.join(book_out_dir, f"{this_num}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(chapter, fh, ensure_ascii=False, indent=2)

    if verbose:
        print(f"[{book_id}] wrote {len(chapters)} chapter(s) to {book_out_dir}")

    return len(chapters)

def main():
    parser = argparse.ArgumentParser(
        description="Convert eBible.org-style HTML Bible chapter files into JSON.")
    parser.add_argument("directory", help="Base directory containing books.json and a 'vs' folder")
    parser.add_argument("--books-json", default=None,
                         help="Path to books.json (default: <directory>/books.json)")
    parser.add_argument("--vs-dir", default=None,
                         help="Path to the folder with the html files (default: <directory>/vs)")
    parser.add_argument("--out", default=None,
                         help="Output directory (default: <directory>/verses)")
    parser.add_argument("--books", nargs="+", default=None,
                         help="Only process these book ids (default: all books in books.json)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    directory = args.directory
    books_json_path = args.books_json or os.path.join(directory, "books.json")
    vs_dir = args.vs_dir or os.path.join(directory, "vs")
    out_dir = args.out or os.path.join(directory, "verses")

    if not os.path.exists(books_json_path):
        print(f"Error: books.json not found at {books_json_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(vs_dir):
        print(f"Error: html directory not found at {vs_dir}", file=sys.stderr)
        sys.exit(1)

    with open(books_json_path, encoding="utf-8") as fh:
        books = json.load(fh)

    if args.books:
        wanted = {b.upper() for b in args.books}
        books = [b for b in books if b["id"].upper() in wanted]

    os.makedirs(out_dir, exist_ok=True)

    total_chapters = 0
    total_books = 0
    for book in books:
        n = process_book(book, vs_dir, out_dir, verbose=args.verbose)
        if n:
            total_books += 1
            total_chapters += n

    print(f"Done. Processed {total_books} book(s), {total_chapters} chapter(s) total.")

if __name__ == "__main__":
    main()