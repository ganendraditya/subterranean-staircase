"""macOS Native Window Enumerator and Window Grabber using Apple Quartz / CoreGraphics.

Extracts list of visible application windows and provides targeted window frame capture.
"""

from __future__ import annotations

import time
from typing import List, Optional
import numpy as np

from core.capture.base import BaseCapture
from core.capture.screen import MSSScreenCapture
from core.contracts import Frame, Rect, WindowInfo

try:
    import Quartz
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False


class MacOSWindowCapture(BaseCapture):
    """macOS-specific window grabber and enumerator via Apple Quartz (CoreGraphics)."""

    def __init__(self, fallback_screen_capture: Optional[BaseCapture] = None) -> None:
        self._screen_capture = fallback_screen_capture or MSSScreenCapture()

    def list_windows(self) -> List[WindowInfo]:
        """List on-screen visible application windows in macOS."""
        if not HAS_QUARTZ:
            return []

        # Options: Only on-screen windows, exclude desktop/dock artifacts
        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
        results: List[WindowInfo] = []

        for win in window_list:
            # Filter out non-standard layers (keep standard window layer = 0)
            layer = win.get(Quartz.kCGWindowLayer, 0)
            if layer != 0:
                continue

            # Bounds dictionary
            bounds_dict = win.get(Quartz.kCGWindowBounds, {})
            width = int(bounds_dict.get("Width", 0))
            height = int(bounds_dict.get("Height", 0))
            left = int(bounds_dict.get("X", 0))
            top = int(bounds_dict.get("Y", 0))

            # Skip tiny invisible helper windows/status items
            if width < 100 or height < 100:
                continue

            owner_name = str(win.get(Quartz.kCGWindowOwnerName, ""))
            window_title = str(win.get(Quartz.kCGWindowName, "")) or owner_name
            window_id = int(win.get(Quartz.kCGWindowNumber, 0))

            results.append(
                WindowInfo(
                    window_id=window_id,
                    title=window_title,
                    owner_name=owner_name,
                    rect=Rect(left=left, top=top, width=width, height=height),
                    is_minimized=False,
                )
            )

        return results

    def get_monitor_bounds(self, monitor_index: int = 1) -> Rect:
        """Delegate monitor boundaries calculation to the screen capture driver."""
        return self._screen_capture.get_monitor_bounds(monitor_index)

    def grab_screen(self, monitor_index: int = 1, crop_rect: Optional[Rect] = None) -> Frame:
        """Capture monitor screen via the underlying screen capture driver."""
        return self._screen_capture.grab_screen(monitor_index, crop_rect)

    def grab_window(self, window_id: int | str, crop_rect: Optional[Rect] = None) -> Frame:
        """Capture a targeted macOS window using CGWindowListCreateImage."""
        if not HAS_QUARTZ:
            raise RuntimeError("Quartz framework not available on this platform")

        win_id = int(window_id)
        # Query only the target window info directly instead of enumerating all desktop windows
        info_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionIncludingWindow,
            win_id,
        )
        if not info_list:
            raise ValueError(f"Window with ID {window_id} not found or no longer visible")

        win = info_list[0]
        bounds = win.get(Quartz.kCGWindowBounds, {})
        window_rect = Rect(
            left=int(bounds.get("X", 0)),
            top=int(bounds.get("Y", 0)),
            width=int(bounds.get("Width", 0)),
            height=int(bounds.get("Height", 0)),
        )

        # Capture the window image directly from WindowServer
        image_ref = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            win_id,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )

        if image_ref is None:
            raise RuntimeError(f"Failed to capture image for window {window_id} (check Screen Recording permissions)")

        width = Quartz.CGImageGetWidth(image_ref)
        height = Quartz.CGImageGetHeight(image_ref)
        bytes_per_row = Quartz.CGImageGetBytesPerRow(image_ref)

        # Extract raw bitmap data
        prov = Quartz.CGImageGetDataProvider(image_ref)
        data = Quartz.CGDataProviderCopyData(prov)
        buf = np.frombuffer(data, dtype=np.uint8)

        # Handle row stride/padding
        expected_size = height * bytes_per_row
        if buf.size < expected_size:
            raise RuntimeError("Unexpected buffer size returned by Quartz image provider")

        img_raw = buf[:expected_size].reshape((height, bytes_per_row))
        # Slice out row padding to get tightly packed (height, width, 4)
        img_bgra = img_raw[:, : width * 4].reshape((height, width, 4))
        # Convert to BGR format
        img_bgr = img_bgra[:, :, :3].copy()

        actual_rect = window_rect
        if crop_rect is not None:
            if crop_rect.width <= 0 or crop_rect.height <= 0:
                raise ValueError("crop_rect width and height must be positive")

            # Local cropping relative to window bounds
            target_left = max(0, min(crop_rect.left, width))
            target_top = max(0, min(crop_rect.top, height))
            target_right = max(target_left, min(crop_rect.right, width))
            target_bottom = max(target_top, min(crop_rect.bottom, height))

            if target_right == target_left or target_bottom == target_top:
                raise ValueError("crop_rect does not intersect with the window area")

            img_bgr = img_bgr[target_top:target_bottom, target_left:target_right]
            actual_rect = Rect(
                left=window_rect.left + target_left,
                top=window_rect.top + target_top,
                width=target_right - target_left,
                height=target_bottom - target_top,
            )

        return Frame(
            image=img_bgr,
            timestamp=time.time(),
            source_rect=actual_rect,
            window_id=win_id,
        )
