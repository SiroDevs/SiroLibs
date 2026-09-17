import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent  # <v2>
OLD_INFO_PATH = ROOT / "old-info.json"
ROOT_INFO_PATH = ROOT / "info.json"

NON_GROUP_NAMES = {SCRIPT_DIR.name, "__pycache__", ".git", "node_modules"}


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    if not OLD_INFO_PATH.exists():
        sys.exit(
            f"error: {OLD_INFO_PATH} not found - expected the flat master "
            f"info.json at the v2 root"
        )

    pool = {e["abbreviation"].lower(): e for e in load_json(OLD_INFO_PATH, [])}

    group_dirs = sorted(
        p for p in ROOT.iterdir() if p.is_dir() and p.name not in NON_GROUP_NAMES
    )

    root_groups = []
    newly_matched = 0

    for group_dir in group_dirs:
        group_info_path = group_dir / "info.json"
        existing_by_path = {
            e["path"]: e for e in load_json(group_info_path, []) if "path" in e
        }

        bible_dirs = sorted(
            p
            for p in group_dir.iterdir()
            if p.is_dir() and (p / "books.json").exists()
        )

        group_entries = []
        for bible_dir in bible_dirs:
            leaf = bible_dir.name

            if leaf in existing_by_path:
                group_entries.append(existing_by_path[leaf])
                continue

            match = pool.pop(leaf.lower(), None)
            if match is None:
                print(
                    f"  ! warning: {group_dir.name}/{leaf} has no matching entry "
                    f"in {OLD_INFO_PATH.name} (and isn't already in "
                    f"{group_info_path.name}) - add it there by hand"
                )
                continue

            entry = {**match, "path": leaf}
            group_entries.append(entry)
            newly_matched += 1
            print(f"  + matched {group_dir.name}/{leaf}")

        if group_entries:
            save_json(group_info_path, group_entries)
            print(
                f"wrote {group_info_path.relative_to(ROOT)} "
                f"({len(group_entries)} bible(s))"
            )
            root_groups.append(group_dir.name)

    save_json(OLD_INFO_PATH, list(pool.values()))
    print(
        f"\n{newly_matched} newly matched this run, "
        f"{len(pool)} bible(s) left in {OLD_INFO_PATH.name}"
    )

    save_json(ROOT_INFO_PATH, root_groups)
    print(f"wrote {ROOT_INFO_PATH.relative_to(ROOT)}: {root_groups}")


if __name__ == "__main__":
    sys.exit(main())