"""Centralized configuration schema and persistence manager.

Persists user settings to ~/.config/subtitle-translator/config.json with safe defaults.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.contracts import CaptureMode


def get_default_config_path() -> Path:
    """Return default user config path: ~/.config/subtitle-translator/config.json"""
    base_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base_dir / "subtitle-translator" / "config.json"


@dataclass
class HotkeyConfig:
    """Configured global hotkeys."""
    toggle_translation: str = "Ctrl+Shift+S"
    select_roi: str = "Ctrl+Shift+R"
    toggle_overlay: str = "Ctrl+Shift+H"


@dataclass
class OverlayStyleConfig:
    """Visual style settings for the transparent subtitle overlay."""
    font_family: str = "Arial"
    font_size: int = 24
    font_bold: bool = True
    text_color: str = "#FFFFFF"        # White text
    stroke_color: str = "#000000"      # Black outline for WCAG AA contrast
    stroke_width: int = 3
    background_color: str = "#000000"  # Subtle pill background
    background_opacity: float = 0.4
    fade_out_seconds: float = 3.5      # Auto fade-out on speech pause


@dataclass
class LLMTranslationConfig:
    """Settings for Universal OpenAI-Compatible Cloud LLM translation."""
    enabled: bool = False
    base_url: str = "https://api.groq.com/openai/v1"
    api_key: str = ""
    model_name: str = "llama-3.3-70b-versatile"
    timeout_seconds: float = 3.0
    fallback_to_local: bool = True


@dataclass
class AppConfig:
    """Root application configuration schema."""
    version: str = "1.0.0"
    source_language: str = "en"
    target_language: str = "id"
    capture_mode: str = CaptureMode.FULL_SCREEN.value
    target_window_title: Optional[str] = None
    custom_roi: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)
    custom_overlay_position: Optional[Tuple[int, int]] = None  # (bottom_center_x, bottom_center_y)
    fps_limit: int = 10
    frame_diff_threshold: float = 0.015  # 1.5% pixel variance threshold to trigger OCR
    check_updates: bool = True
    auto_install_updates: bool = False
    autostart_on_boot: bool = False
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    overlay: OverlayStyleConfig = field(default_factory=OverlayStyleConfig)
    llm: LLMTranslationConfig = field(default_factory=LLMTranslationConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config dataclass to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppConfig:
        """Create AppConfig from dictionary with nested dataclass handling."""
        hotkeys_data = data.get("hotkeys")
        if isinstance(hotkeys_data, dict):
            valid_keys = HotkeyConfig.__dataclass_fields__
            hotkeys = HotkeyConfig(**{k: v for k, v in hotkeys_data.items() if k in valid_keys})
        else:
            hotkeys = HotkeyConfig()

        overlay_data = data.get("overlay")
        if isinstance(overlay_data, dict):
            valid_keys = OverlayStyleConfig.__dataclass_fields__
            overlay = OverlayStyleConfig(**{k: v for k, v in overlay_data.items() if k in valid_keys})
        else:
            overlay = OverlayStyleConfig()

        llm_data = data.get("llm")
        if isinstance(llm_data, dict):
            valid_keys = LLMTranslationConfig.__dataclass_fields__
            llm = LLMTranslationConfig(**{k: v for k, v in llm_data.items() if k in valid_keys})
        else:
            llm = LLMTranslationConfig()

        raw_roi = data.get("custom_roi")
        validated_roi: Optional[Tuple[int, int, int, int]] = None
        if raw_roi and len(raw_roi) == 4:
            try:
                validated_roi = tuple(int(x) for x in raw_roi)  # type: ignore[assignment]
            except (ValueError, TypeError):
                validated_roi = None

        raw_pos = data.get("custom_overlay_position")
        validated_pos: Optional[Tuple[int, int]] = None
        if isinstance(raw_pos, (list, tuple)) and len(raw_pos) == 2:
            try:
                validated_pos = (int(raw_pos[0]), int(raw_pos[1]))
            except (ValueError, TypeError):
                validated_pos = None

        return cls(
            version=data.get("version", "1.0.0"),
            source_language=data.get("source_language", "en"),
            target_language=data.get("target_language", "id"),
            capture_mode=data.get("capture_mode", CaptureMode.FULL_SCREEN.value),
            target_window_title=data.get("target_window_title"),
            custom_roi=validated_roi,
            custom_overlay_position=validated_pos,
            fps_limit=data.get("fps_limit", 10),
            frame_diff_threshold=data.get("frame_diff_threshold", 0.015),
            check_updates=bool(data.get("check_updates", True)),
            auto_install_updates=bool(data.get("auto_install_updates", False)),
            autostart_on_boot=bool(data.get("autostart_on_boot", False)),
            hotkeys=hotkeys,
            overlay=overlay,
            llm=llm,
        )


class ConfigManager:
    """Manages loading, modifying, and saving application configuration."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or get_default_config_path()
        self.config: AppConfig = self.load()

    def load(self) -> AppConfig:
        """Load config from disk; fallback to default if missing or invalid."""
        if not self.config_path.exists():
            return AppConfig()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppConfig.from_dict(data)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Failed to load config from %s, falling back to defaults: %s",
                self.config_path,
                exc,
            )
            return AppConfig()

    def save(self) -> None:
        """Persist current config atomically to disk to prevent file corruption."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.config_path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.config.to_dict(), f, indent=2)
            try:
                os.chmod(temp_file, 0o600)
            except OSError:
                pass
            os.replace(temp_file, self.config_path)
            try:
                os.chmod(self.config_path, 0o600)
            except OSError:
                pass
        except Exception:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise

    def update(self, **kwargs: Any) -> None:
        """Update top-level configuration values and auto-save, safely merging nested configs."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                current_attr = getattr(self.config, key)
                if isinstance(value, dict) and hasattr(current_attr, "__dataclass_fields__"):
                    merged_dict = asdict(current_attr)
                    merged_dict.update(value)
                    valid_keys = current_attr.__dataclass_fields__
                    filtered = {k: v for k, v in merged_dict.items() if k in valid_keys}
                    setattr(self.config, key, type(current_attr)(**filtered))
                else:
                    setattr(self.config, key, value)
        self.save()

    def purge_user_data(self) -> None:
        """Purge all caches, downloaded models, and configuration files, resetting state to defaults."""
        from core.storage.cache import get_default_cache_db_path
        import shutil

        cache_dir = get_default_cache_db_path().parent
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)

        if self.config_path.exists():
            self.config_path.unlink(missing_ok=True)

        self.config = AppConfig()
        self.save()
