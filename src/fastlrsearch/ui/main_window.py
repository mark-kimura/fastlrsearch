"""Main application window."""

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtGui import QAction, QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from fastlrsearch.config import settings
from fastlrsearch.search import SearchResult
from fastlrsearch.ui.details_panel import DetailsPanel
from fastlrsearch.ui.results_grid import ResultsGrid
from fastlrsearch.ui.workers import (
    ImageSearchWorker,
    IngestionWorker,
    ModelLoadWorker,
    SearchWorker,
)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, api_token: str | None = None):
        super().__init__()
        self._thread_pool = QThreadPool.globalInstance()
        self._ingestion_worker: IngestionWorker | None = None
        self._ingestion_start_time: float = 0.0
        self._current_results: list[SearchResult] = []
        self._current_page = 0
        self._results_per_page = 100
        # Track current search for server-side pagination
        self._current_query: str | None = None
        self._current_image_path: Path | None = None
        self._api_token = api_token
        self._setup_ui()
        self._setup_menu()
        self._load_model_async()
        self._check_incomplete_indexing()

    def _setup_ui(self):
        self.setWindowTitle("FastLRSearch")
        self.setMinimumSize(1280, 720)  # 16:9 aspect ratio

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Search bar area
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search photos... (or drag an image here)")
        self.search_input.setStyleSheet(
            self._search_input_default_style +
            " QLineEdit { font-size: 18px; }"
        )
        self.search_input.setMinimumHeight(40)
        self.search_input.setAcceptDrops(False)  # Let MainWindow handle drops
        self.search_input.returnPressed.connect(self._on_search)

        # Add custom clear action with larger icon
        from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
        from PySide6.QtCore import QSize

        # Create a larger X icon - draw lines instead of text for better scaling
        icon_size = 24
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        pen = QPen(QColor("#aaaaaa"))
        pen.setWidth(3)
        painter.setPen(pen)
        margin = 4
        painter.drawLine(margin, margin, icon_size - margin, icon_size - margin)
        painter.drawLine(icon_size - margin, margin, margin, icon_size - margin)
        painter.end()

        clear_action = self.search_input.addAction(
            QIcon(pixmap), QLineEdit.ActionPosition.TrailingPosition
        )
        clear_action.triggered.connect(self._on_clear_search)

        # Make the action icon larger via textMargins to give it more space
        self.search_input.setTextMargins(8, 0, 32, 0)

        search_layout.addWidget(self.search_input, stretch=1)

        self.search_button = QPushButton("Search")
        self.search_button.setStyleSheet("font-size: 18px; padding: 8px 20px;")
        self.search_button.setMinimumHeight(40)
        self.search_button.clicked.connect(self._on_search)
        search_layout.addWidget(self.search_button)

        self.image_button = QPushButton("Search by Image...")
        self.image_button.setStyleSheet("font-size: 18px; padding: 8px 20px;")
        self.image_button.setMinimumHeight(40)
        self.image_button.clicked.connect(self._on_image_search)
        search_layout.addWidget(self.image_button)

        # Controls bar (thumbnail size, results per page)
        controls_layout = QHBoxLayout()

        # Column count slider
        controls_layout.addWidget(QLabel("Columns:"))
        self.column_slider = QSlider(Qt.Orientation.Horizontal)
        self.column_slider.setMinimum(2)
        self.column_slider.setMaximum(10)
        self.column_slider.setValue(5)  # Default 5 columns
        self.column_slider.setMaximumWidth(150)
        self.column_slider.setToolTip("Number of columns")
        self.column_slider.valueChanged.connect(self._on_column_count_changed)
        controls_layout.addWidget(self.column_slider)

        self.column_label = QLabel("5")
        self.column_label.setMinimumWidth(25)
        controls_layout.addWidget(self.column_label)

        controls_layout.addStretch()

        # Results per page selector
        controls_layout.addWidget(QLabel("Show:"))
        self.limit_combo = QComboBox()
        self.limit_combo.addItems(["50", "100", "200", "500", "1000"])
        self.limit_combo.setCurrentText("100")
        self.limit_combo.currentTextChanged.connect(self._on_limit_changed)
        controls_layout.addWidget(self.limit_combo)

        # Pagination controls
        self.prev_button = QPushButton("<")
        self.prev_button.setMaximumWidth(30)
        self.prev_button.clicked.connect(self._on_prev_page)
        self.prev_button.setEnabled(False)
        controls_layout.addWidget(self.prev_button)

        self.page_label = QLabel("")
        self.page_label.setMinimumWidth(100)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(self.page_label)

        self.next_button = QPushButton(">")
        self.next_button.setMaximumWidth(30)
        self.next_button.clicked.connect(self._on_next_page)
        self.next_button.setEnabled(False)
        controls_layout.addWidget(self.next_button)

        # Main content: splitter with results and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left column: search bar + gallery + controls below
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        left_layout.addLayout(search_layout)  # Search bar at top

        self.results_grid = ResultsGrid()
        self.results_grid.photo_selected.connect(self._on_photo_selected)
        left_layout.addWidget(self.results_grid, stretch=1)

        left_layout.addLayout(controls_layout)  # Controls below gallery

        splitter.addWidget(left_container)

        # Right column: details panel
        self.details_panel = DetailsPanel()
        self.details_panel.find_similar_clicked.connect(self._on_find_similar)
        splitter.addWidget(self.details_panel)

        # Set initial splitter sizes (70% results, 30% details)
        splitter.setSizes([800, 350])

        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setContentsMargins(8, 0, 0, 0)  # Left padding
        self.status_bar.addWidget(self.status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.hide()
        self.status_bar.addWidget(self.progress_bar)

    def _setup_menu(self):
        import sys
        is_macos = sys.platform == "darwin"
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("File")

        prefs_action = QAction("Preferences...", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self._show_preferences)
        if is_macos:
            # Let macOS move this to the app menu (standard Mac UX)
            prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        file_menu.addAction(prefs_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        if is_macos:
            quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        file_menu.addAction(quit_action)

        if is_macos:
            # On macOS, Preferences and Quit move to the app menu,
            # so add Index Statistics to File to keep it non-empty
            stats_action = QAction("Index Statistics...", self)
            stats_action.triggered.connect(self._show_stats)
            file_menu.addAction(stats_action)

            file_menu.addSeparator()

            copy_token_action = QAction("Copy API Token", self)
            copy_token_action.triggered.connect(self._copy_api_token)
            file_menu.addAction(copy_token_action)
        else:
            # Tools menu (Linux/Windows only - on macOS these go in File)
            tools_menu = menu_bar.addMenu("Tools")

            stats_action = QAction("Index Statistics...", self)
            stats_action.triggered.connect(self._show_stats)
            tools_menu.addAction(stats_action)

            tools_menu.addSeparator()

            copy_token_action = QAction("Copy API Token", self)
            copy_token_action.triggered.connect(self._copy_api_token)
            tools_menu.addAction(copy_token_action)

        # Help menu
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About FastLRSearch", self)
        about_action.triggered.connect(self._show_about)
        if is_macos:
            # Let macOS move this to the app menu (standard Mac UX)
            about_action.setMenuRole(QAction.MenuRole.AboutRole)
        help_menu.addAction(about_action)

        if is_macos:
            # Add a visible item so Help menu isn't empty on macOS
            help_action = QAction("FastLRSearch Help", self)
            help_action.triggered.connect(self._show_about)
            help_action.setMenuRole(QAction.MenuRole.NoRole)
            help_menu.addAction(help_action)

    def _load_model_async(self):
        """Load embedding model in background."""
        self.status_label.setText("Loading model...")
        worker = ModelLoadWorker("embedder")
        worker.signals.status.connect(self._on_model_status)
        worker.signals.result.connect(self._on_model_loaded)
        worker.signals.error.connect(self._on_model_error)
        self._thread_pool.start(worker)

    def _on_model_status(self, message: str):
        """Handle model loading status update."""
        # Don't overwrite status if indexing is already running
        if self._ingestion_worker is None:
            self.status_label.setText(message)

    def _on_model_loaded(self, message: str):
        # Don't overwrite status if indexing is already running
        if self._ingestion_worker is None:
            self.status_label.setText("Ready")

    def _on_model_error(self, error: str):
        self.status_label.setText(f"Model error: {error}")

    def _check_incomplete_indexing(self):
        """Check for incomplete indexing and prompt to resume."""
        from PySide6.QtCore import QTimer

        # Delay the check to let the window fully initialize
        QTimer.singleShot(500, self._show_resume_prompt)

    def _show_resume_prompt(self):
        """Show resume prompt if there's incomplete indexing."""
        try:
            from fastlrsearch.ingestion.pipeline import IngestionPipeline

            status = IngestionPipeline.get_checkpoint_status()
            if status and status["total_count"] > 0:
                processed = status["processed_count"]
                total = status["total_count"]
                percent = (processed / total * 100) if total > 0 else 0

                reply = QMessageBox.question(
                    self,
                    "Resume Indexing",
                    f"Incomplete indexing detected.\n\n"
                    f"Progress: {processed:,} of {total:,} photos ({percent:.1f}%)\n\n"
                    f"Continue indexing?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self._do_start_ingestion()
                else:
                    # Clear stale checkpoint so it doesn't prompt again
                    IngestionPipeline.clear_checkpoint_file()
        except Exception:
            # Don't crash on startup if checkpoint check fails
            pass

    @Slot()
    def _on_clear_search(self):
        """Handle clear button - clears text and results."""
        self.search_input.clear()
        self._current_query = None
        self._current_image_path = None
        self._current_results = []
        self._current_page = 0
        self.results_grid.clear()
        self.details_panel.clear()
        self._update_pagination_controls()

    @Slot()
    def _on_search(self):
        """Handle text search."""
        query = self.search_input.text().strip()
        if not query:
            return

        # Store search for pagination and reset to first page
        self._current_query = query
        self._current_image_path = None
        self._current_page = 0

        self._execute_current_search()

    def _execute_current_search(self):
        """Execute the current search with current page offset."""
        offset = self._current_page * self._results_per_page

        self.search_button.setEnabled(False)
        self.results_grid.clear("Searching...")

        if self._current_image_path:
            # Image-based search
            query = self.search_input.text().strip() or None
            self.status_label.setText(f"Searching by image: {self._current_image_path.name}")
            worker = ImageSearchWorker(
                self._current_image_path,
                query=query,
                limit=self._results_per_page,
                offset=offset,
            )
        elif self._current_query:
            # Text-based search
            self.status_label.setText(f"Searching: {self._current_query}")
            worker = SearchWorker(
                self._current_query,
                mode="vector",
                limit=self._results_per_page,
                offset=offset,
            )
        else:
            self.search_button.setEnabled(True)
            return

        worker.signals.result.connect(self._on_search_results)
        worker.signals.error.connect(self._on_search_error)
        worker.signals.finished.connect(lambda: self.search_button.setEnabled(True))
        self._thread_pool.start(worker)

    @Slot()
    def _on_image_search(self):
        """Handle search by image dialog."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Image",
            str(settings.photo_root),
            "Images (*.jpg *.jpeg *.png *.webp *.cr2 *.dng *.nef *.arw *.raf)",
        )

        if file_path:
            self._search_by_image(Path(file_path))

    def _search_by_image(self, image_path: Path):
        """Perform image-based search."""
        # Store search for pagination and reset to first page
        self._current_image_path = image_path
        self._current_query = None
        self._current_page = 0

        self.details_panel.clear()
        self._execute_current_search()

    def _on_search_results(self, results: list[SearchResult]):
        """Handle search results."""
        self._current_results = results
        self.results_grid.set_results(results)
        self._update_pagination_controls()
        self.status_label.setText("Ready")

    def _on_search_error(self, error: str):
        """Handle search error."""
        self.status_label.setText(f"Search error: {error}")
        QMessageBox.warning(self, "Search Error", error)

    @Slot(SearchResult)
    def _on_photo_selected(self, result: SearchResult):
        """Handle photo selection in grid."""
        self.details_panel.set_result(result)

    @Slot(str)
    def _on_find_similar(self, photo_id: str):
        """Handle find similar request (pure image search, ignores text)."""
        from fastlrsearch.indexing import get_sqlite_store

        store = get_sqlite_store()
        record = store.get_photo(photo_id)

        if record and record.path:
            # Clear text input - Find Similar is pure image search
            self.search_input.clear()
            image_path = settings.photo_root / record.path
            self._search_by_image(image_path)

    @Slot()
    def _do_start_ingestion(self):
        """Start photo ingestion (called from Preferences dialog)."""
        import time

        if self._ingestion_worker is not None:
            QMessageBox.information(self, "Ingestion", "Indexing is already running")
            return

        self.status_label.setText("Starting indexing...")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self._ingestion_start_time = time.time()

        self._ingestion_worker = IngestionWorker()
        self._ingestion_worker.signals.progress.connect(self._on_ingestion_progress)
        self._ingestion_worker.signals.result.connect(self._on_ingestion_complete)
        self._ingestion_worker.signals.error.connect(self._on_ingestion_error)
        self._ingestion_worker.signals.status.connect(self.status_label.setText)
        self._thread_pool.start(self._ingestion_worker)

    def _on_ingestion_progress(self, current: int, total: int):
        """Handle ingestion progress with ETA calculation."""
        import time

        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

        # Calculate ETA
        elapsed = time.time() - self._ingestion_start_time
        if current > 0 and elapsed > 0:
            rate = current / elapsed  # photos per second
            remaining = total - current
            eta_seconds = remaining / rate if rate > 0 else 0

            # Format ETA
            if eta_seconds < 60:
                eta_str = f"{int(eta_seconds)}s"
            elif eta_seconds < 3600:
                eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
            else:
                hours = int(eta_seconds // 3600)
                mins = int((eta_seconds % 3600) // 60)
                eta_str = f"{hours}h {mins}m"

            self.status_label.setText(
                f"Indexing: {current:,}/{total:,} ({rate:.1f}/s, ETA: {eta_str})"
            )
        else:
            self.status_label.setText(f"Indexing: {current:,}/{total:,}")

    def _on_ingestion_complete(self, stats):
        """Handle ingestion completion."""
        self._ingestion_worker = None
        self.progress_bar.hide()
        # Show summary in status bar (non-intrusive)
        self.status_label.setText(
            f"Indexing complete: {stats.total_processed} indexed, "
            f"{stats.total_skipped} skipped, {stats.total_errors} errors "
            f"({stats.elapsed_seconds:.1f}s)"
        )

    def _on_ingestion_error(self, error: str):
        """Handle ingestion error."""
        self._ingestion_worker = None
        self.progress_bar.hide()
        self.status_label.setText(f"Indexing error: {error}")
        QMessageBox.warning(self, "Indexing Error", error)

    def _show_stats(self):
        """Show index statistics."""
        from fastlrsearch.indexing import get_qdrant_store, get_sqlite_store, get_thumbnail_cache

        try:
            sqlite = get_sqlite_store()
            qdrant = get_qdrant_store()
            thumbs = get_thumbnail_cache()

            stats = (
                f"Photos in database: {sqlite.count()}\n"
                f"Photos with captions: {sqlite.count_captioned()}\n"
                f"Vectors indexed: {qdrant.count()}\n"
                f"Thumbnails cached: {thumbs.count()}\n"
                f"Thumbnail cache size: {thumbs.size_bytes() / 1024 / 1024:.1f} MB"
            )

            QMessageBox.information(self, "Index Statistics", stats)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to get stats: {e}")

    def _copy_api_token(self):
        """Copy API token to clipboard for Lightroom plugin."""
        from PySide6.QtWidgets import QApplication

        if self._api_token:
            QApplication.clipboard().setText(self._api_token)
            QMessageBox.information(
                self,
                "API Token Copied",
                "The API token has been copied to clipboard.\n\n"
                "Paste it in the Lightroom plugin settings\n"
                "(File > Plug-in Manager > FastLRSearch).",
            )
        else:
            QMessageBox.warning(
                self,
                "API Token Not Available",
                "The API server is not running.\n"
                "Token is not available.",
            )

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About FastLRSearch",
            "FastLRSearch v0.1.0\n\n"
            "Fast offline photo search with semantic embeddings.\n\n"
            "Uses SigLIP for image/text embeddings and\n"
            "hybrid search with RRF fusion.",
        )

    def _show_preferences(self):
        """Show preferences dialog."""
        from fastlrsearch.ui.preferences_dialog import PreferencesDialog

        # Determine current indexing state
        indexing_running = self._ingestion_worker is not None
        indexing_paused = self._ingestion_worker.is_paused if self._ingestion_worker else False

        dialog = PreferencesDialog(
            self,
            indexing_running=indexing_running,
            indexing_paused=indexing_paused,
        )
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.start_indexing.connect(self._do_start_ingestion)
        dialog.pause_indexing.connect(self._do_pause_ingestion)
        dialog.resume_indexing.connect(self._do_resume_ingestion)
        dialog.rebuild_index.connect(self._do_rebuild_index)
        dialog.exec()

    def _on_settings_changed(self):
        """Handle settings change from preferences."""
        self.status_label.setText("Settings saved. Restart may be required for some changes.")

    def _do_pause_ingestion(self):
        """Pause the current ingestion."""
        if self._ingestion_worker is not None:
            self._ingestion_worker.pause()
            self.status_label.setText("Indexing paused")

    def _do_resume_ingestion(self):
        """Resume the paused ingestion."""
        if self._ingestion_worker is not None:
            self._ingestion_worker.resume()
            self.status_label.setText("Indexing resumed...")

    def _do_rebuild_index(self):
        """Rebuild index from scratch."""
        import shutil

        self.status_label.setText("Rebuilding index...")

        try:
            # Close existing stores
            from fastlrsearch.indexing import close_qdrant_store, close_sqlite_store

            close_qdrant_store()
            close_sqlite_store()

            # Delete index data
            if settings.qdrant_path.exists():
                shutil.rmtree(settings.qdrant_path)
            if settings.checkpoints_dir.exists():
                shutil.rmtree(settings.checkpoints_dir)
            if settings.thumbnails_dir.exists():
                shutil.rmtree(settings.thumbnails_dir)
            if settings.sqlite_path.exists():
                settings.sqlite_path.unlink()

            # Recreate directories
            settings.ensure_dirs()

            self.status_label.setText("Index cleared. Starting fresh indexing...")

            # Start fresh indexing
            self._do_start_ingestion()

        except Exception as e:
            self.status_label.setText(f"Rebuild failed: {e}")
            QMessageBox.warning(self, "Rebuild Error", f"Failed to rebuild index:\n{e}")

    def _on_column_count_changed(self, value: int):
        """Handle column count slider change."""
        self.column_label.setText(str(value))
        self.results_grid.set_column_count(value)

    def _on_limit_changed(self, text: str):
        """Handle results per page change."""
        self._results_per_page = int(text)
        self._current_page = 0
        # Re-execute search with new limit if we have an active search
        if self._current_query or self._current_image_path:
            self._execute_current_search()

    def _on_prev_page(self):
        """Go to previous page (fetches from server)."""
        if self._current_page > 0:
            self._current_page -= 1
            self._execute_current_search()

    def _on_next_page(self):
        """Go to next page (fetches from server)."""
        # Only advance if current page is full (more results may exist)
        if len(self._current_results) == self._results_per_page:
            self._current_page += 1
            self._execute_current_search()

    def _update_pagination_controls(self):
        """Update pagination buttons and label."""
        num_results = len(self._current_results)

        # Prev enabled if not on first page
        self.prev_button.setEnabled(self._current_page > 0)

        # Next enabled if current page is full (may have more results)
        self.next_button.setEnabled(num_results == self._results_per_page)

        if num_results > 0:
            start = self._current_page * self._results_per_page + 1
            end = start + num_results - 1
            self.page_label.setText(f"Results {start}-{end}")
        else:
            if self._current_page > 0:
                self.page_label.setText("No more results")
            else:
                self.page_label.setText("No results")

    # Drag and drop support
    _search_input_default_style = "QLineEdit { color: white; } QLineEdit::placeholder { color: #888; }"
    _search_input_drop_style = "QLineEdit { color: white; border: 2px solid #4a9eff; background-color: #2a3a4a; } QLineEdit::placeholder { color: #888; }"

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                path = Path(urls[0].toLocalFile())
                if path.suffix.lower() in settings.supported_extensions:
                    self.search_input.setStyleSheet(self._search_input_drop_style)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.search_input.setStyleSheet(self._search_input_default_style)
        event.accept()

    def dropEvent(self, event: QDropEvent):
        self.search_input.setStyleSheet(self._search_input_default_style)
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            self._search_by_image(path)
            event.acceptProposedAction()

    def closeEvent(self, event):
        """Handle window close."""
        # Cancel any running ingestion
        if self._ingestion_worker:
            self._ingestion_worker.cancel()

        # Wait for thread pool workers to finish
        self._thread_pool.waitForDone(5000)  # 5 second timeout

        # Close stores to release Qdrant/SQLite threads and file locks
        from fastlrsearch.indexing import close_qdrant_store, close_sqlite_store
        close_qdrant_store()
        close_sqlite_store()

        # Unload model to release any inference threads
        from fastlrsearch.ingestion.embedder import unload_embedder
        unload_embedder()

        # Stop API server if running
        from fastlrsearch.api import stop_server
        stop_server()

        event.accept()
