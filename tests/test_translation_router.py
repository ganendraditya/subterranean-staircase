"""Unit tests for TranslationRouter and multi-hop pivot routing."""

from core.translate.languages import BIG_5_LANGUAGES
from core.translate.models import RECOMMENDED_MODELS
from core.translate.router import TranslationRouter, normalize_lang_code


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
    # Cross language pairs with English pivot (ja->en and en->id exist in catalog)
    assert router.resolve_route("ja", "id") == [("ja", "en"), ("en", "id")]
    assert router.resolve_route("ko", "id") == [("ko", "en"), ("en", "id")]
    assert router.resolve_route("zh", "id") == [("zh", "en"), ("en", "id")]


def test_router_unobtainable_routes_return_empty() -> None:
    router = TranslationRouter()
    # Reverse directions without models in catalog return []
    assert router.resolve_route("id", "en") == []
    assert router.resolve_route("en", "ja") == []
    assert router.resolve_route("id", "ja") == []


def test_router_required_pairs_helper() -> None:
    router = TranslationRouter()
    assert router.required_pairs("ja", "id") == ["ja-en", "en-id"]
    assert router.required_pairs("en", "id") == ["en-id"]
    assert router.required_pairs("ja", "ja") == []


def test_all_deliverable_routes_exist_in_catalog() -> None:
    router = TranslationRouter()
    for _, s_code in BIG_5_LANGUAGES:
        for _, t_code in BIG_5_LANGUAGES:
            hops = router.resolve_route(s_code, t_code)
            for hop_s, hop_t in hops:
                assert f"{hop_s}-{hop_t}" in RECOMMENDED_MODELS
