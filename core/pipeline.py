"""Event-driven pipeline orchestrator for Subtitle Translator V1.

Connects Capture -> Diff -> OCR -> Spatial -> History -> Translate -> Overlay
across non-blocking background threads, guaranteeing zero UI freezing.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.capture.base import BaseCapture
from core.capture.factory import create_capture_driver
from core.config import AppConfig, ConfigManager
from core.contracts import Frame, Rect, TranslationRequest
from core.ocr.engine import BaseOCR, RapidOCREngine
from core.storage.cache import SQLiteTranslationCache
from core.subtitle.filters import SubtitleTextFilter
from core.subtitle.history import SubtitleHistoryTracker
from core.subtitle.spatial import DualBandSpatialFilter
from core.translate.local import BaseTranslator, CTranslate2Engine
from core.vision.diff import FrameDiffDetector

logger = logging.getLogger(__name__)


class PipelineSignals(QObject):
    """Signals emitted from background pipeline worker to Qt UI thread."""
    subtitle_ready = pyqtSignal(str)          # Translated text to display
    translation_status = pyqtSignal(str)       # Status updates (e.g. "Processing", "Idle")
    error_occurred = pyqtSignal(str)           # Error notifications


class TranslationPipelineWorker(QThread):
    """Background worker executing the high-frequency capture, vision, and translation loop."""

    def __init__(
        self,
        config_manager: ConfigManager,
        signals: PipelineSignals,
        capture_driver: Optional[BaseCapture] = None,
        ocr_engine: Optional[BaseOCR] = None,
        translator_engine: Optional[BaseTranslator] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.signals = signals

        self._running = False
        self._target_window_id: Optional[int | str] = None
        self._target_roi: Optional[Rect] = None
        self._state_lock = threading.Lock()

        # Core engines (injected or default)
        self.capture_driver = capture_driver or create_capture_driver()
        self.ocr_engine = ocr_engine or RapidOCREngine()

        # Cache & Translator setup
        cache = SQLiteTranslationCache()
        self.translator_engine = translator_engine or CTranslate2Engine(cache=cache)

        # Filters
        self.diff_detector = FrameDiffDetector(default_threshold=self.config_manager.config.frame_diff_threshold)
        self.spatial_filter = DualBandSpatialFilter()
        self.history_tracker = SubtitleHistoryTracker()
        self.text_filter = SubtitleTextFilter(target_script=self.config_manager.config.source_language)

        self._last_translated_sentence: str = ""

    def set_target_window(self, window_id: Optional[int | str]) -> None:
        """Lock capture onto a specific window ID, or None for full screen."""
        with self._state_lock:
            self._target_window_id = window_id
            self.diff_detector.reset()
            self.history_tracker.reset()
            self._last_translated_sentence = ""

    def set_custom_roi(self, roi: Optional[Rect]) -> None:
        """Focus translation on a user-selected custom bounding rectangle."""
        with self._state_lock:
            self._target_roi = roi
            self.diff_detector.reset()
            self.history_tracker.reset()
            self._last_translated_sentence = ""

    def stop(self, timeout_ms: int = 3000) -> bool:
        """Signal thread to cleanly terminate loop and wait for completion."""
        self._running = False
        return self.wait(timeout_ms)

    def run(self) -> None:
        """Main execution loop running decoupled in background QThread."""
        self._running = True
        logger.info("Subtitle translation pipeline worker started.")

        while self._running:
            loop_start = time.perf_counter()
            cfg = self.config_manager.config
            interval = 1.0 / max(1, cfg.fps_limit)

            try:
                self._process_cycle(cfg)
            except Exception as e:
                logger.error("Pipeline cycle error: %s", e, exc_info=True)
                self.signals.error_occurred.emit(str(e))

            # Sleep remaining budget in small slices so stop() responds instantly
            elapsed = time.perf_counter() - loop_start
            sleep_time = max(0.01, interval - elapsed)
            slices = int(sleep_time / 0.02) + 1
            slice_dur = sleep_time / slices
            for _ in range(slices):
                if not self._running:
                    break
                time.sleep(slice_dur)

        logger.info("Subtitle translation pipeline worker stopped.")

    def _process_cycle(self, cfg: AppConfig) -> None:
        """Execute one complete capture -> diff -> OCR -> translate pass."""
        with self._state_lock:
            crop = self._target_roi
            target_win = self._target_window_id

        # 1. Capture Frame (Window or Screen)
        if target_win is not None:
            try:
                frame = self.capture_driver.grab_window(target_win, crop_rect=crop)
            except Exception:
                # Target window temporarily inaccessible -> fallback to screen for this cycle
                frame = self.capture_driver.grab_screen(1, crop_rect=crop)
        else:
            frame = self.capture_driver.grab_screen(1, crop_rect=crop)

        if frame is None or frame.image is None or frame.image.size == 0:
            return

        # 2. Perceptual Frame-Diff Check (Short-circuit static frames < 1ms)
        with self._state_lock:
            if not self.diff_detector.has_changed(frame.image, threshold=cfg.frame_diff_threshold):
                return  # Scene / subtitles unchanged, save 100% OCR compute!

        # 3. Text Extraction (RapidOCR ONNX)
        detections = self.ocr_engine.detect(frame)
        if not detections:
            return

        # 4. Spatial Band Filtering (Reject center-screen reading text & noise unless custom ROI is set)
        with self._state_lock:
            has_custom_roi = self._target_roi is not None

        if has_custom_roi:
            spatial_candidates = detections
        else:
            frame_rect = Rect(0, 0, frame.width, frame.height)
            spatial_candidates = self.spatial_filter.filter_detections(detections, frame_rect)

        if not spatial_candidates:
            return

        # 5. Multilingual script filtering & text sanitation (synchronized with active config)
        self.text_filter.target_script = cfg.source_language.lower()
        valid_candidates = self.text_filter.filter_and_clean(spatial_candidates)
        if not valid_candidates:
            return

        # 6. Temporal History Stabilization & Anti-Flicker
        stable_tracks = self.history_tracker.update(valid_candidates, now=frame.timestamp)
        if not stable_tracks:
            return

        # Form sentence from stable tracks (top-to-bottom)
        raw_sentence = " ".join(t.stable_text for t in stable_tracks).strip()
        if not raw_sentence or raw_sentence == self._last_translated_sentence:
            return

        self._last_translated_sentence = raw_sentence

        # 7. Translation Request
        req = TranslationRequest(
            source_text=raw_sentence,
            source_lang=cfg.source_language,
            target_lang=cfg.target_language,
            timestamp=frame.timestamp,
        )

        try:
            result = self.translator_engine.translate(req)
            if result.translated_text:
                self.signals.subtitle_ready.emit(result.translated_text)
        except Exception as e:
            logger.warning("Translation failed: %s", e)
            self.signals.error_occurred.emit(f"Translation failed: {e}")
