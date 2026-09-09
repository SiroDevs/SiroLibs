#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

DEFAULT_COPYRIGHT = "PUBLIC DOMAIN"
DEFAULT_SOURCE_NAME = "swahili"
SCRIPT_ROOT = Path(__file__).resolve().parent.parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_SESSION_WARMED = False


def warm_up_session():
    global _SESSION_WARMED
    if _SESSION_WARMED:
        return
    try:
        SESSION.get("https://www.bible.com/", timeout=30)
    except Exception:
        pass
    _SESSION_WARMED = True


def build_url(bible_id: int, usfm: str, name: str) -> str:
    return f"https://www.bible.com/bible/{bible_id}/{usfm}.{name.upper()}"


def extract_usfm_from_href(href: str, name: str) -> str:
    """Turn a Previous/Next chapter link (relative or absolute) into a bare
    usfm token like 'GEN.2' or 'GEN.INTRO1', stripping the trailing version
    name segment."""
    if not href:
        return ""
    last_segment = href.rstrip("/").split("/")[-1]
    parts = last_segment.split(".")
    if parts and parts[-1].upper() == name.upper():
        parts = parts[:-1]
    return ".".join(parts)


def fetch_page(bible_id: int, usfm: str, name: str, debug_dir: Path = None):
    """Fetch a chapter page and return (chapter_div, heading_text, prev_href, next_href).

    bible.com now renders with the Next.js App Router, which no longer embeds
    a __NEXT_DATA__ JSON blob. The chapter content, heading, and prev/next
    links are all present directly in the rendered HTML, so we parse those
    instead.
    """
    warm_up_session()
    url = build_url(bible_id, usfm, name)
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    chapter_div = soup.find("div", class_="chapter")

    if chapter_div is None:
        detail = f"status {resp.status_code}, {len(resp.text)} bytes"
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / f"{usfm.replace('.', '_')}.html"
            debug_path.write_text(resp.text, encoding="utf-8")
            detail += f", saved to {debug_path}"
        raise RuntimeError(f"Could not find chapter content on {url} ({detail})")

    h1 = soup.find("h1")
    heading_text = h1.get_text(strip=True) if h1 else ""

    prev_href = None
    next_href = None
    for a in soup.find_all("a", href=True):
        label = a.get_text(strip=True).lower()
        if label == "next chapter":
            next_href = a["href"]
        elif label == "previous chapter":
            prev_href = a["href"]

    return chapter_div, heading_text, prev_href, next_href


def has_class(tag: Tag, cls: str) -> bool:
    return cls in (tag.get("class") or [])


def parse_note(note_span: Tag) -> dict:
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
            continue
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


def parse_chapter_html(chapter_html_or_div, book_id: str, chapter_number: str) -> list:
    """Accepts either a raw HTML string or an already-parsed <div class="chapter">
    Tag (the latter is what fetch_page now returns)."""
    if isinstance(chapter_html_or_div, Tag):
        chapter_div = chapter_html_or_div
    else:
        soup = BeautifulSoup(chapter_html_or_div, "html.parser")
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
            continue
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


def normalize_ref(usfm_token: str) -> dict:
    parts = usfm_token.split(".")
    book_id = parts[0]
    raw_number = parts[1] if len(parts) > 1 else ""
    number = "intro" if raw_number.upper().startswith("INTRO") else raw_number
    return {"id": f"{book_id}.{number}", "number": number, "bookId": book_id}


def extract_book_name_from_heading(heading_text: str, chapter_number: str) -> str:
    text = heading_text.strip()
    stripped = re.sub(r"\s*" + re.escape(chapter_number) + r"\s*$", "", text)
    if stripped == text:
        stripped = re.sub(r"\s*\d+\s*$", "", text)
    return stripped.strip().title()


def build_chapter_json(bible_id: int, usfm: str, name: str, copyright_text: str,
                        book_name_cache: dict, debug_dir: Path = None) -> tuple:
    chapter_div, heading_text, prev_href, next_href = fetch_page(
        bible_id, usfm, name, debug_dir=debug_dir
    )

    book_id, chapter_number = usfm.split(".", 1)

    is_newly_resolved = book_id not in book_name_cache
    if is_newly_resolved:
        book_name_cache[book_id] = extract_book_name_from_heading(heading_text, chapter_number)
    local_book_name = book_name_cache[book_id]

    content = parse_chapter_html(chapter_div, book_id, chapter_number)

    result = {
        "id": f"{book_id}.{chapter_number}",
        "number": chapter_number,
        "bookId": book_id,
        "reference": f"{local_book_name} {chapter_number}",
        "copyright": copyright_text,
        "verseCount": count_verses(content),
        "content": content,
    }

    if next_href:
        next_usfm = extract_usfm_from_href(next_href, name)
        if next_usfm:
            result["next"] = normalize_ref(next_usfm)
    if prev_href:
        prev_usfm = extract_usfm_from_href(prev_href, name)
        if prev_usfm:
            result["previous"] = normalize_ref(prev_usfm)

    return result, local_book_name, is_newly_resolved


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def copy_template_files(source_dir: Path, dest_dir: Path) -> tuple:
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_books = dest_dir / "books.json"
    dest_chapters = dest_dir / "chapters.json"

    if dest_books.exists() and dest_chapters.exists():
        print(f"Found existing {dest_books} and {dest_chapters}; resuming with them as-is")
        return dest_books, dest_chapters

    src_books = source_dir / "books.json"
    src_chapters = source_dir / "chapters.json"
    if not src_books.exists() or not src_chapters.exists():
        raise FileNotFoundError(
            f"Expected books.json and chapters.json in {source_dir}, "
            f"found books.json={src_books.exists()} chapters.json={src_chapters.exists()}"
        )

    shutil.copy2(src_books, dest_books)
    shutil.copy2(src_chapters, dest_chapters)
    print(f"Copied templates from {source_dir} to {dest_dir}")

    return dest_books, dest_chapters


