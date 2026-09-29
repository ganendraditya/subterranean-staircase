"""Translation routing module for direct and multi-hop pivot translation paths.

Supports direct 1-hop execution when a specialized bilingual model exists,
and intelligent 2-hop English pivot execution (e.g. ja -> en -> id)
for cross-language pairs without direct NMT models.
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from core.translate.models import RECOMMENDED_MODELS


def normalize_lang_code(code: str) -> str:
    """Normalize language code (e.g. 'en_US' -> 'en', 'zh_CN' -> 'zh').
    
    Collapses language tags to their base code (e.g. 'en', 'zh', 'ja').
    """
    clean = code.strip().replace("_", "-")
    parts = clean.split("-")
    return parts[0].lower()


class TranslationRouter:
    """Calculates translation hops given available direct models in catalog."""

    def __init__(self, available_direct_pairs: Optional[Set[str]] = None) -> None:
        """Initialize router.

        If available_direct_pairs is None, loads authoritative catalog pairs from RECOMMENDED_MODELS.
        """
        if available_direct_pairs is not None:
            self.available_direct_pairs = set(available_direct_pairs)
        else:
            self.available_direct_pairs = set(RECOMMENDED_MODELS.keys())

    def required_pairs(self, source_lang: str, target_lang: str) -> List[str]:
        """Return list of pair identifiers required for translation (e.g. ['ja-en', 'en-id'])."""
        hops = self.resolve_route(source_lang, target_lang)
        return [f"{s}-{t}" for s, t in hops]

    def resolve_route(self, source_lang: str, target_lang: str) -> List[Tuple[str, str]]:
        """Resolve route into a sequence of (src, tgt) hops.

        1. If source == target -> [] (no-op)
        2. If direct pair exists in available_direct_pairs -> [(src, tgt)] (1 hop)
        3. If src != 'en' and tgt != 'en':
           - Check 2-hop pivot via English: (src -> en) then (en -> tgt)
           - Both hops MUST exist in available_direct_pairs to be considered deliverable
        4. Returns [] if no deliverable route can be constructed from available models.
        """
        src = normalize_lang_code(source_lang)
        tgt = normalize_lang_code(target_lang)

        if not src or not tgt or src == tgt:
            return []

        pair = f"{src}-{tgt}"
        # Direct model available in catalog
        if pair in self.available_direct_pairs:
            return [(src, tgt)]

        # If either is English but direct pair is absent from catalog, route cannot be fulfilled
        if src == "en" or tgt == "en":
            return []

        # 2-hop pivot via English: src -> en -> tgt
        hop1 = f"{src}-en"
        hop2 = f"en-{tgt}"
        # Both legs must be present in catalog to form a deliverable pivot route
        if hop1 in self.available_direct_pairs and hop2 in self.available_direct_pairs:
            return [(src, "en"), ("en", tgt)]

        return []
