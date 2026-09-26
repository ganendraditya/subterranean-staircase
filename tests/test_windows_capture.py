"""Unit tests for Windows Window Capture and Capture Factory."""

from unittest.mock import MagicMock, patch
import pytest

from core.capture.factory import create_capture_driver
from core.capture.platform.windows import WindowsWindowCapture, _get_window_rect
from core.capture.screen import MSSScreenCapture
from core.contracts import Rect


def test_capture_factory_macos() -> None:
    with patch("sys.platform", "darwin"):
        driver = create_capture_driver()
        assert driver.__class__.__name__ == "MacOSWindowCapture"


def test_capture_factory_windows() -> None:
    with patch("sys.platform", "win32"):
        driver = create_capture_driver()
        assert driver.__class__.__name__ == "WindowsWindowCapture"


def test_capture_factory_fallback_linux() -> None:
    with patch("sys.platform", "linux"):
        driver = create_capture_driver()
        assert isinstance(driver, MSSScreenCapture)


def test_windows_capture_on_non_windows_raises_or_empty() -> None:
    # Explicitly mock HAS_WIN32 as False to test fallback behavior on Linux/unsupported OS
    with patch("core.capture.platform.windows.HAS_WIN32", False), \
         patch("core.capture.platform.windows._user32", None), \
         patch("core.capture.platform.windows._dwmapi", None):
        capturer = WindowsWindowCapture()
        assert capturer.list_windows() == []

        with pytest.raises(RuntimeError, match="only available on Windows"):
            capturer.grab_window(1234)

        assert _get_window_rect(1234) is None


def test_windows_grab_window_mocked() -> None:
    import numpy as np
    with patch("core.capture.platform.windows.HAS_WIN32", True), \
         patch("core.capture.platform.windows._user32") as mock_u32, \
         patch("core.capture.platform.windows._gdi32") as mock_gdi, \
         patch("core.capture.platform.windows._get_window_rect") as mock_rect:

        mock_u32.IsWindow.return_value = True
        mock_rect.return_value = Rect(10, 20, 400, 300)

        mock_u32.GetWindowDC.return_value = 1001
        mock_gdi.CreateCompatibleDC.return_value = 1002
        mock_gdi.CreateCompatibleBitmap.return_value = 1003
        mock_gdi.SelectObject.return_value = 1004
        mock_u32.PrintWindow.return_value = 1

        def fake_get_di_bits(dc, bmp, start, lines, buf, info, usage):
            buf.raw = np.zeros((300, 400, 4), dtype=np.uint8).tobytes()
            return lines

        mock_gdi.GetDIBits.side_effect = fake_get_di_bits

        capturer = WindowsWindowCapture()
        frame = capturer.grab_window(999)

        assert frame.width == 400
        assert frame.height == 300
        assert frame.source_rect == Rect(10, 20, 400, 300)
        assert frame.window_id == 999
