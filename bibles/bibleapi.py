import argparse
import json
import os
import sys
import time
import requests

BASE_URL = "https://api.scripture.api.bible/v1"
API_KEY = "TGRJdsFgcxbJJkUTWAItT"

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"api-key": API_KEY})
    return s


def get(session: requests.Session, endpoint: str, retries: int = 3, backoff: float = 2.0):
    """GET an endpoint, retry on 429 / 5xx, raise on other errors."""
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 429:
                wait = backoff * attempt
                print(f"  [rate-limit] waiting {wait}s before retry {attempt}/{retries} …")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == retries:
                print(f"  [error] {exc}")
                raise
            time.sleep(backoff * attempt)


def save(data, directory: str, filename: str):
    """Write *data* as pretty-printed JSON to <directory>/<filename>.json."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{filename}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  saved → {path}")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_bible_info(session, bible_id: str, out_dir: str):
    print(f"\n[1/4] Fetching bible info …")
    data = get(session, f"bibles/{bible_id}")
    save(data, out_dir, "bible-info")
    return data


def fetch_books(session, bible_id: str, out_dir: str):
    print(f"\n[2/4] Fetching books …")
    data = get(session, f"bibles/{bible_id}/books")
    save(data, out_dir, "bible-books")
    books = data.get("data", [])
    print(f"  found {len(books)} books")
    return books


def fetch_chapters(session, bible_id: str, book_id: str, out_dir: str):
    data = get(session, f"bibles/{bible_id}/books/{book_id}/chapters")
    return data.get("data", [])


def fetch_all_chapters(session, bible_id: str, books: list, out_dir: str):
    """Fetch chapters for every book and persist as a single file."""
    print(f"\n[3/4] Fetching chapters for all books …")
    all_chapters: dict[str, list] = {}
    for book in books:
        book_id = book["id"]
        print(f"  chapters for {book_id} …", end=" ", flush=True)
        chapters = fetch_chapters(session, bible_id, book_id, out_dir)
        # strip the intro chapter (id ends with '.intro') — it has no verses
        chapters = [c for c in chapters if not c["id"].endswith(".intro")]
        all_chapters[book_id] = chapters
        print(f"{len(chapters)} chapters")
    save(all_chapters, out_dir, "bible-chapters")
    return all_chapters


def fetch_all_verses(session, bible_id: str, all_chapters: dict, out_dir: str):
    """
    Step 4: loop every book → every chapter, fetch chapter content
    (which includes verses) and append results to bible-verses.json.
    """
    print(f"\n[4/4] Fetching chapter content (verses) …")

    verses_path = os.path.join(out_dir, "bible-verses.json")

    # resume support: load whatever we've already fetched
    if os.path.exists(verses_path):
        print(f"  resuming from existing {verses_path}")
        accumulated = load_json(verses_path)
    else:
        accumulated = {}

    total_books = len(all_chapters)
    for book_idx, (book_id, chapters) in enumerate(all_chapters.items(), start=1):
        if book_id not in accumulated:
            accumulated[book_id] = {}

        print(f"\n  [{book_idx}/{total_books}] {book_id} ({len(chapters)} chapters)")
        for ch in chapters:
            chapter_id = ch["id"]          # e.g. "GEN.1"
            if chapter_id in accumulated[book_id]:
                print(f"    {chapter_id} (cached, skipping)")
                continue

            print(f"    {chapter_id} …", end=" ", flush=True)
            try:
                data = get(
                    session,
                    f"bibles/{bible_id}/chapters/{chapter_id}"
                    "?content-type=json&include-notes=false"
                    "&include-titles=true&include-chapter-numbers=true"
                    "&include-verse-numbers=true&include-verse-spans=false",
                )
                accumulated[book_id][chapter_id] = data.get("data", data)
                print("ok")
            except Exception as exc:
                print(f"FAILED ({exc}) — skipping")
                accumulated[book_id][chapter_id] = {"error": str(exc)}

            # flush after every chapter so progress is never lost
            with open(verses_path, "w", encoding="utf-8") as f:
                json.dump(accumulated, f, ensure_ascii=False, indent=2)

    print(f"\n  saved → {verses_path}")
    return accumulated

def parse_args():
    p = argparse.ArgumentParser(description="Fetch Bible data from api.bible")
    p.add_argument("--bible-id", required=True, help="Bible ID from api.bible")
    p.add_argument(
        "--out-dir",
        default="swahili",
        help="Output directory name (default: swahili)",
    )
    p.add_argument(
        "--skip-verses",
        action="store_true",
        help="Skip step 4 (verse fetching) — useful for quick metadata-only runs",
    )
    return p.parse_args()


def main():
    args = parse_args()

    session  = make_session()
    bible_id = args.bible_id
    out_dir  = args.out_dir

    print(f"Bible ID : {bible_id}")
    print(f"Output   : {out_dir}/")

    fetch_bible_info(session, bible_id, out_dir)
    books        = fetch_books(session, bible_id, out_dir)
    all_chapters = fetch_all_chapters(session, bible_id, books, out_dir)

    if not args.skip_verses:
        fetch_all_verses(session, bible_id, all_chapters, out_dir)

    print("\n✓ All done!")


if __name__ == "__main__":
    main()