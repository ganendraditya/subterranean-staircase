"""Multilingual script detection, OCR text normalization, and noise filters.

Handles Latin, Japanese (Hiragana/Katakana), Korean (Hangul), Chinese (CJK),
and Arabic script categorization while sanitizing common subtitle artifacts.
"""

from __future__ import annotations

import re
from typing import List
from core.contracts import SubtitleDetection

# Pre-compiled regex patterns for Unicode script detection
_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_HIRAGANA = re.compile(r"[\u3040-\u309f]")
_KATAKANA = re.compile(r"[\u30a0-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")

# Common subtitle timestamp and prefix noise patterns (e.g., "[00:12]", "(EN)")
_TIMESTAMP_PREFIX = re.compile(r"^\s*\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]\s*")
_LANG_PREFIX = re.compile(
    r"^\s*(?:\(\s*(?:en|id|ja|zh|ko|fr|de|es|ar)\s*\)|(?:en|id|ja|zh|ko|fr|de|es|ar)\s*:)\s*",
    re.IGNORECASE,
)
_REPEATED_PUNCT = re.compile(r"([!?.,])\1+")
_EXCESSIVE_WHITESPACE = re.compile(r"\s+")


def detect_script(text: str) -> str:
    """Detect dominant script family: 'ar', 'ja', 'ko', 'zh', or 'latin'."""
    if not text:
        return "latin"

    # Count character frequencies for script families to determine dominant script
    ar_count = len(_ARABIC.findall(text))
    ja_kana_count = len(_HIRAGANA.findall(text)) + len(_KATAKANA.findall(text))
    ko_count = len(_HANGUL.findall(text))
    cjk_count = len(_CJK.findall(text))
    latin_count = len(re.findall(r"[a-zA-Z\u00c0-\u024f]", text))

    # If Kana is present, CJK characters in the same sentence are part of Japanese text
    ja_count = ja_kana_count + (cjk_count if ja_kana_count > 0 else 0)
    zh_count = cjk_count if ja_kana_count == 0 else 0

    counts = {
        "ar": ar_count,
        "ko": ko_count,
        "ja": ja_count,
        "zh": zh_count,
        "latin": latin_count,
    }
    top_script, max_count = max(counts.items(), key=lambda item: item[1])
    if max_count > 0:
        return top_script

    return "latin"


def clean_subtitle_text(text: str) -> str:
    """Clean subtitle artifacts, prefix timestamps, and collapse erratic whitespace."""
    if not text:
        return ""

    # Remove timestamps like [01:23] or language prefixes like (EN)
    cleaned = _TIMESTAMP_PREFIX.sub("", text)
    cleaned = _LANG_PREFIX.sub("", cleaned)

    # Normalize multiple punctuation (e.g. "???" -> "?", "..." preserved)
    # Don't collapse triple dots into single dot
    def _punct_repl(match: re.Match[str]) -> str:
        ch = match.group(1)
        if ch == "." and len(match.group(0)) >= 2:
            return "..."
        return ch

    cleaned = _REPEATED_PUNCT.sub(_punct_repl, cleaned)
    cleaned = _EXCESSIVE_WHITESPACE.sub(" ", cleaned)
    return cleaned.strip()


class SubtitleTextFilter:
    """Filters and sanitizes OCR detections against expected source script."""

    def __init__(self, target_script: str = "latin") -> None:
        self.target_script = target_script.lower()

    def filter_and_clean(
        self,
        detections: List[SubtitleDetection],
    ) -> List[SubtitleDetection]:
        """Sanitize text and filter out detections that completely contradict expected script."""
        cleaned_detections: List[SubtitleDetection] = []

        for det in detections:
            sanitized = clean_subtitle_text(det.text)
            if not sanitized:
                continue

            detected_script = detect_script(sanitized)

            # If expecting latin (en, id, fr, de, etc.) and it's pure CJK/Arabic, skip unless requested
            if self.target_script in ("latin", "en", "id", "fr", "de", "es"):
                if detected_script in ("ja", "ko", "zh", "ar"):
                    continue
            elif self.target_script in ("ja", "ko", "zh", "ar"):
                # If expecting Japanese, accept Kanji (tagged as zh if standalone) or Kana (ja)
                if self.target_script == "ja" and detected_script in ("ja", "zh", "latin"):
                    pass
                elif detected_script != self.target_script and detected_script != "latin":
                    continue

            # If target script is Japanese and standalone Kanji was tagged as zh, normalize language to ja
            final_language = "ja" if (self.target_script == "ja" and detected_script == "zh") else detected_script

            # Create immutable new SubtitleDetection with sanitized string and detected script
            cleaned_detections.append(
                SubtitleDetection(
                    text=sanitized,
                    confidence=det.confidence,
                    box=det.box,
                    language=final_language,
                    timestamp=det.timestamp,
                )
            )

        return cleaned_detections
