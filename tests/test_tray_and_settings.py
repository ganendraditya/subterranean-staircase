"""Unit tests for SettingsDialog and TrayController."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PyQt6.QtWidgets import QApplication

from core.capture.base import BaseCapture
from core.config import ConfigManager
from core.contracts import Rect, WindowInfo
from ui.control_center import ControlCenterDialog
from ui.settings_dialog import SettingsDialog
from ui.tray import TrayController, create_default_tray_icon


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_create_default_tray_icon(qapp) -> None:
    icon = create_default_tray_icon()
    assert not icon.isNull()


def test_settings_dialog_save(qapp, tmp_path: Path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    dialog = SettingsDialog(config_manager=config_mgr)

    # Change settings
    dialog.source_combo.setCurrentIndex(dialog.source_combo.findData("ja"))
    dialog.target_combo.setCurrentIndex(dialog.target_combo.findData("en"))
    dialog.font_size_spin.setValue(36)
    dialog.fade_out_spin.setValue(5)

    # Save
    dialog._save_and_close()

    assert config_mgr.config.source_language == "ja"
    assert config_mgr.config.target_language == "en"
    assert config_mgr.config.overlay.font_size == 36
    assert config_mgr.config.overlay.fade_out_seconds == 5.0


def test_settings_dialog_custom_language(qapp, tmp_path: Path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    # Set a custom/unlisted language code (e.g. "ru", "nl")
    config_mgr.update(source_language="ru", target_language="nl")

    dialog = SettingsDialog(config_manager=config_mgr)
    assert dialog.source_combo.currentData() == "ru"
    assert dialog.target_combo.currentData() == "nl"


def test_tray_controller_signals_and_menu(qapp, tmp_path: Path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    config_mgr.update(check_updates=False)

    tray = TrayController(config_manager=config_mgr)

    # 1. Test Toggle Translation from minimal context menu
    toggled_states: list[bool] = []
    tray.translation_toggled.connect(toggled_states.append)

    tray._on_toggle()
    assert len(toggled_states) == 1
    assert toggled_states[0] is True
    assert tray.toggle_action.text() == "Pause Translation"

    tray._on_toggle()
    assert len(toggled_states) == 2
    assert toggled_states[1] is False
    assert tray.toggle_action.text() == "Start Translation"

    # 2. Test click activation routes to control_center_requested
    cc_requested: list[bool] = []
    tray.control_center_requested.connect(lambda: cc_requested.append(True))
    from PyQt6.QtWidgets import QSystemTrayIcon
    tray._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert len(cc_requested) == 1

    tray.close()


def test_control_center_dialog(qapp, tmp_path: Path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    mock_capture = MagicMock(spec=BaseCapture)
    mock_capture.list_windows.return_value = [
        WindowInfo(window_id=123, title="VLC Player", owner_name="vlc", rect=Rect(0, 0, 800, 600))
    ]

    cc = ControlCenterDialog(config_manager=config_mgr, capture_driver=mock_capture)

    # 1. Check window population
    assert cc.window_combo.count() == 2
    assert "Entire Screen" in cc.window_combo.itemText(0)
    assert "vlc: VLC Player" in cc.window_combo.itemText(1)

    # 2. Check window selection signal
    selected_wins = []
    cc.window_selected.connect(selected_wins.append)
    cc.window_combo.setCurrentIndex(1)
    assert len(selected_wins) == 1
    assert selected_wins[0].window_id == 123

    # 3. Check translation toggle button
    toggled = []
    cc.translation_toggled.connect(toggled.append)
    cc.toggle_btn.click()
    assert len(toggled) == 1
    assert toggled[0] is True

    cc.set_active(True)
    assert cc.toggle_btn.text() == "Pause Translation"
    assert "TRANSLATING" in cc.status_badge.text()

    cc.set_active(False)
    assert cc.toggle_btn.text() == "Start Translation"
    assert "STANDBY" in cc.status_badge.text()

    # 4. Check ROI signal
    roi_req = []
    cc.select_roi_requested.connect(lambda: roi_req.append(True))
    cc.roi_btn.click()
    assert len(roi_req) == 1

    # 5. Check preferences save
    cc.font_size_spin.setValue(32)
    assert config_mgr.config.overlay.font_size == 32

    # 6. Verify scroll area containment
    assert hasattr(cc, "scroll_area")
    assert cc.scroll_area.widgetResizable()
    assert cc.scroll_area.widget() is not None
    assert cc.scroll_area.widget().layout().count() >= 5

    # 7. Check draggable repositioning controls
    assert hasattr(cc, "reposition_btn")
    assert hasattr(cc, "reset_pos_btn")
    assert hasattr(cc, "reposition_hint")
    assert cc.reposition_btn.text() == "✋ Move Subtitles"
    assert cc.reposition_hint.text() == "Auto bottom-center"
    assert not cc.reset_pos_btn.isVisible()

    reposition_signals = []
    cc.reposition_overlay_toggled.connect(reposition_signals.append)
    cc.reposition_btn.click()
    assert len(reposition_signals) == 1
    assert reposition_signals[0] is True
    assert cc.reposition_btn.text() == "🔒 Lock Position"

    # Reset position signal
    reset_signals = []
    cc.reset_overlay_position_requested.connect(lambda: reset_signals.append(True))
    cc.reset_pos_btn.click()
    assert len(reset_signals) == 1
    assert cc.reposition_btn.text() == "✋ Move Subtitles"

    cc.close()


def test_tray_controller_set_active(qapp, tmp_path: Path) -> None:
    config_mgr = ConfigManager(config_path=tmp_path / "config.json")
    config_mgr.update(check_updates=False)
    tray = TrayController(config_manager=config_mgr)

    tray.set_active(True)
    assert tray._is_active is True
    assert tray.toggle_action.text() == "Pause Translation"

    tray.set_active(False)
    assert tray._is_active is False
    assert tray.toggle_action.text() == "Start Translation"
    tray.close()


def test_macos_activation_policy_toggle() -> None:
    import sys
    from run import _set_macos_activation_policy
    if sys.platform == "darwin":
        from AppKit import (
            NSApp,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )
        if NSApp is not None:
            _set_macos_activation_policy(regular=False)
            assert NSApp.activationPolicy() == NSApplicationActivationPolicyAccessory
            _set_macos_activation_policy(regular=True)
            assert NSApp.activationPolicy() == NSApplicationActivationPolicyRegular
            _set_macos_activation_policy(regular=False)
            assert NSApp.activationPolicy() == NSApplicationActivationPolicyAccessory




