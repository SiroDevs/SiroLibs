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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def build_url(bible_id: int, usfm: str, name: str) -> str:
    return f"https://www.bible.com/bible/{bible_id}/{usfm}.{name.upper()}"


def fetch_page(bible_id: int, usfm: str, name: str, debug_dir: Path = None):
    url = build_url(bible_id, usfm, name)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")

    if not script_tag or not script_tag.string:
        detail = f"status {resp.status_code}, {len(resp.text)} bytes"
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_path = debug_dir / f"{usfm.replace('.', '_')}.html"
            debug_path.write_text(resp.text, encoding="utf-8")
            detail += f", saved to {debug_path}"
        raise RuntimeError(f"Could not find __NEXT_DATA__ script on {url} ({detail})")

    next_data = json.loads(script_tag.string)
    h1 = soup.find("h1")
    heading_text = h1.get_text(strip=True) if h1 else ""
    return next_data, heading_text


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


def parse_chapter_html(chapter_html: str, book_id: str, chapter_number: str) -> list:
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
    next_data, heading_text = fetch_page(bible_id, usfm, name, debug_dir=debug_dir)
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
            print(f"{log_prefix}[{idx + 1}/{book_total}] "
                  f"(overall {done_so_far}/{total}) Already have {out_path}, skipping")
            continue

        try:
            result, local_name, is_newly_resolved = build_chapter_json(
                args.bible_id, usfm, args.name, args.copyright, book_name_cache,
                debug_dir=debug_dir,
            )
        except Exception as exc:
            print(f"{log_prefix}FAILED {usfm}: {exc}; moving on")
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
    print(f"Processing {len(book_ids)} books ({total} chapters total), one book at a time. "
          f"Chapters with an existing verses/<BOOK>/<n>.json are skipped, so re-running "
          f"this same command resumes where it left off.")

    done = 0
    for book_id in book_ids:
        done = process_book(
            book_id, chapters_by_book[book_id], args,
            books_by_id, chapters_by_book, book_name_cache,
            books_path, chapters_path, verses_dir, debug_dir, done, total,
        )


if __name__ == "__main__":
    main()