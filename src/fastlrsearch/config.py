"""Configuration management for FastLRSearch.

All configurable values are defined here. No hardcoded values elsewhere.
Settings can be overridden via environment variables with FASTLRSEARCH_ prefix.
Settings are also loaded from ~/.config/fastlrsearch/settings.json if present.
"""

import json
from pathlib import Path
from typing import Any, Literal

import platformdirs
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _config_dir() -> Path:
    """Cross-platform config directory for fastlrsearch."""
    return Path(platformdirs.user_config_dir("fastlrsearch"))


def _load_json_settings() -> dict[str, Any]:
    """Load settings from JSON config file."""
    config_file = _config_dir() / "settings.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="FASTLRSEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    def __init__(self, **data):
        # Load JSON settings first, then override with env vars and explicit args
        json_settings = _load_json_settings()
        merged = {**json_settings, **data}
        super().__init__(**merged)

    # === Paths ===
    photo_root: Path = Field(
        default=Path.home() / "Pictures",
        description="Root directory containing photos to index",
    )
    data_dir_override: Path | None = Field(
        default=None,
        description="Custom data directory (if None, uses photo_root/.fastlrsearch)",
    )

    @property
    def data_dir(self) -> Path:
        """Data directory - custom path or within photo root for portability."""
        if self.data_dir_override:
            return self.data_dir_override
        return self.photo_root / ".fastlrsearch"

    @property
    def qdrant_path(self) -> Path:
        """Qdrant storage directory."""
        return self.data_dir / "qdrant"

    @property
    def sqlite_path(self) -> Path:
        """SQLite database path."""
        return self.data_dir / "index.db"

    @property
    def thumbnails_dir(self) -> Path:
        """Thumbnail cache directory."""
        return self.data_dir / "thumbnails"

    @property
    def checkpoints_dir(self) -> Path:
        """Checkpoint directory for resumable ingestion."""
        return self.data_dir / "checkpoints"

    # === Models ===
    embedding_model: str = Field(
        default="google/siglip2-so400m-patch16-512",
        description="HuggingFace model ID for image/text embeddings (SigLIP 2)",
    )
    caption_model: str = Field(
        default="microsoft/Florence-2-base",
        description="HuggingFace model ID for caption generation",
    )
    embedding_dim: int = Field(
        default=1152,
        description="Embedding vector dimension (model-specific)",
    )

    # === Image Processing ===
    embedding_resize: int = Field(
        default=512,
        description="Long side resize for embedding model input (model's native size)",
    )
    thumbnail_size: int = Field(
        default=512,
        description="Long side for cached thumbnails (used for preview)",
    )
    supported_extensions: tuple[str, ...] = Field(
        default=(".jpg", ".jpeg", ".png", ".webp", ".cr2", ".cr3", ".dng", ".nef", ".arw", ".raf", ".rw2", ".orf"),
        description="File extensions to index",
    )
    raw_extensions: tuple[str, ...] = Field(
        default=(".cr2", ".cr3", ".dng", ".nef", ".arw", ".raf", ".rw2", ".orf"),
        description="RAW file extensions (used for skip_jpeg_if_raw_exists)",
    )
    skip_jpeg_if_raw_exists: bool = Field(
        default=True,
        description="Skip JPEG/PNG files if a RAW file with same name exists in same folder",
    )

    # === GPU / Batching ===
    batch_size: int = Field(
        default=128,
        description="Default batch size for GPU inference",
    )
    batch_size_max: int = Field(
        default=256,
        description="Maximum batch size to try before OOM fallback",
    )
    batch_size_min: int = Field(
        default=32,
        description="Minimum batch size after OOM fallback",
    )
    device: Literal["cuda", "mps", "cpu", "auto"] = Field(
        default="auto",
        description="Compute device (auto = cuda if available, then mps, else cpu)",
    )

    # === Search Parameters ===
    search_k_vec: int = Field(
        default=200,
        description="Number of results to retrieve from vector search",
    )
    search_k_text: int = Field(
        default=200,
        description="Number of results to retrieve from BM25 text search",
    )
    rrf_k: int = Field(
        default=60,
        description="RRF constant for rank fusion",
    )
    default_results: int = Field(
        default=50,
        description="Default number of results to return",
    )
    default_threshold: float = Field(
        default=0.0,
        description="Default similarity threshold (0 = no threshold)",
    )

    # === Vector DB ===
    qdrant_collection: str = Field(
        default="photos",
        description="Qdrant collection name",
    )
    vector_distance: Literal["Cosine", "Euclid", "Dot"] = Field(
        default="Cosine",
        description="Vector distance metric",
    )

    # === API Server ===
    api_host: str = Field(
        default="127.0.0.1",
        description="API server bind address (loopback only for security)",
    )
    api_port: int = Field(
        default=17831,
        description="API server port",
    )
    api_photo_root: str | None = Field(
        default=None,
        description="Override photo_root for API responses (e.g., 'Z:\\' for Windows clients)",
    )
    @property
    def api_discovery_path(self) -> Path:
        """Path to API discovery file for Lightroom plugin (cross-platform)."""
        return Path(platformdirs.user_data_dir("fastlrsearch")) / "api.json"

    # === UI ===
    ui_grid_columns: int = Field(
        default=4,
        description="Number of columns in results grid",
    )
    ui_preview_size: int = Field(
        default=800,
        description="Maximum size for detail preview images",
    )

    # === Ingestion ===
    checkpoint_interval: int = Field(
        default=1000,
        description="Save checkpoint every N images",
    )
    caption_batch_size: int = Field(
        default=8,
        description="Batch size for caption generation (smaller due to memory)",
    )

    @field_validator("photo_root", mode="before")
    @classmethod
    def expand_path(cls, v):
        """Expand ~ and resolve path."""
        if isinstance(v, str):
            return Path(v).expanduser().resolve()
        return v

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def get_device(self) -> str:
        """Resolve 'auto' device to actual device."""
        if self.device == "auto":
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        return self.device


# Global settings instance (can be overridden in tests)
settings = Settings()
