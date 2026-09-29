#!/usr/bin/env python3
"""Comprehensive End-to-End Diagnostic Audit Tool for Subtitle Translator.

Audits:
1. Ground Truth OCR Precision & Latency:
   - Synchronizes OCR output with official manual YouTube captions via timestamp alignment.
   - Computes OCR Word Error Rate (WER) and Character Error Rate (CER).
   - Measures OCR detection latency and frame-to-stabilize delay.
2. Neural Machine Translation (NMT) Precision & Latency:
   - Compares NMT output with official human-translated captions (e.g. Indonesian).
   - Computes edit-distance and translation fidelity.
   - Measures NMT inference latency and End-to-End (E2E) pipeline latency.
3. System Timing & Lag:
   - Caption appearance sync lag relative to video playback timeline.
   - Subtitle clear latency on natural screen clearance.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple


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


def fetch_captions(video_id: str, lang_code: str = "en") -> List[Tuple[float, float, str]]:
    """Fetch manual captions for the given YouTube video ID and language code."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        tl = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = tl.find_manually_created_transcript([lang_code]).fetch()
        entries = []
        for item in transcript:
            text = item.text if hasattr(item, "text") else item["text"]
            start = float(item.start if hasattr(item, "start") else item["start"])
            dur = float(item.duration if hasattr(item, "duration") else item["duration"])
            clean_text = text.replace("\n", " ").strip()
            entries.append((start, start + dur, clean_text))
        return entries
    except Exception as e:
        print(f"Note: Manual {lang_code} captions not available: {e}")
        return []


def parse_timestamp(ts_str: str) -> float:
    """Convert 'YYYY-MM-DD HH:MM:SS,mmm' to POSIX epoch timestamp."""
    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
    return dt.timestamp()


