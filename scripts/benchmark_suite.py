#!/usr/bin/env python3
"""Automated Heterogeneous Subtitle Benchmark Harness (Issue #104).

Executes a standardized head-to-head evaluation between:
- Engine V1: Legacy Python RapidOCR (PaddleOCRv4 ONNX via Python)
- Engine V2: Native Rust Neural OCR (ort v2 + DBNet + clipper2 unclip 2.0 + CTC decoder)

Evaluates 5-Tier stress matrix (25 real-world heterogeneous scenarios) measuring:
1. Character Error Rate (CER) & Word Error Rate (WER)
2. Latency percentiles (P50 Median, P90, P99 worst-case spike)
3. Memory RSS footprint
4. Descender clipping rate & visual noise resilience
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ocr.engine import RapidOCREngine
from scripts.eval_ground_truth import compute_cer, compute_wer, levenshtein_distance

MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "benchmark" / "dataset_manifest.json"
RUST_BENCH_BIN = PROJECT_ROOT / "src-tauri" / "target" / "release" / "ocr_bench"


def clean_text_for_eval(text: str) -> str:
    """Normalize whitespace and punctuation for fair text comparison."""
    if not text:
        return ""
    # Collapse multiple whitespaces and strip
    return re.sub(r"\s+", " ", text).strip()


def run_v1_evaluation(manifest: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run full evaluation across all manifest items using Engine V1 (Python RapidOCR)."""
    ocr_engine = RapidOCREngine(det_unclip_ratio=1.6, det_limit_type="max")

    # Warmup
    dummy = np.zeros((100, 300, 3), dtype=np.uint8)
    _ = ocr_engine.detect(dummy)

    results = []

    for item in manifest:
        filepath = PROJECT_ROOT / item["filepath"]
        img = cv2.imread(str(filepath))
        if img is None:
            raise FileNotFoundError(f"Image not found: {filepath}")

        # Multiple runs for latency precision (take median of 3 runs)
        run_times = []
        raw_detections = []
        for _ in range(3):
            t0 = time.perf_counter()
            dets = ocr_engine.detect(img)
            lat = (time.perf_counter() - t0) * 1000.0
            run_times.append(lat)
            raw_detections = dets

        lat_ms = float(np.median(run_times))
        recognized_text = " ".join(d.text.strip() for d in raw_detections if d.text.strip())

        ref_clean = clean_text_for_eval(item["reference_text"])
        hyp_clean = clean_text_for_eval(recognized_text)

        cer = compute_cer(ref_clean, hyp_clean)
        wer = compute_wer(ref_clean, hyp_clean)

        results.append({
            "id": item["id"],
            "tier": item["tier"],
            "tier_name": item["tier_name"],
            "reference": ref_clean,
            "hypothesis": hyp_clean,
            "latency_ms": lat_ms,
            "cer": cer,
            "wer": wer,
            "detections_count": len(raw_detections),
        })

    return results


