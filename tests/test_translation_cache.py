"""Unit tests and concurrency stress tests for SQLiteTranslationCache in WAL mode."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import pytest

from core.storage.cache import SQLiteTranslationCache


def test_sqlite_cache_basic_crud(tmp_path: Path) -> None:
    db_file = tmp_path / "test_cache.db"
    cache = SQLiteTranslationCache(db_path=db_file, max_entries=5)

    assert cache.count() == 0
    assert cache.get("Hello", "en", "id") is None

    # Insert entry
    cache.set("Hello", "en", "id", "Halo")
    assert cache.count() == 1
    assert cache.get("Hello", "en", "id") == "Halo"

    # Case insensitivity for language codes and whitespace handling
    assert cache.get("  Hello  ", "EN", "ID") == "Halo"

    # Different language pair should not collide
    assert cache.get("Hello", "en", "ja") is None


def test_sqlite_cache_lru_eviction(tmp_path: Path) -> None:
    db_file = tmp_path / "test_lru.db"
    # Max entries = 3
    cache = SQLiteTranslationCache(db_path=db_file, max_entries=3)

    cache.set("one", "en", "id", "satu")
    time.sleep(0.01)
    cache.set("two", "en", "id", "dua")
    time.sleep(0.01)
    cache.set("three", "en", "id", "tiga")
    assert cache.count() == 3

    # Access "one" so it becomes recently used
    time.sleep(0.01)
    assert cache.get("one", "en", "id") == "satu"

    # Insert "four", capacity (3) exceeded -> oldest entry ("two") should be evicted
    time.sleep(0.01)
    cache.set("four", "en", "id", "empat")

    assert cache.count() == 3
    assert cache.get("one", "en", "id") == "satu"      # Kept
    assert cache.get("two", "en", "id") is None       # Evicted!
    assert cache.get("three", "en", "id") == "tiga"    # Kept
    assert cache.get("four", "en", "id") == "empat"    # Kept


def test_sqlite_cache_concurrent_multi_threading(tmp_path: Path) -> None:
    db_file = tmp_path / "test_concurrency.db"
    cache = SQLiteTranslationCache(db_path=db_file, max_entries=500)

    # Concurrently write 100 translations from 10 threads
    def _worker(thread_id: int) -> None:
        for i in range(10):
            word = f"word_{thread_id}_{i}"
            trans = f"terjemah_{thread_id}_{i}"
            cache.set(word, "en", "id", trans)
            retrieved = cache.get(word, "en", "id")
            assert retrieved == trans

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_worker, tid) for tid in range(10)]
        for f in futures:
            f.result()

    assert cache.count() == 100


def test_sqlite_cache_clear(tmp_path: Path) -> None:
    db_file = tmp_path / "test_clear.db"
    cache = SQLiteTranslationCache(db_path=db_file)

    cache.set("apple", "en", "id", "apel")
    cache.set("banana", "en", "id", "pisang")
    assert cache.count() == 2

    # Clear should successfully delete and vacuum without transaction error
    cache.clear()
    assert cache.count() == 0
    assert cache.get("apple", "en", "id") is None
    # Connection should still be functional after isolation level restore
    cache.set("cherry", "en", "id", "ceri")
    assert cache.get("cherry", "en", "id") == "ceri"
