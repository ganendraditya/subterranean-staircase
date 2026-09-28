"""PyQt6 Update Dialog and background workers for in-app self-updater."""

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

from core.updater import UpdateInfo, UpdateManager
from ui.styles import MODERN_DARK_THEME

logger = logging.getLogger("subtitle_translator.ui.updater")


class UpdateCheckWorker(QThread):
    """Background worker for non-blocking update checking."""
    check_finished = pyqtSignal(object)  # Emits UpdateInfo

    def __init__(self, update_manager: UpdateManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.update_manager = update_manager

    def run(self) -> None:
        info = self.update_manager.check_for_updates()
        self.check_finished.emit(info)


class ApplyUpdateWorker(QThread):
    """Background worker executing git pull and pip install."""
    progress_changed = pyqtSignal(str)
    update_finished = pyqtSignal(bool, str)

    def __init__(self, update_manager: UpdateManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.update_manager = update_manager

    def run(self) -> None:
        success, msg = self.update_manager.apply_update(
            progress_cb=self.progress_changed.emit,
        )
        self.update_finished.emit(success, msg)


class UpdateProgressDialog(QDialog):
    """Modal dialog displaying update installation progress."""

    def __init__(self, update_manager: UpdateManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.update_manager = update_manager
        self.worker: Optional[ApplyUpdateWorker] = None

        self.setWindowTitle("Updating Subtitle Translator")
        self.setStyleSheet(MODERN_DARK_THEME)
        self.setFixedSize(400, 170)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.status_label = QLabel("Initializing update...")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate animated progress
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.reject)
        layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def start_update(self) -> None:
        """Start background update execution."""
        self.worker = ApplyUpdateWorker(self.update_manager, self)
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.update_finished.connect(self._on_finished)
        self.worker.start()
        self.exec()

    def _on_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_finished(self, success: bool, message: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.status_label.setText("✔ Update complete! Restarting application...")
            # Automatically restart application
            QMessageBox.information(
                self,
                "Update Complete",
                "Subtitle Translator has been updated successfully.\nThe application will now restart.",
            )
            self.update_manager.restart_app()
        else:
            self.status_label.setText(f"❌ {message}")
            self.close_btn.setEnabled(True)
