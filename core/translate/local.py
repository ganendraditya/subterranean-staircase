"""Offline translation engine interface and CTranslate2 quantized MarianMT implementation.

Provides high-throughput C++ inference, 2-hop English routing fallback,
and seamless integration with the SQLite WAL translation cache.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from core.contracts import TranslationRequest, TranslationResult
from core.storage.cache import SQLiteTranslationCache

try:
    import ctranslate2
    import sentencepiece as spm
    HAS_CTRANSLATE2 = True
except ImportError:
    HAS_CTRANSLATE2 = False


def get_default_models_dir() -> Path:
    """Return default models directory: ~/.cache/subtitle-translator/models/"""
    base_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base_dir / "subtitle-translator" / "models"


class BaseTranslator(ABC):
    """Abstract interface for subtitle translation engines."""

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate request payload into normalized TranslationResult."""
        pass


class CTranslate2Engine(BaseTranslator):
    """Production offline translation engine powered by quantized CTranslate2 INT8 models."""

    def __init__(
        self,
        models_dir: Optional[Path] = None,
        cache: Optional[SQLiteTranslationCache] = None,
        device: str = "cpu",
        inter_threads: int = 1,
        intra_threads: int = 2,
    ) -> None:
        self.models_dir = models_dir or get_default_models_dir()
        self.cache = cache
        self.device = device
        self.inter_threads = inter_threads
        self.intra_threads = intra_threads

        # Model and tokenizer cache: { "en-id": (translator, sp_source, sp_target) }
        self._loaded_pairs: Dict[str, Tuple[Any, Any, Any]] = {}

    def _route(self, source_lang: str, target_lang: str) -> List[Tuple[str, str]]:
        """Determine translation routing path (direct vs 2-hop via English)."""
        src = source_lang.strip()
        tgt = target_lang.strip()

        if src.lower() == tgt.lower():
            return []

        src_base = src.replace("_", "-").split("-")[0].lower()
        tgt_base = tgt.replace("_", "-").split("-")[0].lower()

        # If source is English regional variant (e.g. en-US), map to standard 'en' for model resolution
        eff_src = "en" if src_base == "en" else src
        eff_tgt = "en" if tgt_base == "en" else tgt

        if eff_src.lower() == eff_tgt.lower():
            return []

        # Direct pair if source or target base language is English
        if src_base == "en" or tgt_base == "en":
            return [(eff_src, eff_tgt)]

        # 2-hop routing: eff_src -> en -> eff_tgt
        return [(eff_src, "en"), ("en", eff_tgt)]

    def _get_pair_model_path(self, src: str, tgt: str) -> Path:
        """Get filesystem directory for the specific language pair model with path-traversal protection."""
        valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        if not (set(src).issubset(valid_chars) and set(tgt).issubset(valid_chars)) or not src or not tgt:
            raise ValueError(f"Invalid language codes: '{src}', '{tgt}'")
        return self.models_dir / f"opus-mt-{src}-{tgt}"

    def load_pair(self, src: str, tgt: str) -> Tuple[Any, Any, Any]:
        """Load or retrieve cached CTranslate2 translator, source tokenizer, and target tokenizer."""
        pair_key = f"{src}-{tgt}"
        if pair_key in self._loaded_pairs:
            return self._loaded_pairs[pair_key]

        if not HAS_CTRANSLATE2:
            raise RuntimeError("ctranslate2 or sentencepiece is not installed")

        model_path = self._get_pair_model_path(src, tgt)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model for language pair '{pair_key}' not found at {model_path}. "
                f"Please download the model before translating."
            )

        sp_src_path = model_path / "source.spm"
        if not sp_src_path.exists():
            sp_src_path = model_path / "spm.model"
            if not sp_src_path.exists():
                raise FileNotFoundError(f"SentencePiece tokenizer model not found in {model_path}")

        sp_source = spm.SentencePieceProcessor()
        sp_source.load(str(sp_src_path))

        # Check for dedicated target tokenizer (common in Opus-MT bilingual models)
        sp_tgt_path = model_path / "target.spm"
        if sp_tgt_path.exists():
            sp_target = spm.SentencePieceProcessor()
            sp_target.load(str(sp_tgt_path))
        else:
            sp_target = sp_source

        translator = ctranslate2.Translator(
            str(model_path),
            device=self.device,
            inter_threads=self.inter_threads,
            intra_threads=self.intra_threads,
        )

        self._loaded_pairs[pair_key] = (translator, sp_source, sp_target)
        return translator, sp_source, sp_target

    def _translate_step(self, text: str, src: str, tgt: str) -> str:
        """Execute a single-step translation using loaded CTranslate2 model and dual tokenizers."""
        translator, sp_source, sp_target = self.load_pair(src, tgt)

        tokens = sp_source.encode(text, out_type=str)
        # MarianMT / Opus-MT models require the end-of-sequence token </s> to prevent infinite repetition loops
        if not tokens or tokens[-1] != "</s>":
            tokens.append("</s>")

        results = translator.translate_batch(
            [tokens],
            max_decoding_length=128,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
        )
        if not results or not results[0].hypotheses:
            return ""
        output_tokens = results[0].hypotheses[0]
        # Decode target tokens using the target tokenizer
        translated_text = sp_target.decode(output_tokens)
        return str(translated_text).strip()

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate source text with multi-hop support and cache lookup."""
        text = request.source_text.strip()
        src = request.source_lang.strip()
        tgt = request.target_lang.strip()
        start_time = time.perf_counter()

        if not text or src.lower() == tgt.lower():
            return TranslationResult(
                source_text=request.source_text,
                translated_text=text,
                source_lang=src,
                target_lang=tgt,
                from_cache=False,
                latency_ms=0.0,
            )

        # 1. Check SQLite translation memory cache
        if self.cache is not None:
            cached_trans = self.cache.get(text, src, tgt)
            if cached_trans is not None:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return TranslationResult(
                    source_text=request.source_text,
                    translated_text=cached_trans,
                    source_lang=src,
                    target_lang=tgt,
                    from_cache=True,
                    latency_ms=elapsed_ms,
                )

        # 2. Execute translation route
        route = self._route(src, tgt)
        current_text = text

        for hop_src, hop_tgt in route:
            current_text = self._translate_step(current_text, hop_src, hop_tgt)
            if not current_text:
                break

        # 3. Store translated output in cache
        if self.cache is not None and current_text:
            self.cache.set(text, src, tgt, current_text)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return TranslationResult(
            source_text=request.source_text,
            translated_text=current_text,
            source_lang=src,
            target_lang=tgt,
            from_cache=False,
            latency_ms=elapsed_ms,
        )
