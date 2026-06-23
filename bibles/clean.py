#!/usr/bin/env python3
"""
Script to recursively process JSON files in a directory:
1. Ensures all JSON files are properly indented (pretty-printed)
2. Removes any "bibleId" field from all JSON objects regardless of its value
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Union


def remove_bible_id(data: Any) -> Any:
    """
    Recursively remove all 'bibleId' keys from a JSON structure.
    
    Args:
        data: JSON data (dict, list, or primitive)
    
    Returns:
        Modified data with all 'bibleId' keys removed
    """
    if isinstance(data, dict):
        # Create a new dict without 'bibleId' key
        return {
            key: remove_bible_id(value)
            for key, value in data.items()
            if key.lower() != "bibleid"  # Case-insensitive check
        }
    elif isinstance(data, list):
        # Process each item in the list
        return [remove_bible_id(item) for item in data]
    else:
        # Return primitive values as-is
        return data


def process_json_file(file_path: Path, indent: int = 2) -> bool:
    """
    Process a single JSON file:
    1. Read and parse the JSON
    2. Remove all 'bibleId' fields
    3. Write back with proper indentation
    
    Args:
        file_path: Path to the JSON file
        indent: Number of spaces for indentation
    
    Returns:
        True if successful, False otherwise
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
            # Add a newline at the end for good practice
            f.write('\n')
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON decode error in {file_path}: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Error processing {file_path}: {e}")
        return False


def find_json_files(root_dir: Path) -> List[Path]:
    """
    Recursively find all JSON files in a directory.
    
    Args:
        root_dir: Root directory to search
    
    Returns:
        List of Path objects for all JSON files found
    """
    json_files = []
    
    if not root_dir.exists():
        print(f"❌ Directory does not exist: {root_dir}")
        return json_files
    
    if not root_dir.is_dir():
        print(f"❌ Path is not a directory: {root_dir}")
        return json_files
    
    # Walk through the directory recursively
    for file_path in root_dir.rglob('*.json'):
        if file_path.is_file():
            json_files.append(file_path)
    
    return json_files


def process_directory(
    root_dir: Path, 
    indent: int = 2, 
    dry_run: bool = False
) -> None:
    """
    Process all JSON files in a directory recursively.
    
    Args:
        root_dir: Root directory to process
        indent: Number of spaces for JSON indentation
        dry_run: If True, only show what would be processed without modifying files
    """
    json_files = find_json_files(root_dir)
    
    if not json_files:
        print(f"📁 No JSON files found in {root_dir}")
        return
    
    print(f"📁 Found {len(json_files)} JSON file(s) in {root_dir}")
    
    if dry_run:
        print("🔍 DRY RUN - No files will be modified")
        for file_path in json_files:
            print(f"  📄 {file_path.relative_to(root_dir)}")
        
        # Show sample of what would be removed
        if json_files:
            sample_file = json_files[0]
            try:
                with open(sample_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                has_bible_id = False
                
                def check_bible_id(d):
                    if isinstance(d, dict) and any(k.lower() == 'bibleid' for k in d):
                        return True
                    if isinstance(d, dict):
                        return any(check_bible_id(v) for v in d.values())
                    if isinstance(d, list):
                        return any(check_bible_id(item) for item in d)
                    return False
                
                if check_bible_id(data):
                    print(f"\n📋 Sample: {sample_file.relative_to(root_dir)} contains 'bibleId' fields that would be removed")
            except:
                pass
        return
    
    # Process each file
    success_count = 0
    modified_count = 0
    
    for file_path in json_files:
        print(f"  📄 Processing: {file_path.relative_to(root_dir)}")
        
        # Check if file contains bibleId before processing (for reporting)
        has_bible_id = False
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            def check_bible_id(d):
                if isinstance(d, dict) and any(k.lower() == 'bibleid' for k in d):
                    return True
                if isinstance(d, dict):
                    return any(check_bible_id(v) for v in d.values())
                if isinstance(d, list):
                    return any(check_bible_id(item) for item in d)
                return False
            
            has_bible_id = check_bible_id(data)
        except:
            pass
        
        if process_json_file(file_path, indent):
            success_count += 1
            if has_bible_id:
                modified_count += 1
                print(f"    ✅ Removed 'bibleId' fields and formatted")
            else:
                print(f"    ✅ Formatted (no 'bibleId' fields found)")
        else:
            print(f"    ❌ Failed to process")
    
    print(f"\n✅ Processed {success_count}/{len(json_files)} files successfully")
    print(f"📝 Modified {modified_count} files (removed 'bibleId' fields)")


def main():
    """Main entry point with command-line argument parsing."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Recursively process JSON files: format with proper indentation and remove "bibleId" fields'
    )
    parser.add_argument(
        'directory',
        type=str,
        help='Root directory to process'
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
    parser.add_argument(
        '--no-recursive',
        action='store_true',
        help='Only process files in the immediate directory (not recursive)'
    )
    
    args = parser.parse_args()
    
    # Use current directory if no directory specified
    root_dir = Path(args.directory)
    
    if not args.dry_run:
        # Ask for confirmation before making changes
        print(f"⚠️  This will modify JSON files in: {root_dir}")
        print(f"   - Format all JSON files with {args.indent} spaces indentation")
        print("   - Remove ALL 'bibleId' fields (regardless of value)")
        
        if not args.no_recursive:
            print("   - Process subdirectories recursively")
        
        response = input("\nContinue? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Operation cancelled")
            return
    
    # Override rglob if no-recursive flag is set
    original_rglob = None
    if args.no_recursive:
        # We'll use a non-recursive approach
        def find_json_files_non_recursive(root_dir):
            json_files = []
            if root_dir.exists() and root_dir.is_dir():
                for file_path in root_dir.glob('*.json'):
                    if file_path.is_file():
                        json_files.append(file_path)
            return json_files
        
        # Monkey patch the find_json_files function for this run
        global find_json_files
        find_json_files = find_json_files_non_recursive
    
    process_directory(root_dir, args.indent, args.dry_run)


if __name__ == "__main__":
    main()