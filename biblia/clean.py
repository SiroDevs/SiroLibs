#!/usr/bin/env python3
"""
Script to recursively process JSON files in a directory and its subdirectories:
1. Ensures all JSON files are properly indented (pretty-printed)
2. Removes any "bibleId" field from all JSON objects regardless of its value
"""

import json
import os
from pathlib import Path
from typing import Any


def remove_bible_id(data: Any) -> Any:
    """
    Recursively remove all 'bibleId' keys from a JSON structure.
    """
    if isinstance(data, dict):
        # Remove 'bibleId' key (case-insensitive) and process nested structures
        return {
            key: remove_bible_id(value)
            for key, value in data.items()
            if key.lower() != "bibleid"
        }
    elif isinstance(data, list):
        # Process each item in the list
        return [remove_bible_id(item) for item in data]
    else:
        return data


def process_json_file(file_path: Path, indent: int = 2) -> bool:
    """
    Process a single JSON file: format and remove bibleId fields.
    """
    try:
        # Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Remove all bibleId fields
        modified_data = remove_bible_id(data)
        
        # Write back with proper indentation
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(modified_data, f, indent=indent, ensure_ascii=False)
            f.write('\n')
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON decode error in {file_path}: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error processing {file_path}: {e}")
        return False


def main():
    """
    Main function - recursively process all JSON files in the specified directory.
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Recursively process JSON files in a directory and all subdirectories'
    )
    parser.add_argument(
        'directory',
        type=str,
        default='.',
        nargs='?',
        help='Root directory to process (default: current directory)'
    )
    parser.add_argument(
        '--indent',
        type=int,
        default=2,
        help='Number of spaces for JSON indentation (default: 2)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be processed without modifying files'
    )
    
    args = parser.parse_args()
    
    # Get the directory to process
    root_dir = Path(args.directory)
    
    if not root_dir.exists():
        print(f"❌ Directory does not exist: {root_dir}")
        return
    
    if not root_dir.is_dir():
        print(f"❌ Path is not a directory: {root_dir}")
        return
    
    # Recursively find ALL JSON files in directory and subdirectories
    print(f"🔍 Searching for JSON files in: {root_dir}")
    print("   (including all subdirectories)")
    
    json_files = list(root_dir.rglob('*.json'))
    
    if not json_files:
        print(f"📁 No JSON files found in {root_dir} or its subdirectories")
        return
    
    print(f"\n📁 Found {len(json_files)} JSON file(s)")
    
    # Show all files that will be processed
    if args.dry_run:
        print("\n🔍 DRY RUN - No files will be modified")
        print("Files that would be processed:")
        for file_path in sorted(json_files):
            # Show relative path from the root directory
            rel_path = file_path.relative_to(root_dir)
            print(f"  📄 {rel_path}")
        print(f"\n📋 Would process {len(json_files)} file(s)")
        return
    
    # Ask for confirmation
    print(f"\n⚠️  This will modify {len(json_files)} JSON file(s)")
    print("   - Format all JSON with proper indentation")
    print("   - Remove ALL 'bibleId' fields (regardless of value)")
    print(f"   - Process subdirectories recursively")
    
    response = input("\nContinue? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("❌ Operation cancelled")
        return
    
    # Process all files
    print("\n⏳ Processing files...")
    success_count = 0
    modified_count = 0
    
    for file_path in sorted(json_files):
        rel_path = file_path.relative_to(root_dir)
        print(f"\n  📄 {rel_path}")
        
        # Check if file has bibleId before processing
        has_bible_id = False
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            def check_for_bible_id(d):
                if isinstance(d, dict) and any(k.lower() == 'bibleid' for k in d):
                    return True
                if isinstance(d, dict):
                    return any(check_for_bible_id(v) for v in d.values())
                if isinstance(d, list):
                    return any(check_for_bible_id(item) for item in d)
                return False
            
            has_bible_id = check_for_bible_id(data)
        except:
            pass
        
        if process_json_file(file_path, args.indent):
            success_count += 1
            if has_bible_id:
                modified_count += 1
                print(f"    ✅ Removed 'bibleId' fields and formatted")
            else:
                print(f"    ✅ Formatted (no 'bibleId' fields found)")
        else:
            print(f"    ❌ Failed to process")
    
    # Summary
    print(f"\n{'='*50}")
    print(f"✅ SUCCESS: Processed {success_count}/{len(json_files)} files")
    print(f"📝 Modified {modified_count} files (removed 'bibleId' fields)")
    
    if success_count < len(json_files):
        failed = len(json_files) - success_count
        print(f"⚠️  {failed} file(s) failed to process")


if __name__ == "__main__":
    main()