"""Unified Control Center Dialog for Subtitle Translator.

Replaces multi-level tray context menus with an interactive, modern,
single-click control window directly accessible from the Menu Bar / System Tray.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.autostart import AutostartManager
from core.capture.base import BaseCapture
from core.config import ConfigManager
from core.contracts import Rect, WindowInfo
from core.translate.models import RECOMMENDED_MODELS, ModelManager
from core.updater import UpdateInfo, UpdateManager
from ui.model_dialog import ModelDownloadProgressDialog
from ui.styles import MODERN_DARK_THEME
from ui.updater_dialog import UpdateCheckWorker, UpdateProgressDialog

logger = logging.getLogger("subtitle_translator.ui.control_center")


class ControlCenterDialog(QDialog):
    """Unified single-window control panel for Subtitle Translator."""

    translation_toggled = pyqtSignal(bool)
    select_roi_requested = pyqtSignal()
    window_selected = pyqtSignal(object)  # WindowInfo or None
    settings_saved = pyqtSignal()
    quit_requested = pyqtSignal()

    LANGUAGES = [
        ("English", "en"),
        ("Indonesian", "id"),
        ("Japanese", "ja"),
        ("Korean", "ko"),
        ("Chinese", "zh"),
        ("French", "fr"),
        ("German", "de"),
        ("Spanish", "es"),
    ]

    def __init__(
        self,
        config_manager: ConfigManager,
        capture_driver: Optional[BaseCapture] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.capture_driver = capture_driver
        self.model_manager = ModelManager()
        self.autostart_manager = AutostartManager()
        self.update_manager = UpdateManager()

        self._is_active: bool = False
        self._available_windows: List[WindowInfo] = []
        self._check_worker: Optional[UpdateCheckWorker] = None

        self._init_window()
        self._init_ui()
        self.refresh_state()

    def _init_window(self) -> None:
        """Configure top-level dialog properties."""
        self.setObjectName("SettingsRoot")
        self.setStyleSheet(MODERN_DARK_THEME)
        self.setWindowTitle("Subtitle Translator — Control Center")
        self.setMinimumWidth(540)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )

    def _init_ui(self) -> None:
        """Construct the unified control center UI sections."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # Section 1: Live Translation Status & Primary Toggle
        # -------------------------------------------------------------
        status_card = QFrame(self)
        status_card.setObjectName("CardPanel")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)

        status_left = QVBoxLayout()
        status_left.setSpacing(4)

        title_label = QLabel("Subtitle Translator", status_card)
        title_label.setObjectName("SectionHeader")
        status_left.addWidget(title_label)

        self.status_badge = QLabel("○ STANDBY", status_card)
        self.status_badge.setObjectName("StatusBadgeStandby")
        status_left.addWidget(self.status_badge)

        status_layout.addLayout(status_left)
        status_layout.addStretch()

        self.toggle_btn = QPushButton("Start Translation", status_card)
        self.toggle_btn.setObjectName("StartButton")
        self.toggle_btn.setMinimumHeight(42)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        status_layout.addWidget(self.toggle_btn)

        main_layout.addWidget(status_card)

        # -------------------------------------------------------------
        # Section 2: Capture Target & Region of Interest (ROI)
        # -------------------------------------------------------------
        capture_card = QFrame(self)
        capture_card.setObjectName("CardPanel")
        capture_layout = QVBoxLayout(capture_card)
        capture_layout.setSpacing(10)

        capture_header = QLabel("Screen & Window Capture", capture_card)
        capture_header.setObjectName("SectionHeader")
        capture_layout.addWidget(capture_header)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        target_label = QLabel("Target:", capture_card)
        target_label.setFixedWidth(55)
        target_row.addWidget(target_label)

        self.window_combo = QComboBox(capture_card)
        self.window_combo.currentIndexChanged.connect(lambda idx: self._on_target_window_changed(idx))
        target_row.addWidget(self.window_combo, stretch=1)

        self.refresh_windows_btn = QPushButton("↻", capture_card)
        self.refresh_windows_btn.setToolTip("Refresh open application windows")
        self.refresh_windows_btn.setFixedWidth(36)
        self.refresh_windows_btn.clicked.connect(self._populate_windows)
        target_row.addWidget(self.refresh_windows_btn)

        capture_layout.addLayout(target_row)

        roi_row = QHBoxLayout()
        self.roi_btn = QPushButton("🎯 Select Screen Region (ROI)...", capture_card)
        self.roi_btn.setObjectName("SecondaryButton")
        self.roi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.roi_btn.clicked.connect(self._on_roi_clicked)
        roi_row.addWidget(self.roi_btn)

        self.roi_hint = QLabel("Full capture area active", capture_card)
        self.roi_hint.setObjectName("SubtleHint")
        roi_row.addWidget(self.roi_hint)
        roi_row.addStretch()

        capture_layout.addLayout(roi_row)
        main_layout.addWidget(capture_card)

        # -------------------------------------------------------------
        # Section 3: Language & Offline Translation Models
        # -------------------------------------------------------------
        lang_card = QFrame(self)
        lang_card.setObjectName("CardPanel")
        lang_layout = QVBoxLayout(lang_card)
        lang_layout.setSpacing(10)

        lang_header = QLabel("Language & Translation Model", lang_card)
        lang_header.setObjectName("SectionHeader")
        lang_layout.addWidget(lang_header)

        lang_select_row = QHBoxLayout()
        lang_select_row.setSpacing(10)

        self.source_lang_combo = QComboBox(lang_card)
        for name, code in self.LANGUAGES:
            self.source_lang_combo.addItem(f"{name} ({code})", code)
        self.source_lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_select_row.addWidget(self.source_lang_combo, stretch=1)

        arrow_label = QLabel("→", lang_card)
        arrow_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #9CA3AF;")
        lang_select_row.addWidget(arrow_label)

        self.target_lang_combo = QComboBox(lang_card)
        for name, code in self.LANGUAGES:
            self.target_lang_combo.addItem(f"{name} ({code})", code)
        self.target_lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_select_row.addWidget(self.target_lang_combo, stretch=1)

        lang_layout.addLayout(lang_select_row)

        # Model Status Row
        self.model_status_frame = QFrame(lang_card)
        self.model_status_frame.setStyleSheet("background-color: #27272A; border-radius: 6px; padding: 6px 10px;")
        model_status_layout = QHBoxLayout(self.model_status_frame)
        model_status_layout.setContentsMargins(6, 4, 6, 4)

        self.model_status_label = QLabel("Checking model status...", self.model_status_frame)
        model_status_layout.addWidget(self.model_status_label, stretch=1)

        self.model_action_btn = QPushButton("Download", self.model_status_frame)
        self.model_action_btn.setObjectName("PrimaryButton")
        self.model_action_btn.clicked.connect(self._on_current_model_action_clicked)
        model_status_layout.addWidget(self.model_action_btn)

        lang_layout.addWidget(self.model_status_frame)
        main_layout.addWidget(lang_card)

        # -------------------------------------------------------------
        # Section 4: Subtitle Appearance & System
        # -------------------------------------------------------------
        settings_card = QFrame(self)
        settings_card.setObjectName("CardPanel")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setSpacing(10)

        settings_header = QLabel("Appearance & Preferences", settings_card)
        settings_header.setObjectName("SectionHeader")
        settings_layout.addWidget(settings_header)

        sliders_row = QHBoxLayout()
        sliders_row.setSpacing(16)

        font_col = QVBoxLayout()
        font_col.addWidget(QLabel("Font Size:"))
        self.font_size_spin = QSpinBox(settings_card)
        self.font_size_spin.setRange(12, 64)
        self.font_size_spin.setValue(self.config_manager.config.overlay.font_size)
        self.font_size_spin.valueChanged.connect(self._save_preferences)
        font_col.addWidget(self.font_size_spin)
        sliders_row.addLayout(font_col)

        fade_col = QVBoxLayout()
        fade_col.addWidget(QLabel("Fade-Out Delay:"))
        self.fade_out_spin = QSpinBox(settings_card)
        self.fade_out_spin.setRange(1, 15)
        self.fade_out_spin.setSuffix(" sec")
        self.fade_out_spin.setValue(int(self.config_manager.config.overlay.fade_out_seconds))
        self.fade_out_spin.valueChanged.connect(self._save_preferences)
        fade_col.addWidget(self.fade_out_spin)
        sliders_row.addLayout(fade_col)

        settings_layout.addLayout(sliders_row)

        # Autostart & Updates
        self.autostart_cb = QCheckBox("Start automatically on system login", settings_card)
        self.autostart_cb.setChecked(
            self.config_manager.config.autostart_on_boot or self.autostart_manager.is_enabled()
        )
        self.autostart_cb.toggled.connect(self._on_autostart_toggled)
        settings_layout.addWidget(self.autostart_cb)

        updates_row = QHBoxLayout()
        self.check_updates_cb = QCheckBox("Check updates on launch", settings_card)
        self.check_updates_cb.setChecked(self.config_manager.config.check_updates)
        self.check_updates_cb.toggled.connect(self._save_preferences)
        updates_row.addWidget(self.check_updates_cb)
        updates_row.addStretch()

        self.check_now_btn = QPushButton("Check Now", settings_card)
        self.check_now_btn.clicked.connect(self._check_updates_now)
        updates_row.addWidget(self.check_now_btn)
        settings_layout.addLayout(updates_row)

        main_layout.addWidget(settings_card)

        # -------------------------------------------------------------
        # Section 5: Footer Actions
        # -------------------------------------------------------------
        footer_layout = QHBoxLayout()

        self.quit_btn = QPushButton("Quit Subtitle Translator", self)
        self.quit_btn.setObjectName("DangerButton")
        self.quit_btn.clicked.connect(self.quit_requested.emit)
        footer_layout.addWidget(self.quit_btn)

        footer_layout.addStretch()

        self.close_btn = QPushButton("Close Control Center", self)
        self.close_btn.setObjectName("PrimaryButton")
        self.close_btn.clicked.connect(self.hide)
        footer_layout.addWidget(self.close_btn)

        main_layout.addLayout(footer_layout)

    def set_active(self, active: bool) -> None:
        """Update live translation status appearance."""
        self._is_active = active
        if active:
            self.status_badge.setText("● TRANSLATING")
            self.status_badge.setObjectName("StatusBadgeActive")
            self.toggle_btn.setText("Pause Translation")
            self.toggle_btn.setObjectName("PauseButton")
        else:
            self.status_badge.setText("○ STANDBY")
            self.status_badge.setObjectName("StatusBadgeStandby")
            self.toggle_btn.setText("Start Translation")
            self.toggle_btn.setObjectName("StartButton")

        # Force stylesheet re-evaluation on updated object names
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)

    def refresh_state(self) -> None:
        """Synchronize UI with persistent configuration and installed models."""
        cfg = self.config_manager.config

        # Source / Target Lang
        s_idx = self.source_lang_combo.findData(cfg.source_language)
        if s_idx >= 0:
            self.source_lang_combo.blockSignals(True)
            self.source_lang_combo.setCurrentIndex(s_idx)
            self.source_lang_combo.blockSignals(False)

        t_idx = self.target_lang_combo.findData(cfg.target_language)
        if t_idx >= 0:
            self.target_lang_combo.blockSignals(True)
            self.target_lang_combo.setCurrentIndex(t_idx)
            self.target_lang_combo.blockSignals(False)

        # Refresh target windows
        self._populate_windows()

        # Refresh model status
        self._refresh_model_status()

    def _populate_windows(self) -> None:
        """Enumerate application windows and populate target combobox."""
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem("Entire Screen (Full Display)", None)

        if self.capture_driver is not None:
            try:
                self._available_windows = self.capture_driver.list_windows()
                for win in self._available_windows[:15]:
                    title = win.title.strip() or win.owner_name
                    label = f"{win.owner_name}: {title[:32]}"
                    self.window_combo.addItem(label, win)
            except Exception as e:
                logger.debug("Failed to list windows: %s", e)

        self.window_combo.blockSignals(False)

    def _on_target_window_changed(self, index: int) -> None:
        """Handle window selection change."""
        win = self.window_combo.currentData()
        self.window_selected.emit(win)

    def _on_toggle_clicked(self) -> None:
        """Toggle active translation."""
        self.translation_toggled.emit(not self._is_active)

    def _on_roi_clicked(self) -> None:
        """Trigger ROI selector."""
        self.hide()
        self.select_roi_requested.emit()

    def set_roi_hint(self, roi_text: str) -> None:
        """Update ROI description label."""
        self.roi_hint.setText(roi_text)

    def _get_current_pair_id(self) -> str:
        src = self.source_lang_combo.currentData() or "en"
        tgt = self.target_lang_combo.currentData() or "id"
        return f"{src}-{tgt}"

    def _refresh_model_status(self) -> None:
        """Update model availability badge and download button for active language pair."""
        pair_id = self._get_current_pair_id()
        installed = self.model_manager.is_installed(pair_id)

        meta = RECOMMENDED_MODELS.get(pair_id)
        size_str = f"~{meta.approx_size_mb} MB" if meta else ""

        if installed:
            disk_mb = self.model_manager.get_disk_size_mb(pair_id)
            self.model_status_label.setText(f"✔ Ready: {pair_id} ({disk_mb} MB on disk)")
            self.model_status_label.setStyleSheet("color: #4ADE80; font-weight: 500;")
            self.model_action_btn.setText("Delete")
            self.model_action_btn.setObjectName("TableDeleteButton")
        else:
            self.model_status_label.setText(f"⚠ Model not downloaded ({size_str})")
            self.model_status_label.setStyleSheet("color: #FBBF24; font-weight: 500;")
            self.model_action_btn.setText("Download")
            self.model_action_btn.setObjectName("PrimaryButton")

        self.model_action_btn.style().unpolish(self.model_action_btn)
        self.model_action_btn.style().polish(self.model_action_btn)

    def _on_current_model_action_clicked(self) -> None:
        """Handle Download or Delete for the currently selected language pair."""
        pair_id = self._get_current_pair_id()
        if self.model_manager.is_installed(pair_id):
            confirm = QMessageBox.question(
                self,
                "Delete Model",
                f"Delete offline translation model for '{pair_id}'?\nThis will reclaim disk space.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.model_manager.delete_model(pair_id)
                self._refresh_model_status()
        else:
            dialog = ModelDownloadProgressDialog(self.model_manager, pair_id, self)
            dialog.start_download()
            self._refresh_model_status()

    def _on_language_changed(self) -> None:
        """Handle source/target language combobox changes."""
        src = self.source_lang_combo.currentData()
        tgt = self.target_lang_combo.currentData()
        if src and tgt:
            self.config_manager.update(source_language=src, target_language=tgt)
            self._refresh_model_status()
            self.settings_saved.emit()

    def _save_preferences(self) -> None:
        """Persist font size, fade-out, and auto-update checks."""
        self.config_manager.update(
            check_updates=self.check_updates_cb.isChecked(),
            overlay={
                "font_size": self.font_size_spin.value(),
                "fade_out_seconds": float(self.fade_out_spin.value()),
            },
        )
        self.settings_saved.emit()

    def _on_autostart_toggled(self, checked: bool) -> None:
        """Toggle system autostart."""
        if checked:
            self.autostart_manager.enable()
        else:
            self.autostart_manager.disable()
        self.config_manager.update(autostart_on_boot=checked)
        self.settings_saved.emit()

    def _check_updates_now(self) -> None:
        """Trigger manual update check."""
        self.check_now_btn.setEnabled(False)
        self.check_now_btn.setText("Checking...")
        self._check_worker = UpdateCheckWorker(self.update_manager, self)
        self._check_worker.check_finished.connect(self._on_update_checked)
        self._check_worker.start()

    def _on_update_checked(self, info: UpdateInfo) -> None:
        """Handle update check completion."""
        self.check_now_btn.setEnabled(True)
        self.check_now_btn.setText("Check Now")
        if info.has_update:
            reply = QMessageBox.information(
                self,
                "Update Available",
                f"A new version of Subtitle Translator is available!\n\nUpdate now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                dialog = UpdateProgressDialog(self.update_manager, self)
                dialog.start_update()
        else:
            QMessageBox.information(self, "Up to Date", "You are running the latest version!")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Pressing Escape hides the control center without quitting."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)
