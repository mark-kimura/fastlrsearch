"""File scanner for photo discovery and change detection.

Walks directories to find photos, computes stable IDs, and tracks changes.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import xxhash

from fastlrsearch.config import settings


@dataclass
class ScannedFile:
    """Metadata for a scanned file."""

    path: Path  # Absolute path
    relative_path: str  # Relative to photo_root (for portability)
    size: int  # File size in bytes
    mtime: float  # Modification time
    photo_id: str  # Stable ID based on path + size + mtime
    extension: str  # Lowercase extension including dot


def compute_photo_id(relative_path: str, size: int, mtime: float) -> str:
    """Compute stable ID for a photo.

    Uses xxhash for speed. ID changes if file is modified.
    """
    h = xxhash.xxh64()
    h.update(relative_path.encode("utf-8"))
    h.update(str(size).encode("utf-8"))
    h.update(str(mtime).encode("utf-8"))
    return h.hexdigest()


def is_supported_extension(path: Path) -> bool:
    """Check if file extension is supported."""
    return path.suffix.lower() in settings.supported_extensions


def has_raw_counterpart(filepath: Path) -> bool:
    """Check if a RAW file with same base name exists in the same folder.

    Used to skip JPEGs when RAW+JPEG pairs exist.
    """
    stem = filepath.stem
    parent = filepath.parent
    for raw_ext in settings.raw_extensions:
        # Check both lowercase and uppercase versions
        if (parent / f"{stem}{raw_ext}").exists():
            return True
        if (parent / f"{stem}{raw_ext.upper()}").exists():
            return True
    return False


def should_skip_for_raw(filepath: Path) -> bool:
    """Check if this file should be skipped because a RAW counterpart exists."""
    if not settings.skip_jpeg_if_raw_exists:
        return False

    ext = filepath.suffix.lower()
    # Only skip non-RAW image files (JPEG, PNG, WebP)
    if ext in settings.raw_extensions:
        return False
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        return has_raw_counterpart(filepath)
    return False


def scan_directory(
    root: Path | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> Iterator[ScannedFile]:
    """Scan directory for supported image files.

    Args:
        root: Directory to scan (defaults to settings.photo_root)
        progress_callback: Optional callback(current_count) for progress updates

    Yields:
        ScannedFile for each discovered image
    """
    if root is None:
        root = settings.photo_root

    root = Path(root).resolve()
    count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden directories and our data directory
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d != ".fastlrsearch"
        ]

        for filename in filenames:
            if filename.startswith("."):
                continue

            filepath = Path(dirpath) / filename

            if not is_supported_extension(filepath):
                continue

            # Skip JPEG/PNG if RAW counterpart exists (configurable)
            if should_skip_for_raw(filepath):
                continue

            try:
                stat = filepath.stat()
                relative_path = filepath.relative_to(root).as_posix()

                yield ScannedFile(
                    path=filepath,
                    relative_path=relative_path,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    photo_id=compute_photo_id(relative_path, stat.st_size, stat.st_mtime),
                    extension=filepath.suffix.lower(),
                )

                count += 1
                if progress_callback and count % 1000 == 0:
                    progress_callback(count)

            except (OSError, PermissionError) as e:
                # Skip files we can't access
                print(f"Warning: Cannot access {filepath}: {e}")
                continue


def scan_single_file(filepath: Path, root: Path | None = None) -> ScannedFile | None:
    """Scan a single file and return its metadata.

    Args:
        filepath: Path to the file
        root: Photo root for computing relative path

    Returns:
        ScannedFile or None if file is not supported/accessible
    """
    if root is None:
        root = settings.photo_root

    root = Path(root).resolve()
    filepath = Path(filepath).resolve()

    if not is_supported_extension(filepath):
        return None

    # Skip JPEG/PNG if RAW counterpart exists (configurable)
    if should_skip_for_raw(filepath):
        return None

    try:
        stat = filepath.stat()
        relative_path = filepath.relative_to(root).as_posix()

        return ScannedFile(
            path=filepath,
            relative_path=relative_path,
            size=stat.st_size,
            mtime=stat.st_mtime,
            photo_id=compute_photo_id(relative_path, stat.st_size, stat.st_mtime),
            extension=filepath.suffix.lower(),
        )
    except (OSError, PermissionError, ValueError):
        return None
