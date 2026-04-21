from __future__ import annotations

import sqlite3
from pathlib import Path

from app.metadata_correction import AUDIT_MARKER, correct_archive_metadata
from app.models import ArchiveMetadataCorrectionFields, ArchiveMetadataCorrectionRequest


CREATE_ARCHIVES_SQL = """
CREATE TABLE archives (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT,
    status TEXT,
    failure_reason TEXT,
    filament_used_grams REAL,
    cost REAL,
    quantity INTEGER,
    external_url TEXT,
    notes TEXT
)
"""


def _create_metadata_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "bambuddy-metadata.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(CREATE_ARCHIVES_SQL)
        connection.execute(
            """
            INSERT INTO archives (
                id, started_at, completed_at, created_at, status, failure_reason,
                filament_used_grams, cost, quantity, external_url, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                101,
                "2026-04-10T00:00:00+00:00",
                "2026-04-10T04:00:00+00:00",
                "2026-04-10T00:00:00+00:00",
                "completed",
                None,
                42.5,
                2.35,
                1,
                None,
                "existing note",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


def test_metadata_correction_applies_advanced_archive_fields(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path)

    response = correct_archive_metadata(
        db_path,
        ArchiveMetadataCorrectionRequest(
            archive_id=101,
            fields=ArchiveMetadataCorrectionFields(
                created_at="2026-04-11T00:00:00+00:00",
                filament_used_grams=48.75,
                cost=2.60,
                quantity=2,
                external_url="https://printables.com/model/12345",
            ),
            reason="Correct archive day and advanced metadata",
            request_id="corr-101",
            dry_run=False,
        ),
    )

    assert response.applied is True
    assert response.changed is True
    assert response.updated_fields == ["created_at", "filament_used_grams", "cost", "quantity", "external_url"]
    assert response.after["filament_used_grams"] == 48.75
    assert response.after["cost"] == 2.6
    assert response.after["quantity"] == 2
    assert response.after["external_url"] == "https://printables.com/model/12345"
    assert response.derived_impacts["created_day_changed"] is True
    assert response.derived_impacts["filament_used_grams_changed"] is True
    assert response.derived_impacts["cost_changed"] is True
    assert response.derived_impacts["quantity_changed"] is True
    assert response.derived_impacts["external_url_changed"] is True
    assert any("filament_used_grams" in warning for warning in response.warnings)
    assert any("cost" in warning for warning in response.warnings)

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT created_at, filament_used_grams, cost, quantity, external_url, notes FROM archives WHERE id = ?",
            (101,),
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        "2026-04-11T00:00:00+00:00",
        48.75,
        2.6,
        2,
        "https://printables.com/model/12345",
        row[5],
    )
    assert AUDIT_MARKER in row[5]
    assert "external_url" in row[5]
    assert "filament_used_grams" in row[5]