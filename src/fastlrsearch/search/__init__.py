"""Search engine with hybrid vector + text search.

Public API:
- hybrid_search: Combined vector + BM25 search with RRF fusion
- image_search: Reference image search
- search_by_text: Vector-only text search
- search_by_image: Vector-only image search
- search_text: BM25-only text search
"""

from fastlrsearch.search.hybrid import (
    SearchResult,
    hybrid_search,
    image_search,
    rrf_fusion,
)
from fastlrsearch.search.text_search import normalize_query, search_text
from fastlrsearch.search.vector_search import (
    search_by_image,
    search_by_text,
    search_by_vector,
)

__all__ = [
    # Hybrid search
    "hybrid_search",
    "image_search",
    "SearchResult",
    "rrf_fusion",
    # Vector search
    "search_by_text",
    "search_by_image",
    "search_by_vector",
    # Text search
    "search_text",
    "normalize_query",
]
