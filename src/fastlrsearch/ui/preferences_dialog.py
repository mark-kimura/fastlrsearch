"""Preferences dialog for application settings."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from fastlrsearch.config import settings


class PreferencesDialog(QDialog):
    """Dialog for editing application preferences."""

    settings_changed = Signal()
    start_indexing = Signal()  # Request to start indexing
    pause_indexing = Signal()  # Request to pause indexing
    resume_indexing = Signal()  # Request to resume indexing
    rebuild_index = Signal()  # Request to rebuild index from scratch

    def __init__(self, parent=None, indexing_running: bool = False, indexing_paused: bool = False):
        super().__init__(parent)
        self._indexing_running = indexing_running
        self._indexing_paused = indexing_paused
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(550)
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # === Paths Group ===
        paths_group = QGroupBox("Paths")
        paths_layout = QFormLayout(paths_group)
        paths_layout.setSpacing(12)

        # Photo root directory
        photo_root_layout = QHBoxLayout()
        self.photo_root_edit = QLineEdit()
        self.photo_root_edit.setReadOnly(True)
        photo_root_layout.addWidget(self.photo_root_edit, stretch=1)

        browse_photo_btn = QPushButton("Browse...")
        browse_photo_btn.clicked.connect(self._browse_photo_root)
        photo_root_layout.addWidget(browse_photo_btn)

        paths_layout.addRow("Photo Root:", photo_root_layout)

        # Data directory
        data_dir_layout = QHBoxLayout()
        self.data_dir_edit = QLineEdit()
        self.data_dir_edit.setReadOnly(True)
        self.data_dir_edit.setPlaceholderText("(Default: inside photo root)")
        data_dir_layout.addWidget(self.data_dir_edit, stretch=1)

        browse_data_btn = QPushButton("Browse...")
        browse_data_btn.clicked.connect(self._browse_data_dir)
        data_dir_layout.addWidget(browse_data_btn)

        clear_data_btn = QPushButton("Reset")
        clear_data_btn.setToolTip("Use default location (photo_root/.fastlrsearch)")
        clear_data_btn.clicked.connect(self._clear_data_dir)
        data_dir_layout.addWidget(clear_data_btn)

        paths_layout.addRow("Data Directory:", data_dir_layout)

        # Path info
        self.data_info_label = QLabel()
        self.data_info_label.setStyleSheet("color: #888; font-size: 11px;")
        self.data_info_label.setWordWrap(True)
        paths_layout.addRow("", self.data_info_label)

        layout.addWidget(paths_group)

        # === Indexing Group ===
        index_group = QGroupBox("Photo Indexing")
        index_layout = QVBoxLayout(index_group)

        index_info = QLabel(
            "Indexing scans your photo root directory and creates searchable embeddings.\n"
            "This runs in the background - you can search while indexing is in progress."
        )
        index_info.setStyleSheet("color: #aaa; font-size: 11px;")
        index_info.setWordWrap(True)
        index_layout.addWidget(index_info)

        index_btn_layout = QHBoxLayout()

        # Show appropriate button based on indexing state
        if self._indexing_running:
            if self._indexing_paused:
                self.index_button = QPushButton("Resume Indexing")
                self.index_button.clicked.connect(self._on_resume_indexing)
            else:
                self.index_button = QPushButton("Pause Indexing")
                self.index_button.clicked.connect(self._on_pause_indexing)

            # Add status indicator
            status_label = QLabel("Indexing in progress..." if not self._indexing_paused else "Indexing paused")
            status_label.setStyleSheet("color: #4a9; font-size: 11px;" if not self._indexing_paused else "color: #a94; font-size: 11px;")
            index_btn_layout.addWidget(status_label)
        else:
            self.index_button = QPushButton("Start Indexing")
            self.index_button.clicked.connect(self._on_start_indexing)

        index_btn_layout.addWidget(self.index_button)
        index_btn_layout.addStretch()

        index_layout.addLayout(index_btn_layout)

        # Rebuild button (separate row)
        rebuild_layout = QHBoxLayout()
        self.rebuild_button = QPushButton("Rebuild Index...")
        self.rebuild_button.setToolTip("Delete all index data and start fresh")
        self.rebuild_button.clicked.connect(self._on_rebuild_index)
        # Disable rebuild while indexing is running
        self.rebuild_button.setEnabled(not self._indexing_running)
        rebuild_layout.addWidget(self.rebuild_button)
        rebuild_layout.addStretch()

        index_layout.addLayout(rebuild_layout)

        layout.addWidget(index_group)

        # === API Server Group ===
        api_group = QGroupBox("API Server")
        api_layout = QFormLayout(api_group)
        api_layout.setSpacing(12)

        self.api_port_spin = QSpinBox()
        self.api_port_spin.setRange(1024, 65535)
        self.api_port_spin.setValue(settings.api_port)
        self.api_port_spin.setToolTip("Port for the API server (requires restart)")
        api_layout.addRow("Port:", self.api_port_spin)

        api_info = QLabel(f"API server runs at http://localhost:{settings.api_port}")
        api_info.setStyleSheet("color: #888; font-size: 11px;")
        api_layout.addRow("", api_info)
        self.api_info_label = api_info
        self.api_port_spin.valueChanged.connect(self._update_api_info)

        layout.addWidget(api_group)

        # Spacer
        layout.addStretch()

        # Note about restart
        note_label = QLabel(
            "Note: Path changes require restart to take full effect.\n"
            "Settings saved to: ~/.config/fastlrsearch/settings.json"
        )
        note_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(note_label)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_current_settings(self):
        """Load current settings into the form."""
        self.photo_root_edit.setText(str(settings.photo_root))

        if settings.data_dir_override:
            self.data_dir_edit.setText(str(settings.data_dir_override))
        else:
            self.data_dir_edit.setText("")

        self._update_data_info()

    def _update_data_info(self):
        """Update the data directory info label."""
        photo_root = self.photo_root_edit.text()
        data_dir = self.data_dir_edit.text()

        if data_dir:
            self.data_info_label.setText(f"Using custom data directory: {data_dir}")
        else:
            default_path = Path(photo_root) / ".fastlrsearch" if photo_root else "(unknown)"
            self.data_info_label.setText(f"Using default: {default_path}")

    def _update_api_info(self):
        """Update the API info label when port changes."""
        port = self.api_port_spin.value()
        self.api_info_label.setText(f"API server runs at http://localhost:{port}")

    def _browse_photo_root(self):
        """Open directory picker for photo root."""
        current = self.photo_root_edit.text()
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Photo Root Directory",
            current if Path(current).exists() else str(Path.home()),
        )
        if directory:
            self.photo_root_edit.setText(directory)
            self._update_data_info()

    def _browse_data_dir(self):
        """Open directory picker for data directory."""
        current = self.data_dir_edit.text() or self.photo_root_edit.text()
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Data Directory",
            current if Path(current).exists() else str(Path.home()),
        )
        if directory:
            self.data_dir_edit.setText(directory)
            self._update_data_info()

    def _clear_data_dir(self):
        """Clear custom data directory (use default)."""
        self.data_dir_edit.setText("")
        self._update_data_info()

    def _on_start_indexing(self):
        """Start indexing and close dialog."""
        # Save settings first
        if self._save_settings():
            self.start_indexing.emit()
            self.accept()

    def _on_pause_indexing(self):
        """Pause indexing and close dialog."""
        self.pause_indexing.emit()
        self.accept()

    def _on_resume_indexing(self):
        """Resume indexing and close dialog."""
        self.resume_indexing.emit()
        self.accept()

    def _on_rebuild_index(self):
        """Rebuild index from scratch after confirmation."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.warning(
            self,
            "Rebuild Index",
            "This will delete all index data and thumbnails, then start fresh indexing.\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.rebuild_index.emit()
            self.accept()

    def _save_and_accept(self):
        """Save settings and close dialog."""
        if self._save_settings():
            self.settings_changed.emit()
            self.accept()

    def _save_settings(self) -> bool:
        """Save settings to config file. Returns True on success."""
        import json

        new_photo_root = Path(self.photo_root_edit.text())
        data_dir_text = self.data_dir_edit.text().strip()
        new_data_dir = Path(data_dir_text) if data_dir_text else None

        # Validate photo root
        if not new_photo_root.exists():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "Invalid Directory",
                f"Photo root directory does not exist:\n{new_photo_root}",
            )
            return False

        # Validate data dir if set
        if new_data_dir and not new_data_dir.parent.exists():
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "Invalid Directory",
                f"Data directory parent does not exist:\n{new_data_dir.parent}",
            )
            return False

        # Save to config file
        config_dir = Path.home() / ".config" / "fastlrsearch"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "settings.json"

        # Load existing settings
        existing = {}
        if config_file.exists():
            try:
                existing = json.loads(config_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Update settings
        existing["photo_root"] = str(new_photo_root)
        if new_data_dir:
            existing["data_dir_override"] = str(new_data_dir)
        elif "data_dir_override" in existing:
            del existing["data_dir_override"]

        # API port
        new_api_port = self.api_port_spin.value()
        existing["api_port"] = new_api_port

        # Write back
        config_file.write_text(json.dumps(existing, indent=2))

        # Update runtime settings
        settings.photo_root = new_photo_root
        settings.data_dir_override = new_data_dir
        settings.api_port = new_api_port

        return True
