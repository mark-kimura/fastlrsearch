"""Main entry point for FastLRSearch desktop application."""

import sys


def main():
    """Launch the FastLRSearch desktop application."""
    # Lazy imports to speed up startup
    from fastlrsearch.config import settings

    # Ensure data directories exist
    settings.ensure_dirs()

    # Import and launch UI
    from fastlrsearch.ui.app import run_app

    sys.exit(run_app())


if __name__ == "__main__":
    main()
