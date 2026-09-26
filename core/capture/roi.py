"""ROI (Region of Interest) geometry helpers and coordinate clipping."""

from __future__ import annotations

from core.contracts import Rect
import numpy as np


class ROIHelper:
    """Helper methods for calculating and slicing regions of interest (ROI)."""

    @staticmethod
    def crop_rect(image: np.ndarray, rect: Rect) -> np.ndarray:
        """Crop an image array to the given Rect bounds with dimension safety clamping."""
        img_h, img_w = image.shape[:2]

        left = max(0, min(rect.left, img_w))
        top = max(0, min(rect.top, img_h))
        right = max(left, min(rect.right, img_w))
        bottom = max(top, min(rect.bottom, img_h))

        return image[top:bottom, left:right]

    @staticmethod
    def get_bottom_band(rect: Rect, ratio: float = 0.25) -> Rect:
        """Calculate bottom subtitle focus band (default bottom 25% of rectangle)."""
        if not (0.0 < ratio < 1.0):
            raise ValueError("Band ratio must be between 0.0 and 1.0")
        band_h = int(rect.height * ratio)
        band_top = rect.top + (rect.height - band_h)
        return Rect(left=rect.left, top=band_top, width=rect.width, height=band_h)

    @staticmethod
    def get_top_band(rect: Rect, ratio: float = 0.20) -> Rect:
        """Calculate top subtitle focus band (default top 20% of rectangle)."""
        if not (0.0 < ratio < 1.0):
            raise ValueError("Band ratio must be between 0.0 and 1.0")
        band_h = int(rect.height * ratio)
        return Rect(left=rect.left, top=rect.top, width=rect.width, height=band_h)

    @staticmethod
    def clamp_to_bounds(rect: Rect, max_width: int, max_height: int) -> Rect:
        """Clamp a rectangle entirely within screen/image boundaries."""
        left = max(0, min(rect.left, max_width))
        top = max(0, min(rect.top, max_height))
        right = max(left, min(rect.right, max_width))
        bottom = max(top, min(rect.bottom, max_height))
        return Rect(left=left, top=top, width=right - left, height=bottom - top)
