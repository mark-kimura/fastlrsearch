"""Desktop UI for FastLRSearch.

Public API:
- run_app: Launch the desktop application
- MainWindow: Main application window class
"""

from fastlrsearch.ui.app import run_app
from fastlrsearch.ui.main_window import MainWindow

__all__ = [
    "run_app",
    "MainWindow",
]
