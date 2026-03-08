"""Main entry point for FastLRSearch desktop application."""

import sys


def main():
    """Launch the FastLRSearch desktop application."""
    # On macOS, set the process name so the app menu shows "FastLRSearch"
    # instead of "Python"
    if sys.platform == "darwin":
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info:
                info["CFBundleName"] = "FastLRSearch"
        except ImportError:
            pass  # pyobjc not installed, app menu will show "Python"

    # Lazy imports to speed up startup
    from fastlrsearch.config import settings

    # Ensure data directories exist
    settings.ensure_dirs()

    # Import and launch UI
    from fastlrsearch.ui.app import run_app

    sys.exit(run_app())


if __name__ == "__main__":
    main()
