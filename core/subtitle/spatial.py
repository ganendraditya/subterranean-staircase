"""Spatial heuristic filtering for detected subtitles.

Prioritizes bottom band (primary dialog) and top band (secondary captions),
rejecting reading noise, book text, and center-screen UI elements without requiring YOLO.
"""

from __future__ import annotations

from typing import List
from core.contracts import Rect, SubtitleDetection


class DualBandSpatialFilter:
    """Filters OCR detections based on vertical screen geometry and subtitle characteristics."""

    def __init__(
        self,
        top_band_ratio: float = 0.20,
        bottom_band_ratio: float = 0.30,
        min_confidence: float = 0.40,
        min_text_length: int = 1,
    ) -> None:
        if not (0.0 < top_band_ratio < 0.5):
            raise ValueError("top_band_ratio must be between 0.0 and 0.5")
        if not (0.0 < bottom_band_ratio < 0.5):
            raise ValueError("bottom_band_ratio must be between 0.0 and 0.5")

        self.top_band_ratio = top_band_ratio
        self.bottom_band_ratio = bottom_band_ratio
        self.min_confidence = min_confidence
        self.min_text_length = min_text_length

    def filter_detections(
        self,
        detections: List[SubtitleDetection],
        frame_rect: Rect,
    ) -> List[SubtitleDetection]:
        """Filter detections to retain only valid subtitles in top or bottom bands."""
        if not detections or frame_rect.height <= 0:
            return []

        top_cutoff = frame_rect.top + (frame_rect.height * self.top_band_ratio)
        bottom_cutoff = frame_rect.top + (frame_rect.height * (1.0 - self.bottom_band_ratio))

        filtered: List[SubtitleDetection] = []
        for det in detections:
            # 1. Basic text sanity and confidence check
            text = det.text.strip()
            if len(text) < self.min_text_length:
                continue
            if det.confidence < self.min_confidence:
                continue

            # 2. Check vertical center position relative to top/bottom bands
            center_y = det.box.center_y
            in_top_band = center_y <= top_cutoff
            in_bottom_band = center_y >= bottom_cutoff

            if in_top_band or in_bottom_band:
                filtered.append(det)

        # 3. Stable vertical reading order (top-to-bottom, primary bottom subtitles grouped)
        filtered.sort(key=lambda d: d.box.center_y)
        return filtered
