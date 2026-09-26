"""Domain data contracts and boundary interfaces.

Strict, typed models establishing a single source of truth across modules.
Enforces Dependency Inversion (DIP) and Orthogonality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple
import numpy as np


class CaptureMode(str, Enum):
    """Supported screen capture targeting modes."""
    FULL_SCREEN = "full_screen"
    WINDOW = "window"
    CUSTOM_ROI = "custom_roi"


@dataclass(frozen=True)
class Rect:
    """Immutable bounding rectangle in pixel coordinates."""
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center_x(self) -> float:
        return self.left + (self.width / 2.0)

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2.0)

    def as_tuple(self) -> Tuple[int, int, int, int]:
        """Return (left, top, width, height)."""
        return (self.left, self.top, self.width, self.height)


@dataclass
class WindowInfo:
    """Metadata describing a discoverable OS desktop window."""
    window_id: int | str
    title: str
    owner_name: str
    rect: Rect
    is_minimized: bool = False


@dataclass
class Frame:
    """Raw captured screen image buffer with timestamp and metadata."""
    image: np.ndarray  # BGR format array (H, W, C)
    timestamp: float
    source_rect: Rect
    window_id: Optional[int | str] = None

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])


@dataclass(frozen=True)
class SubtitleBox:
    """Bounding polygon vertices for detected text [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]."""
    points: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]

    @classmethod
    def from_list(cls, pts: List[List[float]]) -> SubtitleBox:
        assert len(pts) == 4, "Bounding polygon must have exactly 4 points"
        return cls(
            points=(
                (float(pts[0][0]), float(pts[0][1])),
                (float(pts[1][0]), float(pts[1][1])),
                (float(pts[2][0]), float(pts[2][1])),
                (float(pts[3][0]), float(pts[3][1])),
            )
        )

    @property
    def min_y(self) -> float:
        return min(p[1] for p in self.points)

    @property
    def max_y(self) -> float:
        return max(p[1] for p in self.points)

    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2.0


@dataclass
class SubtitleDetection:
    """Single OCR text line extracted from a captured frame."""
    text: str
    confidence: float
    box: SubtitleBox
    language: Optional[str] = None
    timestamp: float = 0.0


@dataclass
class TranslationRequest:
    """Payload dispatched to the translation worker."""
    source_text: str
    source_lang: str
    target_lang: str
    timestamp: float = 0.0


@dataclass
class TranslationResult:
    """Normalized translation response consumed by the overlay renderer."""
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    from_cache: bool = False
    latency_ms: float = 0.0
