import sys

__all__ = []

if sys.platform == "darwin":
    try:
        from core.capture.platform.macos import MacOSWindowCapture
        __all__.append("MacOSWindowCapture")
    except ImportError:
        pass
elif sys.platform == "win32":
    try:
        from core.capture.platform.windows import WindowsWindowCapture
        __all__.append("WindowsWindowCapture")
    except ImportError:
        pass
