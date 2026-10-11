"""Unit tests verifying the 5-tier benchmark dataset and manifest integrity (Issue #104)."""

import json
from pathlib import Path
import pytest

MANIFEST_PATH = Path(__file__).resolve().parent / "fixtures" / "benchmark" / "dataset_manifest.json"


def test_benchmark_manifest_integrity() -> None:
    assert MANIFEST_PATH.is_file(), "dataset_manifest.json must exist"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert len(manifest) == 25, f"Expected exactly 25 benchmark scenarios, got {len(manifest)}"

    # Check 5 tiers are represented evenly
    tier_counts = {}
    for item in manifest:
        t = item["tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1
        img_path = Path(__file__).resolve().parent.parent / item["filepath"]
        assert img_path.is_file(), f"Benchmark frame {item['filepath']} must exist on disk"
        assert len(item["reference_text"]) > 0

    assert tier_counts[1] == 5
    assert tier_counts[2] == 5
    assert tier_counts[3] == 5
    assert tier_counts[4] == 5
    assert tier_counts[5] == 5
