"""System Tray / macOS Menu Bar Controller.

Provides system tray integration (status item on macOS menu bar, tray icon on Windows)
with quick actions: Start/Pause, Target Window selection, Settings, and Quit.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

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

        self.update_manager = UpdateManager()
        self._update_action: Optional[QAction] = None
        self._update_worker: Optional[UpdateCheckWorker] = None

        self._setup_menu()
        self._tray_icon.setContextMenu(self._menu)

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

    def set_active(self, active: bool) -> None:
        """Set active translation state and update toggle action text."""
        self._is_active = active
        self.toggle_action.setText("Pause Translation" if self._is_active else "Start Translation")

    def check_for_updates_background(self) -> None:
        """Initiate non-blocking background update check."""
        self._update_worker = UpdateCheckWorker(self.update_manager, self)
        self._update_worker.check_finished.connect(self._on_background_update_checked)
        self._update_worker.start()

    def _on_background_update_checked(self, info: UpdateInfo) -> None:
        """Callback when background update check finishes."""
        if not info.has_update:
            return

        if self.config_manager.config.auto_install_updates:
            # Auto-install silently / automatically
            self._trigger_update_flow(info, prompt=False)
        else:
            self._show_update_action(info)

    def _show_update_action(self, info: UpdateInfo) -> None:
        """Display 'Update Available' banner action at the top of the menu."""
        if self._update_action is None:
            self._update_action = QAction(f"✨ Update Available ({info.latest_commit})", self._menu)
            self._update_action.triggered.connect(lambda: self._trigger_update_flow(info, prompt=True))
            # Insert before first action
            first_action = self._menu.actions()[0] if self._menu.actions() else None
            if first_action:
                self._menu.insertAction(first_action, self._update_action)
                self._menu.insertSeparator(first_action)
            else:
                self._menu.addAction(self._update_action)

            # Show desktop notification via TrayIcon if supported
            if QSystemTrayIcon.supportsMessages():
                self._tray_icon.showMessage(
                    "Subtitle Translator",
                    f"New version available ({info.latest_commit})!\nClick tray menu to install.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )

    def _trigger_update_flow(self, info: UpdateInfo, prompt: bool = True) -> None:
        """Execute update confirmation and progress dialog."""
        if prompt:
            confirm = QMessageBox.question(
                None,
                "Update Subtitle Translator",
                f"A new version is available ({info.current_commit} → {info.latest_commit}).\n\n"
                "Would you like to install the update and restart the application now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        dialog = UpdateProgressDialog(self.update_manager)
        dialog.start_update()

    def _populate_windows_menu(self) -> None:
        """Dynamically populate list of active desktop application windows."""
        for act in self.window_menu.actions():
            act.deleteLater()
        self.window_menu.clear()

        # Default Full Screen option
        full_screen_action = QAction("Entire Screen (Full Display)", self.window_menu)
        full_screen_action.triggered.connect(lambda checked: self.window_selected.emit(None))
        self.window_menu.addAction(full_screen_action)
        self.window_menu.addSeparator()

        if self.capture_driver is None:
            return

        windows = self.capture_driver.list_windows()
        for win in windows[:15]:  # Top 15 visible windows
            title = win.title.strip() or win.owner_name
            label = f"{win.owner_name}: {title[:35]}"
            action = QAction(label, self.window_menu)
            action.triggered.connect(lambda checked, w=win: self.window_selected.emit(w))
            self.window_menu.addAction(action)
