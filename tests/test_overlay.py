"""Unit tests for SubtitleOverlayWindow."""

import time
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.config import OverlayStyleConfig
from ui.overlay import SubtitleOverlayWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_overlay_initialization(qapp) -> None:
    style = OverlayStyleConfig(font_size=20, text_color="#FFFFFF")
    overlay = SubtitleOverlayWindow(style_config=style)

    assert overlay.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_overlay_text_lifecycle(qapp) -> None:
    overlay = SubtitleOverlayWindow()

    # Initial empty
    assert overlay._current_text == ""

    # Update text
    overlay.update_text("Hello World!")
    assert overlay._current_text == "Hello World!"

    # Whitespace trimmed
    overlay.update_text("   Hello World!   ")
    assert overlay._current_text == "Hello World!"

    # Clear
    overlay.clear_text()
    assert overlay._current_text == ""


def test_overlay_click_through_toggle(qapp) -> None:
    overlay = SubtitleOverlayWindow()

    # Default is click-through
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert not overlay._interactive_mode

    # Toggle to interactive mode for dragging/repositioning
    overlay.set_click_through(False)
    assert not (overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)
    assert overlay._interactive_mode


def test_overlay_fade_out_behavior(qapp) -> None:
    style = OverlayStyleConfig(fade_out_seconds=0.1)
    overlay = SubtitleOverlayWindow(style_config=style)

    overlay.update_text("Temporary Subtitle")
    assert overlay._current_text == "Temporary Subtitle"

    # Simulate passage of time beyond fade-out threshold
    overlay._last_update_time = time.monotonic() - 0.2
    overlay._check_fade_out()

    assert overlay._current_text == ""


def test_overlay_paint_rendering(qapp) -> None:
    from PyQt6.QtGui import QImage
    style = OverlayStyleConfig(
        font_size=24,
        font_bold=True,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width=2,
        background_opacity=0.5,
    )
    overlay = SubtitleOverlayWindow(style_config=style)
    overlay.resize(800, 150)
    overlay.update_text("Test Rendering Subtitle")

    # Render widget directly into an offscreen image buffer
    image = QImage(800, 150, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    overlay.render(image)

    assert not image.isNull()


def test_overlay_multiline_wrapped_rendering(qapp) -> None:
    from PyQt6.QtGui import QImage
    overlay = SubtitleOverlayWindow()
    overlay.resize(400, 200)
    overlay.update_text("Line One of the Subtitle\nLine Two with long text that wraps across multiple lines")

    image = QImage(400, 200, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    overlay.render(image)
    assert not image.isNull()


def test_overlay_click_through_toggle_preserves_visibility(qapp) -> None:
    overlay = SubtitleOverlayWindow()
    overlay.show()
    assert overlay.isVisible()

    # Toggling click-through should preserve visibility
    overlay.set_click_through(False)
    assert overlay.isVisible()
    assert overlay._interactive_mode

    overlay.set_click_through(True)
    assert overlay.isVisible()
    assert not overlay._interactive_mode
    overlay.hide()


def test_overlay_macos_fullscreen_spaces_configuration(qapp) -> None:
    from ctypes import c_void_p
    import sys
    overlay = SubtitleOverlayWindow()
    overlay.show()
    overlay.update_text("Floating Text")
    if sys.platform == "darwin":
        import objc
        from AppKit import (
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSScreenSaverWindowLevel,
        )
        view = objc.objc_object(c_void_p=int(overlay.winId()))
        nswindow = view.window()
        assert nswindow is not None
        behavior = nswindow.collectionBehavior()
        assert behavior & NSWindowCollectionBehaviorCanJoinAllSpaces
        assert behavior & NSWindowCollectionBehaviorFullScreenAuxiliary
        assert nswindow.level() >= NSScreenSaverWindowLevel
        assert not nswindow.hidesOnDeactivate()
        assert hasattr(overlay, "_space_observer")
        overlay.raise_front()
    overlay.close()


def test_overlay_bottom_center_anchoring_and_interactive_mode(qapp) -> None:
    overlay = SubtitleOverlayWindow()
    overlay.show()

    # 1. Test bottom-center anchoring math
    overlay.set_bottom_center(center_x=500, bottom_y=700, canvas_width=600, canvas_height=140)
    assert overlay.x() == 200
    assert overlay.y() == 560
    assert overlay.width() == 600
    assert overlay.height() == 140
    assert overlay.get_bottom_center() == (500, 700)

    # 2. Test interactive repositioning mode
    assert not overlay._interactive_mode
    overlay.set_interactive_mode(True)
    assert overlay._interactive_mode
    assert overlay.cursor().shape() == Qt.CursorShape.SizeAllCursor

    # 3. Simulate dragging event
    received_positions = []
    overlay.position_changed.connect(lambda cx, by: received_positions.append((cx, by)))
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QPointF
    # Press at top-left
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        QPointF(210, 570),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press_event)
    assert overlay._drag_pos is not None

    # Move by 50px right, 30px down
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(60, 40),
        QPointF(260, 600),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseMoveEvent(move_event)
    assert len(received_positions) == 1
    assert received_positions[0] == (550, 730)

    # Release
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(60, 40),
        QPointF(260, 600),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release_event)
    assert overlay._drag_pos is None

    # 4. Turn off interactive mode
    overlay.set_interactive_mode(False)
    assert not overlay._interactive_mode

    overlay.close()
