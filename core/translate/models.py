"""Model registry, metadata, and downloading service for CTranslate2 MarianMT models.

Provides metadata for popular translation pairs (e.g. ja-en, ko-en, zh-en, en-id),
tracks local disk usage, downloads models from HuggingFace with progress callbacks,
and cleanly deletes downloaded models from disk.
"""

from __future__ import annotations

import logging
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from core.translate.constants import get_default_models_dir

logger = logging.getLogger("subtitle_translator.model_manager")

# Popular CTranslate2 converted Opus-MT / MarianMT models hosted on Hugging Face
HF_BASE_URL = "https://huggingface.co"

@dataclass
class ModelMetadata:
    """Information regarding a supported translation model pair."""
    pair_id: str             # e.g. "ja-en"
    source_lang: str         # e.g. "ja"
    target_lang: str         # e.g. "en"
    name: str                # e.g. "Japanese → English"
    description: str         # e.g. "Anime / Japanese Media"
    approx_size_mb: int      # e.g. 150
    hf_repo: str             # e.g. "michaelfeil/ct2fast-opus-mt-ja-en"
    files: List[str]         # Files needed for CTranslate2 + SentencePiece


# Catalog of primary recommended models hosted on Hugging Face (Public CTranslate2 converted weights)
RECOMMENDED_MODELS: Dict[str, ModelMetadata] = {
    "ja-en": ModelMetadata(
        pair_id="ja-en",
        source_lang="ja",
        target_lang="en",
        name="Japanese → English",
        description="Anime, J-Dramas, and Japanese streams",
        approx_size_mb=155,
        hf_repo="gaudi/opus-mt-ja-en-ctranslate2",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
    "ko-en": ModelMetadata(
        pair_id="ko-en",
        source_lang="ko",
        target_lang="en",
        name="Korean → English",
        description="K-Dramas, variety shows, and streams",
        approx_size_mb=148,
        hf_repo="gaudi/opus-mt-ko-en-ctranslate2",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
    "zh-en": ModelMetadata(
        pair_id="zh-en",
        source_lang="zh",
        target_lang="en",
        name="Chinese → English",
        description="C-Dramas, Donghua, and Chinese videos",
        approx_size_mb=152,
        hf_repo="gaudi/opus-mt-zh-en-ctranslate2",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
    "en-id": ModelMetadata(
        pair_id="en-id",
        source_lang="en",
        target_lang="id",
        name="English → Indonesian",
        description="Western movies, YouTube, and tech talks to Indonesian",
        approx_size_mb=75,
        hf_repo="manancode/opus-mt-en-id-ctranslate2-android",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
    "es-en": ModelMetadata(
        pair_id="es-en",
        source_lang="es",
        target_lang="en",
        name="Spanish → English",
        description="Latin American & Spanish films/shows",
        approx_size_mb=142,
        hf_repo="gaudi/opus-mt-es-en-ctranslate2",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
    "fr-en": ModelMetadata(
        pair_id="fr-en",
        source_lang="fr",
        target_lang="en",
        name="French → English",
        description="French cinema and international media",
        approx_size_mb=144,
        hf_repo="gaudi/opus-mt-fr-en-ctranslate2",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
    "de-en": ModelMetadata(
        pair_id="de-en",
        source_lang="de",
        target_lang="en",
        name="German → English",
        description="German films and media",
        approx_size_mb=146,
        hf_repo="gaudi/opus-mt-de-en-ctranslate2",
        files=["model.bin", "source.spm", "target.spm", "shared_vocabulary.json", "config.json"],
    ),
}


class ModelManager:
    """Manages discovery, disk inspection, downloading, and removal of offline models."""

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = models_dir or get_default_models_dir()

    def get_model_path(self, pair_id: str) -> Path:
        """Return expected filesystem path for a given pair ID."""
        return self.models_dir / f"opus-mt-{pair_id}"

    def is_installed(self, pair_id: str) -> bool:
        """Check if a model pair is completely downloaded and ready."""
        path = self.get_model_path(pair_id)
        if not path.is_dir():
            return False

        # Must have model.bin, at least one sentencepiece/vocabulary file, and config.json
        has_bin = (path / "model.bin").exists()
        has_spm = (path / "source.spm").exists() or (path / "spm.model").exists()
        has_cfg = (path / "config.json").exists()
        return has_bin and has_spm and has_cfg

    def get_disk_size_mb(self, pair_id: str) -> float:
        """Calculate total size in megabytes of an installed model."""
        path = self.get_model_path(pair_id)
        if not path.is_dir():
            return 0.0

        total_bytes = 0
        for entry in path.rglob("*"):
            if entry.is_file():
                total_bytes += entry.stat().st_size
        return round(total_bytes / (1024 * 1024), 2)

    def list_models_status(self) -> List[Dict[str, Any]]:
        """List all catalog models along with their installation status and size."""
        results = []
        for pair_id, meta in RECOMMENDED_MODELS.items():
            installed = self.is_installed(pair_id)
            size = self.get_disk_size_mb(pair_id) if installed else 0.0
            results.append({
                "pair_id": pair_id,
                "name": meta.name,
                "description": meta.description,
                "approx_size_mb": meta.approx_size_mb,
                "installed": installed,
                "installed_size_mb": size,
            })
        return results

    def download_model(
        self,
        pair_id: str,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> Tuple[bool, str]:
        """Download model files from Hugging Face into destination folder.

        progress_cb signature: (current_bytes, total_bytes, status_message)
        """
        meta = RECOMMENDED_MODELS.get(pair_id)
        if not meta:
            return False, f"Unknown model pair '{pair_id}'."

        dest_dir = self.get_model_path(pair_id)
        dest_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = dest_dir.parent / f".tmp_{dest_dir.name}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        total_size_estimate = meta.approx_size_mb * 1024 * 1024
        downloaded_so_far = 0

        try:
            for file_name in meta.files:
                file_url = f"{HF_BASE_URL}/{meta.hf_repo}/resolve/main/{file_name}"
                target_file = temp_dir / file_name

                if progress_cb:
                    progress_cb(downloaded_so_far, total_size_estimate, f"Downloading {file_name}...")

                req = urllib.request.Request(
                    file_url,
                    headers={"User-Agent": "SubterraneanStaircase/1.0"},
                )

                try:
                    with urllib.request.urlopen(req, timeout=30) as resp, open(target_file, "wb") as out_fp:
                        chunk_size = 128 * 1024
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            out_fp.write(chunk)
                            downloaded_so_far += len(chunk)
                            if progress_cb:
                                progress_cb(
                                    downloaded_so_far,
                                    max(total_size_estimate, downloaded_so_far),
                                    f"Downloading {file_name}...",
                                )
                except urllib.error.HTTPError as e:
                    # Some files like target.spm might be optional in certain repos
                    if e.code == 404 and file_name in ["target.spm", "shared_vocabulary.json"]:
                        logger.debug("Optional file %s not found on HF (code 404), skipping.", file_name)
                        continue
                    raise

            # Atomic move from temp to destination
            for f in temp_dir.iterdir():
                shutil.move(str(f), str(dest_dir / f.name))
            shutil.rmtree(temp_dir, ignore_errors=True)

            if progress_cb:
                progress_cb(total_size_estimate, total_size_estimate, "Download complete!")
            return True, f"Successfully downloaded model for {meta.name}."

        except Exception as e:
            logger.exception("Failed to download model %s: %s", pair_id, e)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False, f"Download failed: {str(e)}"

    def delete_model(self, pair_id: str) -> Tuple[bool, str]:
        """Delete an installed model folder from disk to free up space."""
        path = self.get_model_path(pair_id)
        if not path.exists():
            return False, f"Model '{pair_id}' is not installed."

        try:
            shutil.rmtree(path)
            logger.info("Successfully removed model directory: %s", path)
            return True, f"Model '{pair_id}' was cleanly deleted."
        except Exception as e:
            logger.exception("Failed to delete model %s: %s", pair_id, e)
            return False, f"Failed to delete model: {str(e)}"
