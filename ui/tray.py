"""System Tray / macOS Menu Bar Controller.

Provides system tray integration (status item on macOS menu bar, tray icon on Windows)
with quick actions: Start/Pause, Target Window selection, Settings, and Quit.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from core.capture.base import BaseCapture
from core.config import ConfigManager


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
    """Manages OS System Tray Menu Bar icon, window picker submenu, and quick toggles."""

    # Signals
    translation_toggled = pyqtSignal(bool)
    select_roi_requested = pyqtSignal()
    window_selected = pyqtSignal(object)  # WindowInfo or None for full screen
    settings_requested = pyqtSignal()
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
        self._tray_icon.setToolTip("Subtitle Translator V1")
        self._menu = QMenu()

        self._setup_menu()
        self._tray_icon.setContextMenu(self._menu)

    def show(self) -> None:
        """Display the system tray icon."""
        self._tray_icon.show()

    def hide(self) -> None:
        """Hide the system tray icon."""
        self._tray_icon.hide()

    def _setup_menu(self) -> None:
        """Construct the tray menu items."""
        self._menu.clear()

        # 1. Start/Stop Toggle Action
        self.toggle_action = QAction("Start Translation", self)
        self.toggle_action.triggered.connect(self._on_toggle)
        self._menu.addAction(self.toggle_action)

        # 2. Select Custom ROI
        self.roi_action = QAction("Select Screen Region (ROI)...", self)
        self.roi_action.triggered.connect(self.select_roi_requested.emit)
        self._menu.addAction(self.roi_action)

        # 3. Submenu: Target Window
        self.window_menu = self._menu.addMenu("Target Window")
        self.window_menu.aboutToShow.connect(self._populate_windows_menu)

        self._menu.addSeparator()

        # 4. Settings Dialog Action
        self.settings_action = QAction("Settings...", self)
        self.settings_action.triggered.connect(self.settings_requested.emit)
        self._menu.addAction(self.settings_action)

        self._menu.addSeparator()

        # 5. Quit Action
        self.quit_action = QAction("Quit Subtitle Translator", self)
        self.quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self.quit_action)

    def _on_toggle(self) -> None:
        """Handle Start / Pause translation toggle."""
        self._is_active = not self._is_active
        self.toggle_action.setText("Pause Translation" if self._is_active else "Start Translation")
        self.translation_toggled.emit(self._is_active)

    def _populate_windows_menu(self) -> None:
        """Dynamically populate list of active desktop application windows."""
        self.window_menu.clear()

        # Default Full Screen option
        full_screen_action = QAction("Entire Screen (Full Display)", self)
        full_screen_action.triggered.connect(lambda checked: self.window_selected.emit(None))
        self.window_menu.addAction(full_screen_action)
        self.window_menu.addSeparator()

        if self.capture_driver is None:
            return

        windows = self.capture_driver.list_windows()
        for win in windows[:15]:  # Top 15 visible windows
            title = win.title.strip() or win.owner_name
            label = f"{win.owner_name}: {title[:35]}"
            action = QAction(label, self)
            action.triggered.connect(lambda checked, w=win: self.window_selected.emit(w))
            self.window_menu.addAction(action)
