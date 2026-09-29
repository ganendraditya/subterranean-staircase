"""Multilingual script detection and subtitle text normalization.

Handles Latin, Japanese (Hiragana/Katakana), Korean (Hangul), Chinese (CJK),
and Arabic script categorization purely using Unicode codepoints without regex.
"""

from __future__ import annotations

from typing import List
from core.contracts import SubtitleDetection


def detect_script(text: str) -> str:
    """Detect dominant script family: 'ar', 'ja', 'ko', 'zh', or 'latin' using Unicode codepoints."""
    if not text:
        return "latin"

    ar_count = 0
    ja_kana_count = 0
    ko_count = 0
    cjk_count = 0
    latin_count = 0

    for ch in text:
        cp = ord(ch)
        # Arabic: U+0600 - U+06FF
        if 0x0600 <= cp <= 0x06FF:
            ar_count += 1
        # Japanese Hiragana: U+3040 - U+309F
        elif 0x3040 <= cp <= 0x309F:
            ja_kana_count += 1
        # Japanese Katakana: U+30A0 - U+30FF
        elif 0x30A0 <= cp <= 0x30FF:
            ja_kana_count += 1
        # Korean Hangul: U+AC00 - U+D7AF
        elif 0xAC00 <= cp <= 0xD7AF:
            ko_count += 1
        # CJK Unified Ideographs & extensions
        elif (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0xF900 <= cp <= 0xFAFF):
            cjk_count += 1
        # Latin basic & extended (A-Z, a-z, accented Latin)
        elif (65 <= cp <= 90) or (97 <= cp <= 122) or (0x00C0 <= cp <= 0x024F):
            latin_count += 1

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
    """Normalize subtitle text by collapsing whitespace without artificial word stripping."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


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
