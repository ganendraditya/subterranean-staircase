"""Constants and directory helpers for local machine translation models."""

from __future__ import annotations

import os
from pathlib import Path


def get_default_models_dir() -> Path:
    """Return default models directory: ~/.cache/subtitle-translator/models/"""
    base_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base_dir / "subtitle-translator" / "models"