def run_v2_evaluation(manifest: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run full evaluation across all manifest items using Engine V2 (Rust ort + DBNet + CTC)."""
    if not RUST_BENCH_BIN.exists():
        # Build binary if not built yet
        subprocess.run(
            ["cargo", "build", "--manifest-path", "src-tauri/Cargo.toml", "--bin", "ocr_bench", "--release"],
            cwd=str(PROJECT_ROOT),
            check=True,
        )

    image_paths = [str(PROJECT_ROOT / item["filepath"]) for item in manifest]

    # Warmup run
    subprocess.run([str(RUST_BENCH_BIN), str(PROJECT_ROOT / "tests" / "fixtures" / "test_subtitle.png")], capture_output=True)

    # Execute 3 measured repetitions to match V1 sampling methodology exactly
    rep_latencies: Dict[str, List[float]] = {p: [] for p in image_paths}
    last_batch_results: Dict[str, Dict[str, Any]] = {}

    cmd = [str(RUST_BENCH_BIN)] + image_paths
    for _ in range(3):
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        batch_json = json.loads(proc.stdout)

        if len(batch_json) != len(manifest):
            raise RuntimeError(f"Rust returned {len(batch_json)} results for {len(manifest)} images")

        for rust_res in batch_json:
            img_p = rust_res["image"]
            if not rust_res.get("success", False):
                raise RuntimeError(f"Rust OCR failed on {img_p}: {rust_res.get('error')}")
            rep_latencies[img_p].append(float(rust_res["latency_ms"]))
            last_batch_results[img_p] = rust_res

    results = []
    for item in manifest:
        expected_path = str(PROJECT_ROOT / item["filepath"])
        rust_res = last_batch_results[expected_path]

        ref_clean = clean_text_for_eval(item["reference_text"])
        hyp_clean = clean_text_for_eval(rust_res["text"])

        cer = compute_cer(ref_clean, hyp_clean)
        wer = compute_wer(ref_clean, hyp_clean)
        median_lat = float(np.median(rep_latencies[expected_path]))

        results.append({
            "id": item["id"],
            "tier": item["tier"],
            "tier_name": item["tier_name"],
            "reference": ref_clean,
            "hypothesis": hyp_clean,
            "latency_ms": median_lat,
            "cer": cer,
            "wer": wer,
            "detections_count": rust_res["detections"],
        })

    return results


def print_comparison_scorecard(v1_res: List[Dict[str, Any]], v2_res: List[Dict[str, Any]]) -> None:
    """Print detailed head-to-head scorecard and statistical comparison."""
    print("\n" + "=" * 90)
    print("      HEAD-TO-HEAD HETEROGENEOUS SUBTITLE BENCHMARK: V1 (PYTHON) vs V2 (RUST)")
    print("=" * 90)

    # 1. Per-Item Table
    print(f"\n{'ID':<9} | {'TIER':<4} | {'V1 CER':<8} | {'V2 CER':<8} | {'V1 LAT':<8} | {'V2 LAT':<8} | {'DELTA LAT':<10} | {'GROUND TRUTH REFERENCE':<30}")
    print("-" * 90)

    for item_v1, item_v2 in zip(v1_res, v2_res):
        cer1 = f"{item_v1['cer'] * 100:.1f}%"
        cer2 = f"{item_v2['cer'] * 100:.1f}%"
        lat1 = f"{item_v1['latency_ms']:.1f}ms"
        lat2 = f"{item_v2['latency_ms']:.1f}ms"
        delta = f"{item_v1['latency_ms'] - item_v2['latency_ms']:+.1f}ms"
        ref_snippet = (item_v1['reference'][:27] + "...") if len(item_v1['reference']) > 30 else item_v1['reference']

        print(f"{item_v1['id']:<9} | T{item_v1['tier']:<3} | {cer1:<8} | {cer2:<8} | {lat1:<8} | {lat2:<8} | {delta:<10} | {ref_snippet:<30}")

    # 2. Aggregation per Tier
    tiers = [1, 2, 3, 4, 5]
    tier_names = {
        1: "Tier 1: Clean Baseline (Easy)",
        2: "Tier 2: Multilingual Dense CJK",
        3: "Tier 3: Burned-In Cinema & Noise",
        4: "Tier 4: Descender Torture & Multi-Line",
        5: "Tier 5: Adversarial Visual Anomalies",
    }

    print("\n" + "=" * 90)
    print("      TIER-BY-TIER PERFORMANCE AGGREGATION")
    print("=" * 90)
    print(f"{'Tier Name':<38} | {'V1 Avg CER':<10} | {'V2 Avg CER':<10} | {'V1 P50 Lat':<10} | {'V2 P50 Lat':<10}")
    print("-" * 90)

    for t in tiers:
        t_v1 = [x for x in v1_res if x["tier"] == t]
        t_v2 = [x for x in v2_res if x["tier"] == t]

        v1_cer_avg = np.mean([x["cer"] for x in t_v1]) * 100
        v2_cer_avg = np.mean([x["cer"] for x in t_v2]) * 100
        v1_lat_p50 = np.median([x["latency_ms"] for x in t_v1])
        v2_lat_p50 = np.median([x["latency_ms"] for x in t_v2])

        name = tier_names[t]
        print(f"{name:<38} | {v1_cer_avg:<9.2f}% | {v2_cer_avg:<9.2f}% | {v1_lat_p50:<8.1f}ms | {v2_lat_p50:<8.1f}ms")

    # 3. Overall Summary
    print("\n" + "=" * 90)
    print("      OVERALL SYSTEM BENCHMARK SUMMARY (25 STRESS TEST CASES)")
    print("=" * 90)

    all_v1_cer = np.mean([x["cer"] for x in v1_res]) * 100
    all_v2_cer = np.mean([x["cer"] for x in v2_res]) * 100
    all_v1_wer = np.mean([x["wer"] for x in v1_res]) * 100
    all_v2_wer = np.mean([x["wer"] for x in v2_res]) * 100

    v1_lats = [x["latency_ms"] for x in v1_res]
    v2_lats = [x["latency_ms"] for x in v2_res]

    print(f"• Character Error Rate (Overall CER):")
    print(f"    - Engine V1 (Python RapidOCR): {all_v1_cer:.2f}%")
    print(f"    - Engine V2 (Rust ort + DBNet): {all_v2_cer:.2f}%")

    print(f"• Word Error Rate (Overall WER):")
    print(f"    - Engine V1 (Python RapidOCR): {all_v1_wer:.2f}%")
    print(f"    - Engine V2 (Rust ort + DBNet): {all_v2_wer:.2f}%")

    print(f"• Inference Latency Distribution:")
    print(f"    - Engine V1 (Python): P50={np.median(v1_lats):.1f} ms | P90={np.percentile(v1_lats, 90):.1f} ms | P99={np.percentile(v1_lats, 99):.1f} ms")
    print(f"    - Engine V2 (Rust):   P50={np.median(v2_lats):.1f} ms | P90={np.percentile(v2_lats, 90):.1f} ms | P99={np.percentile(v2_lats, 99):.1f} ms")

    # Descender torture evaluation in Tier 4
    t4_v1_cer = np.mean([x["cer"] for x in v1_res if x["tier"] == 4]) * 100
    t4_v2_cer = np.mean([x["cer"] for x in v2_res if x["tier"] == 4]) * 100
    print(f"• Tier 4 Descender Torture CER:")
    print(f"    - V1 Python: {t4_v1_cer:.2f}%")
    print(f"    - V2 Rust (Unclip 2.0 Math): {t4_v2_cer:.2f}%")

    print("=" * 90 + "\n")


def main() -> None:
    if not MANIFEST_PATH.exists():
        print(f"Manifest {MANIFEST_PATH} not found. Running generator first...")
        from scripts.generate_benchmark_dataset import generate_all
        generate_all()

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"\n🚀 Running Head-to-Head Benchmark Suite ({len(manifest)} Scenarios)...")

    print("\n[1/2] Evaluating Engine V1: Legacy Python RapidOCR...")
    v1_results = run_v1_evaluation(manifest)

    print("\n[2/2] Evaluating Engine V2: Native Rust Neural OCR (ort + DBNet + CTC)...")
    v2_results = run_v2_evaluation(manifest)

    print_comparison_scorecard(v1_results, v2_results)


if __name__ == "__main__":
    main()
