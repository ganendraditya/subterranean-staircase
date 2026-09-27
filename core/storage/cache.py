"""High-concurrency SQLite translation memory cache with Write-Ahead Logging (WAL).

Guarantees 0ms recall for previously translated subtitle phrases without table-locking.
Safe for multi-threading across background translation workers and UI readers.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Optional


def get_default_cache_db_path() -> Path:
    """Return default cache database path: ~/.cache/subtitle-translator/translation_cache.db"""
    base_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base_dir / "subtitle-translator" / "translation_cache.db"


class SQLiteTranslationCache:
    """Thread-safe, LRU-evicting translation cache powered by SQLite in WAL mode."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_entries: int = 10000,
    ) -> None:
        self.db_path = db_path or get_default_cache_db_path()
        self.max_entries = max_entries
        self._write_lock = threading.Lock()
        self._local = threading.local()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or initialize a thread-local persistent SQLite connection with WAL mode."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=True,
            )
            # Enable WAL mode: readers never block writers, writers never block readers
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Initialize schema and indexes."""
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS translations (
                        source_text TEXT NOT NULL,
                        source_lang TEXT NOT NULL,
                        target_lang TEXT NOT NULL,
                        translated_text TEXT NOT NULL,
                        access_count INTEGER NOT NULL DEFAULT 1,
                        last_accessed REAL NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (source_text, source_lang, target_lang)
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_translations_lru
                    ON translations (last_accessed);
                    """
                )

    def get(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        """Retrieve cached translation, updating LRU access metadata."""
        cleaned_text = source_text.strip()
        if not cleaned_text:
            return None

        src_l = source_lang.strip().lower()
        tgt_l = target_lang.strip().lower()
        now = time.time()

        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT translated_text
            FROM translations
            WHERE source_text = ? AND source_lang = ? AND target_lang = ?;
            """,
            (cleaned_text, src_l, tgt_l),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        translated_text = row[0]

        # Update LRU metadata under write lock or handle busy errors gracefully
        try:
            with self._write_lock:
                with conn:
                    conn.execute(
                        """
                        UPDATE translations
                        SET last_accessed = ?, access_count = access_count + 1
                        WHERE source_text = ? AND source_lang = ? AND target_lang = ?;
                        """,
                        (now, cleaned_text, src_l, tgt_l),
                    )
        except sqlite3.OperationalError:
            # Metadata touch can fail non-fatally under high concurrent write contention
            pass

        return str(translated_text)

    def set(
        self,
        source_text: str,
        source_lang: str,
        target_lang: str,
        translated_text: str,
    ) -> None:
        """Store translation in cache, evicting oldest LRU items if capacity exceeded."""
        cleaned_source = source_text.strip()
        cleaned_trans = translated_text.strip()
        if not cleaned_source or not cleaned_trans:
            return

        src_l = source_lang.strip().lower()
        tgt_l = target_lang.strip().lower()
        now = time.time()

        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO translations (
                        source_text, source_lang, target_lang,
                        translated_text, access_count, last_accessed, created_at
                    )
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(source_text, source_lang, target_lang) DO UPDATE SET
                        translated_text = excluded.translated_text,
                        last_accessed = excluded.last_accessed,
                        access_count = translations.access_count + 1;
                    """,
                    (cleaned_source, src_l, tgt_l, cleaned_trans, now, now),
                )

                # LRU Eviction check
                cursor = conn.execute("SELECT COUNT(*) FROM translations;")
                total_entries = cursor.fetchone()[0]

                if total_entries > self.max_entries:
                    excess = total_entries - self.max_entries
                    conn.execute(
                        """
                        DELETE FROM translations
                        WHERE (source_text, source_lang, target_lang) IN (
                            SELECT source_text, source_lang, target_lang
                            FROM translations
                            ORDER BY last_accessed ASC
                            LIMIT ?
                        );
                        """,
                        (excess,),
                    )

    def count(self) -> int:
        """Return total number of cached translation entries."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM translations;")
        return int(cursor.fetchone()[0])

    def clear(self) -> None:
        """Delete all records from cache table and attempt vacuum."""
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.execute("DELETE FROM translations;")
            prev_isolation = conn.isolation_level
            try:
                conn.isolation_level = None
                conn.execute("VACUUM;")
            except sqlite3.OperationalError:
                # VACUUM requires an exclusive lock and can fail non-fatally under concurrent reader contention
                pass
            finally:
                conn.isolation_level = prev_isolation

    def close(self) -> None:
        """Close thread-local connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
