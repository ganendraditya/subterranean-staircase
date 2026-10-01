"""SQLite-backed subtitle session history recorder and exporter (.srt / .vtt).

Records live translation events (timestamps, source language, target language,
original text, translated text, and duration) with full transactional safety.
Allows exporting recorded sessions to standard SubRip (.srt) and WebVTT (.vtt) formats.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import List, Optional


def get_default_history_db_path() -> Path:
    """Return default history database path: ~/.cache/subtitle-translator/session_history.db"""
    base_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base_dir / "subtitle-translator" / "session_history.db"


@dataclass
class SubtitleRecord:
    """Represents a single captured and translated subtitle entry."""
    id: Optional[int]
    session_id: str
    start_time: float
    end_time: float
    source_lang: str
    target_lang: str
    source_text: str
    translated_text: str
    created_at: float = 0.0


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SubRip (.srt) timestamp format: HH:MM:SS,mmm"""
    total_ms = max(0, int(round(seconds * 1000.0)))
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """Format seconds into WebVTT (.vtt) timestamp format: HH:MM:SS.mmm"""
    total_ms = max(0, int(round(seconds * 1000.0)))
    hours = total_ms // 3600000
    minutes = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


class SessionHistoryRecorder:
    """High-concurrency SQLite session history recorder and subtitle formatter."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or get_default_history_db_path()
        self._write_lock = threading.Lock()
        self._local = threading.local()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def close(self) -> None:
        """Close thread-local SQLite connection if open."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or initialize a thread-local persistent SQLite connection with WAL mode."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=True,
            )
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Initialize session history schema and indexes."""
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subtitle_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        start_time REAL NOT NULL,
                        end_time REAL NOT NULL,
                        source_lang TEXT NOT NULL,
                        target_lang TEXT NOT NULL,
                        source_text TEXT NOT NULL,
                        translated_text TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_records_session
                    ON subtitle_records (session_id, start_time);
                    """
                )

    def record(
        self,
        session_id: str,
        start_time: float,
        end_time: float,
        source_lang: str,
        target_lang: str,
        source_text: str,
        translated_text: str,
    ) -> Optional[int]:
        """Record a translated subtitle event into the database."""
        src_clean = source_text.strip()
        trans_clean = translated_text.strip()
        if not src_clean or not trans_clean:
            return None

        # Ensure valid end time
        if end_time <= start_time:
            end_time = start_time + 2.0  # default 2-second display window

        now = time.time()
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO subtitle_records (
                        session_id, start_time, end_time,
                        source_lang, target_lang,
                        source_text, translated_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        session_id,
                        start_time,
                        end_time,
                        source_lang.strip().lower(),
                        target_lang.strip().lower(),
                        src_clean,
                        trans_clean,
                        now,
                    ),
                )
                return cursor.lastrowid

    def update_last_end_time(self, session_id: str, end_time: float) -> None:
        """Update end timestamp of the most recent record in this session."""
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    UPDATE subtitle_records
                    SET end_time = ?
                    WHERE id = (
                        SELECT id FROM subtitle_records
                        WHERE session_id = ?
                        ORDER BY id DESC LIMIT 1
                    );
                    """,
                    (end_time, session_id),
                )

    def get_records(self, session_id: Optional[str] = None) -> List[SubtitleRecord]:
        """Fetch records ordered chronologically. If session_id is None, fetch all records."""
        conn = self._get_connection()
        if session_id:
            cursor = conn.execute(
                """
                SELECT id, session_id, start_time, end_time, source_lang, target_lang, source_text, translated_text, created_at
                FROM subtitle_records
                WHERE session_id = ?
                ORDER BY start_time ASC, id ASC;
                """,
                (session_id,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, session_id, start_time, end_time, source_lang, target_lang, source_text, translated_text, created_at
                FROM subtitle_records
                ORDER BY start_time ASC, id ASC;
                """
            )

        rows = cursor.fetchall()
        return [
            SubtitleRecord(
                id=r[0],
                session_id=r[1],
                start_time=r[2],
                end_time=r[3],
                source_lang=r[4],
                target_lang=r[5],
                source_text=r[6],
                translated_text=r[7],
                created_at=r[8],
            )
            for r in rows
        ]

    def count(self, session_id: Optional[str] = None) -> int:
        """Return total record count for the given session or all sessions."""
        conn = self._get_connection()
        if session_id:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM subtitle_records WHERE session_id = ?;", (session_id,)
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM subtitle_records;")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def clear(self, session_id: Optional[str] = None) -> None:
        """Clear records for a given session or entire database."""
        with self._write_lock:
            conn = self._get_connection()
            with conn:
                if session_id:
                    conn.execute("DELETE FROM subtitle_records WHERE session_id = ?;", (session_id,))
                else:
                    conn.execute("DELETE FROM subtitle_records;")

    def export_srt(
        self,
        session_id: Optional[str] = None,
        use_translated: bool = True,
        relative_to_start: bool = True,
    ) -> str:
        """Generate standard SubRip (.srt) subtitle string."""
        records = self.get_records(session_id)
        if not records:
            return ""

        # Avoid calculating multi-session offset against the first session's start time
        apply_relative = relative_to_start and session_id is not None
        t0 = records[0].start_time if apply_relative else 0.0
        lines: list[str] = []

        for idx, rec in enumerate(records, start=1):
            s_rel = max(0.0, rec.start_time - t0)
            e_rel = max(s_rel + 0.5, rec.end_time - t0)

            t_start_str = format_srt_timestamp(s_rel)
            t_end_str = format_srt_timestamp(e_rel)
            text_str = rec.translated_text if use_translated else rec.source_text

            lines.append(f"{idx}\n{t_start_str} --> {t_end_str}\n{text_str}\n")

        return "\n".join(lines).strip() + "\n"

    def export_vtt(
        self,
        session_id: Optional[str] = None,
        use_translated: bool = True,
        relative_to_start: bool = True,
    ) -> str:
        """Generate standard WebVTT (.vtt) subtitle string."""
        records = self.get_records(session_id)
        header = "WEBVTT\n\n"
        if not records:
            return header

        apply_relative = relative_to_start and session_id is not None
        t0 = records[0].start_time if apply_relative else 0.0
        cues: list[str] = []

        for idx, rec in enumerate(records, start=1):
            s_rel = max(0.0, rec.start_time - t0)
            e_rel = max(s_rel + 0.5, rec.end_time - t0)

            t_start_str = format_vtt_timestamp(s_rel)
            t_end_str = format_vtt_timestamp(e_rel)
            text_str = rec.translated_text if use_translated else rec.source_text

            cues.append(f"{idx}\n{t_start_str} --> {t_end_str}\n{text_str}\n")

        return header + "\n".join(cues).strip() + "\n"
