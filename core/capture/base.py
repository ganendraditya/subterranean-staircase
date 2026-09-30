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
    def grab_window(
        self,
        window_id: int | str,
        crop_rect: Optional[Rect] = None,
        is_global_coords: Optional[bool] = None,
    ) -> Frame:
        """Capture a specific application window by its OS window identifier.

        Args:
            window_id: OS window identifier.
            crop_rect: Optional cropping rectangle.
            is_global_coords: If True, crop_rect is in global screen coordinates and
                will be converted to window-local coordinates. If False, crop_rect is
                already window-local. If None, resolves via coordinate enclosure.
        """
        pass

    @abstractmethod
    def get_monitor_bounds(self, monitor_index: int = 1) -> Rect:
        """Get geometry rectangle for the specified monitor."""
        pass

    def bring_window_to_front(self, window_id: int | str) -> bool:
        """Attempt to activate and bring the targeted window to the foreground."""
        return False
