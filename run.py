"""Subtitle Translator V1 Desktop Application Entrypoint."""

import logging
import sys
from typing import Optional

from PyQt6.QtWidgets import QApplication

from core.capture.factory import create_capture_driver
from core.config import ConfigManager
from core.contracts import Rect, WindowInfo
from core.pipeline import PipelineSignals, TranslationPipelineWorker
from ui.overlay import SubtitleOverlayWindow
from ui.region_selector import RegionSelectorWidget
from ui.settings_dialog import SettingsDialog
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
        self.region_selector: Optional[RegionSelectorWidget] = None
        self.settings_dialog: Optional[SettingsDialog] = None

        # Background Worker
        self.worker = TranslationPipelineWorker(
            config_manager=self.config_manager,
            signals=self.signals,
            capture_driver=self.capture_driver,
        )

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect inter-component event listeners."""
        # Pipeline -> Overlay
        self.signals.subtitle_ready.connect(self.overlay.update_text)

        # Tray -> Pipeline & UI
        self.tray.translation_toggled.connect(self._on_translation_toggled)
        self.tray.select_roi_requested.connect(self._open_roi_selector)
        self.tray.window_selected.connect(self._on_window_selected)
        self.tray.settings_requested.connect(self._open_settings)
        self.tray.quit_requested.connect(self.quit)

    def _on_translation_toggled(self, active: bool) -> None:
        """Start or pause translation worker."""
        if active:
            logger.info("Starting translation overlay...")
            self.overlay.show()
            if not self.worker.isRunning():
                self.worker.start()
        else:
            logger.info("Pausing translation overlay...")
            self.overlay.clear_text()
            self.overlay.hide()
            if self.worker.isRunning():
                self.worker.stop()

    def _open_roi_selector(self) -> None:
        """Open interactive screen region selector."""
        logger.info("Opening custom ROI selector...")
        self.region_selector = RegionSelectorWidget(
            on_selected=self._on_roi_selected,
            on_cancelled=lambda: logger.info("ROI selection cancelled."),
        )
        # Cover primary screen
        bounds = self.capture_driver.get_monitor_bounds(1)
        self.region_selector.setGeometry(bounds.left, bounds.top, bounds.width, bounds.height)
        self.region_selector.show()

    def _on_roi_selected(self, roi: Rect) -> None:
        """Apply chosen custom ROI."""
        logger.info("Custom ROI selected: %s", roi.as_tuple())
        self.worker.set_custom_roi(roi)

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

    def _open_settings(self) -> None:
        """Open settings configuration modal."""
        self.settings_dialog = SettingsDialog(config_manager=self.config_manager)
        if self.settings_dialog.exec():
            # Update overlay style after save
            self.overlay.style_config = self.config_manager.config.overlay
            self.overlay.update()

    def start(self) -> None:
        """Display system tray and initialize geometry."""
        self.tray.show()
        # Default overlay position at bottom center of primary screen
        bounds = self.capture_driver.get_monitor_bounds(1)
        overlay_h = 140
        self.overlay.setGeometry(bounds.left + 150, bounds.bottom - overlay_h - 60, bounds.width - 300, overlay_h)
        logger.info("Subtitle Translator V1 initialized and ready in Menu Bar / System Tray.")

    def quit(self) -> None:
        """Clean teardown of worker and application."""
        logger.info("Shutting down Subtitle Translator V1...")
        if self.worker.isRunning():
            self.worker.stop()
        self.overlay.close()
        self.tray.hide()
        QApplication.quit()


def main() -> int:
    app = QApplication(sys.argv)
    # Prevent macOS from quitting when last window is hidden
    app.setQuitOnLastWindowClosed(False)

    translator_app = SubtitleTranslatorApp()
    translator_app.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
