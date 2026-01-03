"""Ingestion pipeline for photo indexing.

Public API:
- run_ingestion: Run Stage 1 (embed, pHash, thumbnail)
- IngestionPipeline: Full control over ingestion process
- Embedder: Direct access to embedding model
- Captioner: Direct access to caption model
- scan_directory: File discovery
"""

from fastlrsearch.ingestion.captioner import Captioner, get_captioner, unload_captioner
from fastlrsearch.ingestion.dedup import are_similar, compute_phash, find_duplicates
from fastlrsearch.ingestion.embedder import Embedder, get_embedder, unload_embedder
from fastlrsearch.ingestion.image_loader import (
    load_for_embedding,
    load_for_thumbnail,
    load_image,
)
from fastlrsearch.ingestion.pipeline import (
    IngestionPipeline,
    IngestionStats,
    ProcessedPhoto,
    run_ingestion,
)
from fastlrsearch.ingestion.scanner import ScannedFile, scan_directory, scan_single_file

__all__ = [
    # Pipeline
    "run_ingestion",
    "IngestionPipeline",
    "ProcessedPhoto",
    "IngestionStats",
    # Scanner
    "scan_directory",
    "scan_single_file",
    "ScannedFile",
    # Image loading
    "load_image",
    "load_for_embedding",
    "load_for_thumbnail",
    # Embedder
    "Embedder",
    "get_embedder",
    "unload_embedder",
    # Captioner
    "Captioner",
    "get_captioner",
    "unload_captioner",
    # Dedup
    "compute_phash",
    "are_similar",
    "find_duplicates",
]
