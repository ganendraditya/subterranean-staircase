"""Unit tests for CTranslate2Engine and 2-hop routing."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.contracts import TranslationRequest, TranslationResult
from core.storage.cache import SQLiteTranslationCache
from core.translate.local import BaseTranslator, CTranslate2Engine


def test_routing_logic() -> None:
    engine = CTranslate2Engine()

    # Identical source and target
    assert engine._route("en", "en") == []

    # Direct 1-hop pairs
    assert engine._route("en", "id") == [("en", "id")]
    assert engine._route("id", "en") == [("id", "en")]
    assert engine._route("ja", "en") == [("ja", "en")]
    assert engine._route("en", "zh") == [("en", "zh")]

    # 2-hop routing through English
    assert engine._route("ja", "id") == [("ja", "en"), ("en", "id")]
    assert engine._route("ko", "id") == [("ko", "en"), ("en", "id")]
    assert engine._route("ja", "zh") == [("ja", "en"), ("en", "zh")]
    assert engine._route("id", "zh") == [("id", "en"), ("en", "zh")]

    # Regional English (en-US, en_GB) maps to standard 'en' for Opus-MT model compatibility
    assert engine._route("ja", "en_GB") == [("ja", "en")]

    # Regional English to English variant returns empty route
    assert engine._route("en-US", "en") == []
    assert engine._route("en-US", "en-GB") == []
    assert engine._route("en", "en-US") == []

    # Unobtainable routes return empty
    assert engine._route("en", "ja") == []


def test_translate_empty_route_raises_value_error() -> None:
    engine = CTranslate2Engine()
    # When no route exists in catalog, translate() must raise ValueError to prevent cache poisoning
    req = TranslationRequest(source_text="Test", source_lang="en", target_lang="ja")
    with pytest.raises(ValueError, match="No translation route available"):
        engine.translate(req)


def test_translate_empty_or_same_language() -> None:
    engine = CTranslate2Engine()

    res_empty = engine.translate(TranslationRequest(source_text="", source_lang="en", target_lang="id"))
    assert res_empty.translated_text == ""

    res_same = engine.translate(TranslationRequest(source_text="Hello", source_lang="en", target_lang="en"))
    assert res_same.translated_text == "Hello"

    res_variant = engine.translate(TranslationRequest(source_text="Hello", source_lang="en-US", target_lang="en"))
    assert res_variant.translated_text == "Hello"


def test_translate_with_cache_hit(tmp_path: Path) -> None:
    cache = SQLiteTranslationCache(db_path=tmp_path / "cache.db")
    cache.set("Good morning", "en", "id", "Selamat pagi")

    engine = CTranslate2Engine(cache=cache)
    req = TranslationRequest(source_text="Good morning", source_lang="en", target_lang="id")

    result = engine.translate(req)
    assert result.translated_text == "Selamat pagi"
    assert result.from_cache is True
    assert result.latency_ms >= 0.0


def test_translate_missing_model_raises_filenotfound(tmp_path: Path) -> None:
    engine = CTranslate2Engine(models_dir=tmp_path / "nonexistent_models")
    req = TranslationRequest(source_text="Test", source_lang="en", target_lang="id")

    with pytest.raises(FileNotFoundError, match="not found"):
        engine.translate(req)


def test_translate_mocked_execution(tmp_path: Path) -> None:
    cache = SQLiteTranslationCache(db_path=tmp_path / "cache.db")
    engine = CTranslate2Engine(cache=cache)

    mock_translator = MagicMock()
    # Mock hypotheses
    mock_batch_res = MagicMock()
    mock_batch_res.hypotheses = [["Selamat", "malam"]]
    mock_translator.translate_batch.return_value = [mock_batch_res]

    mock_sp = MagicMock()
    mock_sp.encode.return_value = ["Good", "night"]
    mock_sp.decode.return_value = "Selamat malam"

    # Inject mock pair directly into engine (translator, sp_source, sp_target)
    engine._loaded_pairs["en-id"] = (mock_translator, mock_sp, mock_sp)

    req = TranslationRequest(source_text="Good night", source_lang="en", target_lang="id")
    result = engine.translate(req)

    assert result.translated_text == "Selamat malam"
    assert result.from_cache is False

    # Second call should hit the SQLite cache
    result2 = engine.translate(req)
    assert result2.translated_text == "Selamat malam"
    assert result2.from_cache is True


def test_translate_path_traversal_protection(tmp_path: Path) -> None:
    engine = CTranslate2Engine(models_dir=tmp_path)
    req = TranslationRequest(source_text="Test", source_lang="../../etc", target_lang="passwd")

    with pytest.raises(ValueError, match="Invalid language codes"):
        engine.translate(req)


def test_regional_language_tags(tmp_path: Path) -> None:
    engine = CTranslate2Engine(models_dir=tmp_path)
    # Regional tags with hyphen or underscore should be allowed
    path = engine._get_pair_model_path("en", "zh-CN")
    assert path.name == "opus-mt-en-zh-CN"

    path2 = engine._get_pair_model_path("en", "pt_BR")
    assert path2.name == "opus-mt-en-pt_BR"
