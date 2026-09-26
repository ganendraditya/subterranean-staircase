"""Unit tests for BaseCapture interface and ROI geometry helper."""

from typing import List, Optional
import numpy as np
import pytest

from core.capture import BaseCapture, ROIHelper
from core.contracts import Frame, Rect, WindowInfo


class DummyCapture(BaseCapture):
    """Mock implementation to verify the abstract interface contract."""

    def list_windows(self) -> List[WindowInfo]:
        return [
            WindowInfo(
                window_id=101,
                title="VLC media player",
                owner_name="vlc",
                rect=Rect(100, 100, 1280, 720),
            )
        ]

    def grab_screen(self, monitor_index: int = 1, crop_rect: Optional[Rect] = None) -> Frame:
        rect = crop_rect or Rect(0, 0, 1920, 1080)
        img = np.zeros((rect.height, rect.width, 3), dtype=np.uint8)
        return Frame(image=img, timestamp=1.0, source_rect=rect)

    def grab_window(self, window_id: int | str, crop_rect: Optional[Rect] = None) -> Frame:
        rect = crop_rect or Rect(100, 100, 1280, 720)
        img = np.zeros((rect.height, rect.width, 3), dtype=np.uint8)
        return Frame(image=img, timestamp=1.0, source_rect=rect, window_id=window_id)

    def get_monitor_bounds(self, monitor_index: int = 1) -> Rect:
        return Rect(0, 0, 1920, 1080)


def test_base_capture_interface_contract() -> None:
    driver = DummyCapture()
    windows = driver.list_windows()
    assert len(windows) == 1
    assert windows[0].title == "VLC media player"

    frame = driver.grab_screen()
    assert frame.width == 1920
    assert frame.height == 1080

    win_frame = driver.grab_window(101)
    assert win_frame.window_id == 101


def test_roi_helper_crop_rect() -> None:
    # 100x100 white image
    image = np.ones((100, 100, 3), dtype=np.uint8) * 255
    # Mark a 20x20 region at (10, 20) with zeros
    image[20:40, 10:30] = 0

    crop = ROIHelper.crop_rect(image, Rect(left=10, top=20, width=20, height=20))
    assert crop.shape == (20, 20, 3)
    assert np.all(crop == 0)


def test_roi_helper_out_of_bounds_clamping() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    # Exceeding bounds
    crop = ROIHelper.crop_rect(image, Rect(left=80, top=80, width=50, height=50))
    # Should safely clamp to remaining area (20x20) without throwing IndexError
    assert crop.shape == (20, 20, 3)


def test_roi_helper_bottom_and_top_bands() -> None:
    video_rect = Rect(left=0, top=0, width=1920, height=1080)

    # Bottom 25% (1080 * 0.25 = 270 px)
    bottom_band = ROIHelper.get_bottom_band(video_rect, ratio=0.25)
    assert bottom_band.left == 0
    assert bottom_band.width == 1920
    assert bottom_band.height == 270
    assert bottom_band.top == 1080 - 270
    assert bottom_band.bottom == 1080

    # Top 20% (1080 * 0.20 = 216 px)
    top_band = ROIHelper.get_top_band(video_rect, ratio=0.20)
    assert top_band.left == 0
    assert top_band.width == 1920
    assert top_band.height == 216
    assert top_band.top == 0
    assert top_band.bottom == 216

def test_roi_helper_invalid_ratio() -> None:
    video_rect = Rect(left=0, top=0, width=1920, height=1080)
    with pytest.raises(ValueError, match="Band ratio must be between 0.0 and 1.0"):
        ROIHelper.get_bottom_band(video_rect, ratio=1.5)
    
    with pytest.raises(ValueError, match="Band ratio must be between 0.0 and 1.0"):
        ROIHelper.get_top_band(video_rect, ratio=-0.5)
    video_rect = Rect(left=0, top=0, width=1920, height=1080)

    # Bottom 25% (1080 * 0.25 = 270 px)
    bottom_band = ROIHelper.get_bottom_band(video_rect, ratio=0.25)
    assert bottom_band.left == 0
    assert bottom_band.width == 1920
    assert bottom_band.height == 270
    assert bottom_band.top == 1080 - 270
    assert bottom_band.bottom == 1080

    # Top 20% (1080 * 0.20 = 216 px)
    top_band = ROIHelper.get_top_band(video_rect, ratio=0.20)
    assert top_band.left == 0
    assert top_band.width == 1920
    assert top_band.height == 216
    assert top_band.top == 0
    assert top_band.bottom == 216


def test_roi_helper_clamp_to_bounds() -> None:
    out_of_screen = Rect(left=1900, top=1000, width=500, height=500)
    clamped = ROIHelper.clamp_to_bounds(out_of_screen, max_width=1920, max_height=1080)

    assert clamped.left == 1900
    assert clamped.top == 1000
    assert clamped.width == 20
    assert clamped.height == 80
    assert clamped.right == 1920
    assert clamped.bottom == 1080
