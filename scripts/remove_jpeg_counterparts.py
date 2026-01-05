#!/usr/bin/env python3
"""Remove JPEG files from index when RAW counterpart exists.

This script removes indexed JPEGs that have a same-name RAW file,
without requiring a full re-index.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastlrsearch.config import settings
from fastlrsearch.indexing.sqlite_store import SQLiteStore
from fastlrsearch.indexing.qdrant_store import QdrantStore


def find_jpeg_with_raw_counterparts(store: SQLiteStore) -> list[tuple[str, str]]:
    """Find all JPEGs that have a RAW counterpart on the filesystem.

    Checks the actual filesystem, not just the database, to catch
    RAW formats that weren't indexed (like CR3).

    Returns:
        List of (photo_id, path) tuples to remove
    """
    jpeg_extensions = {'.jpg', '.jpeg', '.png', '.webp'}

    # Get all indexed files
    all_photos = list(store.iter_all())

    # Find JPEGs that have a RAW counterpart on disk
    to_remove: list[tuple[str, str]] = []
    for photo in all_photos:
        rel_path = Path(photo.path)
        if rel_path.suffix.lower() in jpeg_extensions:
            # Check filesystem for RAW counterpart
            abs_path = settings.photo_root / rel_path
            if has_raw_on_disk(abs_path):
                to_remove.append((photo.photo_id, photo.path))

    return to_remove


def has_raw_on_disk(filepath: Path) -> bool:
    """Check if a RAW file with same base name exists on disk."""
    stem = filepath.stem
    parent = filepath.parent
    for raw_ext in settings.raw_extensions:
        # Check both lowercase and uppercase versions
        if (parent / f"{stem}{raw_ext}").exists():
            return True
        if (parent / f"{stem}{raw_ext.upper()}").exists():
            return True
    return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Remove JPEG counterparts from index")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    print("Scanning index for JPEG files with RAW counterparts...")

    # Use the actual database location
    db_path = settings.data_dir / "index.db"
    if not db_path.exists():
        db_path = settings.sqlite_path

    print(f"Database: {db_path}")

    sqlite_store = SQLiteStore(db_path)
    qdrant_store = QdrantStore()

    # Find JPEGs to remove
    to_remove = find_jpeg_with_raw_counterparts(sqlite_store)

    if not to_remove:
        print("No JPEG files with RAW counterparts found.")
        return

    print(f"\nFound {len(to_remove)} JPEG files with RAW counterparts:")

    # Show some examples
    for photo_id, path in to_remove[:10]:
        print(f"  - {path}")
    if len(to_remove) > 10:
        print(f"  ... and {len(to_remove) - 10} more")

    # Confirm
    if not args.yes:
        response = input(f"\nRemove {len(to_remove)} files from index? [y/N] ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    # Remove from both stores
    print("\nRemoving from index...")
    removed = 0
    for photo_id, path in to_remove:
        try:
            sqlite_store.delete_photo(photo_id)
            qdrant_store.delete(photo_id)
            removed += 1
            if removed % 100 == 0:
                print(f"  Removed {removed}/{len(to_remove)}...")
        except Exception as e:
            print(f"  Error removing {path}: {e}")

    print(f"\nDone! Removed {removed} JPEG files from index.")
    print(f"Index now contains {sqlite_store.count()} photos.")

    # Close connections
    sqlite_store.close()
    qdrant_store.close()


if __name__ == "__main__":
    main()
