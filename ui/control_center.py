"""Unified Control Center Dialog for Subtitle Translator.

Replaces multi-level tray context menus with an interactive, modern,
single-click control window directly accessible from the Menu Bar / System Tray.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, pyqtSignal
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
from core.translate.languages import BIG_5_LANGUAGES
from core.translate.models import RECOMMENDED_MODELS, ModelManager
from core.translate.router import TranslationRouter, normalize_lang_code
from core.updater import UpdateInfo, UpdateManager
from ui.model_dialog import ModelDownloadProgressDialog
from ui.styles import MODERN_DARK_THEME
from ui.updater_dialog import UpdateCheckWorker, UpdateProgressDialog

logger = logging.getLogger("subtitle_translator.ui.control_center")


class StandbyCaptureSignals(QObject):
    """Signals for asynchronous standby screen/window capture."""

    frame_ready = pyqtSignal(object)


class StandbyCaptureTask(QRunnable):
    """Off-thread task for grabbing preview frames without blocking the Qt GUI thread."""

    def __init__(self, capture_fn, signals: StandbyCaptureSignals) -> None:
        super().__init__()
        self.capture_fn = capture_fn
        self.signals = signals

    def run(self) -> None:
        try:
            img = self.capture_fn()
            self.signals.frame_ready.emit(img)
        except Exception as e:
            logger.debug("Standby background capture failed: %s", e)
            self.signals.frame_ready.emit(None)


class ControlCenterDialog(QDialog):
    """Unified single-window control panel for Subtitle Translator."""

    translation_toggled = pyqtSignal(bool)
    select_roi_requested = pyqtSignal()
    reset_roi_requested = pyqtSignal()
    window_selected = pyqtSignal(object)  # WindowInfo or None
    settings_saved = pyqtSignal()
    quit_requested = pyqtSignal()

    LANGUAGES = BIG_5_LANGUAGES

    def __init__(
        self,
        config_manager: ConfigManager,
        capture_driver: Optional[BaseCapture] = None,
        router: Optional[TranslationRouter] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.capture_driver = capture_driver
        self.router = router if router is not None else TranslationRouter()
        self.model_manager = ModelManager()
        self.autostart_manager = AutostartManager()
        self.update_manager = UpdateManager()

        self._is_active: bool = False
        self._available_windows: List[WindowInfo] = []
        self._check_worker: Optional[UpdateCheckWorker] = None

        self._thread_pool = QThreadPool.globalInstance()
        self._standby_signals = StandbyCaptureSignals()
        self._standby_signals.frame_ready.connect(self._on_standby_frame_received)
        self._standby_busy: bool = False

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(200)  # Smooth 5 FPS standby preview off main thread
        self._preview_timer.timeout.connect(self._on_preview_timer_tick)

        self._init_window()
        self._init_ui()
        self.refresh_state()

    def _init_window(self) -> None:
        """Configure top-level dialog properties."""
        self.setObjectName("SettingsRoot")
        self.setStyleSheet(MODERN_DARK_THEME)
        self.setWindowTitle("Subtitle Translator — Control Center")
        self.setMinimumWidth(560)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowTitleHint
        )
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

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
        self.refresh_windows_btn.setObjectName("SecondaryButton")
        self.refresh_windows_btn.setToolTip("Refresh open application windows")
        self.refresh_windows_btn.setFixedSize(36, 36)
        self.refresh_windows_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_windows_btn.setStyleSheet(
            "QPushButton#SecondaryButton {"
            "  font-size: 16px;"
            "  font-weight: bold;"
            "  padding: 0px;"
            "  text-align: center;"
            "}"
        )
        self.refresh_windows_btn.clicked.connect(self._populate_windows)
        target_row.addWidget(self.refresh_windows_btn)

        capture_layout.addLayout(target_row)

        roi_row = QHBoxLayout()
        self.roi_btn = QPushButton("🎯 Select Region (ROI)...", capture_card)
        self.roi_btn.setObjectName("SecondaryButton")
        self.roi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.roi_btn.clicked.connect(self._on_roi_clicked)
        roi_row.addWidget(self.roi_btn)

        self.reset_roi_btn = QPushButton("✕ Reset", capture_card)
        self.reset_roi_btn.setObjectName("SecondaryButton")
        self.reset_roi_btn.setToolTip("Clear custom ROI and return to full capture area")
        self.reset_roi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_roi_btn.clicked.connect(self._on_reset_roi_clicked)
        self.reset_roi_btn.setVisible(False)  # Visible only when custom ROI is active
        roi_row.addWidget(self.reset_roi_btn)

        self.roi_hint = QLabel("Full capture area active", capture_card)
        self.roi_hint.setObjectName("SubtleHint")
        roi_row.addWidget(self.roi_hint)
        roi_row.addStretch()

        capture_layout.addLayout(roi_row)

        # -------------------------------------------------------------
        # Section 2.5: Real-time Live ROI / Capture Monitor (OBS-Style Preview)
        # -------------------------------------------------------------
        self.preview_container = QFrame(capture_card)
        self.preview_container.setObjectName("PreviewContainer")
        self.preview_container.setStyleSheet(
            "QFrame#PreviewContainer {"
            "  background-color: #0A0D14;"
            "  border: 1px solid #1F2937;"
            "  border-radius: 8px;"
            "  padding: 4px;"
            "}"
        )
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(4)

        preview_header_row = QHBoxLayout()
        preview_title = QLabel("LIVE OCR CAPTURE MONITOR", self.preview_container)
        preview_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #00E5FF; letter-spacing: 0.5px;")
        preview_header_row.addWidget(preview_title)

        self.preview_fps_label = QLabel("STANDBY", self.preview_container)
        self.preview_fps_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #10B981;")
        preview_header_row.addStretch()
        preview_header_row.addWidget(self.preview_fps_label)
        preview_layout.addLayout(preview_header_row)

        self.preview_screen = QLabel(self.preview_container)
        self.preview_screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_screen.setFixedHeight(95)
        self.preview_screen.setStyleSheet(
            "background-color: #000000; border-radius: 4px; color: #6B7280; font-size: 11px;"
        )
        self.preview_screen.setText("Loading live ROI capture feed...")
        preview_layout.addWidget(self.preview_screen)

        capture_layout.addWidget(self.preview_container)
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

        # Packs Table / Manager
        packs_header_row = QHBoxLayout()
        packs_label = QLabel("Installed Language Packs:", lang_card)
        packs_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #9CA3AF;")
        packs_header_row.addWidget(packs_label)
        packs_header_row.addStretch()

        self.download_all_btn = QPushButton("Download All (~450 MB)", lang_card)
        self.download_all_btn.setObjectName("SecondaryButton")
        self.download_all_btn.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.download_all_btn.clicked.connect(self._on_download_all_clicked)
        packs_header_row.addWidget(self.download_all_btn)
        lang_layout.addLayout(packs_header_row)

        self.packs_table = QTableWidget(lang_card)
        self.packs_table.setColumnCount(3)
        self.packs_table.setHorizontalHeaderLabels(["Language Pack", "Status / Size", "Action"])
        self.packs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.packs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.packs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.packs_table.verticalHeader().setVisible(False)
        self.packs_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.packs_table.setFixedHeight(130)
        self.packs_table.setStyleSheet("font-size: 11px;")
        lang_layout.addWidget(self.packs_table)

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

        # Source / Target Lang (fallback safely if config holds deprecated pre-M2 code)
        s_idx = self.source_lang_combo.findData(cfg.source_language)
        if s_idx >= 0:
            self.source_lang_combo.blockSignals(True)
            self.source_lang_combo.setCurrentIndex(s_idx)
            self.source_lang_combo.blockSignals(False)
        else:
            self.source_lang_combo.setCurrentIndex(0)
            self.config_manager.update(source_language=self.source_lang_combo.currentData())

        t_idx = self.target_lang_combo.findData(cfg.target_language)
        if t_idx >= 0:
            self.target_lang_combo.blockSignals(True)
            self.target_lang_combo.setCurrentIndex(t_idx)
            self.target_lang_combo.blockSignals(False)
        else:
            # Choose a target distinct from source language
            current_src = normalize_lang_code(self.source_lang_combo.currentData() or "en")
            fallback_tgt = "id" if current_src == "en" else "en"
            t_idx_fb = self.target_lang_combo.findData(fallback_tgt)
            if t_idx_fb >= 0:
                self.target_lang_combo.setCurrentIndex(t_idx_fb)
            self.config_manager.update(target_language=fallback_tgt)

        # Refresh target windows
        self._populate_windows()

        # Refresh model status and packs table
        self._refresh_model_status()
        self._refresh_packs_table()

    def _populate_windows(self) -> None:
        """Enumerate application windows and populate target combobox, preserving active selection."""
        # Save previous selected window ID / identity
        prev_data = self.window_combo.currentData()
        prev_win_id = getattr(prev_data, "window_id", None) if prev_data is not None else None

        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem("Entire Screen (Full Display)", None)

        matched_index = 0
        if self.capture_driver is not None:
            try:
                self._available_windows = self.capture_driver.list_windows()
                for idx, win in enumerate(self._available_windows[:15], start=1):
                    title = win.title.strip() or win.owner_name
                    label = f"{win.owner_name}: {title[:32]}"
                    self.window_combo.addItem(label, win)
                    if prev_win_id is not None and getattr(win, "window_id", None) == prev_win_id:
                        matched_index = idx
            except Exception as e:
                logger.debug("Failed to list windows: %s", e)

        # Restore previously selected window if it is still open
        if matched_index > 0:
            self.window_combo.setCurrentIndex(matched_index)

        self.window_combo.blockSignals(False)

    def showEvent(self, event) -> None:
        """Start preview timer and take immediate frame when window opens."""
        super().showEvent(event)
        self._preview_timer.start()
        self._on_preview_timer_tick()

    def hideEvent(self, event) -> None:
        """Stop preview timer to conserve CPU when window is closed."""
        super().hideEvent(event)
        self._preview_timer.stop()

    def _on_preview_timer_tick(self) -> None:
        """Dispatch standby frame capture off the main thread to prevent UI freezing."""
        if not self.isVisible() or self._is_active or self._standby_busy:
            return

        crop = None
        roi_data = self.config_manager.config.custom_roi
        if isinstance(roi_data, (list, tuple)) and len(roi_data) == 4:
            try:
                crop = Rect(*(int(x) for x in roi_data))
            except (ValueError, TypeError):
                crop = None

        win_info = self.window_combo.currentData()
        target_win_id = win_info.window_id if win_info is not None else None

        self._standby_busy = True

        def _do_capture():
            if target_win_id is not None:
                try:
                    frame = self.capture_driver.grab_window(target_win_id, crop_rect=crop, is_global_coords=True)
                except Exception:
                    frame = self.capture_driver.grab_screen(1, crop_rect=crop)
            else:
                frame = self.capture_driver.grab_screen(1, crop_rect=crop)
            return frame.image if frame is not None else None

        task = StandbyCaptureTask(_do_capture, self._standby_signals)
        self._thread_pool.start(task)

    def _on_standby_frame_received(self, image) -> None:
        """Handle standby frame captured off the main thread."""
        self._standby_busy = False
        if image is not None and self.isVisible() and not self._is_active:
            self.update_live_preview(image, is_live=False)

    def _on_target_window_changed(self, index: int) -> None:
        """Handle window selection change."""
        win = self.window_combo.currentData()
        self.window_selected.emit(win)
        self._on_preview_timer_tick()

    def _on_toggle_clicked(self) -> None:
        """Toggle active translation."""
        self.translation_toggled.emit(not self._is_active)

    def _on_roi_clicked(self) -> None:
        """Trigger ROI selector."""
        self.hide()
        self.select_roi_requested.emit()

    def _on_reset_roi_clicked(self) -> None:
        """Clear active custom ROI."""
        self.reset_roi_requested.emit()
        self._on_preview_timer_tick()

    def set_roi_hint(self, roi_text: str, has_custom_roi: bool = False) -> None:
        """Update ROI description label and reset button visibility."""
        self.roi_hint.setText(roi_text)
        self.reset_roi_btn.setVisible(has_custom_roi)
        self._on_preview_timer_tick()

    def update_live_preview(self, img_bgr, is_live: bool = True) -> None:
        """Update OBS-style real-time ROI monitor feed from captured numpy image."""
        if not self.isVisible() or img_bgr is None or img_bgr.size == 0:
            return

        try:
            from PyQt6.QtGui import QImage, QPixmap
            import cv2

            h, w = img_bgr.shape[:2]
            # Convert BGR to RGB
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            bytes_per_line = 3 * w
            q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(q_img)

            # Scale to fit monitor box while maintaining aspect ratio
            scaled_pix = pix.scaled(
                self.preview_screen.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_screen.setPixmap(scaled_pix)
            if is_live:
                self.preview_fps_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #10B981;")
                self.preview_fps_label.setText(f"{w}x{h} ACTIVE")
            else:
                self.preview_fps_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #00E5FF;")
                self.preview_fps_label.setText(f"{w}x{h} PREVIEW")
        except Exception as e:
            logger.debug("Failed to render preview frame: %s", e)



    def _refresh_model_status(self) -> None:
        """Update model availability badge and download button for active language pair."""
        src = self.source_lang_combo.currentData() or "en"
        tgt = self.target_lang_combo.currentData() or "id"

        # Same language selected (normalize in case regional tags are used)
        if normalize_lang_code(src) == normalize_lang_code(tgt):
            self.model_status_label.setText("Source and Target are the same language")
            self.model_status_label.setStyleSheet("color: #9CA3AF; font-weight: 500;")
            self.model_action_btn.setEnabled(False)
            self.model_action_btn.setVisible(False)
            return

        self.model_action_btn.setVisible(True)
        needed_pairs = self.router.required_pairs(src, tgt)

        if not needed_pairs:
            self.model_status_label.setText("No translation route available in catalog")
            self.model_status_label.setStyleSheet("color: #F87171; font-weight: 500;")
            self.model_action_btn.setEnabled(False)
            self.model_action_btn.setText("Unavailable")
            self.model_action_btn.setObjectName("SecondaryButton")
            self.model_action_btn.style().unpolish(self.model_action_btn)
            self.model_action_btn.style().polish(self.model_action_btn)
            return

        # Direct 1-hop
        if len(needed_pairs) == 1:
            hop_pair = needed_pairs[0]
            installed = self.model_manager.is_installed(hop_pair)
            meta = RECOMMENDED_MODELS.get(hop_pair)

            if meta is None and not installed:
                self.model_status_label.setText(f"⚠ Direct model '{hop_pair}' not available in catalog")
                self.model_status_label.setStyleSheet("color: #F87171; font-weight: 500;")
                self.model_action_btn.setEnabled(False)
                self.model_action_btn.setText("Unavailable")
                self.model_action_btn.setObjectName("SecondaryButton")
            elif installed:
                disk_mb = self.model_manager.get_disk_size_mb(hop_pair)
                self.model_status_label.setText(f"✔ Ready: Direct {hop_pair} ({disk_mb} MB on disk)")
                self.model_status_label.setStyleSheet("color: #4ADE80; font-weight: 500;")
                self.model_action_btn.setEnabled(True)
                self.model_action_btn.setText("Delete")
                self.model_action_btn.setObjectName("TableDeleteButton")
            else:
                size_str = f"~{meta.approx_size_mb} MB" if meta else ""
                self.model_status_label.setText(f"⚠ Model not downloaded ({size_str})")
                self.model_status_label.setStyleSheet("color: #FBBF24; font-weight: 500;")
                self.model_action_btn.setEnabled(True)
                self.model_action_btn.setText("Download")
                self.model_action_btn.setObjectName("PrimaryButton")
        else:
            # 2-hop Pivot: e.g. ja -> en -> id
            hop1_pair = needed_pairs[0]
            hop2_pair = needed_pairs[1]
            h1_installed = self.model_manager.is_installed(hop1_pair)
            h2_installed = self.model_manager.is_installed(hop2_pair)

            if h1_installed and h2_installed:
                total_mb = round(self.model_manager.get_disk_size_mb(hop1_pair) + self.model_manager.get_disk_size_mb(hop2_pair), 2)
                self.model_status_label.setText(f"✔ Ready: Pivot ({hop1_pair} + {hop2_pair}, {total_mb} MB)")
                self.model_status_label.setStyleSheet("color: #4ADE80; font-weight: 500;")
                self.model_action_btn.setEnabled(True)
                self.model_action_btn.setText("Delete All")
                self.model_action_btn.setObjectName("TableDeleteButton")
            else:
                missing = [p for p in needed_pairs if not self.model_manager.is_installed(p)]
                unobtainable = [p for p in missing if p not in RECOMMENDED_MODELS]
                if unobtainable:
                    self.model_status_label.setText(f"⚠ Missing model(s): {', '.join(unobtainable)}")
                    self.model_status_label.setStyleSheet("color: #F87171; font-weight: 500;")
                    self.model_action_btn.setEnabled(False)
                    self.model_action_btn.setText("Unavailable")
                    self.model_action_btn.setObjectName("SecondaryButton")
                else:
                    self.model_status_label.setText(f"⚠ Pivot requires: {', '.join(missing)}")
                    self.model_status_label.setStyleSheet("color: #FBBF24; font-weight: 500;")
                    self.model_action_btn.setEnabled(True)
                    self.model_action_btn.setText("Download")
                    self.model_action_btn.setObjectName("PrimaryButton")

        self.model_action_btn.style().unpolish(self.model_action_btn)
        self.model_action_btn.style().polish(self.model_action_btn)

    def _on_current_model_action_clicked(self) -> None:
        """Handle Download or Delete for the currently selected language pair or its pivot hops."""
        src = self.source_lang_combo.currentData() or "en"
        tgt = self.target_lang_combo.currentData() or "id"
        needed_pairs = self.router.required_pairs(src, tgt)
        if not needed_pairs:
            return

        all_installed = all(self.model_manager.is_installed(p) for p in needed_pairs)

        if all_installed:
            confirm = QMessageBox.question(
                self,
                "Delete Model",
                f"Delete offline translation model(s) for {', '.join(needed_pairs)}?\nThis will reclaim disk space.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                for p in needed_pairs:
                    self.model_manager.delete_model(p)
                self._refresh_model_status()
        else:
            # Pre-validate all missing hops against catalog before attempting downloads
            missing_pairs = [p for p in needed_pairs if not self.model_manager.is_installed(p)]
            unobtainable = [p for p in missing_pairs if p not in RECOMMENDED_MODELS]
            if unobtainable:
                QMessageBox.warning(
                    self,
                    "Model Unavailable",
                    f"Model(s) {', '.join(unobtainable)} are not available in catalog.\nPlease select a supported route.",
                )
                return

            for p in missing_pairs:
                dialog = ModelDownloadProgressDialog(self.model_manager, p, self)
                dialog.start_download()
            self._refresh_model_status()
            self._refresh_packs_table()

    def _refresh_packs_table(self) -> None:
        """Populate the atomic language packs table with status and action buttons."""
        packs = self.model_manager.list_packs_status()
        self.packs_table.setRowCount(len(packs))

        for row, pack in enumerate(packs):
            pack_id = pack["pack_id"]
            installed = pack["installed"]
            partially_installed = pack.get("partially_installed", False)
            is_core = pack.get("is_core", False)

            name_item = QTableWidgetItem(pack["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.packs_table.setItem(row, 0, name_item)

            if installed:
                status_text = f"✔ Installed ({pack['installed_size_mb']} MB)"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(QColor("#4ADE80"))
                btn = QPushButton("Delete", self.packs_table)
                btn.setObjectName("TableDeleteButton")
                if is_core:
                    btn.setToolTip("Core default pack cannot be deleted")
                    btn.setEnabled(False)
                else:
                    btn.clicked.connect(lambda _, pid=pack_id: self._on_delete_pack_clicked(pid))
            elif partially_installed:
                status_text = f"⚠ Incomplete ({pack['installed_size_mb']} MB)"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(QColor("#FBBF24"))
                btn = QPushButton("Fix / Resume", self.packs_table)
                btn.setObjectName("PrimaryButton")
                btn.clicked.connect(lambda _, pid=pack_id: self._on_download_pack_clicked(pid))
            else:
                status_text = f"Available (~{pack['approx_size_mb']} MB)"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(QColor("#9CA3AF"))
                btn = QPushButton("Download", self.packs_table)
                btn.setObjectName("TableDownloadButton")
                btn.clicked.connect(lambda _, pid=pack_id: self._on_download_pack_clicked(pid))

            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.packs_table.setItem(row, 1, status_item)
            self.packs_table.setCellWidget(row, 2, btn)

    def _on_download_pack_clicked(self, pack_id: str) -> None:
        """Download all translation pairs belonging to an atomic language pack."""
        from core.translate.packs import ATOMIC_LANGUAGE_PACKS
        pack = ATOMIC_LANGUAGE_PACKS.get(pack_id)
        if not pack:
            return

        for pair_id in pack.translation_pairs:
            if not self.model_manager.is_installed(pair_id):
                dialog = ModelDownloadProgressDialog(self.model_manager, pair_id, self)
                dialog.start_download()
                # Stop subsequent dialogs if user cancelled or download failed
                if not self.model_manager.is_installed(pair_id):
                    break

        self._refresh_model_status()
        self._refresh_packs_table()

    def _on_delete_pack_clicked(self, pack_id: str) -> None:
        """Delete an atomic language pack after user confirmation."""
        from core.translate.packs import ATOMIC_LANGUAGE_PACKS
        pack = ATOMIC_LANGUAGE_PACKS.get(pack_id)
        name = pack.name if pack else pack_id

        confirm = QMessageBox.question(
            self,
            "Delete Language Pack",
            f"Are you sure you want to delete '{name}'?\nThis will remove local weights and free disk space.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success, msg = self.model_manager.delete_pack(pack_id)
            if not success:
                QMessageBox.warning(self, "Delete Failed", msg)
            self._refresh_model_status()
            self._refresh_packs_table()

    def _on_download_all_clicked(self) -> None:
        """Download all recommended Big 5 models for complete offline readiness."""
        confirm = QMessageBox.question(
            self,
            "Download All Language Packs",
            "Download all offline models for The Big 5 (~450 MB)?\n\n"
            "This ensures complete offline translation coverage across all language pairs.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        for pair_id in RECOMMENDED_MODELS.keys():
            if not self.model_manager.is_installed(pair_id):
                dialog = ModelDownloadProgressDialog(self.model_manager, pair_id, self)
                dialog.start_download()
                # Stop batch loop if user cancelled or download failed
                if not self.model_manager.is_installed(pair_id):
                    break

        self._refresh_model_status()
        self._refresh_packs_table()

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
