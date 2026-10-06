"""Subtitle Translator V1 Desktop Application Entrypoint."""

import logging
import os
import sys
from typing import Callable, Optional

from PyQt6.QtCore import QDir, QLockFile
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.capture.factory import create_capture_driver
from core.config import ConfigManager
from core.contracts import Rect, WindowInfo
from core.pipeline import PipelineSignals, TranslationPipelineWorker
from core.translate.local import CTranslate2Engine
from core.translate.router import TranslationRouter
from core.storage.cache import SQLiteTranslationCache
from ui.control_center import ControlCenterDialog
from ui.overlay import SubtitleOverlayWindow
from ui.region_selector import RegionSelectorWidget
from ui.tray import TrayController

def _init_logging() -> logging.Logger:
    """Initialize logging.

    Consumer mode (default):
      Logs at WARNING level to stderr. No audit file written to disk to prevent bloat.

    Developer mode (--audit / --debug CLI flag or SUBTRANS_AUDIT=1 / SUBTRANS_DEBUG=1):
      Logs at INFO level, streaming to stdout and recording structured telemetry
      into audit_session.log for diagnostic analysis and Ground Truth benchmarks.
    """
    dev_flags = {"--audit", "--debug"}
    is_dev_mode = any(arg in sys.argv for arg in dev_flags) or os.environ.get("SUBTRANS_AUDIT") == "1" or os.environ.get("SUBTRANS_DEBUG") == "1"

    handlers: list[logging.Handler] = []

    if is_dev_mode:
        handlers.append(logging.StreamHandler(sys.stdout))
        # Prefer project root log for development/testing if writable, fallback to User AppData
        log_candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_session.log"),
        ]
        try:
            from PyQt6.QtCore import QStandardPaths

            base_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            if base_dir:
                app_dir = os.path.join(base_dir, "Subterranean Staircase")
                os.makedirs(app_dir, exist_ok=True)
                log_candidates.append(os.path.join(app_dir, "audit_session.log"))
        except Exception:
            pass

        for candidate in log_candidates:
            try:
                handler = logging.FileHandler(candidate, mode="a", encoding="utf-8")
                handlers.append(handler)
                break
            except Exception:
                continue

        log_level = logging.INFO
    else:
        handlers.append(logging.StreamHandler(sys.stderr))
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        handlers=handlers,
        force=True,
    )
    logger_instance = logging.getLogger("SubtitleTranslator")
    if is_dev_mode:
        logger_instance.info("Developer audit facade ACTIVE (level: INFO, telemetry to audit_session.log).")
    return logger_instance


logger = _init_logging()


