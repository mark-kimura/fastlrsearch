"""API routes for FastLRSearch.

Endpoints:
- GET /health - Health check
- GET /search - Text search
- POST /search/image - Reference image search
- GET /photo/{photo_id} - Get photo details
"""

import io
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from PIL import Image
from pydantic import BaseModel

from fastlrsearch.config import settings
from fastlrsearch.indexing import get_sqlite_store, get_thumbnail_cache
from fastlrsearch.search import SearchResult, hybrid_search, image_search

router = APIRouter()


def _build_absolute_path(relative_path: str) -> str:
    """Build absolute path, using api_photo_root override if configured."""
    if settings.api_photo_root:
        # Join with forward slashes, then convert to backslash if Windows path
        base = settings.api_photo_root.rstrip("/\\")
        abs_path = f"{base}/{relative_path}"
        if "\\" in base:  # Windows-style path
            abs_path = abs_path.replace("/", "\\")
        return abs_path
    else:
        return str(settings.photo_root / relative_path)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"


class SearchResultItem(BaseModel):
    """API search result item."""

    photo_id: str
    score: float
    path: str | None = None
    absolute_path: str | None = None
    caption: str | None = None
    tags: str | None = None
    thumbnail_url: str | None = None

    @classmethod
    def from_result(cls, result: SearchResult) -> "SearchResultItem":
        """Create from SearchResult."""
        abs_path = None
        if result.path:
            abs_path = _build_absolute_path(result.path)

        thumb_url = None
        cache = get_thumbnail_cache()
        if cache.exists(result.photo_id):
            thumb_url = f"/thumbnail/{result.photo_id}"

        return cls(
            photo_id=result.photo_id,
            score=result.score,
            path=result.path,
            absolute_path=abs_path,
            caption=result.caption,
            tags=result.tags,
            thumbnail_url=thumb_url,
        )


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    total: int
    results: list[SearchResultItem]


class PhotoResponse(BaseModel):
    """Photo details response."""

    photo_id: str
    path: str
    absolute_path: str
    caption: str | None = None
    tags: str | None = None
    thumbnail_url: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint (no auth required)."""
    return HealthResponse()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    threshold: float = Query(0.0, ge=0.0, le=1.0, description="Min similarity"),
    mode: Literal["hybrid", "vector", "text"] = Query(
        "hybrid", description="Search mode"
    ),
):
    """Search photos by text query.

    Supports hybrid search (vector + BM25), vector-only, or text-only modes.
    """
    results = hybrid_search(
        query=q,
        limit=limit,
        threshold=threshold,
        mode=mode,
    )

    return SearchResponse(
        query=q,
        total=len(results),
        results=[SearchResultItem.from_result(r) for r in results],
    )


@router.post("/search/image", response_model=SearchResponse)
async def search_by_image(
    file: UploadFile = File(..., description="Reference image"),
    q: str | None = Query(None, description="Optional text query to combine"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    threshold: float = Query(0.0, ge=0.0, le=1.0, description="Min similarity"),
):
    """Search photos by reference image.

    Optionally combine with text query using RRF fusion.
    """
    # Read and validate image
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        image = image.convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    results = image_search(
        image=image,
        query=q,
        limit=limit,
        threshold=threshold,
    )

    return SearchResponse(
        query=q or "(image)",
        total=len(results),
        results=[SearchResultItem.from_result(r) for r in results],
    )


@router.get("/search/similar", response_model=SearchResponse)
async def search_similar_by_path(
    path: str = Query(..., description="Relative path to reference image (relative to photo_root)"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    threshold: float = Query(0.0, ge=0.0, le=1.0, description="Min similarity"),
):
    """Search for similar photos by file path.

    Accepts relative paths for cross-platform compatibility.
    Path is relative to the server's configured photo_root.

    Uses fast path (pre-computed vector) for indexed photos,
    falls back to slow path (re-embed) for unindexed photos.
    """
    from fastlrsearch.search import SearchResult
    from fastlrsearch.search.vector_search import search_by_photo_id

    image_path = settings.photo_root / path

    if not image_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {image_path} (relative path: {path})"
        )

    # FAST PATH: Try to use pre-computed vector if photo is indexed
    store = get_sqlite_store()
    record = store.get_photo_by_path(path)

    if record:
        raw_results = search_by_photo_id(
            record.photo_id,
            limit=limit,
            threshold=threshold,
        )
        if raw_results:
            # Convert raw results to SearchResult objects with metadata
            results = []
            for pid, score in raw_results[:limit]:
                meta = store.get_photo(pid)
                results.append(
                    SearchResult(
                        photo_id=pid,
                        score=score,
                        path=meta.path if meta else None,
                        caption=meta.caption if meta else None,
                        tags=meta.tags if meta else None,
                        vector_score=score,
                    )
                )

            return SearchResponse(
                query=f"(similar to: {image_path.name})",
                total=len(results),
                results=[SearchResultItem.from_result(r) for r in results],
            )

    # SLOW PATH: Fall back to loading image and computing embedding
    try:
        image = Image.open(image_path)
        image = image.convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot open image: {e}")

    results = image_search(
        image=image,
        query=None,
        limit=limit,
        threshold=threshold,
    )

    return SearchResponse(
        query=f"(similar to: {image_path.name})",
        total=len(results),
        results=[SearchResultItem.from_result(r) for r in results],
    )


@router.get("/photo/{photo_id}", response_model=PhotoResponse)
async def get_photo(photo_id: str):
    """Get photo details by ID."""
    store = get_sqlite_store()
    record = store.get_photo(photo_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    abs_path = _build_absolute_path(record.path)

    thumb_url = None
    cache = get_thumbnail_cache()
    if cache.exists(photo_id):
        thumb_url = f"/thumbnail/{photo_id}"

    return PhotoResponse(
        photo_id=record.photo_id,
        path=record.path,
        absolute_path=abs_path,
        caption=record.caption,
        tags=record.tags,
        thumbnail_url=thumb_url,
    )


@router.get("/thumbnail/{photo_id}")
async def get_thumbnail(photo_id: str):
    """Get thumbnail image for a photo."""
    from fastapi.responses import FileResponse

    cache = get_thumbnail_cache()
    thumb_path = cache.get(photo_id)

    if thumb_path is None:
        # Try to generate on demand
        store = get_sqlite_store()
        record = store.get_photo(photo_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Photo not found")

        source_path = settings.photo_root / record.path
        thumb_path = cache.generate(photo_id, source_path)

        if thumb_path is None:
            raise HTTPException(status_code=404, detail="Thumbnail not available")

    return FileResponse(
        thumb_path,
        media_type="image/webp",
        filename=f"{photo_id}.webp",
    )


@router.get("/stats")
async def get_stats():
    """Get index statistics."""
    from fastlrsearch.indexing import get_qdrant_store

    sqlite = get_sqlite_store()
    qdrant = get_qdrant_store()
    thumbs = get_thumbnail_cache()

    return {
        "photos_total": sqlite.count(),
        "photos_captioned": sqlite.count_captioned(),
        "vectors_indexed": qdrant.count(),
        "thumbnails_cached": thumbs.count(),
        "thumbnail_cache_bytes": thumbs.size_bytes(),
    }
