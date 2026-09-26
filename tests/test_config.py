"""Unit tests for configuration manager and schema persistence."""

import json
from pathlib import Path
import pytest
from core.config import AppConfig, ConfigManager, HotkeyConfig, OverlayStyleConfig


def test_default_config_values() -> None:
    config = AppConfig()
    assert config.version == "1.0.0"
    assert config.source_language == "en"
    assert config.target_language == "id"
    assert config.overlay.text_color == "#FFFFFF"
    assert config.overlay.stroke_color == "#000000"
    assert config.hotkeys.toggle_translation == "Ctrl+Shift+S"


def test_config_serialization_roundtrip() -> None:
    config = AppConfig(
        source_language="ja",
        target_language="id",
        custom_roi=(10, 20, 300, 400),
    )
    data = config.to_dict()
    assert data["source_language"] == "ja"
    assert tuple(data["custom_roi"]) == (10, 20, 300, 400)

    reconstructed = AppConfig.from_dict(data)
    assert reconstructed.source_language == "ja"
    assert reconstructed.custom_roi == (10, 20, 300, 400)


def test_config_manager_load_save(tmp_path: Path) -> None:
    config_file = tmp_path / "subdir" / "test_config.json"
    manager = ConfigManager(config_path=config_file)

    # Initially file does not exist, defaults are loaded
    assert manager.config.target_language == "id"

    # Update and verify auto-save
    manager.update(target_language="en", source_language="ko")
    assert config_file.exists()

    # Re-read from disk to confirm persistence
    with open(config_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data["target_language"] == "en"
    assert saved_data["source_language"] == "ko"

    # Load with another manager instance
    new_manager = ConfigManager(config_path=config_file)
    assert new_manager.config.target_language == "en"
    assert new_manager.config.source_language == "ko"


def test_config_manager_corrupted_json_fallback(tmp_path: Path) -> None:
    config_file = tmp_path / "corrupted.json"
    with open(config_file, "w", encoding="utf-8") as f:
        f.write("{ invalid json syntax ...")

    # Corrupted file falls back gracefully to AppConfig defaults without crashing
    manager = ConfigManager(config_path=config_file)
    assert manager.config.source_language == "en"
    assert manager.config.target_language == "id"
