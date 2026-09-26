"""Unit tests for MSSScreenCapture universal screen grabber."""

import mss
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from core.capture.screen import MSSScreenCapture
from core.contracts import Rect


@pytest.fixture
def mock_mss():
    factory_name = "mss.MSS" if hasattr(mss, "MSS") else "mss.mss"
    with patch(factory_name) as mock_cls:
        instance = MagicMock()
        instance.monitors = [
            {"left": 0, "top": 0, "width": 3840, "height": 1080},  # all monitors
            {"left": 0, "top": 0, "width": 1920, "height": 1080},  # monitor 1
            {"left": 1920, "top": 0, "width": 1920, "height": 1080},  # monitor 2
        ]
        # Generate dummy 1080x1920 BGRA image
        dummy_bgra = np.zeros((1080, 1920, 4), dtype=np.uint8)
        instance.grab.return_value = MagicMock(
            raw=dummy_bgra.tobytes(),
            height=1080,
            width=1920,
        )
        mock_cls.return_value = instance
        yield instance


def test_mss_get_monitor_bounds(mock_mss) -> None:
    grabber = MSSScreenCapture()
    bounds = grabber.get_monitor_bounds(monitor_index=1)
    assert bounds.left == 0
    assert bounds.top == 0
    assert bounds.width == 1920
    assert bounds.height == 1080

    bounds_mon2 = grabber.get_monitor_bounds(monitor_index=2)
    assert bounds_mon2.left == 1920
    assert bounds_mon2.width == 1920


def test_mss_invalid_monitor_index(mock_mss) -> None:
    grabber = MSSScreenCapture()
    with pytest.raises(ValueError, match="out of range"):
        grabber.get_monitor_bounds(monitor_index=99)


def test_mss_grab_screen_full(mock_mss) -> None:
    grabber = MSSScreenCapture()
    frame = grabber.grab_screen(monitor_index=1)

    assert frame.image.shape == (1080, 1920, 3)  # Converted to BGR
    assert frame.source_rect.width == 1920
    assert frame.source_rect.height == 1080
    assert frame.timestamp > 0


def test_mss_grab_screen_cropped(mock_mss) -> None:
    grabber = MSSScreenCapture()
    crop = Rect(left=100, top=200, width=500, height=300)

    # Return mocked array matching crop size
    mock_mss.grab.return_value = MagicMock(
        raw=np.zeros((300, 500, 4), dtype=np.uint8).tobytes(),
        height=300,
        width=500,
    )

    frame = grabber.grab_screen(monitor_index=1, crop_rect=crop)
    assert frame.source_rect.left == 100
    assert frame.source_rect.top == 200
    assert frame.source_rect.width == 500
    assert frame.source_rect.height == 300


def test_mss_grab_screen_out_of_bounds_clamping(mock_mss) -> None:
    grabber = MSSScreenCapture()
    # Crop is far beyond monitor bounds [0..1920, 0..1080]
    out_of_bounds = Rect(left=5000, top=5000, width=500, height=300)

    # Disjoint crop rect should raise ValueError
    with pytest.raises(ValueError, match="does not intersect"):
        grabber.grab_screen(monitor_index=1, crop_rect=out_of_bounds)


def test_monitor_relative_coordinate_offsetting(mock_mss) -> None:
    grabber = MSSScreenCapture()
    # Secondary monitor with left offset 1920
    crop_local = Rect(left=50, top=60, width=400, height=200)

    mock_mss.grab.return_value = MagicMock(
        raw=np.zeros((200, 400, 4), dtype=np.uint8).tobytes(),
        height=200,
        width=400,
    )

    frame = grabber.grab_screen(monitor_index=2, crop_rect=crop_local)
    # The target should be translated to monitor 2's space: 1920 + 50 = 1970
    assert frame.source_rect.left == 1970
    assert frame.source_rect.top == 60
    assert frame.source_rect.width == 400
    assert frame.source_rect.height == 200


def test_mss_grab_window_raises_not_implemented() -> None:
    grabber = MSSScreenCapture()
    with pytest.raises(NotImplementedError):
        grabber.grab_window(window_id=123)
