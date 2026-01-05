"""Text search using SQLite FTS5 with BM25 ranking.

Searches over AI-generated captions and tags.
"""

from fastlrsearch.config import settings
from fastlrsearch.indexing import get_sqlite_store


def search_text(
    query: str,
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """Search photos by text using BM25.

    Searches the FTS5 index of captions and tags.

    Args:
        query: Text query (supports FTS5 syntax)
        limit: Max results (defaults to settings.search_k_text)

    Returns:
        List of (photo_id, bm25_score) tuples, sorted by score descending
    """
    store = get_sqlite_store()
    return store.search_text(query, limit=limit)


def normalize_query(query: str) -> str:
    """Normalize query for FTS5.

    Escapes special characters and handles common patterns.

    Args:
        query: Raw user query

    Returns:
        FTS5-safe query string
    """
    import re

    # Strip punctuation that users might include but FTS5 can't handle
    cleaned = re.sub(r'[,;:!?]+', ' ', query)

    # Split into words and filter empty strings
    words = cleaned.strip().split()
    words = [w for w in words if w.strip()]

    if not words:
        return ""

    # If query looks like natural language, use implicit AND
    # FTS5 uses implicit OR by default, but AND is usually what users want
    if len(words) > 1 and not any(w in ["OR", "AND", "NOT"] for w in words):
        # Escape any special characters in words
        escaped = [_escape_fts_word(w) for w in words]
        return " ".join(escaped)

    # Single word - still escape it
    return _escape_fts_word(words[0]) if len(words) == 1 else query


def _escape_fts_word(word: str) -> str:
    """Escape special FTS5 characters in a word."""
    # FTS5 special chars that need quoting: " ' ( ) * - + , : ^
    special_chars = ['"', "'", "(", ")", "*", "-", "+", ",", ":", "^", "."]
    if any(c in word for c in special_chars):
        # Escape internal double quotes by doubling them
        escaped = word.replace('"', '""')
        return f'"{escaped}"'
    return word
