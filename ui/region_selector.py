"""Interactive drag-and-drop screen Region of Interest (ROI) selection overlay.

Allows users to visually select a custom rectangle on screen with semi-transparent
dimming, crisp selection border, and keyboard dismissal (Escape).
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.contracts import Rect


class RegionSelectorWidget(QWidget):
    """Full-screen dimming overlay for clicking and dragging a custom ROI box."""

    # Signal emitted when user confirms a selection: (Rect)
    region_selected = pyqtSignal(object)
    # Signal emitted when user cancels selection (e.g. presses Escape)
    selection_cancelled = pyqtSignal()

    def __init__(
        self,
        on_selected: Optional[Callable[[Rect], None]] = None,
        on_cancelled: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._start_pos: Optional[QPoint] = None
        self._current_pos: Optional[QPoint] = None
        self._is_selecting: bool = False

        if on_selected is not None:
            self.region_selected.connect(on_selected)
        if on_cancelled is not None:
            self.selection_cancelled.connect(on_cancelled)

        self._init_window()

    def _init_window(self) -> None:
        """Initialize full-screen frameless overlay window attributes."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _get_selection_rect(self) -> Optional[QRect]:
        """Compute normalized QRect between start and current drag positions."""
        if self._start_pos is None or self._current_pos is None:
            return None

        left = min(self._start_pos.x(), self._current_pos.x())
        top = min(self._start_pos.y(), self._current_pos.y())
        width = abs(self._current_pos.x() - self._start_pos.x())
        height = abs(self._current_pos.y() - self._start_pos.y())

        if width <= 0 or height <= 0:
            return None

        return QRect(left, top, width, height)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Render darkened mask and highlighted selection box."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Darkened semi-transparent overlay mask
        mask_color = QColor(0, 0, 0, 120)
        painter.fillRect(self.rect(), mask_color)

        selection = self._get_selection_rect()
        if selection is not None and selection.isValid():
            # 2. Clear selected box to show through original screen
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 3. High-contrast crisp border around selection (Anti-Slop craft)
            border_pen = QPen(QColor("#00E5FF"), 2.0, Qt.PenStyle.SolidLine)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(selection)

            # 4. Display coordinate dimension badge
            badge_text = f"{selection.width()} x {selection.height()}"
            font = QFont("Arial", 11)
            painter.setFont(font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 180))

            badge_y = max(10, selection.top() - 25)
            badge_rect = QRect(selection.left(), badge_y, 110, 22)
            painter.drawRoundedRect(badge_rect, 4.0, 4.0)

            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), badge_text)
        else:
            # Display helpful instruction banner at the top
            banner_rect = QRect(0, 40, self.width(), 40)
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(
                banner_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                "Click and drag to select subtitle area. Press ESC to cancel.",
            )

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()
            self._current_pos = self._start_pos
            self._is_selecting = True
            self.update()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._is_selecting:
            self._current_pos = event.position().toPoint()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            self._is_selecting = False
            self._current_pos = event.position().toPoint()
            selection = self._get_selection_rect()

            self.hide()
            # If user clicked once or dragged a tiny box (< 15x8), treat as intentional dismiss/cancel
            if selection is not None and selection.width() >= 15 and selection.height() >= 8:
                # Convert to domain Rect contract
                chosen_rect = Rect(
                    left=selection.left(),
                    top=selection.top(),
                    width=selection.width(),
                    height=selection.height(),
                )
                self.region_selected.emit(chosen_rect)
            else:
                self.selection_cancelled.emit()
            event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle Escape key to cancel selection."""
        if event.key() == Qt.Key.Key_Escape:
            self._is_selecting = False
            self.hide()
            self.selection_cancelled.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
