"""Results grid widget for displaying search results.

Shows thumbnails in a scrollable grid with lazy loading.
Auto-adjusts columns based on available width and thumbnail size.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThreadPool
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from fastlrsearch.config import settings
from fastlrsearch.search import SearchResult
from fastlrsearch.ui.workers import ThumbnailWorker


class ThumbnailWidget(QFrame):
    """Single thumbnail widget in the results grid."""

    clicked = Signal(str)  # Emits photo_id

    def __init__(self, result: SearchResult, thumb_size: int = 256, parent=None):
        super().__init__(parent)
        self.result = result
        self._thumb_size = thumb_size
        self._pixmap: QPixmap | None = None
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Thumbnail image
        self.image_label = QLabel()
        self.image_label.setFixedSize(self._thumb_size, self._thumb_size)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # File path (relative to photo root)
        path = self.result.path or ""
        # Truncate path from the beginning if too long, keeping filename visible
        max_len = 50
        if len(path) > max_len:
            path = "..." + path[-(max_len - 3):]

        self.path_label = QLabel(path)
        self.path_label.setWordWrap(True)
        self.path_label.setMaximumHeight(40)
        self.path_label.setMaximumWidth(self._thumb_size)
        self.path_label.setStyleSheet("font-size: 10px; color: #aaa;")
        self.path_label.setToolTip(self.result.path or "")  # Full path on hover
        layout.addWidget(self.path_label)

        # Score
        score_text = f"Score: {self.result.score:.3f}"
        self.score_label = QLabel(score_text)
        self.score_label.setMaximumWidth(self._thumb_size)
        self.score_label.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(self.score_label)

    def set_thumbnail(self, pixmap: QPixmap):
        """Set the thumbnail image."""
        self._pixmap = pixmap
        self._update_pixmap()

    def _update_pixmap(self):
        """Update pixmap display with current size."""
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self._thumb_size,
                self._thumb_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)

    def set_size(self, size: int):
        """Update thumbnail size."""
        self._thumb_size = size
        self.image_label.setFixedSize(size, size)
        self.path_label.setMaximumWidth(size)
        self.score_label.setMaximumWidth(size)
        self._update_pixmap()

    def set_loading(self):
        """Show loading state."""
        self.image_label.setText("Loading...")

    def set_error(self):
        """Show error state."""
        self.image_label.setText("Error")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.result.photo_id)
        super().mousePressEvent(event)


class ResultsGrid(QScrollArea):
    """Scrollable grid of search results with thumbnails.

    Uses fixed column count, thumbnail size adapts to available width.
    """

    photo_selected = Signal(SearchResult)  # Emits selected result
    find_similar = Signal(str)  # Emits photo_id for "find similar"

    # Widget padding = frame (2) + layout margins (8) + safety buffer = 12
    WIDGET_PADDING = 12
    MIN_THUMB_SIZE = 64
    MAX_THUMB_SIZE = 400

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[SearchResult] = []
        self._widgets: dict[str, ThumbnailWidget] = {}
        self._thread_pool = QThreadPool.globalInstance()
        self._column_count = 5  # Default columns (must match main_window slider)
        self._thumb_size = settings.thumbnail_size
        self._setup_ui()

    def _setup_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container widget
        self.container = QWidget()
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)

        self.setWidget(self.container)

        # Empty state label
        self.empty_label: QLabel | None = QLabel("No results")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; font-size: 14px;")
        self.grid_layout.addWidget(self.empty_label, 0, 0)

    def _calculate_thumb_size(self) -> int:
        """Calculate thumbnail size based on column count and available width."""
        # Available width = viewport - scrollbar buffer - container margins
        margins = self.grid_layout.contentsMargins()
        available_width = self.viewport().width() - 20 - margins.left() - margins.right()

        spacing = self.grid_layout.spacing()
        n = self._column_count

        # N columns need: N * (thumb_size + padding) + (N-1) * spacing = available
        # thumb_size = (available - (N-1) * spacing) / N - padding
        thumb_size = (available_width - (n - 1) * spacing) // n - self.WIDGET_PADDING

        # Clamp to reasonable bounds
        return max(self.MIN_THUMB_SIZE, min(self.MAX_THUMB_SIZE, thumb_size))

    def resizeEvent(self, event: QResizeEvent):
        """Handle resize to recalculate thumbnail size."""
        super().resizeEvent(event)
        self._update_thumb_size()

    def clear(self, message: str = "No results"):
        """Clear all results.

        Args:
            message: Text to show in empty state
        """
        self._results = []
        self._widgets = {}

        # Remove all widgets from layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Show empty state
        self.empty_label = QLabel(message)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; font-size: 14px;")
        self.grid_layout.addWidget(self.empty_label, 0, 0)

    def set_results(self, results: list[SearchResult]):
        """Set the search results to display."""
        self.clear()

        if not results:
            return

        # Remove empty label
        if self.empty_label:
            self.grid_layout.removeWidget(self.empty_label)
            self.empty_label.deleteLater()
            self.empty_label = None

        self._results = results
        # Calculate thumb size for current width/columns before creating widgets
        self._thumb_size = self._calculate_thumb_size()

        for i, result in enumerate(results):
            row = i // self._column_count
            col = i % self._column_count

            widget = ThumbnailWidget(result, thumb_size=self._thumb_size)
            widget.clicked.connect(self._on_thumbnail_clicked)
            widget.set_loading()

            self.grid_layout.addWidget(widget, row, col)
            self._widgets[result.photo_id] = widget

            # Start loading thumbnail
            self._load_thumbnail(result)

    def set_column_count(self, count: int):
        """Update column count and recalculate thumbnail size."""
        self._column_count = count
        self._update_thumb_size()

    def _update_thumb_size(self):
        """Recalculate and apply thumbnail size based on current column count."""
        new_size = self._calculate_thumb_size()
        if new_size != self._thumb_size:
            self._thumb_size = new_size
            for widget in self._widgets.values():
                widget.set_size(new_size)
        if self._results:
            self._relayout_grid()

    def _relayout_grid(self):
        """Re-layout the grid with current column count."""
        # Remove all widgets from layout (but don't delete them)
        for widget in self._widgets.values():
            self.grid_layout.removeWidget(widget)

        # Re-add in new positions
        for i, result in enumerate(self._results):
            if result.photo_id in self._widgets:
                row = i // self._column_count
                col = i % self._column_count
                self.grid_layout.addWidget(self._widgets[result.photo_id], row, col)

    def _load_thumbnail(self, result: SearchResult):
        """Load thumbnail for a result in background."""
        if not result.path:
            return

        source_path = settings.photo_root / result.path
        worker = ThumbnailWorker(result.photo_id, source_path)
        worker.signals.result.connect(self._on_thumbnail_loaded)
        worker.signals.error.connect(self._on_thumbnail_error)
        self._thread_pool.start(worker)

    def _on_thumbnail_loaded(self, data: tuple[str, Path]):
        """Handle thumbnail loaded."""
        photo_id, thumb_path = data

        if photo_id not in self._widgets:
            return

        pixmap = QPixmap(str(thumb_path))
        if not pixmap.isNull():
            self._widgets[photo_id].set_thumbnail(pixmap)
        else:
            self._widgets[photo_id].set_error()

    def _on_thumbnail_error(self, error: str):
        """Handle thumbnail loading error."""
        # Could update specific widget if we tracked which one errored
        pass

    def _on_thumbnail_clicked(self, photo_id: str):
        """Handle thumbnail click."""
        for result in self._results:
            if result.photo_id == photo_id:
                self.photo_selected.emit(result)
                break

    def get_result(self, photo_id: str) -> SearchResult | None:
        """Get result by photo_id."""
        for result in self._results:
            if result.photo_id == photo_id:
                return result
        return None
