"""Windows Native Window Enumerator and Window Grabber using ctypes / Win32 API.

Strictly isolated under core/capture/platform/windows.py so it never pollutes
non-Windows environments (macOS/Linux).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import time
from typing import List, Optional
import numpy as np

from core.capture.base import BaseCapture
from core.capture.screen import MSSScreenCapture
from core.contracts import Frame, Rect, WindowInfo

HAS_WIN32 = sys.platform == "win32"

if HAS_WIN32:
    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi
    _gdi32 = ctypes.windll.gdi32
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    DWMWA_CLOAKED = 14

    # Explicitly configure 64-bit safe restype/argtypes for GDI and User32 handles
    _user32.GetWindowDC.restype = wintypes.HDC
    _user32.GetWindowDC.argtypes = [wintypes.HWND]

    _user32.ReleaseDC.restype = ctypes.c_int
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]

    _gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    _gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]

    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]

    _gdi32.DeleteObject.restype = wintypes.BOOL
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    _gdi32.DeleteDC.restype = wintypes.BOOL
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]

    _user32.PrintWindow.restype = wintypes.BOOL
    _user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

    _gdi32.GetDIBits.restype = ctypes.c_int
    _gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        ctypes.c_void_p,
        wintypes.UINT,
    ]

    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.EnumWindows.argtypes = [
        ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
        wintypes.LPARAM,
    ]

    _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT
    _dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        wintypes.LPCVOID,
        wintypes.DWORD,
    ]
else:
    _RECT = None
    _user32 = None
    _dwmapi = None
    _gdi32 = None
    DWMWA_EXTENDED_FRAME_BOUNDS = 9


def _get_window_rect(hwnd: int) -> Optional[Rect]:
    """Retrieve window geometry using DWM extended frame bounds (excluding drop shadows)."""
    if not HAS_WIN32 or _dwmapi is None:
        return None

    rect = _RECT()
    hr = _dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if hr == 0:
        return Rect(
            left=rect.left,
            top=rect.top,
            width=rect.right - rect.left,
            height=rect.bottom - rect.top,
        )

    # Fallback to standard User32 GetWindowRect
    if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return Rect(
            left=rect.left,
            top=rect.top,
            width=rect.right - rect.left,
            height=rect.bottom - rect.top,
        )
    return None


class WindowsWindowCapture(BaseCapture):
    """Windows-specific window grabber and enumerator via Win32 / GDI / DWM APIs."""

    def __init__(self, fallback_screen_capture: Optional[BaseCapture] = None) -> None:
        self._screen_capture = fallback_screen_capture or MSSScreenCapture()

    def list_windows(self) -> List[WindowInfo]:
        """Enumerate visible desktop application windows on Windows."""
        if not HAS_WIN32 or _user32 is None:
            return []

        windows: List[WindowInfo] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum_proc(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True

            cloaked = wintypes.DWORD(0)
            if _dwmapi is not None:
                hr = _dwmapi.DwmGetWindowAttribute(
                    hwnd,
                    DWMWA_CLOAKED,
                    ctypes.byref(cloaked),
                    ctypes.sizeof(cloaked),
                )
                if hr == 0 and cloaked.value != 0:
                    return True  # Skip hidden/cloaked background UWP and virtual desktop windows

            length = _user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

            # Skip common shell noise windows
            if not title or title in ("Program Manager", "Windows Input Experience", "Settings"):
                return True

            rect = _get_window_rect(hwnd)
            if rect is None or rect.width < 100 or rect.height < 100:
                return True

            is_iconic = bool(_user32.IsIconic(hwnd))

            parts = title.split(" - ")
            owner_name = parts[-1].strip() if len(parts) > 1 else title

            windows.append(
                WindowInfo(
                    window_id=int(hwnd),
                    title=title,
                    owner_name=owner_name,
                    rect=rect,
                    is_minimized=is_iconic,
                )
            )
            return True

        _user32.EnumWindows(_enum_proc, 0)
        return windows

    def get_monitor_bounds(self, monitor_index: int = 1) -> Rect:
        """Delegate monitor boundaries calculation to the screen capture driver."""
        return self._screen_capture.get_monitor_bounds(monitor_index)

    def grab_screen(self, monitor_index: int = 1, crop_rect: Optional[Rect] = None) -> Frame:
        """Capture monitor screen via the underlying screen capture driver."""
        return self._screen_capture.grab_screen(monitor_index, crop_rect)

    def bring_window_to_front(self, window_id: int | str) -> bool:
        """Bring targeted Windows application window to front using SetForegroundWindow."""
        if not HAS_WIN32:
            return False
        try:
            hwnd = int(window_id)
            if _user32.IsWindow(hwnd):
                if _user32.IsIconic(hwnd):
                    _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                _user32.SetForegroundWindow(hwnd)
                return True
        except Exception:
            pass
        return False

    def grab_window(
        self,
        window_id: int | str,
        crop_rect: Optional[Rect] = None,
        is_global_coords: Optional[bool] = None,
    ) -> Frame:
        """Capture a targeted Windows application window using PrintWindow / GDI."""
        if not HAS_WIN32:
            raise RuntimeError("Windows capture driver is only available on Windows OS")

        hwnd = int(window_id)
        if not _user32.IsWindow(hwnd):
            raise ValueError(f"Window handle {window_id} is invalid or no longer exists")

        rect = _get_window_rect(hwnd)
        if rect is None:
            raise RuntimeError(f"Failed to query bounds for window {window_id}")

        width = rect.width
        height = rect.height
        if width <= 0 or height <= 0:
            raise ValueError(f"Window {window_id} has invalid dimensions ({width}x{height})")

        hwnd_dc = None
        mem_dc = None
        bitmap = None
        prev_bmp = None

        try:
            hwnd_dc = _user32.GetWindowDC(hwnd)
            if not hwnd_dc:
                raise RuntimeError(f"Failed to get device context for window {window_id}")

            mem_dc = _gdi32.CreateCompatibleDC(hwnd_dc)
            if not mem_dc:
                raise RuntimeError("Failed to create compatible DC")

            bitmap = _gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                raise RuntimeError("Failed to create compatible bitmap")

            prev_bmp = _gdi32.SelectObject(mem_dc, bitmap)

            # PW_RENDERFULLCONTENT = 2
            rendered = _user32.PrintWindow(hwnd, mem_dc, 2)
            if not rendered:
                # Fallback to standard PrintWindow = 0
                _user32.PrintWindow(hwnd, mem_dc, 0)

            # Extract bitmap bits via GetDIBits
            bmp_info = ctypes.create_string_buffer(40)
            # Fill BITMAPINFOHEADER struct
            ctypes.c_uint32.from_buffer(bmp_info, 0).value = 40
            ctypes.c_int32.from_buffer(bmp_info, 4).value = width
            ctypes.c_int32.from_buffer(bmp_info, 8).value = -height  # top-down DIB
            ctypes.c_uint16.from_buffer(bmp_info, 12).value = 1
            ctypes.c_uint16.from_buffer(bmp_info, 14).value = 32  # 32 bpp
            ctypes.c_uint32.from_buffer(bmp_info, 16).value = 0   # BI_RGB

            buffer_size = width * height * 4
            buf = ctypes.create_string_buffer(buffer_size)

            lines_copied = _gdi32.GetDIBits(
                mem_dc,
                bitmap,
                0,
                height,
                buf,
                bmp_info,
                0,  # DIB_RGB_COLORS
            )
            if not lines_copied:
                raise RuntimeError(f"Failed to copy bitmap data for window {window_id}")

            img_np = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4))
            img_bgr = img_np[:, :, :3].copy()

            actual_rect = rect
            if crop_rect is not None:
                if crop_rect.width <= 0 or crop_rect.height <= 0:
                    raise ValueError("crop_rect width and height must be positive")

                # Convert global screen coordinates (from ROI selector) into local window coordinates
                if is_global_coords is None:
                    # Fallback: check if crop_rect is positioned within window screen coordinates
                    is_global = (
                        crop_rect.left >= rect.left
                        and crop_rect.top >= rect.top
                        and crop_rect.right <= rect.right
                        and crop_rect.bottom <= rect.bottom
                    )
                else:
                    is_global = is_global_coords

                if is_global:
                    local_left = crop_rect.left - rect.left
                    local_top = crop_rect.top - rect.top
                else:
                    local_left = crop_rect.left
                    local_top = crop_rect.top

                target_left = max(0, min(local_left, width))
                target_top = max(0, min(local_top, height))
                target_right = max(target_left, min(local_left + crop_rect.width, width))
                target_bottom = max(target_top, min(local_top + crop_rect.height, height))

                if target_right == target_left or target_bottom == target_top:
                    raise ValueError("crop_rect does not intersect with the window area")

                img_bgr = img_bgr[target_top:target_bottom, target_left:target_right]
                actual_rect = Rect(
                    left=rect.left + target_left,
                    top=rect.top + target_top,
                    width=target_right - target_left,
                    height=target_bottom - target_top,
                )

            return Frame(
                image=img_bgr,
                timestamp=time.time(),
                source_rect=actual_rect,
                window_id=hwnd,
            )
        finally:
            if mem_dc and prev_bmp:
                _gdi32.SelectObject(mem_dc, prev_bmp)
            if bitmap:
                _gdi32.DeleteObject(bitmap)
            if mem_dc:
                _gdi32.DeleteDC(mem_dc)
            if hwnd_dc:
                _user32.ReleaseDC(hwnd, hwnd_dc)
