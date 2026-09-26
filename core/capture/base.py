"""Abstract base capture interface for multi-OS screen and window grabbers.

Strictly decouples capture implementation from core pipeline and UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.contracts import Frame, Rect, WindowInfo


class BaseCapture(ABC):
    """Abstract screen capture driver contract."""

    @abstractmethod
    def list_windows(self) -> List[WindowInfo]:
        """Enumerate visible desktop application windows."""
        pass

    @abstractmethod
    def grab_screen(self, monitor_index: int = 1, crop_rect: Optional[Rect] = None) -> Frame:
        """Capture entire screen or a cropped region of a specific monitor."""
        pass

    @abstractmethod
    def grab_window(self, window_id: int | str, crop_rect: Optional[Rect] = None) -> Frame:
        """Capture a specific application window by its OS window identifier."""
        pass

    @abstractmethod
    def get_monitor_bounds(self, monitor_index: int = 1) -> Rect:
        """Get geometry rectangle for the specified monitor."""
        pass
