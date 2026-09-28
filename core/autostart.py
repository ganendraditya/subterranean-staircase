"""Cross-platform Auto-Start / Launch-on-Boot Manager.

Manages automatic launching on user login:
- macOS: ~/Library/LaunchAgents/com.subtitle-translator.subtrans.plist via launchctl
- Windows: %APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/subtrans.lnk or .bat
- Linux: ~/.config/autostart/subtrans.desktop
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("subtitle_translator.autostart")

MACOS_LABEL = "com.subtitle-translator.subtrans"


class AutostartManager:
    """Manages creation, deletion, and status check of system startup hooks."""

    def __init__(self, launcher_path: Optional[Path] = None) -> None:
        self.launcher_path = launcher_path or self._resolve_default_launcher()

    def _resolve_default_launcher(self) -> Path:
        """Resolve expected launcher path based on OS conventions."""
        if sys.platform == "win32":
            local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            return local_app_data / "Programs" / "SubtitleTranslator" / "subtrans.cmd"
        elif sys.platform == "darwin":
            mac_app_bin = Path.home() / "Applications" / "Subterranean Staircase.app" / "Contents" / "MacOS" / "subtrans"
            if mac_app_bin.exists():
                return mac_app_bin
            return Path.home() / ".local" / "bin" / "subtrans"
        else:
            return Path.home() / ".local" / "bin" / "subtrans"

    # -------------------------------------------------------------------------
    # macOS Implementation (LaunchAgent)
    # -------------------------------------------------------------------------
    def _macos_plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"

    def _enable_macos(self) -> bool:
        import plistlib

        plist_path = self._macos_plist_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)

        plist_data = {
            "Label": MACOS_LABEL,
            "ProgramArguments": [str(self.launcher_path)],
            "RunAtLoad": True,
            "KeepAlive": False,
            "StandardOutPath": str(Path.home() / "Library" / "Logs" / "subtrans.log"),
            "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "subtrans.log"),
        }
        try:
            with plist_path.open("wb") as fp:
                plistlib.dump(plist_data, fp)
            subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, check=False)
            logger.info("macOS LaunchAgent created and loaded: %s", plist_path)
            return True
        except Exception as e:
            logger.exception("Failed to write macOS LaunchAgent: %s", e)
            return False

    def _disable_macos(self) -> bool:
        plist_path = self._macos_plist_path()
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
            try:
                plist_path.unlink(missing_ok=True)
                logger.info("macOS LaunchAgent removed: %s", plist_path)
                return True
            except Exception as e:
                logger.exception("Failed to remove macOS LaunchAgent: %s", e)
                return False
        return True

    def _is_enabled_macos(self) -> bool:
        return self._macos_plist_path().exists()

    # -------------------------------------------------------------------------
    # Windows Implementation (Startup Folder)
    # -------------------------------------------------------------------------
    def _windows_startup_shortcut(self) -> Path:
        app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "subtrans.cmd"

    def _enable_windows(self) -> bool:
        shortcut = self._windows_startup_shortcut()
        shortcut.parent.mkdir(parents=True, exist_ok=True)
        try:
            content = f'@echo off\r\nstart "" "{self.launcher_path}"\r\n'
            shortcut.write_text(content, encoding="utf-8")
            logger.info("Windows startup script created: %s", shortcut)
            return True
        except Exception as e:
            logger.exception("Failed to write Windows startup script: %s", e)
            return False

    def _disable_windows(self) -> bool:
        shortcut = self._windows_startup_shortcut()
        if shortcut.exists():
            try:
                shortcut.unlink(missing_ok=True)
                logger.info("Windows startup script removed: %s", shortcut)
                return True
            except Exception as e:
                logger.exception("Failed to remove Windows startup script: %s", e)
                return False
        return True

    def _is_enabled_windows(self) -> bool:
        return self._windows_startup_shortcut().exists()

    # -------------------------------------------------------------------------
    # Linux Implementation (~/.config/autostart)
    # -------------------------------------------------------------------------
    def _linux_desktop_path(self) -> Path:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_home / "autostart" / "subtrans.desktop"

    def _enable_linux(self) -> bool:
        desktop_file = self._linux_desktop_path()
        desktop_file.parent.mkdir(parents=True, exist_ok=True)
        content = f"""[Desktop Entry]
Type=Application
Name=Subterranean Staircase
Comment=Real-time on-device screen subtitle translator
Exec="{self.launcher_path}"
Terminal=false
Categories=Utility;Translation;
"""
        try:
            desktop_file.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.exception("Failed to write Linux autostart file: %s", e)
            return False

    def _disable_linux(self) -> bool:
        desktop_file = self._linux_desktop_path()
        if desktop_file.exists():
            try:
                desktop_file.unlink(missing_ok=True)
                logger.info("Linux autostart file removed: %s", desktop_file)
                return True
            except Exception as e:
                logger.exception("Failed to remove Linux autostart file: %s", e)
                return False
        return True

    def _is_enabled_linux(self) -> bool:
        return self._linux_desktop_path().exists()

    # -------------------------------------------------------------------------
    # Public Unified API
    # -------------------------------------------------------------------------
    def is_enabled(self) -> bool:
        """Check whether auto-start is active on current platform."""
        if sys.platform == "darwin":
            return self._is_enabled_macos()
        elif sys.platform == "win32":
            return self._is_enabled_windows()
        else:
            return self._is_enabled_linux()

    def set_enabled(self, enable: bool) -> bool:
        """Enable or disable auto-start on current platform."""
        if sys.platform == "darwin":
            return self._enable_macos() if enable else self._disable_macos()
        elif sys.platform == "win32":
            return self._enable_windows() if enable else self._disable_windows()
        else:
            return self._enable_linux() if enable else self._disable_linux()
