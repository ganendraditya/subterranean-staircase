"""Constants and specifications for supported language matrices."""

from __future__ import annotations

from typing import Tuple

# The Curated Big 5 Language Specifications: (DisplayName, Code)
BIG_5_LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("English", "en"),
    ("Indonesian", "id"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Chinese", "zh"),
)
