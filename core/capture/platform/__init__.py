"""Platform-specific capture driver exports."""

from core.capture.platform.macos import MacOSWindowCapture
from core.capture.platform.windows import WindowsWindowCapture

__all__ = ["MacOSWindowCapture", "WindowsWindowCapture"]