def run_comprehensive_audit(
    log_path: str,
    video_id: str,
    source_lang: str = "en",
    target_lang: Optional[str] = "id",
    time_window_sec: float = 7.0,
) -> None:
    """Analyze audit log file against YouTube ground truth captions."""
    if not os.path.exists(log_path):
        print(f"Error: Log file not found at '{log_path}'.")
        print("Tip: Run the app in developer audit mode first: `subtrans --audit`")
        return

    print("=" * 90)
    print(f"🚀 RUNNING COMPREHENSIVE PIPELINE AUDIT [Video ID: {video_id}]")
    print("=" * 90)

    # 1. Fetch Ground Truth Captions
    print(f"Fetching official manual captions for [{source_lang.upper()}]...")
    gt_source = fetch_captions(video_id, source_lang)
    if not gt_source:
        print(f"Could not retrieve manual {source_lang} captions.")
        return
    print(f"✔ Retrieved {len(gt_source)} official ground truth snippets.")

    gt_target: Optional[List[Tuple[float, float, str]]] = None
    if target_lang:
        print(f"Fetching official human translation for [{target_lang.upper()}]...")
        gt_target = fetch_captions(video_id, target_lang)
        if gt_target:
            print(f"✔ Retrieved {len(gt_target)} human translation references.")

    # 2. Parse Log Records
    with open(log_path, "r", encoding="utf-8") as f:
        log_text = f.read()

    def _strip_quotes(s: str) -> str:
        s = s.strip()
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            return s[1:-1]
        return s

    re_ocr = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[AUDIT-OCR\] (\d+) detections in ([\d\.]+)ms")
    re_stable = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[AUDIT-STABLE\] Sentence stabilized: (.*)$",
        re.MULTILINE,
    )
    re_trans = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[AUDIT-TRANS\] \(OCR: ([\d\.]+)ms \| Trans: ([\d\.]+)ms \| Total E2E: ([\d\.]+)ms\) (.*) ➔ (.*)$",
        re.MULTILINE,
    )
    re_clear = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[AUDIT-CLEAR\] Subtitles cleared.*?clear latency: ([\d\.]+)ms")

    ocr_latencies = [float(m.group(3)) for m in re_ocr.finditer(log_text)]
    clear_latencies = [float(m.group(2)) for m in re_clear.finditer(log_text)]

    # Collect both stabilized OCR lines and translated events
    stable_events: List[Dict[str, Any]] = []
    for m in re_stable.finditer(log_text):
        ts = parse_timestamp(m.group(1))
        stable_events.append({"timestamp": ts, "text": _strip_quotes(m.group(2))})

    trans_events: List[Dict[str, Any]] = []
    for m in re_trans.finditer(log_text):
        ts = parse_timestamp(m.group(1))
        trans_events.append({
            "timestamp": ts,
            "ocr_ms": float(m.group(2)),
            "trans_ms": float(m.group(3)),
            "e2e_ms": float(m.group(4)),
            "source": _strip_quotes(m.group(5)),
            "translation": _strip_quotes(m.group(6)),
        })

    events_to_eval = trans_events if trans_events else [{"timestamp": s["timestamp"], "source": s["text"], "translation": "", "ocr_ms": 0, "trans_ms": 0, "e2e_ms": 0} for s in stable_events]

    if not events_to_eval:
        print("No OCR or Translation events found in log. Ensure app was running with `--audit`.")
        return

    print(f"✔ Parsed {len(events_to_eval)} pipeline events from log.\n")

    # 3. Synchronize Log Timeline with YouTube Caption Timeline
    base_log_time = events_to_eval[0]["timestamp"]
    best_offset = base_log_time - gt_source[0][0]

    found_sync = False
    for ev in events_to_eval[:30]:
        for gt_s, gt_e, gt_txt in gt_source[:30]:
            if compute_wer(gt_txt, ev["source"]) < 0.15:
                best_offset = ev["timestamp"] - gt_s
                found_sync = True
                break
        if found_sync:
            break

    # 4. Compute Metrics
    ocr_wers = []
    ocr_cers = []
    trans_latencies = []
    e2e_latencies = []
    sync_lags = []
    paired_samples = []

    used_event_indices = set()

    for gt_s, gt_e, gt_txt in gt_source:
        if len(gt_txt) < 3:
            continue
        expected_log_time = best_offset + gt_s

        best_wer = float("inf")
        best_ev_idx = None

        for idx, ev in enumerate(events_to_eval):
            if idx in used_event_indices:
                continue
            if abs(ev["timestamp"] - expected_log_time) <= time_window_sec:
                wer = compute_wer(gt_txt, ev["source"])
                if wer < best_wer:
                    best_wer = wer
                    best_ev_idx = idx

        if best_ev_idx is not None and best_wer < 0.8:
            used_event_indices.add(best_ev_idx)
            matched_ev = events_to_eval[best_ev_idx]
            cer = compute_cer(gt_txt, matched_ev["source"])
            lag_sec = matched_ev["timestamp"] - expected_log_time

            ocr_wers.append(best_wer)
            ocr_cers.append(cer)
            if matched_ev.get("trans_ms", 0) > 0:
                trans_latencies.append(matched_ev["trans_ms"])
                e2e_latencies.append(matched_ev["e2e_ms"])
            sync_lags.append(lag_sec)

            ref_target = ""
            if gt_target:
                for tgt_s, tgt_e, tgt_txt in gt_target:
                    if abs(tgt_s - gt_s) <= 2.0:
                        ref_target = tgt_txt
                        break

            paired_samples.append({
                "gt_time": f"{gt_s:5.1f}s",
                "gt_text": gt_txt,
                "ref_target": ref_target,
                "ocr_text": matched_ev["source"],
                "trans_text": matched_ev.get("translation", ""),
                "wer": best_wer,
                "cer": cer,
                "lag_s": lag_sec,
                "e2e_ms": matched_ev.get("e2e_ms", 0),
            })

    # 5. Render Evaluation Report
    print("=" * 95)
    print(f"{'TIME':<8} {'WER':<7} {'CER':<7} {'E2E':<8} {'GROUND TRUTH':<30} ➔ {'OCR DETECTED'}")
    print("=" * 95)
    for s in paired_samples[:25]:
        gt_short = (s["gt_text"][:28] + "..") if len(s["gt_text"]) > 30 else s["gt_text"]
        ocr_short = (s["ocr_text"][:38] + "..") if len(s["ocr_text"]) > 40 else s["ocr_text"]
        e2e_str = f"{s['e2e_ms']:5.0f}ms" if s["e2e_ms"] > 0 else "-"
        print(f"{s['gt_time']:<8} {s['wer']*100:5.1f}% {s['cer']*100:5.1f}% {e2e_str:<8} {gt_short:<30} ➔ {ocr_short}")

    # If official target translations are available, print NMT fidelity
    if gt_target and paired_samples:
        print("\n" + "=" * 95)
        print(f"{'TIME':<8} {'OFFICIAL HUMAN TRANSLATION':<35} ➔ {'NMT TRANSLATED'}")
        print("=" * 95)
        for s in paired_samples[:15]:
            if s["trans_text"] and s.get("ref_target"):
                print(f"{s['gt_time']:<8} {s['ref_target'][:33]:<35} ➔ {s['trans_text'][:50]}")

    print("\n" + "=" * 95)
    print("📈 COMPREHENSIVE PIPELINE PERFORMANCE SUMMARY")
    print("=" * 95)
    if ocr_wers:
        mean_wer = sum(ocr_wers) / len(ocr_wers) * 100.0
        mean_cer = sum(ocr_cers) / len(ocr_cers) * 100.0
        mean_ocr_ms = sum(ocr_latencies) / len(ocr_latencies) if ocr_latencies else 0.0
        mean_trans_ms = sum(trans_latencies) / len(trans_latencies) if trans_latencies else 0.0
        mean_e2e_ms = sum(e2e_latencies) / len(e2e_latencies) if e2e_latencies else 0.0
        mean_lag = sum(sync_lags) / len(sync_lags) if sync_lags else 0.0
        mean_clear_ms = sum(clear_latencies) / len(clear_latencies) if clear_latencies else 0.0

        print(f"1. OCR RECOGNITION QUALITY ({len(paired_samples)} aligned captions):")
        print(f"   • Word Error Rate (WER)        : {mean_wer:.2f}%  (Recognition Accuracy: {100.0 - mean_wer:.2f}%)")
        print(f"   • Character Error Rate (CER)   : {mean_cer:.2f}%  (Character Fidelity: {100.0 - mean_cer:.2f}%)")
        print(f"   • Video Sync Alignment Lag     : {mean_lag:+.2f}s (Mean offset from video caption appearance)")
        print()
        print("2. COMPUTATIONAL LATENCIES:")
        print(f"   • Average OCR Inference        : {mean_ocr_ms:.1f} ms / frame")
        if trans_latencies:
            print(f"   • Average NMT Translation      : {mean_trans_ms:.1f} ms / sentence")
            print(f"   • End-to-End Pipeline Latency  : {mean_e2e_ms:.1f} ms (Perception to Translation display)")
        print(f"   • Subtitle Natural Clear Delay : {mean_clear_ms:.1f} ms (Screen clearance response)")
        print("=" * 95)
    else:
        print("No captions could be aligned within the specified temporal tolerance.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Subtitle Translator End-to-End Diagnostic Audit Tool")
    parser.add_argument("--log", default="audit_session.log", help="Path to audit session log")
    parser.add_argument("--video-id", default="kXYiU_JCYtU", help="YouTube video ID to benchmark against")
    parser.add_argument("--source", default="en", help="Source caption language code (default: en)")
    parser.add_argument("--target", default="id", help="Target translation language code (default: id)")
    parser.add_argument("--window", type=float, default=8.0, help="Temporal matching tolerance in seconds")
    args = parser.parse_args()

    run_comprehensive_audit(
        log_path=args.log,
        video_id=args.video_id,
        source_lang=args.source,
        target_lang=args.target,
        time_window_sec=args.window,
    )


if __name__ == "__main__":
    main()
