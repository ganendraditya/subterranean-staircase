"""Atomic Language Pack architecture pairing OCR recognition assets and NMT weights.

Downloading an atomic language pack ensures both translation models and any language-specific
OCR dependencies are present, preventing blind-OCR recognition failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class LanguagePackMetadata:
    """Atomic Language Pack definition bundling translation model pairs and OCR requirements."""
    pack_id: str                      # e.g. "ja", "ko", "zh", "core"
    name: str                         # e.g. "Japanese Language Pack"
    description: str                  # e.g. "Includes ja-en translation and Japanese Kanji/Kana OCR"
    languages: List[str]              # e.g. ["ja"]
    translation_pairs: List[str]      # e.g. ["ja-en"]
    approx_size_mb: int               # e.g. 155
    ocr_model: Optional[str] = None   # None if covered by universal multi-lingual OCR
    is_core: bool = False             # True for Core English <-> Indonesian pack


# The Curated Language Pack Catalog for The Big 5
ATOMIC_LANGUAGE_PACKS: Dict[str, LanguagePackMetadata] = {
    "core": LanguagePackMetadata(
        pack_id="core",
        name="Core Pack (English ↔ Indonesian)",
        description="Bilingual English and Indonesian translation with universal Latin OCR",
        languages=["en", "id"],
        translation_pairs=["en-id", "id-en"],
        approx_size_mb=220,
        ocr_model=None,
        is_core=True,
    ),
    "ja": LanguagePackMetadata(
        pack_id="ja",
        name="Japanese Pack",
        description="Japanese to English translation with Kanji & Kana OCR support",
        languages=["ja"],
        translation_pairs=["ja-en"],
        approx_size_mb=155,
        ocr_model=None,
        is_core=False,
    ),
    "ko": LanguagePackMetadata(
        pack_id="ko",
        name="Korean Pack",
        description="Korean to English translation with Hangul OCR support",
        languages=["ko"],
        translation_pairs=["ko-en"],
        approx_size_mb=148,
        ocr_model=None,
        is_core=False,
    ),
    "zh": LanguagePackMetadata(
        pack_id="zh",
        name="Chinese Pack",
        description="Chinese to English and English to Chinese translation with Hanzi OCR support",
        languages=["zh"],
        translation_pairs=["zh-en", "en-zh"],
        approx_size_mb=307,
        ocr_model=None,
        is_core=False,
    ),
}
