"""Unit tests for TranslationRouter and multi-hop pivot routing."""

import pytest
from core.translate.router import BIG_5_LANGUAGES, TranslationRouter, normalize_lang_code


def test_big_5_languages_defined() -> None:
    codes = [code for _, code in BIG_5_LANGUAGES]
    assert codes == ["en", "id", "ja", "ko", "zh"]


def test_normalize_lang_code() -> None:
    assert normalize_lang_code("en") == "en"
    assert normalize_lang_code("en-US") == "en"
    assert normalize_lang_code("zh-CN") == "zh"
    assert normalize_lang_code(" JA ") == "ja"
    assert normalize_lang_code("ko_KR") == "ko"


def test_router_identity_no_op() -> None:
    router = TranslationRouter()
    assert router.resolve_route("en", "en") == []
    assert router.resolve_route("id", "id") == []
    assert router.resolve_route("ja", "ja") == []
    assert router.resolve_route("en-US", "en-GB") == []


def test_router_direct_1_hop() -> None:
    router = TranslationRouter()
    # Explicitly supported direct pairs in catalog
    assert router.resolve_route("en", "id") == [("en", "id")]
    assert router.resolve_route("ja", "en") == [("ja", "en")]
    assert router.resolve_route("ko", "en") == [("ko", "en")]
    assert router.resolve_route("zh", "en") == [("zh", "en")]


def test_router_pivot_2_hop() -> None:
    router = TranslationRouter()
    # Cross language pairs with English pivot
    assert router.resolve_route("ja", "id") == [("ja", "en"), ("en", "id")]
    assert router.resolve_route("ko", "id") == [("ko", "en"), ("en", "id")]
    assert router.resolve_route("zh", "id") == [("zh", "en"), ("en", "id")]


def test_router_custom_direct_pairs() -> None:
    # If a direct ja-id model exists in custom pair registry, route directly
    router = TranslationRouter(available_direct_pairs={"ja-id", "en-id"})
    assert router.resolve_route("ja", "id") == [("ja", "id")]
    # But ko-id still pivots through en
    assert router.resolve_route("ko", "id") == [("ko", "en"), ("en", "id")]
