"""Unit tests for multilingual script detection and text cleanup filters."""

from core.contracts import SubtitleBox, SubtitleDetection
from core.subtitle.filters import SubtitleTextFilter, clean_subtitle_text, detect_script


def _make_det(text: str) -> SubtitleDetection:
    pts = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    return SubtitleDetection(
        text=text,
        confidence=0.9,
        box=SubtitleBox.from_list(pts),
    )


def test_detect_script() -> None:
    assert detect_script("") == "latin"
    assert detect_script("Hello world, this is English") == "latin"
    assert detect_script("Halo apa kabar") == "latin"
    assert detect_script("こんにちは") == "ja"           # Hiragana
    assert detect_script("アニメーション") == "ja"          # Katakana
    assert detect_script("안녕하세요") == "ko"            # Hangul
    assert detect_script("你好，世界") == "zh"            # CJK
    assert detect_script("مرحبا بكم") == "ar"             # Arabic
    assert detect_script("Hello world with minor glyph: あ") == "latin"


def test_clean_subtitle_text() -> None:
    assert clean_subtitle_text("") == ""
    # Timestamp stripping
    assert clean_subtitle_text("[00:15] Hello there!") == "Hello there!"
    assert clean_subtitle_text("[1:23:45] Look out!!") == "Look out!"
    # Language prefix stripping
    assert clean_subtitle_text("(EN) What are you doing?") == "What are you doing?"
    assert clean_subtitle_text("JA: 待って") == "待って"
    # Preserves ellipsis
    assert clean_subtitle_text("Wait... what???") == "Wait... what?"
    # Strips trailing stutter dashes
    assert clean_subtitle_text("service--") == "service"
    # Collapses erratic spaces
    assert clean_subtitle_text("  Too    many   spaces   ") == "Too many spaces"
    # Player badges stripped when standalone or bracketed, preserved when legitimate words
    assert clean_subtitle_text("cc") == ""
    assert clean_subtitle_text("[CC]") == ""
    assert clean_subtitle_text("Intro") == ""
    assert clean_subtitle_text("intro to physics") == "intro to physics"
    assert clean_subtitle_text("250 cc engine") == "250 cc engine"


def test_subtitle_text_filter_latin() -> None:
    filter_latin = SubtitleTextFilter(target_script="latin")
    dets = [
        _make_det("[01:23] Good morning!"),
        _make_det("こんにちは"),  # Japanese - should be rejected when expecting latin
        _make_det("Halo kawan"),
    ]

    cleaned = filter_latin.filter_and_clean(dets)
    assert len(cleaned) == 2
    assert cleaned[0].text == "Good morning!"
    assert cleaned[0].language == "latin"
    assert cleaned[1].text == "Halo kawan"


def test_subtitle_text_filter_cjk() -> None:
    filter_ja = SubtitleTextFilter(target_script="ja")
    dets = [
        _make_det("こんにちは"),  # Kana
        _make_det("東京"),       # Standalone Kanji (CJK) - should be accepted and tagged as 'ja' in Japanese mode
        _make_det("مرحبا"),      # Arabic should be rejected
    ]

    cleaned = filter_ja.filter_and_clean(dets)
    assert len(cleaned) == 2
    assert cleaned[0].text == "こんにちは"
    assert cleaned[0].language == "ja"
    assert cleaned[1].text == "東京"
    assert cleaned[1].language == "ja"
