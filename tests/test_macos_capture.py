"""Unit tests for macOS Quartz Window Capture."""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from core.capture.platform.macos import MacOSWindowCapture
from core.contracts import Rect


@pytest.fixture
def mock_quartz():
    with patch("core.capture.platform.macos.Quartz") as mock_q:
        mock_q.kCGWindowListOptionOnScreenOnly = 1
        mock_q.kCGWindowListExcludeDesktopElements = 2
        mock_q.kCGNullWindowID = 0
        mock_q.kCGWindowLayer = "kCGWindowLayer"
        mock_q.kCGWindowBounds = "kCGWindowBounds"
        mock_q.kCGWindowOwnerName = "kCGWindowOwnerName"
        mock_q.kCGWindowName = "kCGWindowName"
        mock_q.kCGWindowNumber = "kCGWindowNumber"

        # Mock window list
        mock_win_info = {
            "kCGWindowLayer": 0,
            "kCGWindowNumber": 1234,
            "kCGWindowOwnerName": "VLC",
            "kCGWindowName": "Big Buck Bunny",
            "kCGWindowBounds": {"X": 50, "Y": 60, "Width": 1280, "Height": 720},
        }
        mock_q.CGWindowListCopyWindowInfo.side_effect = lambda opt, win_id: [
            mock_win_info
        ] if win_id == 1234 or win_id == 0 else []

        # Mock Image capture
        mock_img = MagicMock()
        mock_q.CGWindowListCreateImage.return_value = mock_img
        mock_q.CGImageGetWidth.return_value = 1280
        mock_q.CGImageGetHeight.return_value = 720
        mock_q.CGImageGetBytesPerRow.return_value = 1280 * 4

        # Mock Data Provider (1280 * 720 * 4 bytes)
        raw_bytes = np.zeros((720, 1280, 4), dtype=np.uint8).tobytes()
        mock_q.CGDataProviderCopyData.return_value = raw_bytes

        yield mock_q


def test_macos_list_windows(mock_quartz) -> None:
    # Set explicit return value for list_windows call
    mock_quartz.CGWindowListCopyWindowInfo.side_effect = None
    mock_quartz.CGWindowListCopyWindowInfo.return_value = [
        {
            "kCGWindowLayer": 0,
            "kCGWindowNumber": 1234,
            "kCGWindowOwnerName": "VLC",
            "kCGWindowName": "Big Buck Bunny",
            "kCGWindowBounds": {"X": 50, "Y": 60, "Width": 1280, "Height": 720},
        },
        {
            "kCGWindowLayer": 25,
            "kCGWindowNumber": 9999,
            "kCGWindowOwnerName": "Dock",
            "kCGWindowName": "",
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 100, "Height": 50},
        },
    ]

    capturer = MacOSWindowCapture()
    windows = capturer.list_windows()

    assert len(windows) == 1
    win = windows[0]
    assert win.window_id == 1234
    assert win.owner_name == "VLC"
    assert win.title == "Big Buck Bunny"
    assert win.rect == Rect(50, 60, 1280, 720)


def test_macos_grab_window(mock_quartz) -> None:
    capturer = MacOSWindowCapture()
    frame = capturer.grab_window(1234)

    assert frame.width == 1280
    assert frame.height == 720
    assert frame.source_rect == Rect(50, 60, 1280, 720)
    assert frame.window_id == 1234


def test_macos_grab_window_with_crop(mock_quartz) -> None:
    capturer = MacOSWindowCapture()
    crop = Rect(left=0, top=500, width=1280, height=200)
    frame = capturer.grab_window(1234, crop_rect=crop)

    assert frame.width == 1280
    assert frame.height == 200
    assert frame.source_rect.top == 60 + 500  # Window Y offset + crop Y offset


def test_macos_grab_window_not_found(mock_quartz) -> None:
    capturer = MacOSWindowCapture()
    with pytest.raises(ValueError, match="not found"):
        capturer.grab_window(999999)


def test_macos_grab_window_with_row_padding(mock_quartz) -> None:
    width = 1280
    height = 720
    padding = 64
    bytes_per_row = (width * 4) + padding

    mock_quartz.CGImageGetWidth.return_value = width
    mock_quartz.CGImageGetHeight.return_value = height
    mock_quartz.CGImageGetBytesPerRow.return_value = bytes_per_row

    padded_buffer = np.zeros((height, bytes_per_row), dtype=np.uint8)
    padded_buffer[:, : width * 4] = 255
    mock_quartz.CGDataProviderCopyData.return_value = padded_buffer.tobytes()

    capturer = MacOSWindowCapture()
    frame = capturer.grab_window(1234)

    assert frame.width == width
    assert frame.height == height
    assert frame.image.shape == (height, width, 3)
    assert np.all(frame.image == 255)
