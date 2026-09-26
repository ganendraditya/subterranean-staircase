"""Universal cross-platform screen grabber implementation using `mss`.

Captures primary and secondary displays delivering standard BGR NumPy arrays.
"""

from __future__ import annotations

import time
from typing import List, Optional
import mss
import numpy as np

from core.capture.base import BaseCapture
from core.contracts import Frame, Rect, WindowInfo


class MSSScreenCapture(BaseCapture):
    """Screen grabber powered by the cross-platform `mss` library."""

    def __init__(self) -> None:
        # Use mss.MSS() or fallback to mss.mss() for backward compatibility
        self._sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()

    def list_windows(self) -> List[WindowInfo]:
        """Listing specific OS windows requires OS-level APIs (handled by platform drivers)."""
        return []

    def get_monitor_bounds(self, monitor_index: int = 1) -> Rect:
        """Get bounds rectangle for a specific monitor index (1-based index)."""
        monitors = self._sct.monitors
        if not (1 <= monitor_index < len(monitors)):
            raise ValueError(f"Monitor index {monitor_index} out of range (1..{len(monitors) - 1})")

        mon = monitors[monitor_index]
        return Rect(
            left=mon["left"],
            top=mon["top"],
            width=mon["width"],
            height=mon["height"],
        )

    def grab_screen(self, monitor_index: int = 1, crop_rect: Optional[Rect] = None) -> Frame:
        """Capture the screen of the given monitor, optionally cropped by crop_rect."""
        bounds = self.get_monitor_bounds(monitor_index)

        if crop_rect is not None:
            # Differentiate monitor-local coordinates [0..width) from global desktop coordinates
            # A coordinate is local if it fits strictly inside monitor dimensions
            # and is outside the global monitor bounds (when bounds.left != 0 or bounds.top != 0)
            is_already_global = (
                bounds.left <= crop_rect.left < bounds.right
                and bounds.top <= crop_rect.top < bounds.bottom
            )

            if not is_already_global and (bounds.left != 0 or bounds.top != 0) and 0 <= crop_rect.left < bounds.width and 0 <= crop_rect.top < bounds.height:
                offset_left = bounds.left + crop_rect.left
                offset_top = bounds.top + crop_rect.top
            else:
                offset_left = crop_rect.left
                offset_top = crop_rect.top

            # Clean geometric intersection between crop_rect and monitor bounds
            target_left = max(bounds.left, offset_left)
            target_top = max(bounds.top, offset_top)
            target_right = min(bounds.right, offset_left + max(1, crop_rect.width))
            target_bottom = min(bounds.bottom, offset_top + max(1, crop_rect.height))

            if target_right <= target_left or target_bottom <= target_top:
                raise ValueError("crop_rect does not intersect with the monitor area")

            width = target_right - target_left
            height = target_bottom - target_top

            capture_bbox = {
                "left": target_left,
                "top": target_top,
                "width": width,
                "height": height,
            }
            actual_rect = Rect(left=target_left, top=target_top, width=width, height=height)
        else:
            capture_bbox = {
                "left": bounds.left,
                "top": bounds.top,
                "width": bounds.width,
                "height": bounds.height,
            }
            actual_rect = bounds

        sct_img = self._sct.grab(capture_bbox)
        # Convert raw BGRA bytes into BGR numpy array without sequence conversion overhead
        raw_bytes = sct_img.raw if hasattr(sct_img, "raw") else bytes(sct_img)
        img_np = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((sct_img.height, sct_img.width, 4))[:, :, :3]

        return Frame(
            image=img_np,
            timestamp=time.time(),
            source_rect=actual_rect,
        )

    def grab_window(self, window_id: int | str, crop_rect: Optional[Rect] = None) -> Frame:
        """MSS is purely screen-coordinate based. Window grabbing is delegated to platform drivers."""
        raise NotImplementedError("Window-specific grabbing is handled by platform drivers (Quartz/Win32)")

    def close(self) -> None:
        """Release MSS resources."""
        self._sct.close()

    def __enter__(self) -> MSSScreenCapture:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
