import json
import sys
from pathlib import Path


def sort_and_reassign_ids(file_path):
    path = Path(file_path)

    if not path.exists():
        print(f"Error: File not found: {file_path}")
        return

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            print("Error: JSON file must contain an array of objects.")
            return

        # Sort alphabetically by title, case-insensitive
        data.sort(
            key=lambda item: str(item.get("title", "")).strip().lower()
        )

        # Reassign IDs based on the new order
        for index, item in enumerate(data, start=1):
            item["rid"] = index

        # Overwrite the original file
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

        print(f"Successfully processed {len(data)} records.")
        print(f"Updated: {path}")

    except json.JSONDecodeError:
        print(f"Error: {file_path} contains invalid JSON.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 sort_json.py <file.json>")
        sys.exit(1)

    sort_and_reassign_ids(sys.argv[1])
