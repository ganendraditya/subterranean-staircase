"""Unit tests for TranslationPipelineWorker and event orchestration."""

import time
from unittest.mock import MagicMock
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from core.capture.base import BaseCapture
from core.config import ConfigManager
from core.contracts import Frame, Rect, SubtitleBox, SubtitleDetection, TranslationRequest, TranslationResult
from core.ocr.engine import BaseOCR
from core.pipeline import PipelineSignals, TranslationPipelineWorker
from core.translate.local import BaseTranslator


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_pipeline_cycle_end_to_end(qapp, tmp_path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    signals = PipelineSignals()

    # 1. Mock Capture Driver
    mock_capture = MagicMock(spec=BaseCapture)
    img_1 = np.ones((720, 1280, 3), dtype=np.uint8) * 100
    mock_capture.grab_screen.return_value = Frame(
        image=img_1,
        timestamp=1.0,
        source_rect=Rect(0, 0, 1280, 720),
    )

    # 2. Mock OCR Engine
    mock_ocr = MagicMock(spec=BaseOCR)
    box = SubtitleBox.from_list([[100.0, 600.0], [400.0, 600.0], [400.0, 640.0], [100.0, 640.0]])
    mock_ocr.detect.return_value = [
        SubtitleDetection(text="Hello friend", confidence=0.95, box=box, timestamp=1.0)
    ]

    # 3. Mock Translator Engine
    mock_translator = MagicMock(spec=BaseTranslator)
    mock_translator.translate.return_value = TranslationResult(
        source_text="Hello friend",
        translated_text="Halo teman",
        source_lang="en",
        target_lang="id",
    )

    worker = TranslationPipelineWorker(
        config_manager=config_mgr,
        signals=signals,
        capture_driver=mock_capture,
        ocr_engine=mock_ocr,
        translator_engine=mock_translator,
    )
    # Ensure history tracker promotes text to stable on 2nd cycle
    worker.history_tracker.stable_min_count = 1

    received_subtitles: list[str] = []
    signals.subtitle_ready.connect(received_subtitles.append)

    # Execute one pipeline cycle
    worker._process_cycle(config_mgr.config)

    assert len(received_subtitles) == 1
    assert received_subtitles[0] == "Halo teman"
    assert worker._last_translated_sentence == "Hello friend"

    # Second cycle with identical frame: frame-diff short-circuit skips OCR!
    worker._process_cycle(config_mgr.config)
    # No new translation triggered
    assert len(received_subtitles) == 1
    # OCR was only called once
    assert mock_ocr.detect.call_count == 1


def test_pipeline_with_custom_roi_bypasses_spatial_filter(qapp, tmp_path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    signals = PipelineSignals()

    mock_capture = MagicMock(spec=BaseCapture)
    img_1 = np.ones((100, 400, 3), dtype=np.uint8) * 100
    mock_capture.grab_screen.return_value = Frame(
        image=img_1,
        timestamp=1.0,
        source_rect=Rect(100, 200, 400, 100),
    )

    mock_ocr = MagicMock(spec=BaseOCR)
    # Detection located squarely in the middle (Y=50) of the 100px cropped ROI box
    box = SubtitleBox.from_list([[10.0, 40.0], [200.0, 40.0], [200.0, 60.0], [10.0, 60.0]])
    mock_ocr.detect.return_value = [
        SubtitleDetection(text="Custom Box Text", confidence=0.95, box=box, timestamp=1.0)
    ]

    mock_translator = MagicMock(spec=BaseTranslator)
    mock_translator.translate.return_value = TranslationResult(
        source_text="Custom Box Text",
        translated_text="Teks Kotak Kustom",
        source_lang="en",
        target_lang="id",
    )

    worker = TranslationPipelineWorker(
        config_manager=config_mgr,
        signals=signals,
        capture_driver=mock_capture,
        ocr_engine=mock_ocr,
        translator_engine=mock_translator,
    )
    worker.history_tracker.stable_min_count = 1
    worker.set_custom_roi(Rect(100, 200, 400, 100))

    received_subtitles: list[str] = []
    signals.subtitle_ready.connect(received_subtitles.append)

    worker._process_cycle(config_mgr.config)

    assert len(received_subtitles) == 1
    assert received_subtitles[0] == "Teks Kotak Kustom"


def test_pipeline_stop_and_thread_lifecycle(qapp, tmp_path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    signals = PipelineSignals()

    worker = TranslationPipelineWorker(
        config_manager=config_mgr,
        signals=signals,
    )
    worker.start()
    assert worker.isRunning()
    time.sleep(0.05)
    worker.stop(5000)
    assert not worker.isRunning()
