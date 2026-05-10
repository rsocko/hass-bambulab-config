from pathlib import Path

from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app
from app.settings import Settings


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None


def _make_settings(db_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.example",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="test-client",
        manyfold_client_secret="test-secret",
        manyfold_oauth_scopes=None,
        db_path=db_path,
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="test",
        image_revision="test",
        image_created="test",
    )


def _create_client(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path), manyfold_client=FakeManyfoldClient())
    client = TestClient(app)
    client.__enter__()
    return client, db_path


def test_unified_queue_entry_crud_happy_path(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "working_group",
                "source_id": "wg-001",
                "title": "Bracket Batch",
                "copies": 2,
                "duration_bucket": "2-4h",
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["success"] is True
        entry_id = created["entry"]["queue_entry_id"]
        assert created["entry"]["source_id"] == "wg-001"
        assert created["entry"]["copies"] == 2
        assert created["entry"]["duration_bucket"] == "medium"

        get_response = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert get_response.status_code == 200
        assert get_response.json()["entry"]["queue_entry_id"] == entry_id

        to_ready_response = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={
                "state": "ready",
                "rank": 1,
            },
        )
        assert to_ready_response.status_code == 200

        update_response = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={
                "state": "started",
                "copies_completed": 1,
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["entry"]["state"] == "started"
        assert updated["entry"]["copies_completed"] == 1
        assert updated["entry"]["rank"] == 1

        list_response = client.get("/api/unified-queue/entries", params={"state": "started", "limit": 10, "offset": 0})
        assert list_response.status_code == 200
        listed = list_response.json()
        assert listed["success"] is True
        assert listed["pagination"]["total"] == 1
        assert listed["entries"][0]["queue_entry_id"] == entry_id

        delete_response = client.delete(f"/api/unified-queue/entries/{entry_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        missing_after_delete = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert missing_after_delete.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_unified_queue_validation_and_error_responses(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        invalid_source_kind = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "bad", "source_id": "x", "copies": 1},
        )
        assert invalid_source_kind.status_code == 400
        assert invalid_source_kind.json()["success"] is False

        missing_source_id = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "working_file", "copies": 1},
        )
        assert missing_source_id.status_code == 400

        invalid_pagination = client.get("/api/unified-queue/entries", params={"limit": 0})
        assert invalid_pagination.status_code == 400

        not_found_patch = client.patch("/api/unified-queue/entries/missing-id", json={"state": "done"})
        assert not_found_patch.status_code == 404

        not_found_delete = client.delete("/api/unified-queue/entries/missing-id")
        assert not_found_delete.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_unified_queue_state_transition_matrix_and_audit_log(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Transition Test", "state": "idea", "copies": 1},
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        invalid_transition = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "started"},
        )
        assert invalid_transition.status_code == 400
        invalid_payload = invalid_transition.json()
        assert invalid_payload["error"] == "invalid_transition"
        assert invalid_payload["from_state"] == "idea"
        assert invalid_payload["to_state"] == "started"

        to_todo = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "todo"},
            headers={"x-actor": "test-suite"},
        )
        assert to_todo.status_code == 200
        assert to_todo.json()["entry"]["state"] == "todo"

        to_ready = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "ready"},
            headers={"x-actor": "test-suite"},
        )
        assert to_ready.status_code == 200

        to_started = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "started"},
            headers={"x-actor": "test-suite"},
        )
        assert to_started.status_code == 200

        to_blocked = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "blocked", "blocked_reason": "waiting for filament"},
            headers={"x-actor": "test-suite"},
        )
        assert to_blocked.status_code == 200

        back_to_ready = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "ready", "queue_notes": "recovered"},
            headers={"x-actor": "test-suite"},
        )
        assert back_to_ready.status_code == 200
        assert back_to_ready.json()["entry"]["state"] == "ready"

        connection = connect(db_path)
        try:
            rows = connection.execute(
                """
                SELECT event_type, entity_type, entity_id, payload_json
                FROM model_catalog_events
                WHERE event_type = 'unified_queue_state_transition'
                  AND entity_id = ?
                ORDER BY id ASC
                """,
                (entry_id,),
            ).fetchall()
        finally:
            connection.close()

        # We performed 5 valid transitions after creation:
        # idea->todo, todo->ready, ready->started, started->blocked, blocked->ready
        assert len(rows) == 5
        assert str(rows[0]["event_type"]) == "unified_queue_state_transition"
        assert str(rows[0]["entity_type"]) == "unified_queue_entry"
        assert str(rows[0]["entity_id"]) == entry_id
    finally:
        client.__exit__(None, None, None)


def test_unified_queue_migrate_legacy_metadata_creates_entries_and_preserves_fields(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        connection = connect(db_path)
        try:
            # Legacy source model queue metadata
            rows = [
                ("manyfold_model", "gridfinity-bin", "model_catalog", "to_print_status", '"queued"', "str"),
                ("manyfold_model", "gridfinity-bin", "model_catalog", "to_print_priority", "8", "int"),
                ("manyfold_model", "tool-rack", "model_catalog", "to_print_status", '"done"', "str"),
                ("manyfold_model", "tool-rack", "model_catalog", "to_print_priority", "3", "int"),
                ("manyfold_model", "phone-stand", "model_catalog", "to_print_status", '"none"', "str"),
                ("manyfold_model", "phone-stand", "model_catalog", "to_print_priority", "10", "int"),
            ]
            for entity_type, entity_id, ns, key, value_json, value_type in rows:
                connection.execute(
                    """
                    INSERT INTO model_catalog_custom_fields (
                        entity_type, entity_id, field_namespace, field_key, field_value_json, value_type, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (entity_type, entity_id, ns, key, value_json, value_type),
                )
            connection.commit()
        finally:
            connection.close()

        migrate = client.post("/api/unified-queue/migrate-legacy", json={"actor": "test-suite"})
        assert migrate.status_code == 200
        payload = migrate.json()
        assert payload["success"] is True
        assert payload["legacy_models_detected"] == 3
        assert payload["candidates"] == 2
        assert payload["migrated"] == 2
        assert payload["skipped_none"] == 1

        listing = client.get("/api/unified-queue/entries", params={"source_kind": "catalog_model", "limit": 10, "offset": 0})
        assert listing.status_code == 200
        entries = listing.json()["entries"]
        refs = {entry["source_ref"]: entry for entry in entries}
        assert "gridfinity-bin" in refs
        assert "tool-rack" in refs
        assert refs["gridfinity-bin"]["state"] == "todo"
        assert refs["tool-rack"]["state"] == "done"

        # Verify legacy custom fields still exist (no data loss)
        connection = connect(db_path)
        try:
            count_row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM model_catalog_custom_fields
                WHERE field_key IN ('to_print_status', 'to_print_priority')
                """
            ).fetchone()
        finally:
            connection.close()
        assert int(count_row["count"]) == 6

        # Idempotency: re-run migration should not create duplicates
        rerun = client.post("/api/unified-queue/migrate-legacy", json={"actor": "test-suite"})
        assert rerun.status_code == 200
        rerun_payload = rerun.json()
        assert rerun_payload["migrated"] == 0
        assert rerun_payload["skipped_existing"] == 2
    finally:
        client.__exit__(None, None, None)
