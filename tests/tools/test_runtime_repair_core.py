from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.bambuddy.runtime_repair_core import RepairValues, normalize_datetime, repair_archive_runtime


def _create_archive_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "bambuddy.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE print_archives (
                id INTEGER PRIMARY KEY,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT,
                status TEXT,
                failure_reason TEXT,
                notes TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO print_archives (
                id, started_at, completed_at, created_at, status, failure_reason, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                230,
                "2026-04-06 16:31:27.968799",
                "2026-04-12 23:17:01.640523",
                "2026-04-12 23:17:01.640523",
                "failed",
                "Adhesion failure",
                "existing note",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


def test_normalize_datetime_preserves_bambuddy_sqlite_shape() -> None:
    assert normalize_datetime("2026-04-06T20:31:27.968799+00:00", "started_at") == "2026-04-06 20:31:27.968799"
    assert normalize_datetime("2026-04-06T15:31:27.968799-05:00", "started_at") == "2026-04-06 20:31:27.968799"
    assert normalize_datetime("2026-04-06T20:31:27.968799", "started_at") == "2026-04-06 20:31:27.968799"
    assert normalize_datetime("2026-04-06T20:31:27Z", "started_at") == "2026-04-06 20:31:27.000000"


def test_repair_archive_runtime_writes_plain_sqlite_datetimes(tmp_path: Path) -> None:
    db_path = _create_archive_db(tmp_path)

    result = repair_archive_runtime(
        db_path=db_path,
        archive_id=230,
        values=RepairValues(
            started_at="2026-04-06T20:31:27.968799+00:00",
            completed_at="2026-04-06T20:42:27.968799+00:00",
            created_at="2026-04-06T20:31:27.968799+00:00",
            audit_note="runtime repair test",
        ),
        apply=True,
    )

    assert result.changed is True
    assert result.after["started_at"] == "2026-04-06 20:31:27.968799"
    assert result.after["completed_at"] == "2026-04-06 20:42:27.968799"
    assert result.after["created_at"] == "2026-04-06 20:31:27.968799"
    assert "+00:00" not in result.after["started_at"]
    assert "T" not in result.after["started_at"]
    assert "[RUNTIME_REPAIR_V1]" in result.after["notes"]

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT started_at, completed_at, created_at, notes FROM print_archives WHERE id = ?",
            (230,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row["started_at"] == "2026-04-06 20:31:27.968799"
    assert row["completed_at"] == "2026-04-06 20:42:27.968799"
    assert row["created_at"] == "2026-04-06 20:31:27.968799"
    assert "+00:00" not in row["started_at"]
    assert "T" not in row["started_at"]