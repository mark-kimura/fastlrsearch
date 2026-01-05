"""FastLRSearch UI application entry point."""

import sys


def run_app() -> int:
    """Run the desktop application.

    Returns:
        Exit code (0 for success)
    """
    from PySide6.QtWidgets import QApplication

    from fastlrsearch.api import start_server
    from fastlrsearch.config import settings
    from fastlrsearch.ui.main_window import MainWindow

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("FastLRSearch")
    app.setApplicationVersion("0.1.0")

    # Apply dark theme
    app.setStyle("Fusion")
    _apply_dark_palette(app)

    # Start API server in background
    api_token = None
    try:
        api_token = start_server()
    except Exception as e:
        print(f"Warning: Failed to start API server: {e}")

    # Create and show main window
    window = MainWindow(api_token=api_token)
    window.show()

    return app.exec()


def _apply_dark_palette(app):
    """Apply dark color palette to the application."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()

    # Base colors - use ColorRole enum
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

    # Disabled colors
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(127, 127, 127),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(127, 127, 127),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(127, 127, 127),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Highlight,
        QColor(80, 80, 80),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor(127, 127, 127),
    )

    app.setPalette(palette)
