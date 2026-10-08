"""PyQt6 transparent, click-through subtitle overlay window.

Adheres strictly to Anti-Slop WCAG AA contrast standards:
- High contrast stroked text outline (readable over both pitch-black and stark-white video).
- Frameless, translucent click-through window (WA_TranslucentBackground, WindowTransparentForInput).
- Hardware-accelerated smooth rendering and automatic fade-out on speech pauses.
"""

from __future__ import annotations

from ctypes import c_void_p
import sys
import time
from typing import Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QTextLayout
from PyQt6.QtWidgets import QWidget

from core.config import OverlayStyleConfig


class SubtitleOverlayWindow(QWidget):
    """Transparent, frameless, and click-through floating overlay widget for subtitles."""

    position_changed = pyqtSignal(int, int)  # Emits (bottom_center_x, bottom_center_y) during move
    position_locked = pyqtSignal(int, int)   # Emits final (bottom_center_x, bottom_center_y) on mouse release for persistence

    CANVAS_WIDTH = 800
    CANVAS_HEIGHT = 160

    def __init__(
        self,
        style_config: Optional[OverlayStyleConfig] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.style_config = style_config or OverlayStyleConfig()
        self._current_text: str = ""
        self._last_update_time: float = 0.0
        self._interactive_mode: bool = False
        self._drag_pos: Optional[QPoint] = None
        self._custom_bottom_center: Optional[Tuple[int, int]] = None

        self._init_window_flags()

        # Fade-out timer running at ~10 Hz
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(100)
        self._fade_timer.timeout.connect(self._check_fade_out)
        self._fade_timer.start()

    def _init_window_flags(self) -> None:
        """Configure macOS/Windows transparent click-through window attributes."""
        # Frameless and stays on top of video players
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # Transparent background attribute
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.set_click_through(True)
        self._configure_fullscreen_spaces()
        self._setup_space_listener()

    def _setup_space_listener(self) -> None:
        """Register macOS NSWorkspaceActiveSpaceDidChangeNotification listener to keep overlay front."""
        if sys.platform != "darwin":
            return
        try:
            import weakref
            import objc
            from AppKit import NSWorkspace, NSWorkspaceActiveSpaceDidChangeNotification

            try:
                observer_cls = objc.lookUpClass("SubtitleOverlaySpaceObserver")
            except (objc.nosuchclass_error, AttributeError, Exception):
                class SubtitleOverlaySpaceObserver(objc.lookUpClass("NSObject")):
                    def spaceChanged_(self, notification):
                        try:
                            ref = getattr(self, "_overlay_ref", None)
                            overlay = ref() if ref is not None else None
                            if overlay and overlay.isVisible():
                                overlay._configure_fullscreen_spaces()
                                overlay.raise_front()
                        except Exception:
                            pass

                observer_cls = SubtitleOverlaySpaceObserver

            observer = observer_cls.alloc().init()
            observer._overlay_ref = weakref.ref(self)
            ws = NSWorkspace.sharedWorkspace()
            ws.notificationCenter().addObserver_selector_name_object_(
                observer,
                "spaceChanged:",
                NSWorkspaceActiveSpaceDidChangeNotification,
                None,
            )
            self._space_observer = observer
        except Exception:
            pass

    def _configure_fullscreen_spaces(self) -> None:
        """Configure native macOS window attributes to float over fullscreen video spaces."""
        if sys.platform != "darwin":
            return
        try:
            import objc
            from AppKit import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSWindowCollectionBehaviorStationary,
                NSScreenSaverWindowLevel,
            )

            view = objc.objc_object(c_void_p=int(self.winId()))
            nswindow = view.window()
            if nswindow is not None:
                behavior = (
                    NSWindowCollectionBehaviorCanJoinAllSpaces
                    | NSWindowCollectionBehaviorFullScreenAuxiliary
                    | NSWindowCollectionBehaviorStationary
                )
                nswindow.setCollectionBehavior_(behavior)
                nswindow.setLevel_(NSScreenSaverWindowLevel)
                nswindow.setHidesOnDeactivate_(False)
                nswindow.orderFrontRegardless()
        except Exception:
            pass

    def raise_front(self) -> None:
        """Order overlay to front across spaces and above fullscreen spaces."""
        self.raise_()
        if sys.platform == "darwin":
            try:
                import objc
                view = objc.objc_object(c_void_p=int(self.winId()))
                nswindow = view.window()
                if nswindow is not None:
                    nswindow.orderFrontRegardless()
            except Exception:
                pass

    def showEvent(self, event) -> None:  # noqa: N802
        """Re-assert fullscreen space configuration and window hierarchy when shown."""
        super().showEvent(event)
        self._configure_fullscreen_spaces()
        self.raise_front()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Clean up macOS workspace observer and resources on close."""
        if sys.platform == "darwin" and hasattr(self, "_space_observer"):
            try:
                from AppKit import NSWorkspace
                ws = NSWorkspace.sharedWorkspace()
                ws.notificationCenter().removeObserver_(self._space_observer)
            except Exception:
                pass
        super().closeEvent(event)

    def set_bottom_center(self, center_x: int, bottom_y: int, canvas_width: int = CANVAS_WIDTH, canvas_height: int = CANVAS_HEIGHT) -> None:
        """Position window using bottom-center anchor coordinates (x: center, y: baseline)."""
        top_left_x = int(round(center_x - (canvas_width / 2.0)))
        top_left_y = int(round(bottom_y - canvas_height))
        self._custom_bottom_center = (center_x, bottom_y)
        self.setGeometry(top_left_x, top_left_y, canvas_width, canvas_height)

    def get_bottom_center(self) -> Tuple[int, int]:
        """Return current bottom-center coordinates (center_x, bottom_y)."""
        geom = self.geometry()
        center_x = geom.x() + (geom.width() // 2)
        bottom_y = geom.y() + geom.height()
        return (center_x, bottom_y)

    def set_interactive_mode(self, enabled: bool) -> None:
        """Enable interactive moving mode: turns off click-through and shows dashed border."""
        self.set_click_through(not enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.show()
            self.raise_front()
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_click_through(self, enabled: bool) -> None:
        """Toggle mouse click-through behavior while preserving window visibility."""
        self._interactive_mode = not enabled
        was_visible = self.isVisible()

        # In PyQt6, click-through is controlled via WindowType.WindowTransparentForInput flag
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)

        if was_visible:
            self.show()
            self._configure_fullscreen_spaces()

    def update_text(self, text: str) -> None:
        """Display newly translated subtitle text, resetting fade-out timer."""
        cleaned = text.strip()
        if cleaned != self._current_text:
            self._current_text = cleaned
            self._last_update_time = time.monotonic()
            self.update()
            if cleaned:
                self.raise_front()

    def touch(self) -> None:
        """Keep current subtitle alive while still detected on screen (prevents premature fade-out)."""
        if self._current_text:
            self._last_update_time = time.monotonic()

    def clear_text(self) -> None:
        """Clear currently displayed subtitle."""
        if self._current_text:
            self._current_text = ""
            self.update()

    def _check_fade_out(self) -> None:
        """Fade out and clear text if inactive longer than fade_out_seconds."""
        if not self._current_text:
            return

        elapsed = time.monotonic() - self._last_update_time
        if elapsed >= self.style_config.fade_out_seconds:
            self.clear_text()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Render high-contrast stroked subtitle text adhering to WCAG AA."""
        if not self._current_text and not self._interactive_mode:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Setup font
        font = QFont(self.style_config.font_family, self.style_config.font_size)
        font.setBold(self.style_config.font_bold)
        painter.setFont(font)

        rect = self.rect()
        metrics = QFontMetrics(font)

        display_text = self._current_text or ("Drag to Reposition Subtitles" if self._interactive_mode else "")

        # Draw interactive positioning guidelines and dashed border
        if self._interactive_mode:
            dashed_pen = QPen(QColor("#00E5FF"), 2.0, Qt.PenStyle.DashLine)
            painter.setPen(dashed_pen)
            painter.setBrush(QColor(0, 0, 0, 110))
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8.0, 8.0)

            # Draw top helper hint
            hint_font = QFont("Arial", 11)
            painter.setFont(hint_font)
            painter.setPen(QColor("#00E5FF"))
            painter.drawText(
                rect.adjusted(10, 8, -10, -8),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                "Anchored at Bottom-Center • Drag anywhere to move",
            )
            # Revert font for main text
            painter.setFont(font)

        # Calculate bounding box for text
        # Align vertically to bottom of canvas for natural upward subtitle growth
        avail_rect = rect.adjusted(20, 30 if self._interactive_mode else 10, -20, -10)
        text_rect = metrics.boundingRect(
            avail_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom | Qt.TextFlag.TextWordWrap),
            display_text,
        )

        # Draw subtle pill background if enabled
        if self.style_config.background_opacity > 0.0:
            bg_color = QColor(self.style_config.background_color)
            bg_color.setAlphaF(min(1.0, max(0.0, self.style_config.background_opacity)))
            pill_rect = text_rect.adjusted(-12, -6, 12, 6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(pill_rect, 8.0, 8.0)

        # Draw high-contrast text outline (Anti-Slop WCAG AA contrast)
        path = QPainterPath()

        # Multi-line and word-wrapping text layout via QTextLayout
        layout = QTextLayout(display_text, font)
        layout.beginLayout()
        y_cursor = float(text_rect.y())
        max_line_w = float(text_rect.width())

        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max_line_w)
            line.setPosition(QPointF(float(text_rect.x()), y_cursor))
            y_cursor += line.height()
        layout.endLayout()

        for i in range(layout.lineCount()):
            line = layout.lineAt(i)
            start = line.textStart()
            length = line.textLength()
            substr = display_text[start : start + length].rstrip("\r\n")
            pos = line.position()
            # Center each line horizontally within text_rect
            line_w = metrics.horizontalAdvance(substr)
            x_offset = pos.x() + max(0.0, (max_line_w - line_w) / 2.0)
            path.addText(x_offset, pos.y() + metrics.ascent(), font, substr)

        # Stroke pen (outer black outline)
        if self.style_config.stroke_width > 0:
            stroke_pen = QPen(
                QColor(self.style_config.stroke_color),
                float(self.style_config.stroke_width * 2),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.strokePath(path, stroke_pen)

        # Text fill (inner crisp white font)
        painter.fillPath(path, QColor(self.style_config.text_color))

        painter.end()

    # Interactive Drag-and-Drop repositioning support (when not in click-through mode)
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._interactive_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._interactive_mode and self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            new_top_left = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_top_left)
            center_x, bottom_y = self.get_bottom_center()
            self._custom_bottom_center = (center_x, bottom_y)
            self.position_changed.emit(center_x, bottom_y)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._interactive_mode and event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self._drag_pos is not None
            self._drag_pos = None
            if was_dragging:
                center_x, bottom_y = self.get_bottom_center()
                self._custom_bottom_center = (center_x, bottom_y)
                self.position_locked.emit(center_x, bottom_y)
            event.accept()
