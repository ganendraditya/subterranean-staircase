"""PyQt6 transparent, click-through subtitle overlay window.

Adheres strictly to Anti-Slop WCAG AA contrast standards:
- High contrast stroked text outline (readable over both pitch-black and stark-white video).
- Frameless, translucent click-through window (WA_TranslucentBackground, WindowTransparentForInput).
- Hardware-accelerated smooth rendering and automatic fade-out on speech pauses.
"""

from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QTextLayout
from PyQt6.QtWidgets import QWidget

from core.config import OverlayStyleConfig


class SubtitleOverlayWindow(QWidget):
    """Transparent, frameless, and click-through floating overlay widget for subtitles."""

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

    def update_text(self, text: str) -> None:
        """Display newly translated subtitle text, resetting fade-out timer."""
        cleaned = text.strip()
        if cleaned != self._current_text:
            self._current_text = cleaned
            self._last_update_time = time.time()
            self.update()

    def clear_text(self) -> None:
        """Clear currently displayed subtitle."""
        if self._current_text:
            self._current_text = ""
            self.update()

    def _check_fade_out(self) -> None:
        """Fade out and clear text if inactive longer than fade_out_seconds."""
        if not self._current_text:
            return

        elapsed = time.time() - self._last_update_time
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

        display_text = self._current_text or "Subtitle Translation Overlay (Drag to move)"

        # Calculate bounding box for text
        text_rect = metrics.boundingRect(
            rect.adjusted(20, 10, -20, -10),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
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
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._interactive_mode:
            self._drag_pos = None
            event.accept()
