"""Background workers for UI.

Handles GPU inference and I/O in separate threads to keep UI responsive.
"""

from pathlib import Path
from typing import Any, Literal

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals for worker threads."""

    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    progress = Signal(int, int)  # current, total
    status = Signal(str)  # status message


class SearchWorker(QRunnable):
    """Background worker for search operations."""

    def __init__(self, query: str, mode: Literal["hybrid", "vector", "text"] = "hybrid", limit: int = 50, offset: int = 0):
        super().__init__()
        self.query = query
        self.mode: Literal["hybrid", "vector", "text"] = mode
        self.limit = limit
        self.offset = offset
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            from fastlrsearch.search import hybrid_search

            results = hybrid_search(
                query=self.query,
                mode=self.mode,
                limit=self.limit,
                offset=self.offset,
            )
            self.signals.result.emit(results)
        except Exception as e:
            import traceback
            error_msg = f"{e}\n\nFull traceback:\n{traceback.format_exc()}"
            print(error_msg)  # Also print to console
            self.signals.error.emit(error_msg)
        finally:
            self.signals.finished.emit()


class ImageSearchWorker(QRunnable):
    """Background worker for image-based search."""

    def __init__(self, image_path: Path, query: str | None = None, limit: int = 50, offset: int = 0):
        super().__init__()
        self.image_path = image_path
        self.query = query
        self.limit = limit
        self.offset = offset
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            from fastlrsearch.search import image_search

            results = image_search(
                image=self.image_path,
                query=self.query,
                limit=self.limit,
                offset=self.offset,
            )
            self.signals.result.emit(results)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class ThumbnailWorker(QRunnable):
    """Background worker for loading thumbnails."""

    def __init__(self, photo_id: str, source_path: Path):
        super().__init__()
        self.photo_id = photo_id
        self.source_path = source_path
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            from fastlrsearch.indexing import get_thumbnail_cache

            cache = get_thumbnail_cache()
            thumb_path = cache.get_or_generate(self.photo_id, self.source_path)

            if thumb_path and thumb_path.exists():
                self.signals.result.emit((self.photo_id, thumb_path))
            else:
                self.signals.error.emit(f"Failed to generate thumbnail for {self.photo_id}")
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class IngestionWorker(QRunnable):
    """Background worker for ingestion pipeline."""

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._cancelled = False
        self._paused = False

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True
        self._paused = False  # Unpause to allow cancellation to proceed

    def pause(self):
        """Pause ingestion."""
        self._paused = True

    def resume(self):
        """Resume ingestion."""
        self._paused = False

    @property
    def is_paused(self) -> bool:
        """Check if ingestion is paused."""
        return self._paused

    @Slot()
    def run(self):
        import time

        try:
            from fastlrsearch.indexing import get_qdrant_store, get_sqlite_store, PhotoRecord
            from fastlrsearch.ingestion import run_ingestion

            qdrant = get_qdrant_store()
            sqlite = get_sqlite_store()

            # Get path -> photo_id mapping for detecting changed files
            path_to_id = sqlite.get_path_to_id_map()
            # Use paths to determine what to skip (not photo_ids which change with mtime)
            existing_paths = set(path_to_id.keys())

            def on_progress(processed: int, total: int):
                # Wait while paused
                while self._paused and not self._cancelled:
                    time.sleep(0.1)

                if self._cancelled:
                    raise InterruptedError("Ingestion cancelled")
                self.signals.progress.emit(processed, total)

            def on_photo(photo):
                if photo.embedding and not photo.error:
                    # Check if this path was previously indexed with a different photo_id
                    old_photo_id = path_to_id.get(photo.relative_path)
                    if old_photo_id and old_photo_id != photo.photo_id:
                        # Delete old entry from Qdrant (SQLite will be updated by upsert)
                        qdrant.delete(old_photo_id)
                        sqlite.delete_photo(old_photo_id)

                    # Index to Qdrant
                    qdrant.upsert(photo.photo_id, photo.embedding)

                    # Index to SQLite
                    record = PhotoRecord(
                        photo_id=photo.photo_id,
                        path=photo.relative_path,
                        mtime=photo.mtime,
                        phash=photo.phash,
                        embedded_at=photo.mtime,  # Use mtime as embedded_at for now
                    )
                    sqlite.upsert_photo(record)

            stats = run_ingestion(
                existing_paths=existing_paths,
                on_photo=on_photo,
                on_progress=on_progress,
            )

            self.signals.result.emit(stats)

        except InterruptedError:
            # Cancelled by user - don't emit error on clean shutdown
            try:
                self.signals.error.emit("Ingestion cancelled")
            except RuntimeError:
                pass  # Signal source deleted (app closing)
        except Exception as e:
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass  # Signal source deleted (app closing)
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass  # Signal source deleted (app closing)


class ModelLoadWorker(QRunnable):
    """Background worker for loading ML models."""

    def __init__(self, model_type: str = "embedder"):
        super().__init__()
        self.model_type = model_type
        self.signals = WorkerSignals()

    def _is_model_cached(self, model_name: str) -> bool:
        """Check if model is already downloaded in HuggingFace cache."""
        try:
            from huggingface_hub import try_to_load_from_cache
            # Check for a key file that would indicate model is cached
            result = try_to_load_from_cache(model_name, "config.json")
            return result is not None
        except Exception:
            return False

    @Slot()
    def run(self):
        try:
            if self.model_type == "embedder":
                from fastlrsearch.config import settings
                from fastlrsearch.ingestion import get_embedder

                # Check if model needs downloading
                is_cached = self._is_model_cached(settings.embedding_model)
                if is_cached:
                    self.signals.status.emit("Loading model to GPU...")
                else:
                    self.signals.status.emit(f"Downloading model (~4.5GB, please wait)...")

                embedder = get_embedder()
                # Force model load (this triggers download if not cached)
                _ = embedder.model

                # Warm up with a full search to initialize everything
                self.signals.status.emit("Warming up...")
                from fastlrsearch.search import hybrid_search
                _ = hybrid_search("warmup", limit=1)

                self.signals.result.emit("Ready")
            elif self.model_type == "captioner":
                from fastlrsearch.ingestion import get_captioner

                captioner = get_captioner()
                _ = captioner.model
                self.signals.result.emit("Captioner loaded")
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()
