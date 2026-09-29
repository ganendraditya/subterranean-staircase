"""Unit tests for Ground Truth evaluation metrics (WER, CER, Levenshtein distance)."""

from scripts.eval_ground_truth import compute_cer, compute_wer, levenshtein_distance


def test_levenshtein_distance() -> None:
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance(["hello", "world"], ["hello", "world"]) == 0
    assert levenshtein_distance(["hello", "there"], ["hello", "world"]) == 1


def test_compute_wer() -> None:
    # Exact match
    assert compute_wer("Stay Hungry Stay Foolish", "Stay Hungry Stay Foolish") == 0.0
    # 1 word substituted out of 4 words = 25% WER
    assert compute_wer("Stay Hungry Stay Foolish", "Stay Hungry Stay Thirsty") == 0.25
    # Empty reference
    assert compute_wer("", "") == 0.0
    assert compute_wer("", "test") == 1.0


def test_compute_cer() -> None:
    # Exact match
    assert compute_cer("Apple Computer", "Apple Computer") == 0.0
    # Case insensitivity & whitespace ignoring
    assert compute_cer("apple   computer", "Apple Computer") == 0.0
    # 1 character typo out of 9 characters
    assert abs(compute_cer("Macintosh", "Macintosn") - (1 / 9)) < 1e-4
