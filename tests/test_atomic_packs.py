"""Unit tests for Atomic Language Pack architecture."""

from pathlib import Path
from unittest.mock import patch

import pytest
from core.translate.models import ModelManager
from core.translate.packs import ATOMIC_LANGUAGE_PACKS


def test_atomic_packs_curated_catalog() -> None:
    # Validate The Big 5 packs are defined
    assert "core" in ATOMIC_LANGUAGE_PACKS
    assert "ja" in ATOMIC_LANGUAGE_PACKS
    assert "ko" in ATOMIC_LANGUAGE_PACKS
    assert "zh" in ATOMIC_LANGUAGE_PACKS

    core_pack = ATOMIC_LANGUAGE_PACKS["core"]
    assert core_pack.is_core is True
    assert set(core_pack.translation_pairs) == {"en-id", "id-en"}


def test_core_pack_protected_from_deletion(tmp_path: Path) -> None:
    mm = ModelManager(models_dir=tmp_path)
    # Core pack should be protected
    ok, msg = mm.delete_pack("core")
    assert ok is False
    assert "Cannot delete the Core" in msg


def test_pack_installation_lifecycle(tmp_path: Path) -> None:
    mm = ModelManager(models_dir=tmp_path)

    # Initially, packs are not installed
    assert mm.is_pack_installed("ja") is False
    assert mm.get_pack_disk_size_mb("ja") == 0.0

    # Simulate installing ja-en model with > 1KB content to show > 0.0 MB
    ja_dir = mm.get_model_path("ja-en")
    ja_dir.mkdir(parents=True)
    (ja_dir / "model.bin").write_bytes(b"0" * (1024 * 1024))
    (ja_dir / "source.spm").write_bytes(b"dummy_spm")
    (ja_dir / "config.json").write_bytes(b"{}")

    # Now ja pack should report as installed
    assert mm.is_pack_installed("ja") is True
    assert mm.get_pack_disk_size_mb("ja") > 0.0

    # Test pack deletion
    ok, msg = mm.delete_pack("ja")
    assert ok is True
    assert mm.is_pack_installed("ja") is False
    assert not ja_dir.exists()


def test_partial_pack_state_reporting(tmp_path: Path) -> None:
    mm = ModelManager(models_dir=tmp_path)
    # Chinese pack has zh-en and en-zh. Simulate only zh-en installed.
    zh_dir = mm.get_model_path("zh-en")
    zh_dir.mkdir(parents=True)
    (zh_dir / "model.bin").write_bytes(b"0" * (1024 * 1024))
    (zh_dir / "source.spm").write_bytes(b"dummy_spm")
    (zh_dir / "config.json").write_bytes(b"{}")

    assert mm.is_pack_installed("zh") is False
    assert mm.is_pack_partially_installed("zh") is True
    assert mm.get_pack_disk_size_mb("zh") > 0.0


def test_list_packs_status(tmp_path: Path) -> None:
    mm = ModelManager(models_dir=tmp_path)
    packs_status = mm.list_packs_status()

    assert len(packs_status) == len(ATOMIC_LANGUAGE_PACKS)
    pack_ids = [p["pack_id"] for p in packs_status]
    assert "core" in pack_ids
    assert "ja" in pack_ids
