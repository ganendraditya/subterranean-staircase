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
from core.storage.history import SessionHistoryRecorder
from core.subtitle.filters import SubtitleTextFilter
from core.subtitle.history import SubtitleHistoryTracker
from core.subtitle.spatial import DualBandSpatialFilter
from core.translate.local import BaseTranslator, CTranslate2Engine
from core.vision.diff import FrameDiffDetector

logger = logging.getLogger(__name__)


class PipelineSignals(QObject):
    """Signals emitted from background pipeline worker to Qt UI thread."""
    subtitle_ready = pyqtSignal(str)          # Translated text to display
    subtitle_active = pyqtSignal(str)         # Heartbeat to keep active subtitle alive while on screen
    subtitle_cleared = pyqtSignal()           # Signal when subtitles naturally disappear from screen
    translation_status = pyqtSignal(str)      # Status updates (e.g. "Processing", "Idle")
    error_occurred = pyqtSignal(str)          # Error notifications
    frame_captured = pyqtSignal(object)       # Emits captured np.ndarray frame for live GUI preview monitor


class TranslationPipelineWorker(QThread):
    """Background worker executing the high-frequency capture, vision, and translation loop."""

    def __init__(
        self,
        config_manager: ConfigManager,
        signals: PipelineSignals,
        capture_driver: Optional[BaseCapture] = None,
        ocr_engine: Optional[BaseOCR] = None,
        translator_engine: Optional[BaseTranslator] = None,
        history_recorder: Optional[SessionHistoryRecorder] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.signals = signals

        self._running = False
        self._target_window_id: Optional[int | str] = None
        self._target_roi: Optional[Rect] = None
        self._state_lock = threading.Lock()

        # Session tracking for subtitle history recording
        self.history_recorder = history_recorder or SessionHistoryRecorder()
        self._session_id: str = f"session_{int(time.time())}"
        self._last_record_id: Optional[int] = None

        # Core engines (injected or default)
        self.capture_driver = capture_driver or create_capture_driver()
        self.ocr_engine = ocr_engine or RapidOCREngine()

        # Cache & Translator setup (lazy instantiate default cache only if no engine provided)
        if translator_engine is not None:
            self.translator_engine = translator_engine
        else:
            cache = SQLiteTranslationCache()
            self.translator_engine = CTranslate2Engine(cache=cache)

        # Filters
        self.diff_detector = FrameDiffDetector(default_threshold=self.config_manager.config.frame_diff_threshold)
        self.spatial_filter = DualBandSpatialFilter()
        self.history_tracker = SubtitleHistoryTracker()
        self.text_filter = SubtitleTextFilter(target_script=self.config_manager.config.source_language)

        self._last_translated_sentence: str = ""
        self._pending_sentence: str = ""
        self._pending_sentence_time: float = 0.0

    def set_target_window(self, window_id: Optional[int | str]) -> None:
        """Lock capture onto a specific window ID, or None for full screen."""
        with self._state_lock:
            self._target_window_id = window_id
            self.diff_detector.reset()
            self.history_tracker.reset()
            self._last_translated_sentence = ""
            self._pending_sentence = ""
            self._pending_sentence_time = 0.0
        logger.info("[AUDIT-TARGET] Target window updated: %s", window_id if window_id is not None else "Entire Screen")

    def set_custom_roi(self, roi: Optional[Rect]) -> None:
        """Focus translation on a user-selected custom bounding rectangle."""
        with self._state_lock:
            self._target_roi = roi
            self.diff_detector.reset()
            self.history_tracker.reset()
            self._last_translated_sentence = ""
            self._pending_sentence = ""
            self._pending_sentence_time = 0.0
        logger.info("[AUDIT-ROI] Custom ROI updated: %s", roi.as_tuple() if roi is not None else "Full Area")

    def start_new_session(self, session_id: Optional[str] = None) -> str:
        """Start a new session ID for history recording."""
        with self._state_lock:
            self._session_id = session_id or f"session_{int(time.time())}"
            self._last_record_id = None
        logger.info("[AUDIT-SESSION] New session started: %s", self._session_id)
        return self._session_id

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
                frame = self.capture_driver.grab_window(target_win, crop_rect=crop, is_global_coords=True)
            except Exception:
                # Target window temporarily inaccessible -> fallback to screen for this cycle
                frame = self.capture_driver.grab_screen(1, crop_rect=crop)
        else:
            frame = self.capture_driver.grab_screen(1, crop_rect=crop)

        if frame is None or frame.image is None or frame.image.size == 0:
            return

        # Emit frame for real-time OBS-like preview monitor in GUI
        self.signals.frame_captured.emit(frame.image)

        # 2. Perceptual Frame-Diff Check (Short-circuit static frames < 1ms)
        # However, do not short-circuit if history tracker still needs a second frame to stabilize newly appeared subtitles,
        # or if a pending sentence was debounced and is waiting to settle and be translated.
        with self._state_lock:
            has_pending_unstable = (
                any(t.count < self.history_tracker.stable_min_count for t in self.history_tracker.active_tracks)
                or (bool(self._pending_sentence) and self._pending_sentence != self._last_translated_sentence)
            )
            is_changed = self.diff_detector.has_changed(frame.image, threshold=cfg.frame_diff_threshold)
            if not is_changed and not has_pending_unstable:
                return  # Scene / subtitles unchanged and stabilized, save 100% OCR compute!

        # 3. Text Extraction (RapidOCR ONNX)
        t_ocr0 = time.perf_counter()
        detections = self.ocr_engine.detect(frame)
        t_ocr_ms = (time.perf_counter() - t_ocr0) * 1000.0

        if not detections:
            # If screen previously had subtitles but now has zero text, signal natural clear
            if self._last_translated_sentence:
                clear_lag_ms = max(0.0, (time.time() - frame.timestamp) * 1000.0) if frame.timestamp > 0 else 0.0
                logger.info("[AUDIT-CLEAR] Subtitles cleared from screen (0 text detected, clear latency: %.1fms)", clear_lag_ms)
                self.history_tracker.reset()
                self._last_translated_sentence = ""
                self._pending_sentence = ""
                self._pending_sentence_time = 0.0
                self.signals.subtitle_cleared.emit()
            return

        ocr_summary = ", ".join(f"'{d.text}'(conf={d.confidence:.2f})" for d in detections)
        logger.info("[AUDIT-OCR] %d detections in %.1fms: %s", len(detections), t_ocr_ms, ocr_summary)

        # 4. Spatial Band Filtering (Reject center-screen reading text & noise unless custom ROI is set)
        with self._state_lock:
            has_custom_roi = self._target_roi is not None

        if has_custom_roi:
            spatial_candidates = detections
        else:
            frame_rect = Rect(0, 0, frame.width, frame.height)
            spatial_candidates = self.spatial_filter.filter_detections(detections, frame_rect)

        if not spatial_candidates:
            logger.info("[AUDIT-FILTER] Spatial drop: %d items rejected (outside top/bottom subtitle bands)", len(detections))
            if self._last_translated_sentence:
                self.history_tracker.reset()
                self._last_translated_sentence = ""
                self._pending_sentence = ""
                self._pending_sentence_time = 0.0
                self.signals.subtitle_cleared.emit()
            return

        # 5. Multilingual script filtering & text sanitation (synchronized with active config)
        self.text_filter.target_script = cfg.source_language.lower()
        valid_candidates = self.text_filter.filter_and_clean(spatial_candidates)
        if not valid_candidates:
            logger.info("[AUDIT-FILTER] Clean/Script drop: %d items dropped (noise/scrubber or non-%s script)", len(spatial_candidates), cfg.source_language)
            if self._last_translated_sentence:
                self.history_tracker.reset()
                self._last_translated_sentence = ""
                self._pending_sentence = ""
                self._pending_sentence_time = 0.0
                self.signals.subtitle_cleared.emit()
            return

        # 6. Temporal History Stabilization & Anti-Flicker
        stable_tracks = self.history_tracker.update(valid_candidates, now=frame.timestamp, only_current=True)
        if not stable_tracks:
            return

        # Form sentence from stable tracks (top-to-bottom)
        raw_sentence = " ".join(t.stable_text for t in stable_tracks).strip()
        if not raw_sentence:
            return

        now = time.time()

        # If sentence is unchanged, keep subtitle alive on overlay (prevent premature fade-out during pause / long lines)
        if raw_sentence == self._last_translated_sentence:
            self.signals.subtitle_active.emit(raw_sentence)
            with self._state_lock:
                last_rec_id = self._last_record_id
                session_id = self._session_id
            if last_rec_id is not None:
                self.history_recorder.update_last_end_time(session_id, now + 1.5)
            return

        # Progressive sentence debouncing:
        # If words are appending rapidly (typing effect / partial line updates),
        # debounce for 0.12s so NMT translates the finished thought rather than a half-word fragment.
        is_extension = (
            bool(self._pending_sentence)
            and raw_sentence.startswith(self._pending_sentence)
            and len(raw_sentence) > len(self._pending_sentence)
        )
        if is_extension and (now - self._pending_sentence_time) < 0.12:
            self._pending_sentence = raw_sentence
            self._pending_sentence_time = now
            return

        self._pending_sentence = raw_sentence
        self._pending_sentence_time = now
        self._last_translated_sentence = raw_sentence
        logger.info("[AUDIT-STABLE] Sentence stabilized: %r", raw_sentence)

        # 7. Translation Request
        req = TranslationRequest(
            source_text=raw_sentence,
            source_lang=cfg.source_language,
            target_lang=cfg.target_language,
            timestamp=frame.timestamp,
        )

        try:
            t_trans0 = time.perf_counter()
            result = self.translator_engine.translate(req)
            t_trans_ms = (time.perf_counter() - t_trans0) * 1000.0
            if result.translated_text:
                e2e_ms = max(0.0, (time.time() - frame.timestamp) * 1000.0) if frame.timestamp > 0 else (t_ocr_ms + t_trans_ms)
                logger.info("[AUDIT-TRANS] (OCR: %.1fms | Trans: %.1fms | Total E2E: %.1fms) %r ➔ %r", t_ocr_ms, t_trans_ms, e2e_ms, raw_sentence, result.translated_text)
                self.signals.subtitle_ready.emit(result.translated_text)
                # Record to persistent session history
                with self._state_lock:
                    session_id = self._session_id
                rec_id = self.history_recorder.record(
                    session_id=session_id,
                    start_time=frame.timestamp if frame.timestamp > 0 else now,
                    end_time=now + 2.0,
                    source_lang=cfg.source_language,
                    target_lang=cfg.target_language,
                    source_text=raw_sentence,
                    translated_text=result.translated_text,
                )
                if rec_id is not None:
                    with self._state_lock:
                        if self._session_id == session_id:
                            self._last_record_id = rec_id
        except Exception as e:
            logger.warning("[AUDIT-TRANS-ERR] Translation failed: %s", e)
            self.signals.error_occurred.emit(f"Translation failed: {e}")
