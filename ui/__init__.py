"""UI module public exports."""

from ui.overlay import SubtitleOverlayWindow
from ui.region_selector import RegionSelectorWidget
from ui.settings_dialog import SettingsDialog
from ui.tray import TrayController

__all__ = [
    "RegionSelectorWidget",
    "SettingsDialog",
    "SubtitleOverlayWindow",
    "TrayController",
]
