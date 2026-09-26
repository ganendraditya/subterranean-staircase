"""Unit tests for DualBandSpatialFilter."""

import pytest
from core.contracts import Rect, SubtitleBox, SubtitleDetection
from core.subtitle.spatial import DualBandSpatialFilter


def _make_det(text: str, center_y: float, confidence: float = 0.95) -> SubtitleDetection:
    half_h = 10.0
    pts = [
        [100.0, center_y - half_h],
        [300.0, center_y - half_h],
        [300.0, center_y + half_h],
        [100.0, center_y + half_h],
    ]
    return SubtitleDetection(
        text=text,
        confidence=confidence,
        box=SubtitleBox.from_list(pts),
    )


def test_dual_band_filter_ratios() -> None:
    # 1080p frame: top 20% is Y <= 216, bottom 25% is Y >= 810
    frame_rect = Rect(left=0, top=0, width=1920, height=1080)
    filter_engine = DualBandSpatialFilter(top_band_ratio=0.20, bottom_band_ratio=0.25)

    det_top = _make_det("Chapter 1: The Beginning", center_y=150.0)
    det_middle_noise = _make_det("Reading a book in scene", center_y=500.0)
    det_bottom = _make_det("Hello, nice to meet you.", center_y=950.0)

    results = filter_engine.filter_detections(
        [det_middle_noise, det_top, det_bottom],
        frame_rect=frame_rect,
    )

    # Center noise should be eliminated completely
    assert len(results) == 2
    assert results[0].text == "Chapter 1: The Beginning"
    assert results[1].text == "Hello, nice to meet you."


def test_dual_band_filter_confidence_and_length() -> None:
    frame_rect = Rect(left=0, top=0, width=1920, height=1080)
    filter_engine = DualBandSpatialFilter(min_confidence=0.50, min_text_length=2)

    det_low_conf = _make_det("Valid text", center_y=950.0, confidence=0.30)
    det_short_noise = _make_det(".", center_y=950.0, confidence=0.95)
    det_valid = _make_det("Valid text", center_y=950.0, confidence=0.85)

    results = filter_engine.filter_detections(
        [det_low_conf, det_short_noise, det_valid],
        frame_rect=frame_rect,
    )

    assert len(results) == 1
    assert results[0].text == "Valid text"


def test_dual_band_filter_invalid_ratio_raises() -> None:
    with pytest.raises(ValueError, match="top_band_ratio"):
        DualBandSpatialFilter(top_band_ratio=0.6)

    with pytest.raises(ValueError, match="bottom_band_ratio"):
        DualBandSpatialFilter(bottom_band_ratio=-0.1)


def test_dual_band_filter_empty_inputs() -> None:
    filter_engine = DualBandSpatialFilter()
    frame_rect = Rect(left=0, top=0, width=1920, height=1080)
    assert filter_engine.filter_detections([], frame_rect) == []

    # Invalid frame rect
    zero_rect = Rect(left=0, top=0, width=1920, height=0)
    det = _make_det("Test", center_y=10.0)
    assert filter_engine.filter_detections([det], zero_rect) == []
