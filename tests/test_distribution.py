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


def test_subtrans_spec_configuration() -> None:
    spec_path = _root() / "subtrans.spec"
    assert spec_path.exists(), "subtrans.spec is missing"
    content = spec_path.read_text(encoding="utf-8")

    assert "rapidocr_onnxruntime" in content
    assert "ctranslate2" in content
    assert "sentencepiece" in content
    assert "ui/assets" in content
    assert "NSScreenCaptureUsageDescription" in content
    assert "com.subtitle-translator.subtrans" in content
    assert "app_icon.icns" in content
    assert "app_icon.ico" in content


def test_inno_setup_script_configuration() -> None:
    iss_path = _root() / "scripts" / "installer.iss"
    assert iss_path.exists(), "scripts/installer.iss is missing"
    content = iss_path.read_text(encoding="utf-8")

    assert 'MyAppName "Subterranean Staircase"' in content
    assert "Subterranean-Staircase-windows-x64-Setup" in content
    assert "app_icon.ico" in content
    assert "compression=lzma2/ultra64" in content.lower()


def test_build_standalone_script_functions() -> None:
    import sys
    sys.path.insert(0, str(_root()))
    from scripts.build_standalone import get_platform_target

    target = get_platform_target()
    assert isinstance(target, str)
    assert any(target.startswith(prefix) for prefix in ("macos-", "windows-", "linux-"))


def test_package_windows_installer_zip_creation(tmp_path: Path) -> None:
    import sys
    sys.path.insert(0, str(_root()))
    from scripts.build_standalone import package_windows_installer

    fake_app_dir = tmp_path / "Subterranean Staircase"
    fake_app_dir.mkdir()
    (fake_app_dir / "Subterranean Staircase.exe").write_text("dummy binary", encoding="utf-8")
    (fake_app_dir / "config.json").write_text("{}", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    fake_iss = tmp_path / "installer.iss"
    fake_iss.write_text("; fake inno script", encoding="utf-8")

    artifacts = package_windows_installer(fake_app_dir, out_dir, fake_iss)
    assert len(artifacts) >= 1
    zip_artifact = [a for a in artifacts if a.suffix == ".zip"][0]
    assert zip_artifact.exists()
    assert zip_artifact.stat().st_size > 0


def test_package_macos_dmg_dry_run(tmp_path: Path, monkeypatch) -> None:
    import sys
    sys.path.insert(0, str(_root()))
    from scripts.build_standalone import package_macos_dmg

    fake_app = tmp_path / "Subterranean Staircase.app"
    fake_app.mkdir()
    (fake_app / "Contents").mkdir()
    (fake_app / "Contents" / "Info.plist").write_text("<plist></plist>", encoding="utf-8")

    out_dmg = tmp_path / "test.dmg"

    # Mock subprocess.run for hdiutil
    ran_cmds = []

    def mock_run(cmd, check=True):
        ran_cmds.append(cmd)
        out_dmg.write_bytes(b"dummy dmg content")

    monkeypatch.setattr("subprocess.run", mock_run)

    res = package_macos_dmg(fake_app, out_dmg)
    assert res == out_dmg
    assert out_dmg.exists()
    assert len(ran_cmds) == 1
    assert "hdiutil" in ran_cmds[0]


def test_github_actions_workflow_installers_configuration() -> None:
    import yaml
    wf_path = _root() / ".github" / "workflows" / "build-installers.yml"
    assert wf_path.exists(), ".github/workflows/build-installers.yml is missing"

    data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    assert "jobs" in data

    jobs = data["jobs"]
    assert "build-macos" in jobs
    assert "build-windows-x64" in jobs
    assert "publish-release" in jobs

    matrix = jobs["build-macos"]["strategy"]["matrix"]["include"]
    archs = [item["arch"] for item in matrix]
    assert "arm64" in archs
    assert "x86_64" in archs
    assert jobs["build-windows-x64"]["runs-on"] == "windows-latest"



