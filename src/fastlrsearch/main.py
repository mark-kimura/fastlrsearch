"""Main entry point for FastLRSearch desktop application."""

import sys


def _install_lrplugin():
    """Install the Lightroom plugin to the standard Modules directory."""
    import shutil
    from pathlib import Path

    plugin_src = Path(__file__).parent.parent.parent / "fastlrsearch.lrplugin"
    if not plugin_src.is_dir():
        # When installed via pip, plugin is in package data
        plugin_src = Path(__file__).parent / "lrplugin"
    if not plugin_src.is_dir():
        print("Error: Lightroom plugin not found.")
        print("Copy fastlrsearch.lrplugin manually to:")
        print("  ~/Library/Application Support/Adobe/Lightroom/Modules/")
        sys.exit(1)

    dest_base = Path.home() / "Library/Application Support/Adobe/Lightroom/Modules"
    dest_base.mkdir(parents=True, exist_ok=True)
    dest = dest_base / "fastlrsearch.lrplugin"

    if dest.exists():
        shutil.rmtree(dest)

    shutil.copytree(plugin_src, dest)
    print(f"Lightroom plugin installed to {dest}")
    print()
    print("Next steps:")
    print("  1. Open Lightroom Classic")
    print("  2. File → Plug-in Manager → FastLRSearch should appear")
    print("  3. Make sure FastLRSearch desktop app is running")


def main():
    """Launch the FastLRSearch desktop application."""
    if "--install-lrplugin" in sys.argv:
        _install_lrplugin()
        return

    if "--version" in sys.argv:
        print("FastLRSearch 0.1.0")
        return

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
