"""Translation routing module for direct and multi-hop pivot translation paths.

Supports direct 1-hop execution when a specialized bilingual model exists,
and intelligent 2-hop English pivot execution (e.g. ja -> en -> id)
for cross-language pairs without direct NMT models.
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple


# The Curated Big 5 Language Specifications: (DisplayName, Code)
BIG_5_LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("English", "en"),
    ("Indonesian", "id"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Chinese", "zh"),
)


def normalize_lang_code(code: str) -> str:
    """Normalize language code (e.g. 'en_US' -> 'en', 'zh_CN' -> 'zh').
    
    Collapses language tags to their base code (e.g. 'en', 'zh', 'ja').
    """
    clean = code.strip().replace("_", "-")
    parts = clean.split("-")
    return parts[0].lower()


class TranslationRouter:
    """Calculates translation hops given available direct models."""

    def __init__(self, available_direct_pairs: Optional[Set[str]] = None) -> None:
        """Initialize router.

        If available_direct_pairs is None, loads from RECOMMENDED_MODELS catalog.
        """
        if available_direct_pairs is not None:
            self.available_direct_pairs = set(available_direct_pairs)
        else:
            try:
                from core.translate.models import RECOMMENDED_MODELS
                self.available_direct_pairs = set(RECOMMENDED_MODELS.keys())
            except ImportError:
                self.available_direct_pairs = {
                    "ja-en",
                    "ko-en",
                    "zh-en",
                    "en-id",
                    "es-en",
                    "fr-en",
                    "de-en",
                }

    def resolve_route(self, source_lang: str, target_lang: str) -> List[Tuple[str, str]]:
        """Resolve route into a sequence of (src, tgt) hops.

        1. If source == target -> [] (no-op)
        2. If direct pair exists in available_direct_pairs -> [(src, tgt)] (1 hop)
        3. If src == 'en' or tgt == 'en':
           - Direct 1-hop [(src, tgt)]
        4. If src != 'en' and tgt != 'en':
           - 2-hop English pivot: [(src, "en"), ("en", tgt)]
        """
        src = normalize_lang_code(source_lang)
        tgt = normalize_lang_code(target_lang)

        if not src or not tgt or src == tgt:
            return []

        pair = f"{src}-{tgt}"
        # Direct model available in catalog
        if pair in self.available_direct_pairs:
            return [(src, tgt)]

        # If either is English, direct hop is the only valid path
        if src == "en" or tgt == "en":
            return [(src, tgt)]

        # 2-hop pivot via English: src -> en -> tgt
        return [(src, "en"), ("en", tgt)]
