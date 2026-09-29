"""Unit tests for SubtitleHistoryTracker and Jaccard similarity stabilization."""

from core.contracts import SubtitleBox, SubtitleDetection
from core.subtitle.history import SubtitleHistoryTracker, should_replace_best_text, text_similarity


def _make_det(text: str, confidence: float = 0.90, y: float = 900.0) -> SubtitleDetection:
    pts = [
        [100.0, y - 10.0],
        [400.0, y - 10.0],
        [400.0, y + 10.0],
        [100.0, y + 10.0],
    ]
    return SubtitleDetection(
        text=text,
        confidence=confidence,
        box=SubtitleBox.from_list(pts),
    )


def test_jaccard_text_similarity() -> None:
    assert text_similarity("", "hello") == 0.0
    assert text_similarity("hello world", "hello world") == 1.0
    # "i see you" vs "i see them" -> union {"i", "see", "you", "them"} (4), intersection {"i", "see"} (2) -> 2/4 = 0.5
    assert text_similarity("i see you", "i see them") == 0.5
    assert text_similarity("completely different", "totally unrelated") == 0.0


def test_cjk_jaccard_text_similarity() -> None:
    # Testing Japanese Kanji/Kana character segmentation
    # "こんにちは世界" (Hello World - 7 chars) vs "こんにちは" (Hello - 5 chars)
    sim = text_similarity("こんにちは世界", "こんにちは")
    # 5 shared chars out of 7 total -> 5/7 ~ 0.714
    assert 0.70 < sim < 0.73

    # Chinese progressive subtitles: set intersection 4 chars ("今", "天", "气", "好"), union 6 chars -> 4/6 = 0.666...
    sim_zh = text_similarity("今天天气很好", "今天天气真好")
    assert 0.65 < sim_zh < 0.68


def test_cjk_should_replace_best_text() -> None:
    # Longer Japanese sentence should replace shorter candidate
    assert should_replace_best_text(
        current_best="こんにちは",
        current_conf=0.90,
        new_text="こんにちは世界",
        new_conf=0.88,
    ) is True


def test_should_replace_best_text() -> None:
    # Longer text with good confidence wins
    assert should_replace_best_text(
        current_best="I see",
        current_conf=0.90,
        new_text="I see you right now",
        new_conf=0.85,
    ) is True

    # Shorter truncated text loses
    assert should_replace_best_text(
        current_best="I see you right now",
        current_conf=0.85,
        new_text="I see",
        new_conf=0.90,
    ) is False

    # Same words, significantly higher confidence wins
    assert should_replace_best_text(
        current_best="Hello friend",
        current_conf=0.70,
        new_text="Hello friend",
        new_conf=0.95,
    ) is True


def test_history_tracker_temporal_stabilization() -> None:
    tracker = SubtitleHistoryTracker(stable_min_count=2, similarity_threshold=0.5, expire_seconds=2.0)

    # Frame 1 at t=0.0: initial observation
    det1 = _make_det("Wait for me", confidence=0.80)
    stable1 = tracker.update([det1], now=0.0)
    # Count is 1, not yet stable
    assert len(stable1) == 0

    # Frame 2 at t=0.1: second observation (fused with active track)
    det2 = _make_det("Wait for me now", confidence=0.95)
    stable2 = tracker.update([det2], now=0.1)
    assert len(stable2) == 1
    assert stable2[0].count == 2
    assert stable2[0].stable_text == "Wait for me now"
    assert stable2[0].best_conf == 0.95


def test_history_tracker_pruning() -> None:
    tracker = SubtitleHistoryTracker(expire_seconds=1.5)

    det = _make_det("Temporary caption")
    tracker.update([det], now=0.0)
    tracker.update([det], now=0.2)

    # At t=0.5: still alive
    assert len(tracker.update([], now=0.5)) == 1

    # At t=2.0: expired (> 1.5s since last seen at 0.2s)
    assert len(tracker.update([], now=2.0)) == 0


def test_history_tracker_reset() -> None:
    tracker = SubtitleHistoryTracker()
    det = _make_det("Persistent")
    tracker.update([det], now=0.0)
    tracker.update([det], now=0.5)

    tracker.reset()
    assert len(tracker.update([], now=0.6)) == 0


def test_history_tracker_only_current() -> None:
    tracker = SubtitleHistoryTracker(expire_seconds=3.0)
    det1 = _make_det("Line 1 from first caption")
    det2 = _make_det("Line 2 from next caption")

    # Frame 1 & 2: line 1 active
    tracker.update([det1], now=0.0)
    stable1 = tracker.update([det1], now=0.1, only_current=True)
    assert len(stable1) == 1
    assert stable1[0].text == "Line 1 from first caption"

    # Frame 3 & 4: scene switches to line 2 (line 1 is no longer in detections)
    tracker.update([det2], now=0.2, only_current=True)
    stable2 = tracker.update([det2], now=0.3, only_current=True)
    # With only_current=True, line 1 must not be mixed into the returned tracks
    assert len(stable2) == 1
    assert stable2[0].text == "Line 2 from next caption"

