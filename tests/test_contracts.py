"""Unit tests for domain data contracts."""

import numpy as np
import pytest
from core.contracts import (
    CaptureMode,
    Frame,
    Rect,
    SubtitleBox,
    SubtitleDetection,
    TranslationRequest,
    TranslationResult,
    WindowInfo,
)


def test_rect_geometry() -> None:
    rect = Rect(left=100, top=200, width=800, height=600)
    assert rect.right == 900
    assert rect.bottom == 800
    assert rect.center_x == 500.0
    assert rect.center_y == 500.0
    assert rect.as_tuple() == (100, 200, 800, 600)


def test_frame_contract() -> None:
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    rect = Rect(0, 0, 640, 480)
    frame = Frame(image=dummy_img, timestamp=123.456, source_rect=rect)

    assert frame.height == 480
    assert frame.width == 640
    assert frame.timestamp == 123.456


def test_subtitle_box_and_detection() -> None:
    raw_points = [[10.0, 20.0], [50.0, 20.0], [50.0, 40.0], [10.0, 40.0]]
    box = SubtitleBox.from_list(raw_points)

    assert box.min_y == 20.0
    assert box.max_y == 40.0
    assert box.center_y == 30.0

    # Verify invalid point count raises ValueError
    with pytest.raises(ValueError, match="Bounding polygon must have exactly 4 points"):
        SubtitleBox.from_list([[0.0, 0.0], [1.0, 1.0]])

    det = SubtitleDetection(
        text="Hello World",
        confidence=0.98,
        box=box,
        language="en",
    )
    assert det.text == "Hello World"
    assert det.confidence == 0.98
    assert det.box.center_y == 30.0


def test_translation_contracts() -> None:
    req = TranslationRequest(source_text="Hello", source_lang="en", target_lang="id")
    res = TranslationResult(
        source_text="Hello",
        translated_text="Halo",
        source_lang="en",
        target_lang="id",
        from_cache=True,
        latency_ms=0.5,
    )

    assert req.source_text == "Hello"
    assert res.translated_text == "Halo"
    assert res.from_cache is True
