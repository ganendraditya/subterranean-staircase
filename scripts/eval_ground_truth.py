#!/usr/bin/env python3
"""Ground Truth Benchmark & Evaluation Tool for Subtitle OCR and Translation.

Calculates Word Error Rate (WER) and Character Error Rate (CER) by comparing
OCR stabilized detections against official ground truth transcripts (e.g. YouTube).
Uses timestamp-aware alignment to prevent spurious/oracle matching across video time.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
import re
from typing import List, Optional, Tuple


def levenshtein_distance(seq1: List[str] | str, seq2: List[str] | str) -> int:
    """Calculate edit distance between two sequences (words or characters)."""
    n, m = len(seq1), len(seq2)
    if n == 0:
        return m
    if m == 0:
        return n

    current = list(range(m + 1))
    for i in range(1, n + 1):
        previous, current = current, [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            current[j] = min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost  # substitution
            )
    return current[m]


def compute_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate (WER = edit_distance / ref_words)."""
    ref_words = re.findall(r"\w+", reference.lower())
    hyp_words = re.findall(r"\w+", hypothesis.lower())
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return dist / len(ref_words)


def compute_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate (CER = edit_distance / ref_chars)."""
    ref_chars = re.sub(r"\s+", "", reference.lower())
    hyp_chars = re.sub(r"\s+", "", hypothesis.lower())
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    dist = levenshtein_distance(ref_chars, hyp_chars)
    return dist / len(ref_chars)


def fetch_youtube_ground_truth(video_id: str) -> List[Tuple[float, float, str]]:
    """Fetch official ground-truth captions from YouTube supporting both v0.x dict and v1.x object APIs."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            raw_entries = YouTubeTranscriptApi.get_transcript(video_id)
        else:
            raw_entries = YouTubeTranscriptApi().fetch(video_id)

        entries = []
        for item in raw_entries:
            text = item.text if hasattr(item, "text") else item.get("text", "")
            start = float(item.start if hasattr(item, "start") else item.get("start", 0.0))
            dur = float(item.duration if hasattr(item, "duration") else item.get("duration", 0.0))
            clean_text = text.replace("\n", " ").strip()
            entries.append((start, start + dur, clean_text))
        return entries
    except Exception as e:
        print(f"Error fetching YouTube transcript: {e}")
        return []


def parse_log_timestamp(ts_str: str) -> float:
    """Parse log timestamp 'YYYY-MM-DD HH:MM:SS,mmm' to POSIX epoch float."""
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
    return dt.timestamp()


def evaluate_log_against_ground_truth(
    log_path: str,
    video_id: str = "UF8uR6Z6KLc",
    max_time_window_sec: float = 6.0,
) -> None:
    """Parse audit session log and evaluate precision against YouTube ground truth."""
    if not os.path.isfile(log_path):
        print(f"Log file not found: {log_path}")
        return

    print(f"Fetching Ground Truth transcript for YouTube [{video_id}]...")
    gt_entries = fetch_youtube_ground_truth(video_id)
    if not gt_entries:
        print("Failed to retrieve ground truth captions.")
        return

    print(f"✔ Retrieved {len(gt_entries)} ground truth subtitle snippets.")

    with open(log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    stable_matches_raw = re.findall(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[AUDIT-STABLE\] Sentence stabilized: (['\"])(.*?)\2",
        log_content,
    )

    if not stable_matches_raw:
        print("No [AUDIT-STABLE] lines found in log.")
        return

    print(f"✔ Found {len(stable_matches_raw)} OCR stabilized sentences in log.")

    # Parse timestamps for OCR events
    ocr_events: List[Tuple[float, str]] = []
    for ts_str, _, text in stable_matches_raw:
        try:
            t = parse_log_timestamp(ts_str)
            ocr_events.append((t, text))
        except ValueError:
            continue

    if not ocr_events:
        print("Could not parse OCR event timestamps.")
        return

    # Calibrate time offset between log epoch and YouTube video timeline
    # We find the best time offset T_0 such that log_t - T_0 aligns with gt_start
    # using the first few high-confidence anchors
    base_log_time = ocr_events[0][0]
    best_offset = base_log_time - gt_entries[0][0]
    
    # Try finding the lowest-WER anchor match in first 15 entries to lock video sync
    anchor_candidates = []
    for log_t, ocr_txt in ocr_events[:15]:
        for gt_s, gt_e, gt_txt in gt_entries[:15]:
            wer = compute_wer(gt_txt, ocr_txt)
            if wer < 0.15:
                anchor_candidates.append((wer, log_t - gt_s))
    if anchor_candidates:
        _, best_offset = min(anchor_candidates, key=lambda x: x[0])

    wers: List[float] = []
    cers: List[float] = []
    matched_count = 0

    print("=" * 80)
    print(f"{'#':<4} {'WER':<8} {'CER':<8} {'Ground Truth':<30} ➔ {'OCR Detected'}")
    print("=" * 80)

    used_ocr_indices = set()
    for gt_start, gt_end, gt_text in gt_entries:
        if len(gt_text) < 4:
            continue

        target_time = best_offset + gt_start

        # Search candidates strictly within temporal window [target_time - win, target_time + win]
        best_wer = float("inf")
        best_idx: Optional[int] = None
        best_ocr: Optional[str] = None
        for i, (log_t, ocr_text) in enumerate(ocr_events):
            if i in used_ocr_indices:
                continue
            if abs(log_t - target_time) <= max_time_window_sec:
                wer = compute_wer(gt_text, ocr_text)
                if wer < best_wer:
                    best_wer = wer
                    best_ocr = ocr_text
                    best_idx = i

        if best_ocr is not None and best_wer < 0.8:
            used_ocr_indices.add(best_idx)
            cer = compute_cer(gt_text, best_ocr)
            wers.append(best_wer)
            cers.append(cer)
            matched_count += 1
            if matched_count <= 20:
                gt_snippet = (gt_text[:28] + "..") if len(gt_text) > 30 else gt_text
                ocr_snippet = (best_ocr[:38] + "..") if len(best_ocr) > 40 else best_ocr
                print(f"{matched_count:<4} {best_wer*100:5.1f}%  {cer*100:5.1f}%  {gt_snippet:<30} ➔ {ocr_snippet}")

    if wers:
        avg_wer = (sum(wers) / len(wers)) * 100.0
        avg_cer = (sum(cers) / len(cers)) * 100.0
        print("=" * 80)
        print(f"Summary Temporal Evaluation ({matched_count} aligned sentences in time window ±{max_time_window_sec}s):")
        print(f"  • Mean Word Error Rate (WER)     : {avg_wer:.2f}% (Accuracy: {100.0 - avg_wer:.2f}%)")
        print(f"  • Mean Character Error Rate (CER): {avg_cer:.2f}% (Accuracy: {100.0 - avg_cer:.2f}%)")
        print("=" * 80)
    else:
        print("No sentences could be temporally aligned within the time window.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Subtitle OCR against Ground Truth")
    parser.add_argument("--video-id", default="UF8uR6Z6KLc", help="YouTube video ID (default: Steve Jobs 2005)")
    parser.add_argument("--log", default="audit_session.log", help="Path to audit session log")
    parser.add_argument("--window", type=float, default=6.0, help="Temporal window in seconds (default: 6.0s)")
    args = parser.parse_args()

    evaluate_log_against_ground_truth(args.log, args.video_id, max_time_window_sec=args.window)


if __name__ == "__main__":
    main()
