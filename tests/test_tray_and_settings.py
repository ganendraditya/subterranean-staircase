"""Unit tests for SettingsDialog and TrayController."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PyQt6.QtWidgets import QApplication

from core.capture.base import BaseCapture
from core.config import ConfigManager
from core.contracts import Rect, WindowInfo
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
    mock_capture = MagicMock(spec=BaseCapture)
    mock_capture.list_windows.return_value = [
        WindowInfo(window_id=123, title="VLC", owner_name="vlc", rect=Rect(0, 0, 800, 600))
    ]

    tray = TrayController(config_manager=config_mgr, capture_driver=mock_capture)

    # 1. Test Toggle Translation
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

    # 2. Test Populate Windows Submenu and Triggering Action
    tray._populate_windows_menu()
    actions = tray.window_menu.actions()
    # Entire screen + separator + 1 window
    assert len(actions) == 3
    assert "Entire Screen" in actions[0].text()
    assert "vlc: VLC" in actions[2].text()

    # Triggering full screen action should not raise TypeError
    selected_wins: list = []
    tray.window_selected.connect(selected_wins.append)
    actions[0].trigger()
    assert len(selected_wins) == 1
    assert selected_wins[0] is None

    # Triggering specific window action
    actions[2].trigger()
    assert len(selected_wins) == 2
    assert selected_wins[1].window_id == 123
