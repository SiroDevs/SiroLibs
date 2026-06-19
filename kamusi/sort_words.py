"""
sort_words.py

Reads words_rows.csv, sorts the entries alphabetically (A-Z) by the
'title' column, groups all rows that share the same title together,
reassigns the 'rid' column to match the new row order (1, 2, 3, ...),
and writes the result to words_rows_new.csv.

Usage:
    python3 sort_words.py [input_csv] [output_csv]

Defaults:
    input_csv  = words_rows.csv
    output_csv = words_rows_new.csv
"""

import sys
import pandas as pd


def sort_words(input_path: str, output_path: str) -> None:
    # Read the CSV. keep_default_na keeps things simple; titles are required
    # so we don't expect blanks there, but other columns may be empty.
    df = pd.read_csv(input_path)

    if "title" not in df.columns:
        raise ValueError("Expected a 'title' column in the CSV.")

    # Build a case-insensitive sort key so 'Adamu' and 'adamu' sort together
    # the way a dictionary normally would. Using a stable sort (mergesort)
    # means rows that already share the same title keep their original
    # relative order, so they end up grouped together as requested.
    df["_sort_key"] = df["title"].astype(str).str.strip().str.lower()
    df_sorted = df.sort_values(
        by="_sort_key", kind="mergesort"
    ).drop(columns="_sort_key")

    # Reassign rid based on the new row order.
    df_sorted = df_sorted.reset_index(drop=True)
    df_sorted["rid"] = df_sorted.index + 1

    df_sorted.to_csv(output_path, index=False)
    print(f"Sorted {len(df_sorted)} rows by title (A-Z) and saved to {output_path}")


if __name__ == "__main__":
    input_csv = sys.argv[1] if len(sys.argv) > 1 else "words_rows.csv"
    output_csv = sys.argv[2] if len(sys.argv) > 2 else "words_rows_new.csv"
    sort_words(input_csv, output_csv)
