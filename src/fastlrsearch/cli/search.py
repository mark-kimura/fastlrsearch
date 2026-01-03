"""CLI for searching photos.

Usage:
    python -m fastlrsearch.cli.search "sunset over ocean"
    python -m fastlrsearch.cli.search --image /path/to/reference.jpg
"""

import argparse
import sys
from pathlib import Path


def main():
    """Search photos from command line."""
    parser = argparse.ArgumentParser(
        description="Search photos with FastLRSearch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Text search query",
    )
    parser.add_argument(
        "--image", "-i",
        type=Path,
        help="Reference image for similarity search",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=10,
        help="Number of results (default: 10)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["hybrid", "vector", "text"],
        default="hybrid",
        help="Search mode (default: hybrid)",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.0,
        help="Minimum similarity threshold",
    )

    args = parser.parse_args()

    if not args.query and not args.image:
        parser.error("Either query or --image is required")

    # Import here to avoid slow startup for --help
    from fastlrsearch.config import settings
    from fastlrsearch.search import hybrid_search, image_search

    if args.image:
        # Image search
        if not args.image.exists():
            print(f"Error: Image not found: {args.image}", file=sys.stderr)
            return 1

        print(f"Searching by image: {args.image}")
        if args.query:
            print(f"Combined with query: {args.query}")

        results = image_search(
            image=args.image,
            query=args.query,
            limit=args.limit,
            threshold=args.threshold,
        )
    else:
        # Text search
        print(f"Searching: {args.query} (mode: {args.mode})")
        results = hybrid_search(
            query=args.query,
            limit=args.limit,
            threshold=args.threshold,
            mode=args.mode,
        )

    print(f"\nFound {len(results)} results:\n")

    for i, result in enumerate(results, 1):
        abs_path = settings.photo_root / result.path if result.path else "N/A"
        print(f"{i:3}. Score: {result.score:.4f}")
        print(f"     Path: {abs_path}")
        if result.caption:
            caption = result.caption[:80] + "..." if len(result.caption) > 80 else result.caption
            print(f"     Caption: {caption}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
