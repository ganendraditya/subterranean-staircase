"""Abstract Base OCR engine interface and RapidOCR ONNX implementation.

Decouples text recognition from video capture and downstream subtitle filtering.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import time
from typing import Any, List, Optional
import numpy as np

from core.contracts import Frame, SubtitleBox, SubtitleDetection

try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_RAPIDOCR = True
except ImportError:
    HAS_RAPIDOCR = False


class BaseOCR(ABC):
    """Abstract interface for Optical Character Recognition engines."""

    @abstractmethod
    def detect(self, frame_or_image: Frame | np.ndarray) -> List[SubtitleDetection]:
        """Extract text boxes and confidence scores from an image or Frame contract."""
        pass


class RapidOCREngine(BaseOCR):
    """Production-grade OCR engine powered by RapidOCR and ONNX Runtime.

    Replaces monolithic PaddleOCR, executing PP-OCRv4 natively without CUDA lock-in.
    """

    def __init__(
        self,
        rapidocr_instance: Optional[Any] = None,
        *,
        use_cls: bool = False,
        det_unclip_ratio: float = 2.0,
    ) -> None:
        if rapidocr_instance is not None:
            self._engine = rapidocr_instance
        else:
            if not HAS_RAPIDOCR:
                raise RuntimeError("rapidocr-onnxruntime is not installed")
            # Subtitles are strictly horizontal and right-side up; disabling cls saves ~36ms
            # and prevents spurious 180-degree inverted line artifacts.
            # det_unclip_ratio=2.0 prevents character ascender/descender boundary clipping
            # in DBNet text detection (must be prefixed with det_ for RapidOCR config routing).
            self._engine = RapidOCR(
                use_cls=use_cls,
                det_unclip_ratio=det_unclip_ratio,
            )

    def detect(self, frame_or_image: Frame | np.ndarray) -> List[SubtitleDetection]:
        """Detect and recognize text lines within the provided frame.

        Returns a list of strictly-typed SubtitleDetection domain models.
        """
        if isinstance(frame_or_image, Frame):
            image = frame_or_image.image
            frame_timestamp = frame_or_image.timestamp
        else:
            image = frame_or_image
            frame_timestamp = time.time()

        if image is None or image.size == 0:
            return []

        # Adaptive Vertical Strip Cropping for Compact ROIs (height between 60px and 350px):
        # Cuts out empty top/bottom letterbox bars before DBNet inference, shaving ~150-220ms.
        h, w = image.shape[:2]
        y_offset = 0
        infer_image = image
        if 60 <= h <= 350 and w > 100:
            try:
                # Find rows with significant luminance activity (subtitles have high brightness)
                # Compute row max across channels without allocating a separate full-size grayscale buffer
                row_max = np.max(image, axis=(1, 2)) if len(image.shape) == 3 else np.max(image, axis=1)
                active_rows = np.where(row_max > 35)[0]
                if len(active_rows) > 0:
                    y_min = max(0, int(active_rows[0]) - 8)
                    y_max = min(h, int(active_rows[-1]) + 8)
                    # Only crop if it removes at least 25% of empty padding
                    if (y_max - y_min) < (0.75 * h) and (y_max - y_min) >= 20:
                        infer_image = np.ascontiguousarray(image[y_min:y_max, :])
                        y_offset = y_min
            except Exception:
                infer_image = image
                y_offset = 0

        ocr_res = self._engine(infer_image)
        if not ocr_res or not isinstance(ocr_res, (tuple, list)) or not ocr_res[0]:
            return []

        results = ocr_res[0]

        detections: List[SubtitleDetection] = []
        for item in results:
            if not item or len(item) < 3:
                continue

            dt_boxes = item[0]
            text = str(item[1]).strip()
            if not text:
                continue

            try:
                score = float(item[2])
                # dt_boxes can be numpy array or list
                box_points = [list(map(float, pt)) for pt in dt_boxes]
                # Adjust box points back if vertical strip cropping was applied
                if y_offset > 0:
                    box_points = [[pt[0], pt[1] + y_offset] for pt in box_points]
                box = SubtitleBox.from_list(box_points)
                detections.append(
                    SubtitleDetection(
                        text=text,
                        confidence=score,
                        box=box,
                        timestamp=frame_timestamp,
                    )
                )
            except (ValueError, TypeError, IndexError):
                # Skip malformed box geometry or non-numeric score safely
                continue

        return detections
