"""Unit tests verifying installer script syntax and presence."""

from pathlib import Path


def _root() -> Path:
    return Path(__file__).parent.parent


def test_distribution_scripts_exist() -> None:
    root = _root()
    assert (root / "install.sh").exists()
    assert (root / "uninstall.sh").exists()
    assert (root / "install.ps1").exists()
    assert (root / "uninstall.ps1").exists()


def test_shell_scripts_have_correct_shebang() -> None:
    root = _root()
    for name in ("install.sh", "uninstall.sh"):
        with open(root / name, encoding="utf-8") as f:
            assert f.readline().startswith("#!/usr/bin/env bash"), f"{name} missing bash shebang"


def test_shell_scripts_have_errexit() -> None:
    root = _root()
    for name in ("install.sh", "uninstall.sh"):
        content = (root / name).read_text(encoding="utf-8")
        assert "set -euo pipefail" in content, f"{name} missing 'set -euo pipefail'"


def test_install_sh_creates_launcher_in_local_bin() -> None:
    content = (_root() / "install.sh").read_text(encoding="utf-8")
    assert '~/.local/bin' in content or 'BIN_DIR' in content
    assert "subtrans" in content


def test_install_sh_contains_launchagent_support() -> None:
    content = (_root() / "install.sh").read_text(encoding="utf-8")
    assert "LaunchAgent" in content
    assert "com.subtitle-translator.subtrans" in content
    assert "RunAtLoad" in content


def test_install_sh_creates_macos_app_bundle() -> None:
    content = (_root() / "install.sh").read_text(encoding="utf-8")
    assert "Subterranean Staircase.app" in content
    assert "NSScreenCaptureUsageDescription" in content
    assert "CFBundleIdentifier" in content


def test_uninstall_sh_removes_macos_app_bundle() -> None:
    content = (_root() / "uninstall.sh").read_text(encoding="utf-8")
    assert "Subterranean Staircase.app" in content or "Subtitle Translator.app" in content


def test_uninstall_sh_removes_launchagent() -> None:
    content = (_root() / "uninstall.sh").read_text(encoding="utf-8")
    assert "com.subtitle-translator.subtrans.plist" in content
    assert "launchctl unload" in content


def test_uninstall_sh_removes_config_and_cache() -> None:
    content = (_root() / "uninstall.sh").read_text(encoding="utf-8")
    assert "subtitle-translator" in content
    assert "--purge" in content or "PURGE_DATA" in content


def test_uninstall_sh_handles_uninstall_positional_arg() -> None:
    content = (_root() / "uninstall.sh").read_text(encoding="utf-8")
    assert "uninstall) ;;" in content


def test_install_ps1_targets_localappdata() -> None:
    content = (_root() / "install.ps1").read_text(encoding="utf-8")
    assert "LOCALAPPDATA" in content
    assert "subtrans.cmd" in content
    assert "candidates" in content


def test_install_ps1_adds_to_path() -> None:
    content = (_root() / "install.ps1").read_text(encoding="utf-8")
    assert "Environment" in content
    assert "SetValue" in content or "NewUserPath" in content


def test_install_ps1_launcher_stages_uninstaller_to_temp() -> None:
    content = (_root() / "install.ps1").read_text(encoding="utf-8")
    assert "TMP_UNINSTALL" in content
    assert "%TEMP%" in content


def test_uninstall_ps1_accepts_action_positional_param() -> None:
    content = (_root() / "uninstall.ps1").read_text(encoding="utf-8")
    assert "$Action" in content


def test_uninstall_ps1_normalizes_double_dash_args() -> None:
    content = (_root() / "uninstall.ps1").read_text(encoding="utf-8")
    assert "$allArgs" in content
    assert "--force" in content
    assert "--purge" in content


def test_uninstall_ps1_removes_from_path() -> None:
    content = (_root() / "uninstall.ps1").read_text(encoding="utf-8")
    assert "CleanPaths" in content or "SetValue" in content


def test_install_ps1_supports_startup_shortcut() -> None:
    content = (_root() / "install.ps1").read_text(encoding="utf-8")
    assert "Startup" in content
    assert "subtrans.cmd" in content


def test_uninstall_ps1_removes_startup_shortcut() -> None:
    content = (_root() / "uninstall.ps1").read_text(encoding="utf-8")
    assert "Startup" in content
    assert "StartupShortcut" in content


def test_uninstall_ps1_removes_config_and_cache() -> None:
    content = (_root() / "uninstall.ps1").read_text(encoding="utf-8")
    assert "ConfigDir" in content
    assert "CacheDir" in content
