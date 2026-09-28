"""Subtitle Translator V1 Desktop Application Entrypoint."""

import logging
import sys
from typing import Optional

from PyQt6.QtCore import QDir, QLockFile
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.capture.factory import create_capture_driver
from core.config import ConfigManager
from core.contracts import Rect, WindowInfo
from core.pipeline import PipelineSignals, TranslationPipelineWorker
from ui.control_center import ControlCenterDialog
from ui.overlay import SubtitleOverlayWindow
from ui.region_selector import RegionSelectorWidget
from ui.tray import TrayController

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SubtitleTranslator")


class SubtitleTranslatorApp:
    """Main application orchestrator binding UI, Tray, and Pipeline."""

    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.capture_driver = create_capture_driver()
        self.signals = PipelineSignals()

        # UI Components
        self.overlay = SubtitleOverlayWindow(style_config=self.config_manager.config.overlay)
        self.tray = TrayController(
            config_manager=self.config_manager,
            capture_driver=self.capture_driver,
        )
        self.control_center = ControlCenterDialog(
            config_manager=self.config_manager,
            capture_driver=self.capture_driver,
        )
        self.region_selector: Optional[RegionSelectorWidget] = None

        # Background Worker
        self.worker = TranslationPipelineWorker(
            config_manager=self.config_manager,
            signals=self.signals,
            capture_driver=self.capture_driver,
        )

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect inter-component event listeners."""
        # Pipeline -> Overlay & Logging
        self.signals.subtitle_ready.connect(self.overlay.update_text)
        self.signals.error_occurred.connect(self._on_pipeline_error)

        # Tray -> Control Center & Teardown
        self.tray.control_center_requested.connect(self._toggle_control_center)
        self.tray.translation_toggled.connect(self._on_translation_toggled)
        self.tray.quit_requested.connect(self.quit)

        # Control Center -> Actions & Teardown
        self.control_center.translation_toggled.connect(self._on_translation_toggled)
        self.control_center.select_roi_requested.connect(self._open_roi_selector)
        self.control_center.window_selected.connect(self._on_window_selected)
        self.control_center.settings_saved.connect(self._on_settings_saved)
        self.control_center.quit_requested.connect(self.quit)
        self.control_center.finished.connect(self._on_control_center_finished)

    def _on_pipeline_error(self, error: str) -> None:
        """Handle background pipeline errors."""
        logger.error("Pipeline background error: %s", error)

    def _toggle_control_center(self) -> None:
        """Toggle the unified Control Center window."""
        if self.control_center.isVisible():
            self.control_center.hide()
            _set_macos_activation_policy(regular=False)
        else:
            _set_macos_activation_policy(regular=True)
            self.control_center.refresh_state()
            self.control_center.show()
            self.control_center.raise_()
            self.control_center.activateWindow()

    def _on_control_center_finished(self, result: int) -> None:
        """Return to accessory mode when Control Center is dismissed."""
        _set_macos_activation_policy(regular=False)

    def _on_settings_saved(self) -> None:
        """Apply live visual updates when preferences are saved."""
        self.overlay.style_config = self.config_manager.config.overlay
        self.overlay.update()

    def _on_translation_toggled(self, active: bool) -> None:
        """Start or pause translation worker."""
        if active:
            src = self.config_manager.config.source_language
            tgt = self.config_manager.config.target_language
            pair_id = f"{src}-{tgt}"
            from core.translate.models import ModelManager, RECOMMENDED_MODELS
            mm = ModelManager()
            if not mm.is_installed(pair_id):
                _set_macos_activation_policy(regular=True)
                meta = RECOMMENDED_MODELS.get(pair_id)
                size_str = f" (~{meta.approx_size_mb} MB)" if meta else ""
                name_str = meta.name if meta else pair_id
                reply = QMessageBox.question(
                    self.control_center if self.control_center.isVisible() else None,
                    "Translation Model Required",
                    f"The offline translation model for '{name_str}' is not downloaded yet{size_str}.\n\n"
                    "Would you like to download it now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    from ui.model_dialog import ModelDownloadProgressDialog
                    dialog = ModelDownloadProgressDialog(
                        mm, pair_id, parent=self.control_center if self.control_center.isVisible() else None
                    )
                    dialog.start_download()
                    if not self.control_center.isVisible():
                        _set_macos_activation_policy(regular=False)
                    if not mm.is_installed(pair_id):
                        self.tray.set_active(False)
                        self.control_center.set_active(False)
                        return
                else:
                    if not self.control_center.isVisible():
                        _set_macos_activation_policy(regular=False)
                    self.tray.set_active(False)
                    self.control_center.set_active(False)
                    return

            logger.info("Starting translation overlay...")
            self.tray.set_active(True)
            self.control_center.set_active(True)
            self.overlay.show()
            self.overlay.update_text("⚡ Subtitle Translator Active")
            if not self.worker.isRunning():
                self.worker.start()
        else:
            logger.info("Pausing translation overlay...")
            self.tray.set_active(False)
            self.control_center.set_active(False)
            self.overlay.clear_text()
            self.overlay.hide()
            if self.worker.isRunning():
                self.worker.stop()
            # Explicitly release screen/display capture handles so macOS capture indicator dismisses immediately
            if hasattr(self.capture_driver, "close"):
                try:
                    self.capture_driver.close()
                except Exception as e:
                    logger.debug("Failed to close capture driver: %s", e)

    def _open_roi_selector(self) -> None:
        """Open interactive screen region selector."""
        logger.info("Opening custom ROI selector...")
        _set_macos_activation_policy(regular=True)

        def _cleanup() -> None:
            _set_macos_activation_policy(regular=False)

        def _on_selected(roi: Rect) -> None:
            _cleanup()
            self._on_roi_selected(roi)

        def _on_cancelled() -> None:
            _cleanup()
            logger.info("ROI selection cancelled.")

        self.region_selector = RegionSelectorWidget(
            on_selected=_on_selected,
            on_cancelled=_on_cancelled,
        )
        # Cover primary screen
        bounds = self.capture_driver.get_monitor_bounds(1)
        self.region_selector.setGeometry(bounds.left, bounds.top, bounds.width, bounds.height)
        self.region_selector.show()
        self.region_selector.raise_()
        self.region_selector.activateWindow()

    def _on_roi_selected(self, roi: Rect) -> None:
        """Apply chosen custom ROI."""
        logger.info("Custom ROI selected: %s", roi.as_tuple())
        self.worker.set_custom_roi(roi)
        self.control_center.set_roi_hint(f"Custom ROI: {roi.width}x{roi.height} at ({roi.left}, {roi.top})")
        # Position overlay directly near selected ROI
        bounds = self.capture_driver.get_monitor_bounds(1)
        overlay_h = 140
        overlay_w = max(roi.width, 400)
        overlay_x = max(bounds.left, min(roi.left + (roi.width - overlay_w) // 2, bounds.right - overlay_w))
        overlay_y = roi.bottom + 10
        if overlay_y + overlay_h > bounds.bottom:
            overlay_y = max(bounds.top, roi.top - overlay_h - 10)
        self.overlay.setGeometry(overlay_x, overlay_y, overlay_w, overlay_h)
        self.overlay.update_text("🎯 Region locked")

    def _on_window_selected(self, window_info: Optional[WindowInfo]) -> None:
        """Set targeted application window."""
        if window_info is not None:
            logger.info("Target window locked: %s (ID: %s)", window_info.title, window_info.window_id)
            self.worker.set_target_window(window_info.window_id)
            # Center overlay over target window
            r = window_info.rect
            overlay_h = 140
            self.overlay.setGeometry(r.left, r.bottom - overlay_h - 20, r.width, overlay_h)
        else:
            logger.info("Resetting target to entire screen.")
            self.worker.set_target_window(None)
            bounds = self.capture_driver.get_monitor_bounds(1)
            overlay_h = 150
            self.overlay.setGeometry(bounds.left + 100, bounds.bottom - overlay_h - 50, bounds.width - 200, overlay_h)

    def quit(self) -> None:
        """Clean teardown of worker and application."""
        logger.info("Shutting down Subtitle Translator V1...")
        if self.worker.isRunning():
            self.worker.stop()
        self.control_center.close()
        self.overlay.close()
        self.tray.hide()
        QApplication.quit()


def _set_macos_activation_policy(regular: bool) -> None:
    """Dynamically toggle macOS activation policy.

    When regular=True: Shows icon in macOS Dock (when Settings window is opened).
    When regular=False: Hides icon from macOS Dock (pure background menu-bar mode).
    """
    if sys.platform == "darwin":
        try:
            from AppKit import (
                NSApp,
                NSApplicationActivationPolicyAccessory,
                NSApplicationActivationPolicyRegular,
            )
            if NSApp is not None:
                policy = (
                    NSApplicationActivationPolicyRegular
                    if regular
                    else NSApplicationActivationPolicyAccessory
                )
                NSApp.setActivationPolicy_(policy)
                if regular:
                    NSApp.activateIgnoringOtherApps_(True)
        except Exception as e:
            logger.debug("Failed to set macOS activation policy (regular=%s): %s", regular, e)


def main() -> int:
    app = QApplication(sys.argv)
    # Prevent macOS from quitting when last window is hidden
    app.setQuitOnLastWindowClosed(False)

    # Hide from macOS Dock initially (pure status item / tray app)
    _set_macos_activation_policy(regular=False)

    # Enforce single instance to prevent duplicate tray icons
    lock_path = QDir.tempPath() + "/subtrans_single_instance.lock"
    lock_file = QLockFile(lock_path)
    if not lock_file.tryLock(100):
        logger.warning("Another instance of Subterranean Staircase is already running. Exiting.")
        return 0

    translator_app = SubtitleTranslatorApp()
    translator_app.start()

    # Retain lock_file reference throughout app lifecycle
    app._lock_file = lock_file  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
