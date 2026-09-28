"""System Tray / macOS Menu Bar Controller.

Provides system tray integration (status item on macOS menu bar, tray icon on Windows)
that opens the Unified Control Center on click, with an optional quick right-click context menu.
"""

from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from core.capture.base import BaseCapture
from core.config import ConfigManager
from core.updater import UpdateInfo, UpdateManager
from ui.updater_dialog import UpdateCheckWorker, UpdateProgressDialog


def create_default_tray_icon() -> QIcon:
    """Generate a clean 32x32 subtitle badge tray icon in memory without external assets."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Rounded background badge
    painter.setPen(QColor("#00E5FF"))
    painter.setBrush(QColor("#1A1A1A"))
    painter.drawRoundedRect(2, 4, 28, 24, 4.0, 4.0)

    # 'ST' text (Subtitle Translator)
    painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
    painter.setPen(QColor("#00E5FF"))
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), "ST")
    painter.end()

    return QIcon(pixmap)


class TrayController(QObject):
    """Manages OS System Tray Menu Bar icon and routes clicks to the Control Center."""

    control_center_requested = pyqtSignal()
    translation_toggled = pyqtSignal(bool)
    quit_requested = pyqtSignal()

    def __init__(
        self,
        config_manager: ConfigManager,
        capture_driver: Optional[BaseCapture] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.capture_driver = capture_driver
        self._is_active: bool = False

        self._tray_icon = QSystemTrayIcon(create_default_tray_icon(), self)
        self._tray_icon.setToolTip("Subtitle Translator")

        self.update_manager = UpdateManager()
        self._update_worker: Optional[UpdateCheckWorker] = None

        # Setup minimal right-click context menu
        self._context_menu = QMenu()
        self._setup_context_menu()

        # Connect click activation
        self._tray_icon.activated.connect(self._on_tray_activated)

        # On non-macOS platforms, set context menu for right clicks
        if sys.platform != "darwin":
            self._tray_icon.setContextMenu(self._context_menu)

        if self.config_manager.config.check_updates:
            self.check_for_updates_background()

    def show(self) -> None:
        """Display the system tray icon."""
        self._tray_icon.show()

    def hide(self) -> None:
        """Hide the system tray icon."""
        self._tray_icon.hide()

    def close(self) -> None:
        """Clean teardown for workers and tray icon."""
        if self._update_worker is not None and self._update_worker.isRunning():
            self._update_worker.wait(1000)
        self.hide()

    def _setup_context_menu(self) -> None:
        """Construct a minimal fallback context menu for right-click actions."""
        self._context_menu.clear()

        # 1. Open Control Center
        self.open_action = QAction("Open Control Center", self)
        self.open_action.triggered.connect(self.control_center_requested.emit)
        self._context_menu.addAction(self.open_action)

        self._context_menu.addSeparator()

        # 2. Toggle Translation
        self.toggle_action = QAction("Start Translation", self)
        self.toggle_action.triggered.connect(self._on_toggle)
        self._context_menu.addAction(self.toggle_action)

        self._context_menu.addSeparator()

        # 3. Quit
        self.quit_action = QAction("Quit Subtitle Translator", self)
        self.quit_action.triggered.connect(self.quit_requested.emit)
        self._context_menu.addAction(self.quit_action)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle clicks on the tray / status bar icon."""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            # Primary left-click directly opens/toggles the Control Center
            self.control_center_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # Secondary / right click opens minimal menu
            self._context_menu.exec(QCursor.pos())

    def _on_toggle(self) -> None:
        """Handle Start / Pause translation toggle from context menu."""
        self.set_active(not self._is_active)
        self.translation_toggled.emit(self._is_active)

    def set_active(self, active: bool) -> None:
        """Set active translation state and update toggle action text."""
        self._is_active = active
        self.toggle_action.setText("Pause Translation" if self._is_active else "Start Translation")

    def check_for_updates_background(self) -> None:
        """Initiate non-blocking background update check."""
        # Optional background update check logic
        pass
