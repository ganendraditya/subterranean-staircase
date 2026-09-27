"""Unit tests for cross-platform AutostartManager."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.autostart import AutostartManager


def test_autostart_manager_resolve_launcher() -> None:
    mgr = AutostartManager()
    assert mgr.launcher_path is not None
    assert "subtrans" in str(mgr.launcher_path)


def test_autostart_macos(tmp_path: Path) -> None:
    launcher = tmp_path / "bin" / "subtrans"
    launcher.parent.mkdir(parents=True)
    launcher.touch()

    mgr = AutostartManager(launcher_path=launcher)
    dummy_plist = tmp_path / "com.subtitle-translator.subtrans.plist"

    with patch.object(mgr, "_macos_plist_path", return_value=dummy_plist), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        # 1. Enable
        success = mgr._enable_macos()
        assert success is True
        assert dummy_plist.exists()
        content = dummy_plist.read_text(encoding="utf-8")
        assert "com.subtitle-translator.subtrans" in content
        assert str(launcher) in content
        assert "RunAtLoad" in content

        # 2. Check enabled
        assert mgr._is_enabled_macos() is True

        # 3. Disable
        success_disable = mgr._disable_macos()
        assert success_disable is True
        assert not dummy_plist.exists()
        assert mgr._is_enabled_macos() is False


def test_autostart_windows(tmp_path: Path) -> None:
    launcher = tmp_path / "Programs" / "subtrans.cmd"
    launcher.parent.mkdir(parents=True)
    launcher.touch()

    mgr = AutostartManager(launcher_path=launcher)
    dummy_startup = tmp_path / "Startup" / "subtrans.cmd"

    with patch.object(mgr, "_windows_startup_shortcut", return_value=dummy_startup):
        # 1. Enable
        success = mgr._enable_windows()
        assert success is True
        assert dummy_startup.exists()
        content = dummy_startup.read_text(encoding="utf-8")
        assert str(launcher) in content

        # 2. Check enabled
        assert mgr._is_enabled_windows() is True

        # 3. Disable
        success_disable = mgr._disable_windows()
        assert success_disable is True
        assert not dummy_startup.exists()
        assert mgr._is_enabled_windows() is False


def test_autostart_linux(tmp_path: Path) -> None:
    launcher = tmp_path / "bin" / "subtrans"
    launcher.parent.mkdir(parents=True)
    launcher.touch()

    mgr = AutostartManager(launcher_path=launcher)
    dummy_desktop = tmp_path / "autostart" / "subtrans.desktop"

    with patch.object(mgr, "_linux_desktop_path", return_value=dummy_desktop):
        # 1. Enable
        success = mgr._enable_linux()
        assert success is True
        assert dummy_desktop.exists()
        content = dummy_desktop.read_text(encoding="utf-8")
        assert "Subterranean Staircase" in content
        assert str(launcher) in content

        # 2. Check enabled
        assert mgr._is_enabled_linux() is True

        # 3. Disable
        success_disable = mgr._disable_linux()
        assert success_disable is True
        assert not dummy_desktop.exists()
        assert mgr._is_enabled_linux() is False


def test_unified_api_delegation(tmp_path: Path) -> None:
    mgr = AutostartManager(launcher_path=tmp_path / "subtrans")

    with patch.object(mgr, "_enable_macos", return_value=True) as mock_mac_enable, \
         patch.object(mgr, "_disable_macos", return_value=True) as mock_mac_disable, \
         patch.object(mgr, "_is_enabled_macos", return_value=True) as mock_mac_check, \
         patch("sys.platform", "darwin"):
        assert mgr.set_enabled(True) is True
        mock_mac_enable.assert_called_once()

        assert mgr.set_enabled(False) is True
        mock_mac_disable.assert_called_once()

        assert mgr.is_enabled() is True
        mock_mac_check.assert_called_once()
