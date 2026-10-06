"""Universal OpenAI-Compatible Cloud LLM translation engine with local fallback.

Implements standard `/v1/chat/completions` API protocol compatible with Groq, DeepSeek,
OpenAI, OpenRouter, Mistral, Together AI, or local self-hosted instances (Ollama, vLLM, LM Studio).
Features automatic caching in SQLite and graceful fail-safe fallback to CTranslate2.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional, Tuple
import urllib.error
import urllib.request

from core.config import LLMTranslationConfig
from core.contracts import TranslationRequest, TranslationResult
from core.storage.cache import SQLiteTranslationCache
from core.translate.languages import BIG_5_LANGUAGES
from core.translate.local import BaseTranslator
from core.translate.router import normalize_lang_code

logger = logging.getLogger("subtitle_translator.translate.llm")

# Display name lookup for Big 5 and common codes
LANG_CODE_TO_NAME = {code: name for name, code in BIG_5_LANGUAGES}


def normalize_chat_endpoint(base_url: str) -> str:
    """Normalize base URL into full `/v1/chat/completions` endpoint."""
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return "https://api.groq.com/openai/v1/chat/completions"

    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions" if "/v1" in url else f"{url}/v1/chat/completions"


class OpenAICompatibleTranslator(BaseTranslator):
    """Universal OpenAI-Compatible LLM translator for high-context subtitle translation."""

    def __init__(
        self,
        config: Optional[LLMTranslationConfig] = None,
        cache: Optional[SQLiteTranslationCache] = None,
        fallback_engine: Optional[BaseTranslator] = None,
    ) -> None:
        self.config = config or LLMTranslationConfig()
        self.cache = cache
        self.fallback_engine = fallback_engine

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate subtitle text via OpenAI-compatible endpoint with cache & local fallback."""
        cleaned_text = request.source_text.strip()
        if not cleaned_text:
            return TranslationResult(
                source_text=request.source_text,
                translated_text="",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                from_cache=False,
                latency_ms=0.0,
            )

        src_code = normalize_lang_code(request.source_lang)
        tgt_code = normalize_lang_code(request.target_lang)

        # 1. Identity Check
        if src_code == tgt_code:
            return TranslationResult(
                source_text=request.source_text,
                translated_text=cleaned_text,
                source_lang=src_code,
                target_lang=tgt_code,
                from_cache=False,
                latency_ms=0.0,
            )

        # 2. Cache Lookup
        if self.cache is not None:
            cached = self.cache.get(cleaned_text, src_code, tgt_code)
            if cached is not None:
                return TranslationResult(
                    source_text=request.source_text,
                    translated_text=cached,
                    source_lang=src_code,
                    target_lang=tgt_code,
                    from_cache=True,
                    latency_ms=0.0,
                )

        # 3. Dispatch to LLM Endpoint
        t0 = time.perf_counter()
        try:
            translated_text, lat_ms = self._dispatch_llm_request(cleaned_text, src_code, tgt_code)
            if self.cache is not None and translated_text:
                self.cache.set(cleaned_text, src_code, tgt_code, translated_text)

            return TranslationResult(
                source_text=request.source_text,
                translated_text=translated_text,
                source_lang=src_code,
                target_lang=tgt_code,
                from_cache=False,
                latency_ms=lat_ms,
            )
        except Exception as exc:
            lat_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(
                "[LLM-TRANS-ERR] LLM translation failed (%s: %s).",
                type(exc).__name__,
                exc,
            )

            # 4. Fail-safe Fallback to Local Offline Engine
            if self.config.fallback_to_local and self.fallback_engine is not None:
                logger.info("[LLM-FALLBACK] Falling back to local offline translation engine...")
                try:
                    return self.fallback_engine.translate(request)
                except Exception as fallback_exc:
                    logger.warning("[LLM-FALLBACK-ERR] Local fallback also failed: %s", fallback_exc)

            return TranslationResult(
                source_text=request.source_text,
                translated_text="",
                source_lang=src_code,
                target_lang=tgt_code,
                from_cache=False,
                latency_ms=lat_ms,
            )

    def _dispatch_llm_request(self, text: str, src_code: str, tgt_code: str) -> Tuple[str, float]:
        """Execute HTTP request to `/v1/chat/completions` endpoint."""
        endpoint = normalize_chat_endpoint(self.config.base_url)
        src_name = LANG_CODE_TO_NAME.get(src_code, src_code.upper())
        tgt_name = LANG_CODE_TO_NAME.get(tgt_code, tgt_code.upper())

        payload = {
            "model": self.config.model_name or "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are a professional real-time subtitle translator. "
                        f"Translate the following subtitle line from {src_name} to {tgt_name}. "
                        "Output ONLY the direct translated text. "
                        "Do NOT include explanations, notes, quotes, or markdown formatting."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 150,
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Subterranean-Staircase/1.0",
        }
        if self.config.api_key and self.config.api_key.strip():
            headers["Authorization"] = f"Bearer {self.config.api_key.strip()}"

        req = urllib.request.Request(
            endpoint,
            data=body_bytes,
            headers=headers,
            method="POST",
        )

        timeout = max(1.0, float(self.config.timeout_seconds))
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        lat_ms = (time.perf_counter() - t0) * 1000.0

        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"No choices returned by LLM endpoint: {data}")

        msg = choices[0].get("message") or {}
        raw_out = (msg.get("content") or "").strip()

        # Sanitize accidental quotes or markdown codeblocks
        if (raw_out.startswith('"') and raw_out.endswith('"')) or (
            raw_out.startswith("'") and raw_out.endswith("'")
        ):
            raw_out = raw_out[1:-1].strip()
        if raw_out.startswith("```") and raw_out.endswith("```"):
            lines = raw_out.splitlines()
            if len(lines) >= 3:
                raw_out = "\n".join(lines[1:-1]).strip()
            else:
                raw_out = raw_out.strip("`").strip()

        return raw_out, lat_ms

    def test_connection(self) -> Tuple[bool, str]:
        """Test API endpoint connectivity and authentication with a sample phrase."""
        try:
            out, lat_ms = self._dispatch_llm_request("Hello", "en", "id")
            return True, f"Success ({lat_ms:.0f}ms): '{out}'"
        except urllib.error.HTTPError as http_err:
            detail = ""
            try:
                raw_bytes = http_err.read()
                err_body = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                if isinstance(err_body, dict):
                    err_dict = err_body.get("error", {})
                    if isinstance(err_dict, dict):
                        detail = err_dict.get("message", "")
                    elif isinstance(err_dict, str):
                        detail = err_dict
            except Exception:
                pass
            msg_str = f": {detail}" if detail else f" ({http_err.reason})"
            return False, f"HTTP {http_err.code}{msg_str}"
        except urllib.error.URLError as url_err:
            return False, f"Connection error: {url_err.reason}"
        except Exception as e:
            return False, f"Error: {e}"
