"""Thumbnail cache management.

Handles thumbnail generation, storage, and retrieval.
"""

from pathlib import Path

from PIL import Image

from fastlrsearch.config import settings
from fastlrsearch.ingestion.image_loader import load_for_thumbnail


class ThumbnailCache:
    """Cache for photo thumbnails.

    Thumbnails are stored as WebP files for size/quality balance.
    """

    def __init__(self, cache_dir: Path | None = None):
        """Initialize thumbnail cache.

        Args:
            cache_dir: Directory for thumbnails (defaults to settings)
        """
        self.cache_dir = cache_dir or settings.thumbnails_dir

    def ensure_dir(self):
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, photo_id: str) -> Path:
        """Get path to thumbnail file.

        Args:
            photo_id: Photo identifier

        Returns:
            Path to thumbnail (may not exist)
        """
        return self.cache_dir / f"{photo_id}.webp"

    def exists(self, photo_id: str) -> bool:
        """Check if thumbnail exists.

        Args:
            photo_id: Photo identifier

        Returns:
            True if thumbnail exists
        """
        return self.get_path(photo_id).exists()

    def get(self, photo_id: str) -> Path | None:
        """Get thumbnail path if it exists.

        Args:
            photo_id: Photo identifier

        Returns:
            Path to thumbnail or None if not cached
        """
        path = self.get_path(photo_id)
        return path if path.exists() else None

    def generate(
        self,
        photo_id: str,
        source_path: Path,
        force: bool = False,
    ) -> Path | None:
        """Generate thumbnail for a photo.

        Args:
            photo_id: Photo identifier
            source_path: Path to source image
            force: Regenerate even if cached

        Returns:
            Path to thumbnail or None on error
        """
        thumb_path = self.get_path(photo_id)

        if thumb_path.exists() and not force:
            return thumb_path

        self.ensure_dir()

        try:
            img = load_for_thumbnail(source_path)
            if img is None:
                return None

            img.save(thumb_path, "WEBP", quality=85)
            return thumb_path

        except Exception as e:
            print(f"Warning: Thumbnail generation failed for {photo_id}: {e}")
            return None

    def delete(self, photo_id: str):
        """Delete a cached thumbnail.

        Args:
            photo_id: Photo identifier
        """
        path = self.get_path(photo_id)
        if path.exists():
            path.unlink()

    def clear(self):
        """Delete all cached thumbnails."""
        if self.cache_dir.exists():
            for path in self.cache_dir.glob("*.webp"):
                path.unlink()

    def get_or_generate(
        self,
        photo_id: str,
        source_path: Path,
    ) -> Path | None:
        """Get thumbnail, generating if needed.

        Args:
            photo_id: Photo identifier
            source_path: Path to source image

        Returns:
            Path to thumbnail or None on error
        """
        existing = self.get(photo_id)
        if existing:
            return existing
        return self.generate(photo_id, source_path)

    def count(self) -> int:
        """Get number of cached thumbnails."""
        if not self.cache_dir.exists():
            return 0
        return len(list(self.cache_dir.glob("*.webp")))

    def size_bytes(self) -> int:
        """Get total size of cache in bytes."""
        if not self.cache_dir.exists():
            return 0
        return sum(p.stat().st_size for p in self.cache_dir.glob("*.webp"))


# Global singleton
_cache: ThumbnailCache | None = None


def get_thumbnail_cache() -> ThumbnailCache:
    """Get global thumbnail cache instance."""
    global _cache
    if _cache is None:
        _cache = ThumbnailCache()
    return _cache
