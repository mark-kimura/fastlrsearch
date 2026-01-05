"""Hybrid search combining vector and BM25 with RRF fusion.

Uses Reciprocal Rank Fusion to combine results from:
- Vector search (SigLIP embeddings)
- BM25 text search (captions/tags)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

from fastlrsearch.config import settings
from fastlrsearch.indexing import PhotoRecord, get_sqlite_store
from fastlrsearch.search.text_search import normalize_query, search_text
from fastlrsearch.search.vector_search import search_by_image, search_by_text


@dataclass
class SearchResult:
    """A single search result with metadata."""

    photo_id: str
    score: float
    path: str | None = None
    caption: str | None = None
    tags: str | None = None

    # Breakdown of scores (for debugging/UI)
    vector_score: float | None = None
    vector_rank: int | None = None
    text_score: float | None = None
    text_rank: int | None = None


def rrf_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int | None = None,
) -> list[tuple[str, float]]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank_i)) for each list where item appears.

    Args:
        ranked_lists: List of ranked results, each as [(id, score), ...]
        k: RRF constant (defaults to settings.rrf_k)

    Returns:
        Combined ranked list [(id, rrf_score), ...]
    """
    k = k or settings.rrf_k
    scores: dict[str, float] = {}

    for ranked_list in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked_list, start=1):
            if item_id not in scores:
                scores[item_id] = 0.0
            scores[item_id] += 1.0 / (k + rank)

    # Sort by RRF score descending
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_search(
    query: str,
    limit: int | None = None,
    offset: int = 0,
    k_vec: int | None = None,
    k_text: int | None = None,
    threshold: float | None = None,
    mode: Literal["hybrid", "vector", "text"] = "hybrid",
) -> list[SearchResult]:
    """Perform hybrid search combining vector and text search.

    Args:
        query: Search query
        limit: Max final results (defaults to settings.default_results)
        offset: Number of results to skip (for pagination)
        k_vec: Results to retrieve from vector search
        k_text: Results to retrieve from text search
        threshold: Minimum vector similarity
        mode: Search mode - "hybrid", "vector", or "text"

    Returns:
        List of SearchResult with metadata
    """
    limit = limit or settings.default_results
    # Ensure k_vec is at least as large as limit (so we have enough candidates)
    k_vec = max(k_vec or settings.search_k_vec, limit)
    k_text = k_text or settings.search_k_text

    # Collect results from each source
    vector_results: list[tuple[str, float]] = []
    text_results: list[tuple[str, float]] = []

    if mode in ("hybrid", "vector"):
        vector_results = search_by_text(query, limit=k_vec, offset=offset, threshold=threshold)

    if mode in ("hybrid", "text"):
        normalized_query = normalize_query(query)
        text_results = search_text(normalized_query, limit=k_text)

    # Build score maps for breakdown
    vector_scores = {pid: (score, rank + 1) for rank, (pid, score) in enumerate(vector_results)}
    text_scores = {pid: (score, rank + 1) for rank, (pid, score) in enumerate(text_results)}

    # Fuse results
    if mode == "hybrid":
        fused = rrf_fusion([vector_results, text_results])
    elif mode == "vector":
        fused = vector_results
    else:  # text
        fused = text_results

    # Get top N
    top_ids = [pid for pid, _ in fused[:limit]]

    # Fetch metadata from SQLite
    store = get_sqlite_store()
    results = []

    for pid, score in fused[:limit]:
        record = store.get_photo(pid)

        vec_info = vector_scores.get(pid)
        text_info = text_scores.get(pid)

        results.append(
            SearchResult(
                photo_id=pid,
                score=score,
                path=record.path if record else None,
                caption=record.caption if record else None,
                tags=record.tags if record else None,
                vector_score=vec_info[0] if vec_info else None,
                vector_rank=vec_info[1] if vec_info else None,
                text_score=text_info[0] if text_info else None,
                text_rank=text_info[1] if text_info else None,
            )
        )

    return results


def image_search(
    image: Image.Image | Path | str,
    query: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    threshold: float | None = None,
) -> list[SearchResult]:
    """Search by reference image, optionally combined with text.

    Args:
        image: Reference image (PIL Image or path)
        query: Optional text query to combine with image search
        limit: Max results
        offset: Number of results to skip (for pagination)
        threshold: Minimum similarity

    Returns:
        List of SearchResult
    """
    limit = limit or settings.default_results

    # Get image search results (fetch at least as many as requested)
    k_vec = max(settings.search_k_vec, limit)
    image_results = search_by_image(image, limit=k_vec, offset=offset, threshold=threshold)

    # If no text query, just return image results
    if not query:
        store = get_sqlite_store()
        results = []

        for pid, score in image_results[:limit]:
            record = store.get_photo(pid)
            results.append(
                SearchResult(
                    photo_id=pid,
                    score=score,
                    path=record.path if record else None,
                    caption=record.caption if record else None,
                    tags=record.tags if record else None,
                    vector_score=score,
                    vector_rank=image_results.index((pid, score)) + 1,
                )
            )

        return results

    # Combine with text search using RRF
    text_results = search_text(normalize_query(query), limit=settings.search_k_text)

    fused = rrf_fusion([image_results, text_results])

    # Build score maps
    image_scores = {pid: (score, rank + 1) for rank, (pid, score) in enumerate(image_results)}
    text_scores = {pid: (score, rank + 1) for rank, (pid, score) in enumerate(text_results)}

    store = get_sqlite_store()
    results = []

    for pid, score in fused[:limit]:
        record = store.get_photo(pid)

        img_info = image_scores.get(pid)
        text_info = text_scores.get(pid)

        results.append(
            SearchResult(
                photo_id=pid,
                score=score,
                path=record.path if record else None,
                caption=record.caption if record else None,
                tags=record.tags if record else None,
                vector_score=img_info[0] if img_info else None,
                vector_rank=img_info[1] if img_info else None,
                text_score=text_info[0] if text_info else None,
                text_rank=text_info[1] if text_info else None,
            )
        )

    return results