def local_name_from_existing_file(out_path: Path, chapter_number: str) -> str:
    existing = load_json(out_path)
    reference = existing.get("reference", "")
    suffix = f" {chapter_number}"
    if reference.endswith(suffix):
        return reference[: -len(suffix)]
    return reference


def books_by_id_to_list(books_by_id: dict) -> list:
    return list(books_by_id.values())


def process_book(book_id: str, entries: list, args, books_by_id: dict,
                  chapters_by_book: dict, book_name_cache: dict,
                  books_path: Path, chapters_path: Path, verses_dir: Path,
                  debug_dir: Path, done_so_far: int, total: int) -> int:
    log_prefix = f"[{book_id}] "
    book_total = len(entries)
    book_dir = verses_dir / book_id
    book_dir.mkdir(parents=True, exist_ok=True)

    for idx, entry in enumerate(entries):
        number = entry["number"]
        usfm = f"{book_id}.{number}"
        out_path = book_dir / f"{number}.json"

        if out_path.exists():
            if book_id not in book_name_cache:
                book_name_cache[book_id] = local_name_from_existing_file(out_path, number)
            done_so_far += 1
            continue

        try:
            result, local_name, is_newly_resolved = build_chapter_json(
                args.bible_id, usfm, args.name, args.copyright, book_name_cache,
                debug_dir=debug_dir,
            )
        except Exception as first_exc:
            print(f"{log_prefix}FAILED {usfm}: {first_exc}; retrying once in "
                  f"{args.retry_sleep:.0f}s")
            time.sleep(args.retry_sleep)
            try:
                result, local_name, is_newly_resolved = build_chapter_json(
                    args.bible_id, usfm, args.name, args.copyright, book_name_cache,
                    debug_dir=debug_dir,
                )
            except Exception as second_exc:
                print(f"{log_prefix}FAILED {usfm} again: {second_exc}; moving on")
                time.sleep(args.sleep)
                continue

        if is_newly_resolved:
            print(f"{log_prefix}Resolved book name: '{local_name}'")

            book_entry = books_by_id.get(book_id)
            if book_entry:
                book_entry["name"] = local_name
                book_entry["nameLong"] = local_name
                book_entry["abbreviation"] = local_name[:3]

            for ch in chapters_by_book.get(book_id, []):
                ch["reference"] = f"{local_name} {ch['number']}"

            save_json(books_path, books_by_id_to_list(books_by_id))
            save_json(chapters_path, chapters_by_book)

        save_json(out_path, result)

        done_so_far += 1
        print(f"{log_prefix}[{idx + 1}/{book_total}] "
              f"(overall {done_so_far}/{total}) Saved {out_path}")

        time.sleep(args.sleep)

    return done_so_far


def main():
    parser = argparse.ArgumentParser(
        description="Scrape every chapter of a Bible.com version into JSON files, "
                    "localizing book names/references as it goes."
    )
    parser.add_argument("bible_id", type=int, help="Bible version ID, e.g. 2138")
    parser.add_argument("name",
                         help="Version short name, e.g. taita. Used upper-case in the "
                              "URL (e.g. GEN.1.TAITA), and also as the output folder "
                              "name unless a folder argument is given.")
    parser.add_argument("folder", nargs="?", default=None,
                         help="Optional output folder name, if different from `name` "
                              "(e.g. `mbivlia` as the URL version but `kamba` as the "
                              "folder). Defaults to `name` if omitted.")
    parser.add_argument("--source", default=DEFAULT_SOURCE_NAME,
                         help=f"Folder to copy books.json/chapters.json from as the starting "
                              f"template (default: '{DEFAULT_SOURCE_NAME}')")
    parser.add_argument("--copyright", default=DEFAULT_COPYRIGHT,
                         help=f"Copyright string to embed in each chapter JSON "
                              f"(default: '{DEFAULT_COPYRIGHT}')")
    parser.add_argument("--sleep", type=float, default=3.0,
                         help="Seconds to sleep between requests (default: 3.0)")
    parser.add_argument("--retry-sleep", type=float, default=5.0,
                         help="Seconds to wait before the one retry of a failed "
                              "fetch (default: 5.0)")
    args = parser.parse_args()

    folder_name = args.folder or args.name
    dest_dir = SCRIPT_ROOT / folder_name.lower()
    source_dir = SCRIPT_ROOT / args.source.lower()
    verses_dir = dest_dir / "verses"
    debug_dir = dest_dir / "_debug"

    books_path, chapters_path = copy_template_files(source_dir, dest_dir)

    books = load_json(books_path)
    chapters_by_book = load_json(chapters_path)
    books_by_id = {b["id"]: b for b in books}

    book_name_cache = {}
    total = sum(len(entries) for entries in chapters_by_book.values())

    book_ids = list(chapters_by_book.keys())
    print(f"Processing {len(book_ids)} books ({total} chapters total), one book at a time.")

    done = 0
    for book_id in book_ids:
        done = process_book(
            book_id, chapters_by_book[book_id], args,
            books_by_id, chapters_by_book, book_name_cache,
            books_path, chapters_path, verses_dir, debug_dir, done, total,
        )


if __name__ == "__main__":
    main()