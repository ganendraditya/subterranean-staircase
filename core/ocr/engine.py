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

    def __init__(self, rapidocr_instance: Optional[Any] = None) -> None:
        if rapidocr_instance is not None:
            self._engine = rapidocr_instance
        else:
            if not HAS_RAPIDOCR:
                raise RuntimeError("rapidocr-onnxruntime is not installed")
            # RapidOCR automatically resolves execution providers (CoreML / DirectML / CPU)
            self._engine = RapidOCR()

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

        ocr_res = self._engine(image)
        if not ocr_res or not isinstance(ocr_res, (tuple, list)) or not ocr_res[0]:
            return []

        results = ocr_res[0]

        detections: List[SubtitleDetection] = []
        for item in results:
            if not item or len(item) < 3:
                continue

            dt_boxes, text, score = item[0], str(item[1]).strip(), float(item[2])
            if not text:
                continue

            try:
                # dt_boxes can be numpy array or list
                box_points = [list(map(float, pt)) for pt in dt_boxes]
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
                # Skip malformed box geometry safely
                continue

        return detections