class SubtitleTranslatorApp:
    """Main application orchestrator binding UI, Tray, and Pipeline."""

    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.capture_driver = create_capture_driver()
        self.signals = PipelineSignals()
        self.router = TranslationRouter()

        # UI Components
        self.overlay = SubtitleOverlayWindow(style_config=self.config_manager.config.overlay)
        self.tray = TrayController(
            config_manager=self.config_manager,
            capture_driver=self.capture_driver,
        )
        self.control_center = ControlCenterDialog(
            config_manager=self.config_manager,
            capture_driver=self.capture_driver,
            router=self.router,
        )
        self.region_selector: Optional[RegionSelectorWidget] = None
        self._current_target_window: Optional[WindowInfo] = None

        # Background Worker with injected router and cache
        cache = SQLiteTranslationCache()
        translator_engine = CTranslate2Engine(cache=cache, router=self.router)
        self.worker = TranslationPipelineWorker(
            config_manager=self.config_manager,
            signals=self.signals,
            capture_driver=self.capture_driver,
            translator_engine=translator_engine,
        )

        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect inter-component event listeners."""
        # Pipeline -> Overlay & Logging
        self.signals.subtitle_ready.connect(self.overlay.update_text)
        self.signals.subtitle_active.connect(lambda _: self.overlay.touch())
        self.signals.subtitle_cleared.connect(self.overlay.clear_text)
        self.signals.error_occurred.connect(self._on_pipeline_error)
        self.signals.frame_captured.connect(self.control_center.update_live_preview)

        # Tray -> Control Center & Teardown
        self.tray.control_center_requested.connect(self._show_control_center)
        self.tray.translation_toggled.connect(self._on_translation_toggled)
        self.tray.quit_requested.connect(self.quit)

        # Control Center -> Actions & Teardown
        self.control_center.translation_toggled.connect(self._on_translation_toggled)
        self.control_center.select_roi_requested.connect(self._open_roi_selector)
        self.control_center.reset_roi_requested.connect(self._on_reset_roi)
        self.control_center.window_selected.connect(self._on_window_selected)
        self.control_center.reposition_overlay_toggled.connect(self._on_reposition_overlay_toggled)
        self.control_center.reset_overlay_position_requested.connect(self._on_reset_overlay_position)
        self.control_center.settings_saved.connect(self._on_settings_saved)
        self.control_center.quit_requested.connect(self.quit)
        self.control_center.finished.connect(self._on_control_center_finished)

        # Overlay position changed by user dragging (real-time UI hint update + disk persistence on lock/release)
        self.overlay.position_changed.connect(self._on_overlay_dragged)
        self.overlay.position_locked.connect(self._on_overlay_position_persisted)

    def _on_pipeline_error(self, error: str) -> None:
        """Handle background pipeline errors."""
        logger.error("Pipeline background error: %s", error)

    def _show_control_center(self) -> None:
        """Open and bring unified Control Center dialog to foreground."""
        _set_macos_activation_policy(regular=True)
        self.control_center.refresh_state()
        self.control_center.show()
        self.control_center.raise_()
        self.control_center.activateWindow()

    def _on_control_center_finished(self, result: int) -> None:
        """Called when Control Center is dismissed."""
        # Revert to accessory mode so overlay can float over native fullscreen spaces
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

            # 1. Resolve required models via router
            needed_pairs = self.router.required_pairs(src, tgt)
            if not needed_pairs:
                _set_macos_activation_policy(regular=True)
                QMessageBox.warning(
                    self.control_center if self.control_center.isVisible() else None,
                    "Translation Route Unavailable",
                    f"No offline translation route is available for '{src}' ➔ '{tgt}'.\n"
                    "Please select a supported language pair in Control Center.",
                )
                self.tray.set_active(False)
                self.control_center.set_active(False)
                return

            from core.translate.models import ModelManager, RECOMMENDED_MODELS
            mm = ModelManager()
            missing_pairs = [p for p in needed_pairs if not mm.is_installed(p)]

            if missing_pairs:
                _set_macos_activation_policy(regular=True)
                # Format name and approximate size for missing legs
                size_total = sum(RECOMMENDED_MODELS[p].approx_size_mb for p in missing_pairs if p in RECOMMENDED_MODELS)
                desc = ", ".join(f"'{p}'" for p in missing_pairs)
                reply = QMessageBox.question(
                    self.control_center if self.control_center.isVisible() else None,
                    "Translation Model(s) Required",
                    f"The offline translation model(s) for {desc} are not downloaded yet (~{size_total} MB).\n\n"
                    "Would you like to download them now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    from ui.model_dialog import ModelDownloadProgressDialog
                    for p in missing_pairs:
                        if p not in RECOMMENDED_MODELS:
                            continue
                        dialog = ModelDownloadProgressDialog(
                            mm, p, parent=self.control_center if self.control_center.isVisible() else None
                        )
                        dialog.start_download()

                    # Re-verify all required pairs are installed
                    if not all(mm.is_installed(p) for p in needed_pairs):
                        self.tray.set_active(False)
                        self.control_center.set_active(False)
                        return
                else:
                    self.tray.set_active(False)
                    self.control_center.set_active(False)
                    return

            # Revert to accessory mode on macOS so overlay can float over fullscreen spaces
            _set_macos_activation_policy(regular=False)
            logger.info("Starting translation overlay...")
            self.tray.set_active(True)
            self.control_center.set_active(True)
            self.overlay.show()
            self.overlay.raise_front()
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

        # If a target window is locked, bring it to front before overlaying ROI selector
        if self._current_target_window is not None:
            self.capture_driver.bring_window_to_front(self._current_target_window.window_id)

        _set_macos_activation_policy(regular=True)

        def _cleanup() -> None:
            if self.region_selector is not None:
                self.region_selector.deleteLater()
                self.region_selector = None

        def _on_selected(roi: Rect) -> None:
            _cleanup()
            self._on_roi_selected(roi)
            self._show_control_center()

        def _on_cancelled() -> None:
            _cleanup()
            logger.info("ROI selection cancelled.")
            self._show_control_center()

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
        self.region_selector.setFocus()

    def _on_roi_selected(self, roi: Rect) -> None:
        """Apply chosen custom ROI."""
        logger.info("Custom ROI selected: %s", roi.as_tuple())
        self.config_manager.update(custom_roi=list(roi.as_tuple()))
        self.worker.set_custom_roi(roi)
        self.control_center.set_roi_hint(f"Custom ROI: {roi.width}x{roi.height} at ({roi.left}, {roi.top})", has_custom_roi=True)
        self._apply_overlay_geometry()
        self.overlay.update_text("🎯 Region locked")

    def _on_reset_roi(self) -> None:
        """Clear custom ROI and revert to full capture area."""
        logger.info("Clearing custom ROI, reverting to full area.")
        self.config_manager.update(custom_roi=None)
        self.worker.set_custom_roi(None)
        self.control_center.set_roi_hint("Full capture area active", has_custom_roi=False)
        self._apply_overlay_geometry()
        self.overlay.update_text("🔄 Full capture restored")

    def _apply_overlay_geometry(self) -> None:
        """Position overlay respecting saved custom position, target window, or ROI."""
        bounds = self.capture_driver.get_monitor_bounds(1)
        custom_pos = self.config_manager.config.custom_overlay_position

        # 1. Custom user-dragged position takes precedence
        if custom_pos is not None:
            cx, by = custom_pos
            # Clamp inside screen bounds
            cx = max(bounds.left + 200, min(cx, bounds.right - 200))
            by = max(bounds.top + 100, min(by, bounds.bottom - 10))
            self.overlay.set_bottom_center(cx, by)
            return

        # 2. Custom ROI positioning
        saved_roi = None
        roi_data = self.config_manager.config.custom_roi
        if isinstance(roi_data, (list, tuple)) and len(roi_data) == 4:
            try:
                saved_roi = Rect(*(int(x) for x in roi_data))
            except (ValueError, TypeError):
                saved_roi = None

        if saved_roi is not None:
            overlay_h = 140
            overlay_w = max(saved_roi.width, 400)
            overlay_x = max(bounds.left, min(saved_roi.left + (saved_roi.width - overlay_w) // 2, bounds.right - overlay_w))
            overlay_y = saved_roi.bottom + 10
            if overlay_y + overlay_h > bounds.bottom:
                overlay_y = max(bounds.top, saved_roi.top - overlay_h - 10)
            self.overlay.setGeometry(overlay_x, overlay_y, overlay_w, overlay_h)
            return

        # 3. Target window positioning
        if self._current_target_window is not None:
            r = self._current_target_window.rect
            overlay_h = 140
            self.overlay.setGeometry(r.left, r.bottom - overlay_h - 20, r.width, overlay_h)
            return

        # 4. Default auto bottom-center of primary screen
        overlay_h = 140
        overlay_w = min(800, bounds.width - 300)
        overlay_x = bounds.left + (bounds.width - overlay_w) // 2
        overlay_y = bounds.bottom - overlay_h - 60
        self.overlay.setGeometry(overlay_x, overlay_y, overlay_w, overlay_h)

    def _on_reposition_overlay_toggled(self, active: bool) -> None:
        """Handle interactive dragging mode toggle."""
        if active:
            logger.info("Enabling interactive overlay repositioning mode...")
            _set_macos_activation_policy(regular=True)
            self._apply_overlay_geometry()
            self.overlay.set_interactive_mode(True)
        else:
            logger.info("Locking overlay repositioning mode...")
            self.overlay.set_interactive_mode(False)
            if not self.control_center.isVisible():
                _set_macos_activation_policy(regular=False)

    def _on_overlay_dragged(self, center_x: int, bottom_y: int) -> None:
        """Update in-memory coordinates during mouse drag without disk write thrashing."""
        bounds = self.capture_driver.get_monitor_bounds(1)
        cx = max(bounds.left + 200, min(center_x, bounds.right - 200))
        by = max(bounds.top + 100, min(bottom_y, bounds.bottom - 10))
        self.config_manager.config.custom_overlay_position = (cx, by)
        self.control_center.refresh_reposition_hint()

    def _on_overlay_position_persisted(self, center_x: int, bottom_y: int) -> None:
        """Persist finalized coordinates to disk upon drag release."""
        bounds = self.capture_driver.get_monitor_bounds(1)
        cx = max(bounds.left + 200, min(center_x, bounds.right - 200))
        by = max(bounds.top + 100, min(bottom_y, bounds.bottom - 10))
        self.config_manager.update(custom_overlay_position=[cx, by])
        self.control_center.refresh_reposition_hint()

    def _on_reset_overlay_position(self) -> None:
        """Revert overlay positioning to automatic bottom-center."""
        logger.info("Resetting overlay position to auto.")
        self.config_manager.update(custom_overlay_position=None)
        self._apply_overlay_geometry()
        self.overlay.update_text("🔄 Position reset to auto")

    def _on_window_selected(self, window_info: Optional[WindowInfo]) -> None:
        """Set targeted application window."""
        self._current_target_window = window_info
        if window_info is not None:
            logger.info("Target window locked: %s (ID: %s)", window_info.title, window_info.window_id)
            self.worker.set_target_window(window_info.window_id)
        else:
            logger.info("Resetting target to entire screen.")
            self.worker.set_target_window(None)
        self._apply_overlay_geometry()

    def start(self) -> None:
        """Display system tray and initialize geometry."""
        self.tray.show()

        # Restore saved custom ROI from config if present
        roi_data = self.config_manager.config.custom_roi
        saved_roi = None
        if isinstance(roi_data, (list, tuple)) and len(roi_data) == 4:
            try:
                saved_roi = Rect(*(int(x) for x in roi_data))
            except (ValueError, TypeError):
                saved_roi = None

        if saved_roi is not None:
            self.worker.set_custom_roi(saved_roi)
            self.control_center.set_roi_hint(f"Custom ROI: {saved_roi.width}x{saved_roi.height} at ({saved_roi.left}, {saved_roi.top})", has_custom_roi=True)

        self._apply_overlay_geometry()

        logger.info("Subtitle Translator V1 initialized and ready in Menu Bar / System Tray.")

    def quit(self) -> None:
        """Clean teardown of worker and application."""
        logger.info("Shutting down Subtitle Translator V1...")
        if self.worker.isRunning():
            self.worker.stop()
        self.control_center.close()
        self.overlay.close()
        self.tray.hide()
        QApplication.quit()


def _setup_windows_app() -> None:
    """Set explicit AppUserModelID on Windows so taskbar groups properly under its own icon/name."""
    if sys.platform != "win32":
        return

    try:
        import ctypes
        app_id = "subtitletranslator.subtrans.desktop.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as e:
        logger.debug("Failed to set Windows AppUserModelID: %s", e)


def _setup_macos_app(on_reopen: Optional[Callable[[], None]] = None) -> None:
    """Configure macOS process name, activation policy, and Dock click handler."""
    if sys.platform != "darwin":
        return

    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
            NSImage,
            NSProcessInfo,
        )
        import objc

        # Set human-readable process name in macOS menu bar and Dock
        process_info = NSProcessInfo.processInfo()
        process_info.setProcessName_("Subterranean Staircase")

        ns_app = NSApplication.sharedApplication()
        if ns_app is not None:
            # Set application icon in Dock
            icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "app_icon.png")
            if os.path.exists(icon_path):
                ns_img = NSImage.alloc().initWithContentsOfFile_(icon_path)
                if ns_img is not None:
                    ns_app.setApplicationIconImage_(ns_img)

            # Start in accessory mode to enable auxiliary floating overlay across spaces
            ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

            if on_reopen is not None:
                class DockReopenDelegate(objc.lookUpClass("NSObject")):
                    def applicationShouldHandleReopen_hasVisibleWindows_(self, sender, flag):
                        try:
                            on_reopen()
                        except Exception as err:
                            logger.error("Error handling Dock reopen event: %s", err)
                        return True

                delegate = DockReopenDelegate.alloc().init()
                ns_app.setDelegate_(delegate)
                # Keep strong reference so delegate is not garbage collected
                ns_app._dock_delegate = delegate
    except Exception as e:
        logger.debug("Failed to setup macOS app properties: %s", e)


def _set_macos_activation_policy(regular: bool) -> None:
    """Dynamically toggle macOS activation policy between Regular (Dock visible) and Accessory (floating overlay)."""
    if sys.platform == "darwin":
        try:
            from AppKit import (
                NSApp,
                NSApplicationActivationPolicyAccessory,
                NSApplicationActivationPolicyRegular,
            )
            if NSApp is not None:
                target_policy = (
                    NSApplicationActivationPolicyRegular
                    if regular
                    else NSApplicationActivationPolicyAccessory
                )
                if NSApp.activationPolicy() != target_policy:
                    NSApp.setActivationPolicy_(target_policy)
                if regular:
                    NSApp.activateIgnoringOtherApps_(True)
        except Exception as e:
            logger.debug("Failed to set macOS activation policy (regular=%s): %s", regular, e)


def main() -> int:
    # On macOS, configure process name before creating QApplication
    if sys.platform == "darwin":
        try:
            from AppKit import NSProcessInfo
            NSProcessInfo.processInfo().setProcessName_("Subterranean Staircase")
        except Exception:
            pass

    # Enforce single instance before initializing heavy UI / Python modules
    lock_path = QDir.tempPath() + "/subtrans_single_instance.lock"
    lock_file = QLockFile(lock_path)
    if not lock_file.tryLock(100):
        # Already running: trigger existing instance to front on macOS, then exit quietly
        if sys.platform == "darwin":
            try:
                from AppKit import NSRunningApplication
                apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.subtitle-translator.subtrans")
                if apps:
                    apps[0].activateWithOptions_(1 << 1)
            except Exception:
                pass
        logger.info("Subterranean Staircase is already running. Focusing active instance.")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Subterranean Staircase")
    app.setApplicationDisplayName("Subterranean Staircase")

    # Set window icon globally for dialogs and taskbars
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Prevent macOS from quitting when last window is hidden
    app.setQuitOnLastWindowClosed(False)

    translator_app = SubtitleTranslatorApp()

    # Configure platform-specific taskbar/dock integration
    _setup_windows_app()
    _setup_macos_app(on_reopen=translator_app._show_control_center)

    translator_app.start()
    translator_app._show_control_center()

    # Retain lock_file reference throughout app lifecycle
    app._lock_file = lock_file  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
