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


def test_rapidocr_initialization_parameters() -> None:
    with patch("core.ocr.engine.RapidOCR") as mock_rapid:
        _ = RapidOCREngine()
        mock_rapid.assert_called_once_with(use_cls=False, det_unclip_ratio=2.0)


def test_rapidocr_real_instance_unclip_ratio() -> None:
    """Verify that det_unclip_ratio actually reaches DBPostProcess in the real RapidOCR engine."""
    from core.ocr.engine import HAS_RAPIDOCR
    if not HAS_RAPIDOCR:
        pytest.skip("rapidocr-onnxruntime not installed")
    engine = RapidOCREngine()
    # Confirm DBPostProcess postprocessor has active unclip_ratio == 2.0
    assert engine._engine.text_det.postprocess_op.unclip_ratio == 2.0


def test_rapidocr_adaptive_strip_cropping() -> None:
    mock_instance = MagicMock()
    mock_results = [
        [
            [[20.0, 10.0], [200.0, 10.0], [200.0, 40.0], [20.0, 40.0]],
            "Adaptive Cropped Text",
            0.98,
        ]
    ]
    mock_instance.return_value = (mock_results, [0.01])

    engine = RapidOCREngine(rapidocr_instance=mock_instance)
    # Image: height 180, width 800.
    # Empty black padding top (0-60) and bottom (120-180), active text strip in (60-120).
    test_img = np.zeros((180, 800, 3), dtype=np.uint8)
    test_img[70:110, 50:400] = 255  # bright subtitle strip

    detections = engine.detect(test_img)
    assert len(detections) == 1
    # Verify mock was called with cropped height (< 180)
    called_img = mock_instance.call_args[0][0]
    assert called_img.shape[0] < 180
    assert called_img.shape[1] == 800

    # Verify that bounding box Y coordinates were adjusted back with y_offset
    det = detections[0]
    assert det.text == "Adaptive Cropped Text"
    # Y-coordinates should be restored to original coordinate space (> 10.0)
    assert det.box.points[0][1] > 10.0


def test_rapidocr_initialization_failure_when_uninstalled() -> None:
    with patch("core.ocr.engine.HAS_RAPIDOCR", False):
        with pytest.raises(RuntimeError, match="rapidocr-onnxruntime is not installed"):
            RapidOCREngine()
