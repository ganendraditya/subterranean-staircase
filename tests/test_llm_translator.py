"""Unit tests for Universal OpenAI-Compatible Cloud LLM translation engine."""

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from core.config import LLMTranslationConfig
from core.contracts import TranslationRequest, TranslationResult
from core.storage.cache import SQLiteTranslationCache
from core.translate.llm import OpenAICompatibleTranslator, normalize_chat_endpoint
from core.translate.local import BaseTranslator


def test_normalize_chat_endpoint() -> None:
    assert normalize_chat_endpoint("https://api.groq.com/openai/v1") == "https://api.groq.com/openai/v1/chat/completions"
    assert normalize_chat_endpoint("https://api.groq.com/openai/v1/") == "https://api.groq.com/openai/v1/chat/completions"
    assert normalize_chat_endpoint("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
    assert normalize_chat_endpoint("https://api.deepseek.com") == "https://api.deepseek.com/v1/chat/completions"
    assert normalize_chat_endpoint("https://api.example.com/v1/chat/completions") == "https://api.example.com/v1/chat/completions"
    assert normalize_chat_endpoint("") == "https://api.groq.com/openai/v1/chat/completions"


def test_llm_translate_success_and_cache(tmp_path: Path) -> None:
    cache = SQLiteTranslationCache(db_path=tmp_path / "cache.db")
    cfg = LLMTranslationConfig(
        enabled=True,
        base_url="https://api.groq.com/openai/v1",
        api_key="gsk-testkey123",
        model_name="llama-3.3-70b-versatile",
    )
    translator = OpenAICompatibleTranslator(config=cfg, cache=cache)

    mock_resp_json = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Halo dunia"},
                "finish_reason": "stop",
            }
        ],
    }
    mock_resp_bytes = json.dumps(mock_resp_json).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_resp_bytes
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        req = TranslationRequest("Hello world", "en", "id")
        res = translator.translate(req)

        assert res.translated_text == "Halo dunia"
        assert res.from_cache is False
        assert mock_urlopen.call_count == 1

        # Check request headers
        call_args = mock_urlopen.call_args[0]
        http_req = call_args[0]
        assert http_req.full_url == "https://api.groq.com/openai/v1/chat/completions"
        assert http_req.headers.get("Authorization") == "Bearer gsk-testkey123"

        # Check payload
        payload = json.loads(http_req.data.decode("utf-8"))
        assert payload["model"] == "llama-3.3-70b-versatile"
        assert payload["messages"][1]["content"] == "Hello world"

        # 2nd call: should hit SQLite cache with zero HTTP calls!
        res2 = translator.translate(req)
        assert res2.translated_text == "Halo dunia"
        assert res2.from_cache is True
        assert mock_urlopen.call_count == 1  # Unchanged!


def test_llm_sanitizes_wrapping_quotes_and_markdown() -> None:
    cfg = LLMTranslationConfig(enabled=True, api_key="test")
    translator = OpenAICompatibleTranslator(config=cfg)

    # 1. Quoted output
    resp1 = MagicMock()
    resp1.read.return_value = json.dumps(
        {"choices": [{"message": {"content": '"Selamat pagi dunia"'}}]}
    ).encode("utf-8")
    resp1.__enter__.return_value = resp1

    with patch("urllib.request.urlopen", return_value=resp1):
        res = translator.translate(TranslationRequest("Good morning world", "en", "id"))
        assert res.translated_text == "Selamat pagi dunia"

    # 2. Markdown codeblock wrapped output (with language tag)
    resp2 = MagicMock()
    resp2.read.return_value = json.dumps(
        {"choices": [{"message": {"content": "```markdown\nSelamat malam\n```"}}]}
    ).encode("utf-8")
    resp2.__enter__.return_value = resp2

    with patch("urllib.request.urlopen", return_value=resp2):
        res2 = translator.translate(TranslationRequest("Good night", "en", "id"))
        assert res2.translated_text == "Selamat malam"


def test_llm_fallback_to_local_on_http_error() -> None:
    mock_local = MagicMock(spec=BaseTranslator)
    mock_local.translate.return_value = TranslationResult(
        source_text="Hello",
        translated_text="Halo lokal",
        source_lang="en",
        target_lang="id",
    )

    cfg = LLMTranslationConfig(enabled=True, fallback_to_local=True)
    translator = OpenAICompatibleTranslator(config=cfg, fallback_engine=mock_local)

    # Mock HTTP 429 Too Many Requests
    fp = io.BytesIO(b'{"error": "rate_limited"}')
    http_error = urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/chat/completions",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=fp,
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        res = translator.translate(TranslationRequest("Hello", "en", "id"))

        # Must cleanly fallback to local engine
        assert res.translated_text == "Halo lokal"
        assert mock_local.translate.call_count == 1


def test_llm_no_fallback_when_disabled() -> None:
    mock_local = MagicMock(spec=BaseTranslator)
    cfg = LLMTranslationConfig(enabled=True, fallback_to_local=False)
    translator = OpenAICompatibleTranslator(config=cfg, fallback_engine=mock_local)

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        res = translator.translate(TranslationRequest("Hello", "en", "id"))

        assert res.translated_text == ""
        assert mock_local.translate.call_count == 0


def test_llm_test_connection() -> None:
    cfg = LLMTranslationConfig(enabled=True, api_key="secret")
    translator = OpenAICompatibleTranslator(config=cfg)

    # Success case
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {"choices": [{"message": {"content": "Halo"}}]}
    ).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg = translator.test_connection()
        assert ok is True
        assert "Halo" in msg

    # HTTP 401 Unauthorized failure
    fp = io.BytesIO(b'{"error": "invalid_api_key"}')
    http_err = urllib.error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=fp)
    with patch("urllib.request.urlopen", side_effect=http_err):
        ok, msg = translator.test_connection()
        assert ok is False
        assert "401" in msg
