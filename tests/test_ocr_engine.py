"""Unit tests for BaseOCR and RapidOCREngine wrapper."""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from core.contracts import Frame, Rect, SubtitleBox, SubtitleDetection
from core.ocr.engine import BaseOCR, RapidOCREngine


def test_rapidocr_wrapper_with_mock() -> None:
    mock_instance = MagicMock()
    # Mock return format: (results, elapse_list)
    mock_results = [
        [
            [[10, 20], [200, 20], [200, 60], [10, 60]],  # dt_boxes
            "Subtitles are working perfectly",           # rec_res
            0.985,                                        # score
        ]
    ]
    mock_instance.return_value = (mock_results, [0.01, 0.02, 0.01])

    engine = RapidOCREngine(rapidocr_instance=mock_instance)
    dummy_img = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame = Frame(image=dummy_img, timestamp=123.456, source_rect=Rect(0, 0, 1280, 720))

    detections = engine.detect(frame)
    assert len(detections) == 1

    det = detections[0]
    assert det.text == "Subtitles are working perfectly"
    assert det.confidence == 0.985
    assert det.timestamp == 123.456
    assert det.box.center_y == 40.0


def test_rapidocr_empty_or_none_image() -> None:
    mock_instance = MagicMock()
    engine = RapidOCREngine(rapidocr_instance=mock_instance)

    # Empty array
    empty_img = np.array([])
    assert engine.detect(empty_img) == []

    # None results from engine
    mock_instance.return_value = (None, None)
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    assert engine.detect(dummy_img) == []


def test_rapidocr_skips_malformed_boxes() -> None:
    mock_instance = MagicMock()
    # Provide an invalid box with only 2 points
    mock_results = [
        [
            [[10, 20], [200, 20]],
            "Malformed",
            0.90,
        ]
    ]
    mock_instance.return_value = (mock_results, [0.01])

    engine = RapidOCREngine(rapidocr_instance=mock_instance)
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    detections = engine.detect(dummy_img)

    # Malformed box safely skipped without crashing
    assert len(detections) == 0


def test_rapidocr_initialization_failure_when_uninstalled() -> None:
    with patch("core.ocr.engine.HAS_RAPIDOCR", False):
        with pytest.raises(RuntimeError, match="rapidocr-onnxruntime is not installed"):
            RapidOCREngine()
