from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "sidecars" / "bambuddy-runtime-repair") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "sidecars" / "bambuddy-runtime-repair"))


from app import main as sidecar_main  # noqa: E402
from app.models import RestoreFromRequest, RestoreVerifyRequest  # noqa: E402
from app.repair import merge_notes, merge_tags, restore_archive_from_source, restore_verify_after_merge  # noqa: E402


CREATE_PRINT_ARCHIVES_SQL = """
CREATE TABLE print_archives (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT,
    status TEXT,
    failure_reason TEXT,
    is_favorite INTEGER,
    cost REAL,
    quantity INTEGER,
    external_url TEXT,
    tags TEXT,
    notes TEXT,
    file_path TEXT,
    file_size INTEGER,
    content_hash TEXT,
    thumbnail_path TEXT,
    print_name TEXT,
    print_time_seconds INTEGER,
    filament_used_grams REAL,
    filament_type TEXT,
    filament_color TEXT,
    layer_height REAL,
    total_layers INTEGER,
    nozzle_diameter REAL,
    nozzle_temperature INTEGER,
    sliced_for_model TEXT,
    designer TEXT,
    makerworld_url TEXT,
    extra_data TEXT
)
"""


def _create_test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "bambuddy.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(CREATE_PRINT_ARCHIVES_SQL)
        connection.execute(
            """
            INSERT INTO print_archives (
                id, started_at, completed_at, created_at, status, failure_reason,
                is_favorite, cost, quantity, external_url, tags, notes,
                file_path, file_size, content_hash, thumbnail_path,
                print_name, print_time_seconds, filament_used_grams, filament_type,
                filament_color, layer_height, total_layers, nozzle_diameter,
                nozzle_temperature, sliced_for_model, designer, makerworld_url,
                extra_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                191,
                "2026-04-02T16:37:22.828591",
                "2026-04-02T23:58:56.496148",
                "2026-04-02T16:37:22",
                "completed",
                None,
                1,
                None,
                None,
                None,
                "Hueforge,exception:missing_3mf,replaced_by:200",
                "[RECOVERY_AUDIT_V1]\n{\"replaced_by_archive_id\":200}",
                "",
                0,
                None,
                None,
                "Captain America - Stainglass-style Hueforge",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                '{"no_3mf_available": true, "_print_data": {"subtask_name": "200x200 - AMS Ready - Slice & Print"}}',
            ),
        )
        connection.execute(
            """
            INSERT INTO print_archives (
                id, started_at, completed_at, created_at, status, failure_reason,
                is_favorite, cost, quantity, external_url, tags, notes,
                file_path, file_size, content_hash, thumbnail_path,
                print_name, print_time_seconds, filament_used_grams, filament_type,
                filament_color, layer_height, total_layers, nozzle_diameter,
                nozzle_temperature, sliced_for_model, designer, makerworld_url,
                extra_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                200,
                None,
                "2026-04-04T21:45:30.757481",
                "2026-04-04T21:45:30",
                "archived",
                None,
                0,
                1.47,
                None,
                None,
                "repair:recovered,recovered_from:191,recovery_source:sd_cache_3mf,f:14,s:10",
                "[RECOVERY_AUDIT_V1]\n{\"recovered_from_archive_id\":191}\n\n[HA_ENRICHMENT_V1]\n{\"source\":\"archived_filament_slots\"}",
                "archive/1/20260404_174530_200x200 - AMS Ready - Slice & Print/200x200 - AMS Ready - Slice & Print.3mf",
                12005447,
                "4eba6b4eace8d55a2c39c583e610ab7dd3de22dba54ab6d98c16f68afd001953",
                "archive/1/20260404_174530_200x200 - AMS Ready - Slice & Print/thumbnail.png",
                "Captain America - Stained Glass Style",
                22671,
                58.98,
                "PLA",
                "#000000,#042F56,#0056B8,#FFFFFF,#E8DBB7,#DE4343,#F99963,#9D2235",
                0.08,
                26,
                0.4,
                220,
                "P1S",
                "Canadian Gamer",
                "https://makerworld.com/en/models/709013",
                '{"print_time_seconds": 22671, "designer": "Canadian Gamer"}',
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


def test_merge_tags_excludes_fallback_markers_and_preserves_target() -> None:
    merged = merge_tags(
        "Hueforge,exception:missing_3mf,replaced_by:200",
        "repair:recovered,recovered_from:191,recovery_source:sd_cache_3mf,f:14,s:10",
        ["exception:missing_3mf", "replaced_by:*"],
        [],
    )

    assert merged is not None
    assert "Hueforge" in merged
    assert "repair:recovered" in merged
    assert "exception:missing_3mf" not in merged
    assert "replaced_by:200" not in merged


def test_merge_notes_preserves_target_structured_blocks() -> None:
    merged = merge_notes(
        "[RECOVERY_AUDIT_V1]\n{\"replaced_by_archive_id\":200}",
        "[RECOVERY_AUDIT_V1]\n{\"recovered_from_archive_id\":191}\n\n[HA_ENRICHMENT_V1]\n{\"source\":\"archived_filament_slots\"}",
    )

    assert merged is not None
    assert "recovered_from_archive_id" in merged
    assert "HA_ENRICHMENT_V1" in merged
    assert "replaced_by_archive_id" not in merged


def test_restore_archive_from_source_builds_db_backed_dry_run_plan(tmp_path: Path) -> None:
    db_path = _create_test_db(tmp_path)
    request = RestoreFromRequest(
        source_archive_id=191,
        target_archive_id=200,
        dry_run=True,
    )

    response = restore_archive_from_source(db_path, request)
    actions = {action.field: action for action in response.field_actions}

    assert response.applied is False
    assert response.updated is False
    assert response.field_action_summary.copy_count >= 4
    assert "source archive is incomplete" in " ".join(response.warnings)

    assert actions["started_at"].action == "copy"
    assert actions["started_at"].target_after == "2026-04-02T16:37:22.828591"

    assert actions["status"].action == "copy"
    assert actions["status"].target_after == "completed"

    assert actions["is_favorite"].action == "copy"
    assert actions["is_favorite"].target_after is True

    assert actions["file_path"].action == "keep_target"
    assert actions["file_path"].target_after == (
        "archive/1/20260404_174530_200x200 - AMS Ready - Slice & Print/"
        "200x200 - AMS Ready - Slice & Print.3mf"
    )

    assert actions["tags"].action == "merge"
    assert "Hueforge" in (actions["tags"].target_after or "")
    assert "exception:missing_3mf" not in (actions["tags"].target_after or "")

    assert actions["extra_data.no_3mf_available"].action == "skip_disallowed"


def test_restore_archive_from_source_apply_updates_target_fields(tmp_path: Path) -> None:
    db_path = _create_test_db(tmp_path)

    response = restore_archive_from_source(
        db_path,
        RestoreFromRequest(source_archive_id=191, target_archive_id=200, dry_run=False),
    )

    assert response.applied is True
    assert response.updated is True
    assert "started_at" in response.updated_fields
    assert "status" in response.updated_fields
    assert "tags" in response.updated_fields

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT started_at, completed_at, created_at, status, is_favorite, tags, notes FROM print_archives WHERE id = 200"
        ).fetchone()
        assert row is not None
        assert row[0] == "2026-04-02T16:37:22.828591"
        assert row[1] == "2026-04-02T23:58:56.496148"
        assert row[2] == "2026-04-02T16:37:22"
        assert row[3] == "completed"
        assert row[4] == 1
        assert "Hueforge" in row[5]
    finally:
        connection.close()


def test_restore_archive_from_source_reports_skip_equal_for_already_matched_field(tmp_path: Path) -> None:
    db_path = _create_test_db(tmp_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("UPDATE print_archives SET is_favorite = 1 WHERE id = 200")
        connection.commit()
    finally:
        connection.close()

    response = restore_archive_from_source(
        db_path,
        RestoreFromRequest(source_archive_id=191, target_archive_id=200, dry_run=True),
    )
    actions = {action.field: action for action in response.field_actions}

    assert actions["is_favorite"].action == "skip_equal"


def test_restore_verify_after_merge_reports_remaining_differences_and_blocks_delete(tmp_path: Path) -> None:
    db_path = _create_test_db(tmp_path)

    response = restore_verify_after_merge(
        db_path,
        RestoreVerifyRequest(
            source_archive_id=191,
            target_archive_id=200,
            remove_original=True,
            dry_run=True,
        ),
    )

    assert response.verified is False
    assert response.removable is False
    assert response.source_removed is False
    assert response.blocking_difference_count >= 1
    assert response.non_blocking_difference_count >= 1
    assert response.remaining_difference_count >= 1
    assert any(diff.field == "started_at" for diff in response.remaining_differences)


def test_restore_verify_after_merge_can_remove_source_when_no_actionable_differences(tmp_path: Path) -> None:
    db_path = _create_test_db(tmp_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE print_archives
            SET started_at = ?, completed_at = ?, created_at = ?, status = ?, is_favorite = ?,
                tags = ?, notes = ?
            WHERE id = ?
            """,
            (
                "2026-04-02T16:37:22.828591",
                "2026-04-02T23:58:56.496148",
                "2026-04-02T16:37:22",
                "completed",
                1,
                "repair:recovered,recovered_from:191,recovery_source:sd_cache_3mf,f:14,s:10,Hueforge",
                "[RECOVERY_AUDIT_V1]\n{\"recovered_from_archive_id\":191}\n\n[HA_ENRICHMENT_V1]\n{\"source\":\"archived_filament_slots\"}",
                200,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    verify_response = restore_verify_after_merge(
        db_path,
        RestoreVerifyRequest(
            source_archive_id=191,
            target_archive_id=200,
            remove_original=False,
            dry_run=True,
        ),
    )
    assert verify_response.verified is True
    assert verify_response.remaining_difference_count == 0
    assert verify_response.blocking_difference_count == 0

    delete_response = restore_verify_after_merge(
        db_path,
        RestoreVerifyRequest(
            source_archive_id=191,
            target_archive_id=200,
            remove_original=True,
            dry_run=False,
        ),
    )
    assert delete_response.verified is True
    assert delete_response.source_removed is True

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT id FROM print_archives WHERE id = 191").fetchone()
        assert row is None
    finally:
        connection.close()


def test_restore_verify_endpoint_returns_structured_response(tmp_path: Path, monkeypatch) -> None:
    db_path = _create_test_db(tmp_path)
    monkeypatch.setenv("REPAIR_API_TOKEN", "test-token")
    monkeypatch.setenv("BAMBUDDY_DB_PATH", str(db_path))

    client = TestClient(sidecar_main.app)
    response = client.post(
        "/admin/archive-restore-verify",
        headers={"Authorization": "Bearer test-token"},
        json={
            "source_archive_id": 191,
            "target_archive_id": 200,
            "remove_original": False,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_archive_id"] == 191
    assert body["target_archive_id"] == 200
    assert body["remaining_difference_count"] >= 1
    assert body["blocking_difference_count"] >= 1
    assert isinstance(body["remaining_differences"], list)


def test_restore_from_endpoint_applies_and_returns_updated_fields(tmp_path: Path, monkeypatch) -> None:
    db_path = _create_test_db(tmp_path)
    monkeypatch.setenv("REPAIR_API_TOKEN", "test-token")
    monkeypatch.setenv("BAMBUDDY_DB_PATH", str(db_path))

    client = TestClient(sidecar_main.app)
    response = client.post(
        "/admin/archive-restore-from",
        headers={"Authorization": "Bearer test-token"},
        json={
            "source_archive_id": 191,
            "target_archive_id": 200,
            "dry_run": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["updated"] is True
    assert "started_at" in body["updated_fields"]
