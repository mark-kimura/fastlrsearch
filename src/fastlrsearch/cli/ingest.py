"""CLI for photo ingestion pipeline.

Usage:
    fastlrsearch-ingest [--full] [--caption]

Options:
    --full      Force full re-indexing (ignore existing)
    --caption   Also run caption generation (slower)
"""

import argparse
import sys
import time

from tqdm import tqdm


def main():
    """Run ingestion pipeline from command line."""
    parser = argparse.ArgumentParser(
        description="Index photos for FastLRSearch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full re-indexing (ignore existing)",
    )
    parser.add_argument(
        "--caption",
        action="store_true",
        help="Also run caption generation after indexing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override batch size for GPU inference",
    )

    args = parser.parse_args()

    # Import here to avoid slow startup for --help
    from fastlrsearch.config import settings
    from fastlrsearch.indexing import (
        PhotoRecord,
        get_qdrant_store,
        get_sqlite_store,
        get_thumbnail_cache,
    )
    from fastlrsearch.ingestion import (
        IngestionPipeline,
        ProcessedPhoto,
        get_captioner,
        load_for_embedding,
        unload_captioner,
        unload_embedder,
    )

    print("=" * 60)
    print("FastLRSearch Ingestion")
    print("=" * 60)
    print(f"Photo root: {settings.photo_root}")
    print(f"Data dir: {settings.data_dir}")
    print()

    # Ensure directories exist
    settings.ensure_dirs()

    # Get stores
    qdrant = get_qdrant_store()
    sqlite = get_sqlite_store()

    # Get existing IDs for incremental mode
    if args.full:
        print("Full re-indexing mode - clearing existing data...")
        existing_ids = set()
    else:
        existing_ids = qdrant.get_all_ids()
        print(f"Incremental mode - {len(existing_ids)} photos already indexed")

    print()

    # Stage 1: Embedding
    print("Stage 1: Scanning and embedding photos...")
    start_time = time.time()

    pipeline = IngestionPipeline()

    # Clear checkpoint if full mode
    if args.full:
        pipeline.clear_checkpoint()

    # Progress bar
    pbar = tqdm(desc="Processing", unit="photos")
    processed_count = 0
    error_count = 0

    def update_progress(photo: ProcessedPhoto):
        nonlocal processed_count, error_count

        if photo.error:
            error_count += 1
            return

        if photo.embedding:
            # Index to Qdrant
            qdrant.upsert(photo.photo_id, photo.embedding)

            # Index to SQLite
            record = PhotoRecord(
                photo_id=photo.photo_id,
                path=photo.relative_path,
                mtime=photo.mtime,
                phash=photo.phash,
                embedded_at=time.time(),
            )
            sqlite.upsert_photo(record)

            processed_count += 1
            pbar.update(1)

    try:
        for photo in pipeline.run_stage1(existing_ids=existing_ids):
            update_progress(photo)
    except KeyboardInterrupt:
        print("\nInterrupted!")
    finally:
        pbar.close()

    elapsed = time.time() - start_time
    rate = processed_count / elapsed if elapsed > 0 else 0

    print()
    print(f"Stage 1 complete:")
    print(f"  Processed: {processed_count}")
    print(f"  Errors: {error_count}")
    print(f"  Time: {elapsed:.1f}s ({rate:.1f} photos/s)")
    print()

    # Unload embedder to free VRAM
    unload_embedder()

    # Stage 2: Captioning (optional)
    if args.caption:
        print("Stage 2: Generating captions...")
        start_time = time.time()

        # Get uncaptioned photos
        uncaptioned_ids = sqlite.get_uncaptioned_ids()
        print(f"Found {len(uncaptioned_ids)} photos without captions")

        if uncaptioned_ids:
            captioner = get_captioner()
            caption_batch_size = settings.caption_batch_size

            pbar = tqdm(total=len(uncaptioned_ids), desc="Captioning", unit="photos")
            captioned_count = 0

            for i in range(0, len(uncaptioned_ids), caption_batch_size):
                batch_ids = uncaptioned_ids[i : i + caption_batch_size]

                # Load images
                batch_images = []
                batch_records = []

                for pid in batch_ids:
                    record = sqlite.get_photo(pid)
                    if record:
                        source_path = settings.photo_root / record.path
                        img = load_for_embedding(source_path)
                        if img:
                            batch_images.append(img)
                            batch_records.append(record)

                if not batch_images:
                    pbar.update(len(batch_ids))
                    continue

                # Generate captions
                results = captioner.caption_images(batch_images)

                # Update database
                for record, (caption, tags) in zip(batch_records, results):
                    record.caption = caption
                    record.tags = " ".join(tags)
                    record.captioned_at = time.time()
                    sqlite.upsert_photo(record)
                    captioned_count += 1

                pbar.update(len(batch_ids))

            pbar.close()
            unload_captioner()

            elapsed = time.time() - start_time
            print(f"Stage 2 complete: {captioned_count} captions in {elapsed:.1f}s")
        else:
            print("No uncaptioned photos found")

    # Final stats
    print()
    print("=" * 60)
    print("Final Statistics")
    print("=" * 60)
    print(f"Photos in database: {sqlite.count()}")
    print(f"Photos with captions: {sqlite.count_captioned()}")
    print(f"Vectors indexed: {qdrant.count()}")

    thumbs = get_thumbnail_cache()
    print(f"Thumbnails cached: {thumbs.count()}")
    print(f"Thumbnail cache size: {thumbs.size_bytes() / 1024 / 1024:.1f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
