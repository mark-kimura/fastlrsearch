"""SQLite metadata storage with FTS5 text search.

Stores photo metadata and provides BM25 text search over captions/tags.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from fastlrsearch.config import settings


@dataclass
class PhotoRecord:
    """Photo metadata record."""

    photo_id: str
    path: str  # Relative to photo_root
    mtime: float | None = None
    caption: str | None = None
    tags: str | None = None
    phash: str | None = None
    embedded_at: float | None = None
    captioned_at: float | None = None


class SQLiteStore:
    """SQLite store for photo metadata and FTS5 text search."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS photos (
        photo_id TEXT PRIMARY KEY,
        path TEXT NOT NULL,
        mtime REAL,
        caption TEXT,
        tags TEXT,
        phash TEXT,
        embedded_at REAL,
        captioned_at REAL
    );

    CREATE INDEX IF NOT EXISTS idx_photos_path ON photos(path);
    CREATE INDEX IF NOT EXISTS idx_photos_phash ON photos(phash);

    CREATE VIRTUAL TABLE IF NOT EXISTS photo_fts USING fts5(
        photo_id,
        text,
        tokenize='porter unicode61'
    );

    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """

    def __init__(self, db_path: Path | None = None):
        """Initialize SQLite store.

        Args:
            db_path: Database file path (defaults to settings)
        """
        self.db_path = db_path or settings.sqlite_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = self._create_connection()
        return self._conn

    def _create_connection(self) -> sqlite3.Connection:
        """Create database connection and initialize schema."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")

        # Initialize schema
        conn.executescript(self.SCHEMA)
        conn.commit()

        return conn

    def close(self):
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def upsert_photo(self, record: PhotoRecord):
        """Insert or update a photo record.

        Args:
            record: Photo metadata
        """
        self.upsert_photos([record])

    def upsert_photos(self, records: Sequence[PhotoRecord]):
        """Insert or update multiple photo records.

        Args:
            records: List of photo metadata records
        """
        if not records:
            return

        with self.transaction():
            # Upsert main records
            self.conn.executemany(
                """
                INSERT INTO photos (photo_id, path, mtime, caption, tags, phash, embedded_at, captioned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(photo_id) DO UPDATE SET
                    path = excluded.path,
                    mtime = excluded.mtime,
                    caption = COALESCE(excluded.caption, photos.caption),
                    tags = COALESCE(excluded.tags, photos.tags),
                    phash = COALESCE(excluded.phash, photos.phash),
                    embedded_at = COALESCE(excluded.embedded_at, photos.embedded_at),
                    captioned_at = COALESCE(excluded.captioned_at, photos.captioned_at)
                """,
                [
                    (
                        r.photo_id,
                        r.path,
                        r.mtime,
                        r.caption,
                        r.tags,
                        r.phash,
                        r.embedded_at,
                        r.captioned_at,
                    )
                    for r in records
                ],
            )

            # Update FTS index for records with captions or tags
            for r in records:
                if r.caption or r.tags:
                    text = " ".join(filter(None, [r.caption, r.tags]))
                    # Delete existing FTS entry
                    self.conn.execute(
                        "DELETE FROM photo_fts WHERE photo_id = ?",
                        (r.photo_id,),
                    )
                    # Insert new FTS entry
                    self.conn.execute(
                        "INSERT INTO photo_fts (photo_id, text) VALUES (?, ?)",
                        (r.photo_id, text),
                    )

    def get_photo(self, photo_id: str) -> PhotoRecord | None:
        """Get a photo record by ID.

        Args:
            photo_id: Photo identifier

        Returns:
            PhotoRecord or None if not found
        """
        row = self.conn.execute(
            "SELECT * FROM photos WHERE photo_id = ?",
            (photo_id,),
        ).fetchone()

        if row is None:
            return None

        return PhotoRecord(**dict(row))

    def get_photo_by_path(self, path: str) -> PhotoRecord | None:
        """Get a photo record by relative path.

        Args:
            path: Relative path

        Returns:
            PhotoRecord or None if not found
        """
        row = self.conn.execute(
            "SELECT * FROM photos WHERE path = ?",
            (path,),
        ).fetchone()

        if row is None:
            return None

        return PhotoRecord(**dict(row))

    def delete_photo(self, photo_id: str):
        """Delete a photo record.

        Args:
            photo_id: Photo identifier
        """
        with self.transaction():
            self.conn.execute(
                "DELETE FROM photos WHERE photo_id = ?",
                (photo_id,),
            )
            self.conn.execute(
                "DELETE FROM photo_fts WHERE photo_id = ?",
                (photo_id,),
            )

    def search_text(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[tuple[str, float]]:
        """Search photos by text using BM25.

        Args:
            query: Search query
            limit: Max results (defaults to settings.search_k_text)

        Returns:
            List of (photo_id, bm25_score) tuples
        """
        limit = limit or settings.search_k_text

        # FTS5 BM25 search
        # Note: BM25 returns negative scores (lower = better match)
        # We negate to get positive scores (higher = better)
        rows = self.conn.execute(
            """
            SELECT photo_id, -bm25(photo_fts) as score
            FROM photo_fts
            WHERE photo_fts MATCH ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

        return [(row["photo_id"], row["score"]) for row in rows]

    def get_all_ids(self) -> set[str]:
        """Get all photo_ids in the database.

        Useful for incremental ingestion.
        """
        rows = self.conn.execute("SELECT photo_id FROM photos").fetchall()
        return {row["photo_id"] for row in rows}

    def get_all_paths(self) -> set[str]:
        """Get all file paths in the database.

        Useful for incremental ingestion to avoid duplicates.
        """
        rows = self.conn.execute("SELECT path FROM photos").fetchall()
        return {row["path"] for row in rows}

    def get_path_to_id_map(self) -> dict[str, str]:
        """Get mapping from path to photo_id.

        Useful for detecting when a file needs re-indexing.
        """
        rows = self.conn.execute("SELECT path, photo_id FROM photos").fetchall()
        return {row["path"]: row["photo_id"] for row in rows}

    def get_uncaptioned_ids(self, limit: int | None = None) -> list[str]:
        """Get photo_ids that don't have captions yet.

        Args:
            limit: Max results

        Returns:
            List of photo_ids
        """
        query = "SELECT photo_id FROM photos WHERE caption IS NULL"
        if limit:
            query += f" LIMIT {limit}"

        rows = self.conn.execute(query).fetchall()
        return [row["photo_id"] for row in rows]

    def count(self) -> int:
        """Get total number of photos."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM photos").fetchone()
        return row["cnt"]

    def count_captioned(self) -> int:
        """Get number of photos with captions."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM photos WHERE caption IS NOT NULL"
        ).fetchone()
        return row["cnt"]

    def get_config(self, key: str, default: str | None = None) -> str | None:
        """Get a config value.

        Args:
            key: Config key
            default: Default value if not found

        Returns:
            Config value or default
        """
        row = self.conn.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,),
        ).fetchone()

        return row["value"] if row else default

    def set_config(self, key: str, value: str):
        """Set a config value.

        Args:
            key: Config key
            value: Config value
        """
        with self.transaction():
            self.conn.execute(
                """
                INSERT INTO config (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def find_by_phash(
        self,
        phash: str,
        threshold: int = 10,
    ) -> list[PhotoRecord]:
        """Find photos with similar pHash.

        Note: This is a simple implementation that loads all hashes.
        For large datasets, consider a more efficient approach.

        Args:
            phash: Target pHash
            threshold: Max Hamming distance

        Returns:
            List of similar photos
        """
        # For now, just find exact matches
        # Full Hamming distance search would need specialized index
        rows = self.conn.execute(
            "SELECT * FROM photos WHERE phash = ?",
            (phash,),
        ).fetchall()

        return [PhotoRecord(**dict(row)) for row in rows]

    def iter_all(self, batch_size: int = 1000) -> Iterator[PhotoRecord]:
        """Iterate over all photo records.

        Args:
            batch_size: Number of records per batch

        Yields:
            PhotoRecord for each photo
        """
        offset = 0
        while True:
            rows = self.conn.execute(
                "SELECT * FROM photos LIMIT ? OFFSET ?",
                (batch_size, offset),
            ).fetchall()

            if not rows:
                break

            for row in rows:
                yield PhotoRecord(**dict(row))

            offset += batch_size


# Global singleton
_store: SQLiteStore | None = None


def get_sqlite_store() -> SQLiteStore:
    """Get global SQLite store instance."""
    global _store
    if _store is None:
        _store = SQLiteStore()
    return _store


def close_sqlite_store():
    """Close global SQLite store."""
    global _store
    if _store is not None:
        _store.close()
        _store = None
