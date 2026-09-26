"""Unit tests for RegionSelectorWidget."""

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QImage, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication

from core.contracts import Rect
from ui.region_selector import RegionSelectorWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_region_selector_initialization(qapp) -> None:
    selector = RegionSelectorWidget()
    assert selector.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert selector.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert selector.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert selector.cursor().shape() == Qt.CursorShape.CrossCursor


def test_region_selector_drag_and_confirm(qapp) -> None:
    from PyQt6.QtCore import QPointF
    selected_result: list[Rect] = []

    def _on_selected(r: Rect) -> None:
        selected_result.append(r)

    selector = RegionSelectorWidget(on_selected=_on_selected)
    selector.resize(1000, 800)

    # 1. Mouse Press at (100, 200)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(100.0, 200.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    selector.mousePressEvent(press_event)
    assert selector._is_selecting is True

    # 2. Mouse Move to (500, 400)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(500.0, 400.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    selector.mouseMoveEvent(move_event)
    rect = selector._get_selection_rect()
    assert rect is not None
    assert rect.width() == 400
    assert rect.height() == 200

    # 3. Mouse Release at (500, 400)
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(500.0, 400.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    selector.mouseReleaseEvent(release_event)
    assert selector._is_selecting is False

    # Check signal output
    assert len(selected_result) == 1
    assert selected_result[0] == Rect(left=100, top=200, width=400, height=200)


def test_region_selector_cancel_via_escape(qapp) -> None:
    cancelled: list[bool] = []

    def _on_cancel() -> None:
        cancelled.append(True)

    selector = RegionSelectorWidget(on_cancelled=_on_cancel)

    # Simulate pressing Escape
    escape_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )
    selector.keyPressEvent(escape_event)

    assert len(cancelled) == 1
    assert cancelled[0] is True


def test_region_selector_paint_render(qapp) -> None:
    selector = RegionSelectorWidget()
    selector.resize(800, 600)

    # Offscreen image render
    image = QImage(800, 600, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    selector.render(image)

    assert not image.isNull()
