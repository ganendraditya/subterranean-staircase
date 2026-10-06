"""Worker threads and UI dialog for downloading and deleting offline models."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.translate.models import ModelManager
from ui.styles import MODERN_DARK_THEME

logger = logging.getLogger("subtitle_translator.ui.model_dialog")


class ModelDownloadWorker(QThread):
    """Background worker for downloading a model without blocking the UI."""
    progress_updated = pyqtSignal(int, int, str)  # current_bytes, total_bytes, message
    download_finished = pyqtSignal(bool, str)     # success, message

    def __init__(self, model_manager: ModelManager, pair_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.model_manager = model_manager
        self.pair_id = pair_id

    def run(self) -> None:
        def _cb(curr: int, total: int, msg: str) -> None:
            self.progress_updated.emit(curr, total, msg)

        success, message = self.model_manager.download_model(self.pair_id, progress_cb=_cb)
        self.download_finished.emit(success, message)


class ModelDownloadProgressDialog(QDialog):
    """Progress dialog for downloading a specific model pair."""

    def __init__(self, model_manager: ModelManager, pair_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.model_manager = model_manager
        self.pair_id = pair_id
        self.worker: Optional[ModelDownloadWorker] = None

        self.setWindowTitle("Downloading Translation Model")
        self.setStyleSheet(MODERN_DARK_THEME)
        self.setFixedSize(400, 160)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.status_label = QLabel(f"Preparing to download {pair_id}...")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.reject)
        layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def start_download(self) -> None:
        """Start background download."""
        self.worker = ModelDownloadWorker(self.model_manager, self.pair_id, self)
        self.worker.progress_updated.connect(self._on_progress)
        self.worker.download_finished.connect(self._on_finished)
        self.worker.start()
        self.exec()

    def _on_progress(self, current_bytes: int, total_bytes: int, msg: str) -> None:
        self.status_label.setText(msg)
        if total_bytes > 0:
            pct = int((current_bytes / total_bytes) * 100)
            self.progress_bar.setValue(min(100, pct))

    def _on_finished(self, success: bool, message: str) -> None:
        self.close_btn.setEnabled(True)
        if success:
            self.status_label.setText("Model downloaded successfully.")
            self.progress_bar.setValue(100)
            self.accept()
        else:
            self.status_label.setText(f"Failed: {message}")
            QMessageBox.critical(self, "Download Failed", message)
