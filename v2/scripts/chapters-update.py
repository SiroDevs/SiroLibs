#!/usr/bin/env python3
"""
Script to update chapter references in chapters.json with book names from books.json
Usage: python update_chapters.py /path/to/directory
"""

import json
import os
import sys
from pathlib import Path
import shutil

def load_books_data(directory_path):
    """Load book data from books.json in the specified directory"""
    books_file = Path(directory_path) / "books.json"
    
    if not books_file.exists():
        print(f"Error: {books_file} not found!")
        print(f"Please make sure '{directory_path}' contains a books.json file.")
        return None
    
    try:
        with open(books_file, 'r', encoding='utf-8') as f:
            books_data = json.load(f)
        return books_data
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in books.json: {e}")
        return None
    except Exception as e:
        print(f"Error reading books.json: {e}")
        return None

def create_book_name_map(books_data):
    """Create a mapping from book ID to book name"""
    book_map = {}
    
    # Handle both list format and dict format
    if isinstance(books_data, list):
        for book in books_data:
            if "id" in book and "name" in book:
                book_map[book["id"]] = book["name"]
    elif isinstance(books_data, dict):
        # If it's a dict with book IDs as keys
        for book_id, book_info in books_data.items():
            if isinstance(book_info, dict) and "name" in book_info:
                book_map[book_id] = book_info["name"]
            elif isinstance(book_info, str):
                # If it's just a string name
                book_map[book_id] = book_info
    else:
        print("Error: Unexpected books.json format")
        return None
    
    return book_map

def update_chapter_references(chapters_data, book_name_map):
    """Update all chapter references with the proper book names"""
    updated_count = 0
    missing_books = set()
    
    for book_id, chapters in chapters_data.items():
        if book_id in book_name_map:
            book_name = book_name_map[book_id]
            for chapter in chapters:
                chapter_num = chapter.get("number", "")
                # Update the reference
                chapter["reference"] = f"{book_name} {chapter_num}"
                updated_count += 1
        else:
            missing_books.add(book_id)
    
    if missing_books:
        print(f"Warning: No name found for book IDs: {', '.join(missing_books)}")
    
    return updated_count

def process_directory(directory_path):
    """Process the chapters.json and books.json files in the given directory"""
    
    # Load books data
    books_data = load_books_data(directory_path)
    if books_data is None:
        return False
    
    # Create book name mapping
    book_name_map = create_book_name_map(books_data)
    if book_name_map is None:
        return False
    
    # Construct path to chapters.json
    chapters_file = Path(directory_path) / "chapters.json"
    
    # Check if file exists
    if not chapters_file.exists():
        print(f"Error: {chapters_file} not found!")
        print(f"Please make sure '{directory_path}' contains a chapters.json file.")
        return False
    
    # Read the chapters.json file
    try:
        with open(chapters_file, 'r', encoding='utf-8') as f:
            chapters_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in chapters.json: {e}")
        return False
    except Exception as e:
        print(f"Error reading file: {e}")
        return False
    
    # Update references
    updated_count = update_chapter_references(chapters_data, book_name_map)
    
    # Write updated data back to file
    try:
        with open(chapters_file, 'w', encoding='utf-8') as f:
            json.dump(chapters_data, f, ensure_ascii=False, indent=2)
        print(f"✓ Successfully updated {chapters_file}")
        return True
    except Exception as e:
        print(f"Error writing file: {e}")
        return False

def main():
    """Main function to handle command line arguments"""
    if len(sys.argv) != 2:
        print("Usage: python update_chapters.py /path/to/directory")
        print("Example: python update_chapters.py ./bible_data")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    
    # Check if directory exists
    if not os.path.isdir(directory_path):
        print(f"Error: '{directory_path}' is not a valid directory!")
        sys.exit(1)
    
    success = process_directory(directory_path)
    
    if success:
        sys.exit(0)
    else:
        print("❌ Processing failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()