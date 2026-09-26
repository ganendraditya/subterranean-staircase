"""Unit tests and benchmarks for FrameDiffDetector."""

import time
import numpy as np
import pytest

from core.vision.diff import FrameDiffDetector


def test_frame_diff_first_frame() -> None:
    detector = FrameDiffDetector()
    frame1 = np.zeros((1080, 1920, 3), dtype=np.uint8)

    # First frame must always evaluate to changed (diff = 1.0)
    assert detector.calculate_diff(frame1) == 1.0


def test_frame_diff_identical_frames() -> None:
    detector = FrameDiffDetector()
    frame = np.ones((720, 1280, 3), dtype=np.uint8) * 128

    detector.calculate_diff(frame)
    # Consecutive identical frame must yield 0.0 difference
    diff = detector.calculate_diff(frame)
    assert diff == 0.0
    assert not detector.has_changed(frame)


def test_frame_diff_dynamic_content() -> None:
    detector = FrameDiffDetector(default_threshold=0.015)
    black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detector.calculate_diff(black_frame)

    # Introduce a new subtitle (white box in lower region)
    sub_frame = black_frame.copy()
    sub_frame[500:650, 200:1080] = 255

    # has_changed should be True comparing against the black_frame
    assert detector.has_changed(sub_frame)
    # Subsequent call with the exact same sub_frame should be False
    assert not detector.has_changed(sub_frame)


def test_frame_diff_reset() -> None:
    detector = FrameDiffDetector()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    detector.calculate_diff(frame)
    detector.reset()

    # After reset, first frame must again return 1.0
    assert detector.calculate_diff(frame) == 1.0


def test_frame_diff_execution_speed_benchmark() -> None:
    detector = FrameDiffDetector()
    frame_a = np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
    frame_b = np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)

    detector.calculate_diff(frame_a)

    # Measure execution time across 50 iterations
    start = time.perf_counter()
    iterations = 50
    for _ in range(iterations):
        detector.calculate_diff(frame_b)
    elapsed_total = time.perf_counter() - start

    avg_ms = (elapsed_total / iterations) * 1000.0
    # Must be under 2ms per 1080p frame (typically 0.2ms - 0.6ms on Apple Silicon)
    assert avg_ms < 2.0, f"Frame diff is too slow: {avg_ms:.3f} ms"
