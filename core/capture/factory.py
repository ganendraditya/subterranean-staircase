"""Dynamic capture driver factory auto-selecting the optimal backend per OS."""

from __future__ import annotations

import sys
from typing import Optional

from core.capture.base import BaseCapture
from core.capture.screen import MSSScreenCapture


def create_capture_driver(fallback_screen_capture: Optional[BaseCapture] = None) -> BaseCapture:
    """Instantiate the best native capture driver for the host operating system."""
    if sys.platform == "darwin":
        from core.capture.platform.macos import MacOSWindowCapture
        return MacOSWindowCapture(fallback_screen_capture=fallback_screen_capture)

    if sys.platform == "win32":
        from core.capture.platform.windows import WindowsWindowCapture
        return WindowsWindowCapture(fallback_screen_capture=fallback_screen_capture)

    # Linux / generic fallback
    return fallback_screen_capture or MSSScreenCapture()
