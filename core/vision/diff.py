"""Perceptual frame difference detection and short-circuit comparator.

Computes downsampled grayscale pixel variance to bypass OCR when screen/subtitle region is static.
Executes in sub-millisecond time (< 1ms).
"""

from __future__ import annotations

from typing import Optional, Tuple
import numpy as np


class FrameDiffDetector:
    """Detects whether two consecutive video/screen frames have meaningfully changed."""

    def __init__(
        self,
        downsample_size: Tuple[int, int] = (64, 36),
        default_threshold: float = 0.015,
    ) -> None:
        """Initialize detector with target downsample resolution (W, H) and variance threshold."""
        self.downsample_size = downsample_size  # (width, height)
        self.default_threshold = default_threshold
        self._prev_thumbnail: Optional[np.ndarray] = None

    def _to_grayscale_thumbnail(self, image: np.ndarray) -> np.ndarray:
        """Convert BGR image to small float32 grayscale thumbnail array normalized to [0, 1]."""
        # Slicing with strides (step downsampling) is 10x faster than full float conversion
        target_w, target_h = self.downsample_size
        src_h, src_w = image.shape[:2]

        if src_h <= 0 or src_w <= 0:
            return np.zeros((target_h, target_w), dtype=np.float32)

        step_y = max(1, src_h // target_h)
        step_x = max(1, src_w // target_w)

        # Slice down directly on uint8 before color conversion
        sampled = image[::step_y, ::step_x][:target_h, :target_w]

        if sampled.ndim == 3 and sampled.shape[2] == 3:
            # Integer approximation of luminance: (B*29 + G*150 + R*77) >> 8
            gray = (
                sampled[:, :, 0].astype(np.int32) * 29
                + sampled[:, :, 1].astype(np.int32) * 150
                + sampled[:, :, 2].astype(np.int32) * 77
            ) >> 8
        else:
            gray = sampled

        # Pad if sampled size was slightly smaller than target
        if gray.shape[0] < target_h or gray.shape[1] < target_w:
            padded = np.zeros((target_h, target_w), dtype=np.float32)
            padded[:gray.shape[0], :gray.shape[1]] = gray / 255.0
            return padded

        return (gray / 255.0).astype(np.float32)

    def calculate_diff(self, current_image: np.ndarray) -> float:
        """Compute normalized absolute pixel difference [0.0..1.0] against the previous frame.

        Returns 1.0 on the first frame (since there is no previous reference).
        """
        curr_thumb = self._to_grayscale_thumbnail(current_image)

        if self._prev_thumbnail is None:
            self._prev_thumbnail = curr_thumb
            return 1.0

        diff = float(np.mean(np.abs(curr_thumb - self._prev_thumbnail)))
        self._prev_thumbnail = curr_thumb
        return diff

    def has_changed(
        self,
        current_image: np.ndarray,
        threshold: Optional[float] = None,
    ) -> bool:
        """Return True if frame change exceeds threshold, short-circuiting unchanged frames."""
        thresh = threshold if threshold is not None else self.default_threshold
        score = self.calculate_diff(current_image)
        return score >= thresh

    def reset(self) -> None:
        """Clear previous reference frame."""
        self._prev_thumbnail = None
