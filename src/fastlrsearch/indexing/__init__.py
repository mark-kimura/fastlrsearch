"""Indexing layer for vector and metadata storage.

Public API:
- QdrantStore: Vector database operations
- SQLiteStore: Metadata and FTS5 text search
- ThumbnailCache: Thumbnail management
"""

from fastlrsearch.indexing.qdrant_store import (
    QdrantStore,
    close_qdrant_store,
    get_qdrant_store,
)
from fastlrsearch.indexing.sqlite_store import (
    PhotoRecord,
    SQLiteStore,
    close_sqlite_store,
    get_sqlite_store,
)
from fastlrsearch.indexing.thumbnail_cache import (
    ThumbnailCache,
    get_thumbnail_cache,
)

__all__ = [
    # Qdrant
    "QdrantStore",
    "get_qdrant_store",
    "close_qdrant_store",
    # SQLite
    "SQLiteStore",
    "PhotoRecord",
    "get_sqlite_store",
    "close_sqlite_store",
    # Thumbnails
    "ThumbnailCache",
    "get_thumbnail_cache",
]
