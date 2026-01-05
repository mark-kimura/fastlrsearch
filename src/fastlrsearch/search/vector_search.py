"""Vector search using SigLIP embeddings.

Supports both text queries (embedded) and reference image queries.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from fastlrsearch.config import settings
from fastlrsearch.indexing import get_qdrant_store
from fastlrsearch.ingestion import get_embedder, load_for_embedding


def search_by_text(
    query: str,
    limit: int | None = None,
    offset: int = 0,
    threshold: float | None = None,
) -> list[tuple[str, float]]:
    """Search photos by text query.

    Embeds the query text using SigLIP and searches vectors.

    Args:
        query: Text query (e.g., "sunset over ocean")
        limit: Max results (defaults to settings.search_k_vec)
        offset: Number of results to skip (for pagination)
        threshold: Minimum similarity (defaults to settings.default_threshold)

    Returns:
        List of (photo_id, score) tuples, sorted by score descending
    """
    embedder = get_embedder()
    query_vector = embedder.embed_text(query)

    store = get_qdrant_store()
    return store.search(query_vector.tolist(), limit=limit, offset=offset, threshold=threshold)


def search_by_image(
    image: Image.Image | Path | str,
    limit: int | None = None,
    offset: int = 0,
    threshold: float | None = None,
) -> list[tuple[str, float]]:
    """Search photos by reference image.

    Args:
        image: PIL Image, or path to image file
        limit: Max results (defaults to settings.search_k_vec)
        offset: Number of results to skip (for pagination)
        threshold: Minimum similarity (defaults to settings.default_threshold)

    Returns:
        List of (photo_id, score) tuples, sorted by score descending
    """
    # Load image if path provided
    img: Image.Image
    if isinstance(image, (str, Path)):
        loaded = load_for_embedding(Path(image))
        if loaded is None:
            return []
        img = loaded
    else:
        img = image

    embedder = get_embedder()
    query_vector = embedder.embed_image(img)

    store = get_qdrant_store()
    return store.search(query_vector.tolist(), limit=limit, offset=offset, threshold=threshold)


def search_by_vector(
    vector: np.ndarray | list[float],
    limit: int | None = None,
    offset: int = 0,
    threshold: float | None = None,
) -> list[tuple[str, float]]:
    """Search photos by raw embedding vector.

    Args:
        vector: Query embedding vector
        limit: Max results
        offset: Number of results to skip (for pagination)
        threshold: Minimum similarity

    Returns:
        List of (photo_id, score) tuples
    """
    store = get_qdrant_store()
    vec_list = vector.tolist() if isinstance(vector, np.ndarray) else vector
    return store.search(vec_list, limit=limit, offset=offset, threshold=threshold)


def search_by_photo_id(
    photo_id: str,
    limit: int | None = None,
    offset: int = 0,
    threshold: float | None = None,
) -> list[tuple[str, float]]:
    """Search for similar photos using an existing photo's vector.

    Fast path: retrieves pre-computed vector from Qdrant instead of re-embedding.
    Use this when the photo is already indexed.

    Args:
        photo_id: ID of the indexed photo to find similar images for
        limit: Max results
        offset: Number of results to skip (for pagination)
        threshold: Minimum similarity

    Returns:
        List of (photo_id, score) tuples, or empty list if photo not found
    """
    store = get_qdrant_store()
    vector = store.get_vector(photo_id)
    if vector is None:
        return []
    return store.search(vector, limit=limit, offset=offset, threshold=threshold)
