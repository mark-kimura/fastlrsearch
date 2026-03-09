"""Details panel for displaying selected photo information."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from fastlrsearch.config import settings
from fastlrsearch.search import SearchResult


class DetailsPanel(QFrame):
    """Panel showing details of selected photo."""

    find_similar_clicked = Signal(str)  # Emits photo_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: SearchResult | None = None
        self._current_pixmap: QPixmap | None = None
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Preview image - square container that scales with panel width
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #1a1a1a;")
        self.preview_label.setScaledContents(False)  # We handle scaling manually
        self.preview_label.setMinimumSize(200, 200)
        layout.addWidget(self.preview_label)

        # Buttons - directly below preview
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self._on_open_clicked)
        button_layout.addWidget(self.open_button)

        self.similar_button = QPushButton("Find Similar")
        self.similar_button.clicked.connect(self._on_similar_clicked)
        button_layout.addWidget(self.similar_button)

        layout.addLayout(button_layout)

        # Scores
        self.score_label = QLabel()
        self.score_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.score_label)

        # File path
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("font-size: 11px; color: #666;")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        # Push everything to top - empty space goes below
        layout.addStretch()

        # Initially hidden
        self._set_empty_state()

    def _set_empty_state(self):
        """Show empty state."""
        self.preview_label.setText("Select a photo to view details")
        self.path_label.setText("")
        self.score_label.setText("")
        self.open_button.setEnabled(False)
        self.similar_button.setEnabled(False)

    def set_result(self, result: SearchResult):
        """Display details for a search result."""
        self._result = result
        self._current_pixmap: QPixmap | None = None

        # Load preview from cached thumbnail (512px, already EXIF-corrected)
        from fastlrsearch.indexing import get_thumbnail_cache
        cache = get_thumbnail_cache()
        thumb_path = cache.get(result.photo_id)

        pixmap = QPixmap()
        if thumb_path and thumb_path.exists():
            pixmap = QPixmap(str(thumb_path))

        if not pixmap.isNull():
            self._current_pixmap = pixmap
            self._update_preview()
        else:
            self.preview_label.setText("Preview not available")

        # Path
        if result.path:
            abs_path = settings.photo_root / result.path
            self.path_label.setText(str(abs_path))
        else:
            self.path_label.setText("")

        # Similarity score
        self.score_label.setText(f"Similarity: {result.score:.4f}")

        # Enable buttons
        self.open_button.setEnabled(result.path is not None)
        self.similar_button.setEnabled(True)

    def clear(self):
        """Clear the panel."""
        self._result = None
        self._current_pixmap = None
        self._set_empty_state()

    def _update_preview(self):
        """Scale and display the current pixmap to fit the preview label."""
        if self._current_pixmap is None or self._current_pixmap.isNull():
            return

        # Get available size for the preview
        available_width = self.preview_label.width() - 4  # Small margin
        available_height = self.preview_label.height() - 4

        if available_width <= 0 or available_height <= 0:
            available_width = 280  # Fallback
            available_height = 280

        scaled = self._current_pixmap.scaled(
            available_width,
            available_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def resizeEvent(self, event: QResizeEvent):
        """Handle resize to update preview scaling and maintain square aspect."""
        super().resizeEvent(event)
        # Make preview label square based on available width
        preview_width = self.width() - 24  # Account for margins
        self.preview_label.setFixedHeight(preview_width)
        if self._current_pixmap is not None:
            self._update_preview()

    def _on_open_clicked(self):
        """Open file in system file manager."""
        if self._result and self._result.path:
            abs_path = settings.photo_root / self._result.path
            if abs_path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(abs_path)))

    def _on_similar_clicked(self):
        """Trigger find similar search."""
        if self._result:
            self.find_similar_clicked.emit(self._result.photo_id)
