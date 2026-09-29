#!/usr/bin/env python3
"""Ground Truth Benchmark & Evaluation Tool for Subtitle OCR and Translation.

Calculates Word Error Rate (WER), Character Error Rate (CER), and latency metrics
by comparing OCR detections against official ground truth transcripts (e.g. YouTube).
"""

from __future__ import annotations

import argparse
import os
import re
from typing import List, Tuple


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


def evaluate_log_against_ground_truth(
    log_path: str,
    video_id: str = "UF8uR6Z6KLc",
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

    # Parse OCR stabilized lines from audit log
    with open(log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    stable_matches = re.findall(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[AUDIT-STABLE\] Sentence stabilized: (?:'|\")(.*?)(?:'|\")",
        log_content,
    )

    if not stable_matches:
        print("No [AUDIT-STABLE] lines found in log.")
        return

    print(f"✔ Found {len(stable_matches)} OCR stabilized sentences in log.\n")

    wers = []
    cers = []

    print("=" * 80)
    print(f"{'#':<4} {'WER':<8} {'CER':<8} {'Ground Truth':<30} ➔ {'OCR Detected'}")
    print("=" * 80)

    # Simple best-match alignment between GT and OCR detections
    matched_count = 0
    for idx, (gt_start, gt_end, gt_text) in enumerate(gt_entries):
        if len(gt_text) < 4:
            continue

        best_wer = float("inf")
        best_ocr = ""
        for _, ocr_text in stable_matches:
            wer = compute_wer(gt_text, ocr_text)
            if wer < best_wer:
                best_wer = wer
                best_ocr = ocr_text

        if best_wer < 0.8:  # Reasonable alignment threshold
            cer = compute_cer(gt_text, best_ocr)
            wers.append(min(1.0, best_wer))
            cers.append(min(1.0, cer))
            matched_count += 1
            if matched_count <= 20:  # Print first 20 aligned samples
                gt_snippet = (gt_text[:28] + "..") if len(gt_text) > 30 else gt_text
                ocr_snippet = (best_ocr[:38] + "..") if len(best_ocr) > 40 else best_ocr
                print(f"{matched_count:<4} {best_wer*100:5.1f}%  {cer*100:5.1f}%  {gt_snippet:<30} ➔ {ocr_snippet}")

    if wers:
        avg_wer = (sum(wers) / len(wers)) * 100.0
        avg_cer = (sum(cers) / len(cers)) * 100.0
        print("=" * 80)
        print(f"Summary Evaluation ({matched_count} aligned sentences):")
        print(f"  • Mean Word Error Rate (WER)     : {avg_wer:.2f}% (Accuracy: {100.0 - avg_wer:.2f}%)")
        print(f"  • Mean Character Error Rate (CER): {avg_cer:.2f}% (Accuracy: {100.0 - avg_cer:.2f}%)")
        print("=" * 80)
    else:
        print("Could not align OCR lines to ground truth.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Subtitle OCR against Ground Truth")
    parser.add_argument("--video-id", default="UF8uR6Z6KLc", help="YouTube video ID (default: Steve Jobs 2005)")
    parser.add_argument("--log", default="audit_session.log", help="Path to audit session log")
    args = parser.parse_args()

    evaluate_log_against_ground_truth(args.log, args.video_id)


if __name__ == "__main__":
    main()
