"""Ingestion pipeline orchestrator.

Two-stage ingestion:
- Stage 1 (blocking): Scan → Load → Embed → pHash → Index
- Stage 2 (background): Caption generation

Optimized with:
- Prefetch pipeline: Load next batch while GPU processes current
- Parallel thumbnail generation
- Dynamic batch sizing with OOM fallback
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from typing import Callable, Iterator

from PIL import Image

from fastlrsearch.config import settings
from fastlrsearch.ingestion.dedup import compute_phash
from fastlrsearch.ingestion.embedder import Embedder, get_embedder
from fastlrsearch.ingestion.image_loader import load_for_embedding, load_for_thumbnail
from fastlrsearch.ingestion.scanner import ScannedFile, scan_directory


@dataclass
class ProcessedPhoto:
    """Result of processing a single photo."""

    photo_id: str
    relative_path: str
    mtime: float
    embedding: list[float] | None
    phash: str | None
    thumbnail_path: Path | None
    error: str | None = None


@dataclass
class IngestionStats:
    """Statistics for an ingestion run."""

    total_scanned: int = 0
    total_processed: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class LoadedBatch:
    """A batch of loaded images ready for embedding."""

    files: list[ScannedFile]
    images: list[Image.Image]
    failed: list[tuple[ScannedFile, str]]  # (file, error_msg)


class BatchPrefetcher:
    """Prefetches and loads image batches in background threads.

    Loads the next batch while the GPU processes the current one,
    hiding I/O latency behind GPU computation.
    """

    def __init__(self, files: list[ScannedFile], batch_size: int, num_workers: int = 8):
        """Initialize prefetcher.

        Args:
            files: List of files to process
            batch_size: Number of images per batch
            num_workers: Number of parallel loading threads
        """
        self._files = files
        self._batch_size = batch_size
        self._num_workers = num_workers
        self._queue: Queue[LoadedBatch | None] = Queue(maxsize=4)  # Buffer 4 batches
        self._executor = ThreadPoolExecutor(max_workers=num_workers)
        self._thread: Thread | None = None
        self._stop = False

    def start(self):
        """Start the prefetch thread."""
        self._thread = Thread(target=self._prefetch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop prefetching."""
        self._stop = True
        if self._thread:
            self._thread.join(timeout=5)
        self._executor.shutdown(wait=False)

    def get_batch(self, timeout: float = 60) -> LoadedBatch | None:
        """Get the next loaded batch.

        Args:
            timeout: Max seconds to wait

        Returns:
            LoadedBatch or None if no more batches
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def _prefetch_loop(self):
        """Background thread that loads batches."""
        for i in range(0, len(self._files), self._batch_size):
            if self._stop:
                break

            batch_files = self._files[i : i + self._batch_size]
            loaded_batch = self._load_batch_parallel(batch_files)
            self._queue.put(loaded_batch)

        # Signal end of batches
        self._queue.put(None)

    def _load_batch_parallel(self, files: list[ScannedFile]) -> LoadedBatch:
        """Load a batch of images in parallel.

        Args:
            files: Files to load

        Returns:
            LoadedBatch with loaded images and failures
        """
        futures: list[tuple[ScannedFile, Future]] = []

        for f in files:
            future = self._executor.submit(load_for_embedding, f.path)
            futures.append((f, future))

        loaded_files = []
        loaded_images = []
        failed = []

        for f, future in futures:
            try:
                img = future.result(timeout=30)
                if img is not None:
                    loaded_files.append(f)
                    loaded_images.append(img)
                else:
                    failed.append((f, "Failed to load image"))
            except Exception as e:
                failed.append((f, str(e)))

        return LoadedBatch(files=loaded_files, images=loaded_images, failed=failed)


class ThumbnailGenerator:
    """Generates thumbnails in parallel using a thread pool."""

    def __init__(self, num_workers: int = 4):
        """Initialize generator.

        Args:
            num_workers: Number of parallel generation threads
        """
        self._executor = ThreadPoolExecutor(max_workers=num_workers)
        self._pending: list[Future] = []

    def submit(self, photo_id: str, source_path: Path) -> Future:
        """Submit a thumbnail generation job.

        Args:
            photo_id: Photo identifier
            source_path: Path to source image

        Returns:
            Future that resolves to thumbnail path or None
        """
        future = self._executor.submit(self._generate, photo_id, source_path)
        self._pending.append(future)
        return future

    def wait_all(self):
        """Wait for all pending thumbnails to complete."""
        for future in self._pending:
            try:
                future.result(timeout=30)
            except Exception:
                pass
        self._pending.clear()

    def shutdown(self):
        """Shutdown the executor."""
        self._executor.shutdown(wait=True)

    @staticmethod
    def _generate(photo_id: str, source_path: Path) -> Path | None:
        """Generate a single thumbnail.

        Args:
            photo_id: Photo identifier
            source_path: Path to source image

        Returns:
            Path to saved thumbnail or None on error
        """
        thumb_path = settings.thumbnails_dir / f"{photo_id}.webp"

        if thumb_path.exists():
            return thumb_path

        try:
            img = load_for_thumbnail(source_path)
            if img is not None:
                img.save(thumb_path, "WEBP", quality=85)
                return thumb_path
        except Exception:
            pass

        return None


class IngestionPipeline:
    """Orchestrates the photo ingestion pipeline.

    Optimized with prefetch loading and parallel thumbnail generation.
    Supports dynamic batch sizing with OOM fallback.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ):
        """Initialize pipeline.

        Args:
            embedder: Embedder instance (uses global singleton if None)
            on_progress: Callback(processed, total) for progress updates
            on_status: Callback(message) for status text updates
        """
        self._embedder = embedder
        self._on_progress = on_progress
        self._on_status = on_status
        self._checkpoint_path = settings.checkpoints_dir / "ingestion.json"
        self._current_batch_size = settings.batch_size
        self._thumbnail_gen = ThumbnailGenerator(num_workers=4)

    @property
    def embedder(self) -> Embedder:
        """Get embedder instance."""
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def run_stage1(
        self,
        existing_paths: set[str] | None = None,
        resume: bool = True,
    ) -> Iterator[ProcessedPhoto]:
        """Run Stage 1: Scan, embed, pHash, thumbnail.

        Uses prefetch pipeline for efficient I/O overlap with GPU.

        Args:
            existing_paths: Set of relative paths already indexed (for incremental)
            resume: Whether to resume from checkpoint

        Yields:
            ProcessedPhoto for each processed image
        """
        settings.ensure_dirs()

        # Load checkpoint if resuming (these are paths, not photo_ids)
        processed_paths = self._load_checkpoint() if resume else set()

        # Combine with existing paths
        skip_paths = (existing_paths or set()) | processed_paths

        # Scan for files
        print("Scanning for photos...")
        def _scan_progress(count: int):
            msg = f"Scanning photos... ({count:,} found)"
            print(f"  {msg}")
            if self._on_status:
                self._on_status(msg)

        files = list(scan_directory(progress_callback=_scan_progress))
        total = len(files)
        msg = f"Found {total:,} photos"
        print(msg)
        if self._on_status:
            self._on_status(msg)

        # Filter out already processed (by path, not photo_id)
        to_process = [f for f in files if f.relative_path not in skip_paths]
        skipped_count = total - len(to_process)
        msg = f"Found {total:,} photos, {len(to_process):,} new, {skipped_count:,} skipped"
        print(f"  {len(to_process)} new, {skipped_count} skipped")
        if self._on_status:
            self._on_status(msg)

        if not to_process:
            print("Nothing to process.")
            return

        # Start prefetcher with more workers for larger batches
        prefetcher = BatchPrefetcher(
            files=to_process,
            batch_size=self._current_batch_size,
            num_workers=12,
        )
        prefetcher.start()

        start_time = time.time()
        processed_count = skipped_count

        try:
            while True:
                batch = prefetcher.get_batch(timeout=120)
                if batch is None:
                    break

                # Yield errors from loading failures
                for f, error in batch.failed:
                    yield ProcessedPhoto(
                        photo_id=f.photo_id,
                        relative_path=f.relative_path,
                        mtime=f.mtime,
                        embedding=None,
                        phash=None,
                        thumbnail_path=None,
                        error=error,
                    )

                if not batch.images:
                    continue

                # Embed with dynamic batch sizing
                embeddings = self._embed_with_oom_retry(batch.images)

                if embeddings is None:
                    # Complete failure, yield errors
                    for f in batch.files:
                        yield ProcessedPhoto(
                            photo_id=f.photo_id,
                            relative_path=f.relative_path,
                            mtime=f.mtime,
                            embedding=None,
                            phash=None,
                            thumbnail_path=None,
                            error="Embedding failed after OOM retries",
                        )
                    continue

                # Process each result
                for f, img, embedding in zip(batch.files, batch.images, embeddings):
                    try:
                        # Compute pHash
                        phash = compute_phash(img)

                        # Submit thumbnail generation (parallel)
                        self._thumbnail_gen.submit(f.photo_id, f.path)

                        yield ProcessedPhoto(
                            photo_id=f.photo_id,
                            relative_path=f.relative_path,
                            mtime=f.mtime,
                            embedding=embedding.tolist(),
                            phash=phash,
                            thumbnail_path=None,  # Generated async
                        )

                        processed_paths.add(f.relative_path)
                        processed_count += 1

                    except Exception as e:
                        yield ProcessedPhoto(
                            photo_id=f.photo_id,
                            relative_path=f.relative_path,
                            mtime=f.mtime,
                            embedding=None,
                            phash=None,
                            thumbnail_path=None,
                            error=str(e),
                        )

                # Progress callback
                if self._on_progress:
                    self._on_progress(processed_count, total)

                # Save checkpoint after every batch
                self._save_checkpoint(processed_paths, total=total, complete=False)

        finally:
            prefetcher.stop()
            # Wait for remaining thumbnails
            self._thumbnail_gen.wait_all()
            self._thumbnail_gen.shutdown()

        # Mark complete
        self._save_checkpoint(processed_paths, total=total, complete=True)

        elapsed = time.time() - start_time
        rate = processed_count / elapsed if elapsed > 0 else 0
        print(f"Stage 1 complete: {processed_count} photos in {elapsed:.1f}s ({rate:.1f}/s)")

    def _embed_with_oom_retry(self, images: list[Image.Image]) -> list | None:
        """Embed images with OOM retry logic.

        Tries current batch size, falls back to smaller on OOM.

        Args:
            images: Images to embed

        Returns:
            List of embeddings or None on complete failure
        """
        import torch

        batch_sizes = [
            self._current_batch_size,
            settings.batch_size_min,
            1,  # Last resort: one at a time
        ]

        for batch_size in batch_sizes:
            try:
                # Process in sub-batches if needed
                all_embeddings = []
                for i in range(0, len(images), batch_size):
                    sub_batch = images[i : i + batch_size]
                    embeddings = self.embedder.embed_images(sub_batch)
                    all_embeddings.extend(embeddings)

                # Success - try larger batch next time if we were reduced
                if batch_size == self._current_batch_size and batch_size < settings.batch_size_max:
                    self._try_increase_batch_size()

                return all_embeddings

            except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
                if "out of memory" in str(e).lower():
                    print(f"OOM with batch_size={batch_size}, reducing...")
                    torch.cuda.empty_cache()
                    self._current_batch_size = max(settings.batch_size_min, batch_size // 2)
                    continue
                raise

        return None

    def _try_increase_batch_size(self):
        """Try to increase batch size if we've been running smoothly."""
        if self._current_batch_size < settings.batch_size_max:
            self._current_batch_size = min(
                self._current_batch_size + 4,
                settings.batch_size_max,
            )

    def _load_checkpoint(self) -> set[str]:
        """Load checkpoint of processed paths."""
        if not self._checkpoint_path.exists():
            return set()

        try:
            with open(self._checkpoint_path) as f:
                data = json.load(f)
                # Support both new (processed_paths) and old (processed_ids) format
                paths = data.get("processed_paths", [])
                if not paths:
                    # Old checkpoint format - can't use IDs as paths, start fresh
                    return set()
                return set(paths)
        except Exception:
            return set()

    def _save_checkpoint(self, processed_paths: set[str], total: int = 0, complete: bool = False):
        """Save checkpoint of processed paths.

        Args:
            processed_paths: Set of processed file paths
            total: Total number of photos to process
            complete: Whether indexing is complete
        """
        try:
            with open(self._checkpoint_path, "w") as f:
                json.dump({
                    "processed_paths": list(processed_paths),
                    "processed_count": len(processed_paths),
                    "total_count": total,
                    "complete": complete,
                }, f)
        except Exception as e:
            print(f"Warning: Failed to save checkpoint: {e}")

    def clear_checkpoint(self):
        """Clear the checkpoint file."""
        if self._checkpoint_path.exists():
            self._checkpoint_path.unlink()

    @staticmethod
    def clear_checkpoint_file():
        """Clear the checkpoint file (static version for use without instance)."""
        checkpoint_path = settings.checkpoints_dir / "ingestion.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    @staticmethod
    def get_checkpoint_status() -> dict | None:
        """Get checkpoint status for resume prompt.

        Returns:
            Dict with 'processed_count', 'total_count', 'complete' or None if no checkpoint
        """
        checkpoint_path = settings.checkpoints_dir / "ingestion.json"
        if not checkpoint_path.exists():
            return None

        try:
            with open(checkpoint_path) as f:
                data = json.load(f)
                if data.get("complete", False):
                    return None  # Completed, no need to resume
                return {
                    "processed_count": data.get("processed_count", 0),
                    "total_count": data.get("total_count", 0),
                    "complete": data.get("complete", False),
                }
        except Exception:
            return None


def run_ingestion(
    existing_paths: set[str] | None = None,
    on_photo: Callable[[ProcessedPhoto], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> IngestionStats:
    """Run the full Stage 1 ingestion pipeline.

    Args:
        existing_paths: Set of relative paths already indexed (for incremental)
        on_photo: Callback for each processed photo
        on_progress: Callback(processed, total) for progress
        on_status: Callback(message) for status text updates

    Returns:
        IngestionStats with summary
    """
    stats = IngestionStats()
    start_time = time.time()

    pipeline = IngestionPipeline(on_progress=on_progress, on_status=on_status)

    try:
        for photo in pipeline.run_stage1(existing_paths=existing_paths):
            stats.total_scanned += 1

            if photo.error:
                stats.total_errors += 1
            elif photo.embedding is None:
                stats.total_skipped += 1
            else:
                stats.total_processed += 1

            if on_photo:
                on_photo(photo)

    finally:
        stats.elapsed_seconds = time.time() - start_time

    return stats
