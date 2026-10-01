"""Unit tests for SQLite-backed Subtitle Session History Recorder and Exporter."""

from pathlib import Path
import time
import pytest

from core.storage.history import (
    SessionHistoryRecorder,
    format_srt_timestamp,
    format_vtt_timestamp,
)


def test_format_srt_timestamp() -> None:
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(1.5) == "00:00:01,500"
    assert format_srt_timestamp(65.123) == "00:01:05,123"
    assert format_srt_timestamp(3661.004) == "01:01:01,004"


def test_format_vtt_timestamp() -> None:
    assert format_vtt_timestamp(0.0) == "00:00:00.000"
    assert format_vtt_timestamp(1.5) == "00:00:01.500"
    assert format_vtt_timestamp(65.123) == "00:01:05.123"
    assert format_vtt_timestamp(3661.004) == "01:01:01.004"


def test_session_history_record_and_get(tmp_path: Path) -> None:
    db_file = tmp_path / "test_history.db"
    recorder = SessionHistoryRecorder(db_path=db_file)

    assert recorder.count() == 0

    # Insert record
    rec_id1 = recorder.record(
        session_id="sess_1",
        start_time=10.0,
        end_time=12.0,
        source_lang="en",
        target_lang="id",
        source_text="Hello world",
        translated_text="Halo dunia",
    )
    assert rec_id1 is not None

    rec_id2 = recorder.record(
        session_id="sess_1",
        start_time=13.0,
        end_time=15.0,
        source_lang="en",
        target_lang="id",
        source_text="How are you?",
        translated_text="Apa kabar?",
    )
    assert rec_id2 is not None

    # Count checks
    assert recorder.count() == 2
    assert recorder.count("sess_1") == 2
    assert recorder.count("other_sess") == 0

    records = recorder.get_records("sess_1")
    assert len(records) == 2
    assert records[0].source_text == "Hello world"
    assert records[0].translated_text == "Halo dunia"
    assert records[1].source_text == "How are you?"
    assert records[1].translated_text == "Apa kabar?"


def test_session_history_update_last_end_time(tmp_path: Path) -> None:
    db_file = tmp_path / "test_history.db"
    recorder = SessionHistoryRecorder(db_path=db_file)

    recorder.record(
        session_id="sess_1",
        start_time=1.0,
        end_time=2.0,
        source_lang="en",
        target_lang="id",
        source_text="Line 1",
        translated_text="Baris 1",
    )
    recorder.update_last_end_time("sess_1", 3.5)

    records = recorder.get_records("sess_1")
    assert len(records) == 1
    assert records[0].end_time == 3.5


def test_session_history_export_srt(tmp_path: Path) -> None:
    db_file = tmp_path / "test_history.db"
    recorder = SessionHistoryRecorder(db_path=db_file)

    # Empty export
    assert recorder.export_srt("empty_sess") == ""

    recorder.record(
        session_id="sess_1",
        start_time=10.0,
        end_time=12.5,
        source_lang="en",
        target_lang="id",
        source_text="Hello world",
        translated_text="Halo dunia",
    )
    recorder.record(
        session_id="sess_1",
        start_time=14.0,
        end_time=17.0,
        source_lang="en",
        target_lang="id",
        source_text="Goodbye",
        translated_text="Selamat tinggal",
    )

    srt_out = recorder.export_srt("sess_1", relative_to_start=True)
    expected_srt = (
        "1\n00:00:00,000 --> 00:00:02,500\nHalo dunia\n\n"
        "2\n00:00:04,000 --> 00:00:07,000\nSelamat tinggal\n"
    )
    assert srt_out == expected_srt

    # Export source text
    srt_src = recorder.export_srt("sess_1", use_translated=False, relative_to_start=True)
    assert "Hello world" in srt_src
    assert "Goodbye" in srt_src


def test_session_history_export_vtt(tmp_path: Path) -> None:
    db_file = tmp_path / "test_history.db"
    recorder = SessionHistoryRecorder(db_path=db_file)

    recorder.record(
        session_id="sess_1",
        start_time=10.0,
        end_time=12.5,
        source_lang="en",
        target_lang="id",
        source_text="Hello world",
        translated_text="Halo dunia",
    )

    vtt_out = recorder.export_vtt("sess_1", relative_to_start=True)
    assert vtt_out.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.500" in vtt_out
    assert "Halo dunia" in vtt_out


def test_session_history_clear(tmp_path: Path) -> None:
    db_file = tmp_path / "test_history.db"
    recorder = SessionHistoryRecorder(db_path=db_file)

    recorder.record("sess_1", 1.0, 2.0, "en", "id", "Text 1", "Teks 1")
    recorder.record("sess_2", 1.0, 2.0, "en", "id", "Text 2", "Teks 2")
    assert recorder.count() == 2

    recorder.clear("sess_1")
    assert recorder.count("sess_1") == 0
    assert recorder.count("sess_2") == 1

    recorder.clear()
    assert recorder.count() == 0
