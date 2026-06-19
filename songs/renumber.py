#!/usr/bin/env python3

import json
from collections import defaultdict

INPUT_FILE = "songs.json"
OUTPUT_FILE = "songs.new.json"


with open(INPUT_FILE, "r", encoding="utf-8") as f:
    songs = json.load(f)

book_counters = defaultdict(int)

for song in songs:
    book_counters[song["book"]] += 1
    song["songNo"] = book_counters[song["book"]]

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(songs, f, ensure_ascii=False, indent=2)

print(f"Saved {len(songs)} songs to {OUTPUT_FILE}")