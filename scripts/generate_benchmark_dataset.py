#!/usr/bin/env python3
"""Synthetic Heterogeneous Subtitle Benchmark Dataset Generator (Issue #104).

Generates a standardized 5-Tier stress testbed with ground-truth transcripts:
- Tier 1: Clean Baseline (English / Indonesian, high contrast, clean background)
- Tier 2: Multilingual & Dense CJK (Japanese Kanji/Kana, Chinese Hanzi, Korean Hangul)
- Tier 3: Burned-In Cinema & Dynamic Noise (Yellow font #FDE047, italics, high-key bright/snow scene)
- Tier 4: Descender Torture & Spatial Multi-line (Letters g/y/p/q/j touching bottom, multi-line)
- Tier 5: Adversarial Visual Anomalies (Semi-transparent 50% alpha, tilted rotation, small font)
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import random
from typing import Any, Dict, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "tests" / "fixtures" / "benchmark"

# System font paths on macOS
FONT_CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_HANGUL = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT_LATIN = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_LATIN_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_LATIN_ITALIC = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"


def get_font(font_type: str, size: int) -> ImageFont.FreeTypeFont:
    if font_type == "cjk" and os.path.exists(FONT_CJK):
        return ImageFont.truetype(FONT_CJK, size)
    if font_type == "hangul" and os.path.exists(FONT_HANGUL):
        return ImageFont.truetype(FONT_HANGUL, size)
    if font_type == "italic" and os.path.exists(FONT_LATIN_ITALIC):
        return ImageFont.truetype(FONT_LATIN_ITALIC, size)
    if font_type == "bold" and os.path.exists(FONT_LATIN_BOLD):
        return ImageFont.truetype(FONT_LATIN_BOLD, size)
    if os.path.exists(FONT_LATIN):
        return ImageFont.truetype(FONT_LATIN, size)
    return ImageFont.load_default()


def create_base_canvas(width: int = 1280, height: int = 720, bg_type: str = "dark") -> Image.Image:
    if bg_type == "dark":
        # Dark movie background
        arr = np.full((height, width, 3), 24, dtype=np.uint8)
        # Add subtle natural gradient
        gradient = np.linspace(20, 35, height, dtype=np.uint8).reshape(-1, 1, 1)
        arr = np.clip(arr + gradient, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "RGB")
    elif bg_type == "bright_snow":
        # High-key bright video scene (snow / sky glare)
        arr = np.full((height, width, 3), 215, dtype=np.uint8)
        # Noise texture
        np.random.seed(42)
        noise = np.random.randint(-15, 15, (height, width, 3), dtype=np.int16)
        arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "RGB")
    elif bg_type == "explosion":
        # Dynamic colored background (orange-yellow video scene)
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        arr[:, :, 0] = 160  # Red
        arr[:, :, 1] = 90   # Green
        arr[:, :, 2] = 30   # Blue
        return Image.fromarray(arr, "RGB")
    else:
        return Image.new("RGB", (width, height), (30, 30, 30))


def render_subtitle_frame(
    lines: List[str],
    font_type: str = "latin",
    font_size: int = 36,
    text_color: tuple = (255, 255, 255),
    outline_color: tuple = (0, 0, 0),
    outline_width: int = 2,
    bg_type: str = "dark",
    y_anchor: str = "bottom",
    opacity: float = 1.0,
    rotation_deg: float = 0.0,
    add_box_pill: bool = False,
) -> Image.Image:
    canvas = create_base_canvas(1280, 720, bg_type=bg_type).convert("RGBA")
    font = get_font(font_type, font_size)

    # Temporary overlay for alpha transparency & rotation
    text_layer = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

    line_spacing = 10
    line_metrics = []
    total_h = 0
    max_w = 0

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=outline_width)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_metrics.append((w, h))
        max_w = max(max_w, w)
        total_h += h + line_spacing
    total_h -= line_spacing

    if y_anchor == "bottom":
        start_y = 720 - 70 - total_h
    elif y_anchor == "top":
        start_y = 60
    else:
        start_y = (720 - total_h) // 2

    curr_y = start_y
    for i, line in enumerate(lines):
        w, h = line_metrics[i]
        curr_x = (1280 - w) // 2

        if add_box_pill:
            pad_x, pad_y = 12, 6
            pill_rect = [curr_x - pad_x, curr_y - pad_y, curr_x + w + pad_x, curr_y + h + pad_y]
            draw.rectangle(pill_rect, fill=(0, 0, 0, int(180 * opacity)))

        fill_with_alpha = (*text_color[:3], int(255 * opacity))
        outline_with_alpha = (*outline_color[:3], int(255 * opacity))

        draw.text(
            (curr_x, curr_y),
            line,
            font=font,
            fill=fill_with_alpha,
            stroke_width=outline_width,
            stroke_fill=outline_with_alpha,
        )
        curr_y += h + line_spacing

    if abs(rotation_deg) > 0.01:
        text_layer = text_layer.rotate(rotation_deg, resample=Image.Resampling.BILINEAR, center=(640, curr_y - total_h // 2))

    combined = Image.alpha_composite(canvas, text_layer)
    return combined.convert("RGB")


# 25 Heterogeneous Test Scenarios
BENCHMARK_SCENARIOS: List[Dict[str, Any]] = [
    # Tier 1: Clean Baseline (5 Cases)
    {
        "id": "tier1_01",
        "tier": 1,
        "tier_name": "Clean Baseline",
        "reference_text": "Stay Hungry Stay Foolish",
        "lines": ["Stay Hungry Stay Foolish"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 38,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Standard clean white-on-dark centered subtitle",
    },
    {
        "id": "tier1_02",
        "tier": 1,
        "tier_name": "Clean Baseline",
        "reference_text": "Subtitles are working properly on screen",
        "lines": ["Subtitles are working properly on screen"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Full sentence dialog",
    },
    {
        "id": "tier1_03",
        "tier": 1,
        "tier_name": "Clean Baseline",
        "reference_text": "Welcome to the annual conference 2026",
        "lines": ["Welcome to the annual conference 2026"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Alphanumeric sentence with year",
    },
    {
        "id": "tier1_04",
        "tier": 1,
        "tier_name": "Clean Baseline",
        "reference_text": "Halo selamat datang di Indonesia",
        "lines": ["Halo selamat datang di Indonesia"],
        "lang": "id",
        "font_type": "latin",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Indonesian clean title",
    },
    {
        "id": "tier1_05",
        "tier": 1,
        "tier_name": "Clean Baseline",
        "reference_text": "Connecting the dots looking forward",
        "lines": ["Connecting the dots looking forward"],
        "lang": "en",
        "font_type": "bold",
        "font_size": 38,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Bold clean typography",
    },

    # Tier 2: Multilingual Dense CJK (5 Cases)
    {
        "id": "tier2_01",
        "tier": 2,
        "tier_name": "Multilingual Dense CJK",
        "reference_text": "こんにちは世界へようこそ",
        "lines": ["こんにちは世界へようこそ"],
        "lang": "ja",
        "font_type": "cjk",
        "font_size": 38,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Japanese Hiragana and Kanji (World)",
    },
    {
        "id": "tier2_02",
        "tier": 2,
        "tier_name": "Multilingual Dense CJK",
        "reference_text": "東京の夜景は本当に美しいですね",
        "lines": ["東京の夜景は本当に美しいですね"],
        "lang": "ja",
        "font_type": "cjk",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Complex Kanji strokes: 東京, 夜景, 美しい",
    },
    {
        "id": "tier2_03",
        "tier": 2,
        "tier_name": "Multilingual Dense CJK",
        "reference_text": "欢迎来到人工智能的新时代",
        "lines": ["欢迎来到人工智能的新时代"],
        "lang": "zh",
        "font_type": "cjk",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Simplified Chinese: 人工智能",
    },
    {
        "id": "tier2_04",
        "tier": 2,
        "tier_name": "Multilingual Dense CJK",
        "reference_text": "千里之行始于足下",
        "lines": ["千里之行始于足下"],
        "lang": "zh",
        "font_type": "cjk",
        "font_size": 38,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Chinese Idiom (Proverb)",
    },
    {
        "id": "tier2_05",
        "tier": 2,
        "tier_name": "Multilingual Dense CJK",
        "reference_text": "안녕하세요 여러분 반갑습니다",
        "lines": ["안녕하세요 여러분 반갑습니다"],
        "lang": "ko",
        "font_type": "hangul",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Korean Hangul broadcast subtitle",
    },

    # Tier 3: Burned-In Cinema & Noise (5 Cases)
    {
        "id": "tier3_01",
        "tier": 3,
        "tier_name": "Burned-In Cinema & Noise",
        "reference_text": "Watch out! The bridge is collapsing!",
        "lines": ["Watch out! The bridge is collapsing!"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 36,
        "text_color": (253, 224, 71),  # Cinema yellow #FDE047
        "outline_color": (20, 20, 20),
        "outline_width": 2,
        "bg_type": "explosion",
        "y_anchor": "bottom",
        "description": "Cinema yellow font over dynamic warm explosion scene",
    },
    {
        "id": "tier3_02",
        "tier": 3,
        "tier_name": "Burned-In Cinema & Noise",
        "reference_text": "She said it was impossible, but we did it anyway!",
        "lines": ["She said it was impossible, but we did it anyway!"],
        "lang": "en",
        "font_type": "italic",
        "font_size": 34,
        "text_color": (253, 224, 71),
        "outline_color": (0, 0, 0),
        "outline_width": 2,
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Yellow italicized speaker dialogue",
    },
    {
        "id": "tier3_03",
        "tier": 3,
        "tier_name": "Burned-In Cinema & Noise",
        "reference_text": "The snowstorm is getting worse every minute",
        "lines": ["The snowstorm is getting worse every minute"],
        "lang": "en",
        "font_type": "bold",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "outline_color": (0, 0, 0),
        "outline_width": 3,
        "bg_type": "bright_snow",
        "y_anchor": "bottom",
        "description": "White font over high-luminance bright snow background (low contrast test)",
    },
    {
        "id": "tier3_04",
        "tier": 3,
        "tier_name": "Burned-In Cinema & Noise",
        "reference_text": "Hold on tight, we are entering the tunnel!",
        "lines": ["Hold on tight, we are entering the tunnel!"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (253, 224, 71),
        "outline_color": (0, 0, 0),
        "outline_width": 2,
        "bg_type": "bright_snow",
        "y_anchor": "bottom",
        "description": "Yellow cinema font over bright glare background",
    },
    {
        "id": "tier3_05",
        "tier": 3,
        "tier_name": "Burned-In Cinema & Noise",
        "reference_text": "Kami berhasil menemukan jalan keluar rahasia",
        "lines": ["Kami berhasil menemukan jalan keluar rahasia"],
        "lang": "id",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (253, 224, 71),
        "outline_color": (0, 0, 0),
        "outline_width": 2,
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Indonesian cinema subtitle",
    },

    # Tier 4: Descender Torture & Multi-Line (5 Cases)
    {
        "id": "tier4_01",
        "tier": 4,
        "tier_name": "Descender Torture & Multi-line",
        "reference_text": "paying typography equipment, jumping quickly;",
        "lines": ["paying typography equipment, jumping quickly;"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Torture test with descenders: p, y, g, q, j, comma, semicolon",
    },
    {
        "id": "tier4_02",
        "tier": 4,
        "tier_name": "Descender Torture & Multi-line",
        "reference_text": "flying puppies gently playing, quietly praying;",
        "lines": ["flying puppies gently playing, quietly praying;"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 36,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "High density of y, p, g descenders touching boundary",
    },
    {
        "id": "tier4_03",
        "tier": 4,
        "tier_name": "Descender Torture & Multi-line",
        "reference_text": "Where did everyone go? I think they went into the forest.",
        "lines": ["Where did everyone go?", "I think they went into the forest."],
        "lang": "en",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "2-line conversation subtitle stacked vertically",
    },
    {
        "id": "tier4_04",
        "tier": 4,
        "tier_name": "Descender Torture & Multi-line",
        "reference_text": "Apakah kamu mendengar suara itu? Ya, suara itu datang dari bawah tangga.",
        "lines": ["Apakah kamu mendengar suara itu?", "Ya, suara itu datang dari bawah tangga."],
        "lang": "id",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Indonesian 2-line dialog subtitle",
    },
    {
        "id": "tier4_05",
        "tier": 4,
        "tier_name": "Descender Torture & Multi-line",
        "reference_text": "東京タワーが見えますか？ ええ、とても綺麗に見えますよ。",
        "lines": ["東京タワーが見えますか？", "ええ、とても綺麗に見えますよ。"],
        "lang": "ja",
        "font_type": "cjk",
        "font_size": 34,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Japanese 2-line conversation",
    },

    # Tier 5: Adversarial Anomalies & Extreme Edge Cases (5 Cases)
    {
        "id": "tier5_01",
        "tier": 5,
        "tier_name": "Adversarial Anomalies",
        "reference_text": "This subtitle is semi transparent with 55% opacity",
        "lines": ["This subtitle is semi transparent with 55% opacity"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "opacity": 0.55,
        "description": "Semi-transparent subtitle (55% alpha)",
    },
    {
        "id": "tier5_02",
        "tier": 5,
        "tier_name": "Adversarial Anomalies",
        "reference_text": "Tilted camera angle subtitle rotation test",
        "lines": ["Tilted camera angle subtitle rotation test"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "rotation_deg": 3.5,
        "description": "3.5 degree rotated text (handheld camera tilt)",
    },
    {
        "id": "tier5_03",
        "tier": 5,
        "tier_name": "Adversarial Anomalies",
        "reference_text": "Small compact caption line at 22px size",
        "lines": ["Small compact caption line at 22px size"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 22,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Low resolution small caption (22px)",
    },
    {
        "id": "tier5_04",
        "tier": 5,
        "tier_name": "Adversarial Anomalies",
        "reference_text": "[Music] (Laughs) Wait... Did you see that?",
        "lines": ["[Music] (Laughs) Wait... Did you see that?"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 34,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "bottom",
        "description": "Closed captions with music cues, brackets and ellipses",
    },
    {
        "id": "tier5_05",
        "tier": 5,
        "tier_name": "Adversarial Anomalies",
        "reference_text": "Top lyrics and bottom dialogue concurrent split",
        "lines": ["Top lyrics and bottom dialogue concurrent split"],
        "lang": "en",
        "font_type": "latin",
        "font_size": 32,
        "text_color": (255, 255, 255),
        "bg_type": "dark",
        "y_anchor": "top",
        "description": "Secondary subtitle in top band (20% screen ratio)",
    },
]


def generate_all() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    print(f"Generating 25 Heterogeneous Subtitle Benchmark Frames in {OUTPUT_DIR}...")

    for scenario in BENCHMARK_SCENARIOS:
        sid = scenario["id"]
        filename = f"{sid}.png"
        filepath = OUTPUT_DIR / filename

        img = render_subtitle_frame(
            lines=scenario["lines"],
            font_type=scenario.get("font_type", "latin"),
            font_size=scenario.get("font_size", 36),
            text_color=scenario.get("text_color", (255, 255, 255)),
            outline_color=scenario.get("outline_color", (0, 0, 0)),
            outline_width=scenario.get("outline_width", 2),
            bg_type=scenario.get("bg_type", "dark"),
            y_anchor=scenario.get("y_anchor", "bottom"),
            opacity=scenario.get("opacity", 1.0),
            rotation_deg=scenario.get("rotation_deg", 0.0),
            add_box_pill=scenario.get("add_box_pill", False),
        )

        img.save(filepath, "PNG")

        manifest.append({
            "id": sid,
            "tier": scenario["tier"],
            "tier_name": scenario["tier_name"],
            "filename": filename,
            "filepath": str(filepath.relative_to(PROJECT_ROOT)),
            "reference_text": scenario["reference_text"],
            "lang": scenario["lang"],
            "description": scenario["description"],
        })
        print(f"  [Tier {scenario['tier']}] Generated {filename} -> '{scenario['reference_text']}'")

    manifest_path = OUTPUT_DIR / "dataset_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nManifest successfully created at {manifest_path} ({len(manifest)} test cases).")


if __name__ == "__main__":
    generate_all()
