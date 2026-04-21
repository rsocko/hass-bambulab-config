from __future__ import annotations

import sqlite3
from pathlib import Path

from app.metadata_correction import AUDIT_MARKER, correct_archive_metadata
from app.metadata_correction import compute_archive_metadata_revision
from app.models import ArchiveMetadataCorrectionFields, ArchiveMetadataCorrectionRequest


CREATE_ARCHIVES_SQL = """
CREATE TABLE print_archives (
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
            INSERT INTO print_archives (
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
            "SELECT created_at, filament_used_grams, cost, quantity, external_url, notes FROM print_archives WHERE id = ?",
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


def test_metadata_correction_revision_ignores_notes_only_changes(tmp_path: Path) -> None:
    db_path = _create_metadata_db(tmp_path)

    baseline = correct_archive_metadata(
        db_path,
        ArchiveMetadataCorrectionRequest(
            archive_id=101,
            fields=ArchiveMetadataCorrectionFields(filament_used_grams=42.5),
            reason="Baseline preview",
            request_id="corr-baseline",
            dry_run=True,
        ),
    )

    apply_response = correct_archive_metadata(
        db_path,
        ArchiveMetadataCorrectionRequest(
            archive_id=101,
            fields=ArchiveMetadataCorrectionFields(cost=2.5),
            reason="Apply change that appends audit notes",
            request_id="corr-apply",
            dry_run=False,
        ),
    )

    preview_response = correct_archive_metadata(
        db_path,
        ArchiveMetadataCorrectionRequest(
            archive_id=101,
            fields=ArchiveMetadataCorrectionFields(filament_used_grams=40.0),
            reason="Fresh preview after notes changed",
            request_id="corr-preview",
            expected_archive_revision=apply_response.archive_revision,
            dry_run=True,
        ),
    )

    assert baseline.archive_revision != ""
    assert apply_response.archive_revision != ""
    assert preview_response.changed is True
    assert preview_response.updated_fields == ["filament_used_grams"]


def test_metadata_correction_revision_treats_blank_and_null_as_equal() -> None:
    blank_snapshot = {
        "started_at": "",
        "completed_at": "2026-04-19T22:35:36.838594",
        "created_at": "2026-04-19T22:35:36",
        "status": "archived",
        "failure_reason": "",
        "filament_used_grams": 20.3,
        "cost": 0.41,
        "quantity": 1,
        "external_url": "",
    }
    null_snapshot = {
        "started_at": None,
        "completed_at": "2026-04-19T22:35:36.838594",
        "created_at": "2026-04-19T22:35:36",
        "status": "archived",
        "failure_reason": None,
        "filament_used_grams": 20.3,
        "cost": 0.41,
        "quantity": 1,
        "external_url": None,
    }

    assert compute_archive_metadata_revision(blank_snapshot) == compute_archive_metadata_revision(null_snapshot)