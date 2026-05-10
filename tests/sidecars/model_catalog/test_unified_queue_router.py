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


def test_queue_entries_v1_filters_sort_and_pagination(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        seeds = [
            {
                "source_kind": "catalog_model",
                "source_id": "cat-1",
                "title": "Catalog One",
                "state": "todo",
                "rank": 3,
                "duration_bucket": "quick",
            },
            {
                "source_kind": "working_group",
                "source_id": "wg-1",
                "title": "WG One",
                "state": "ready",
                "rank": 1,
                "duration_bucket": "overnight",
            },
            {
                "source_kind": "working_file",
                "source_id": "wf-1",
                "title": "WF One",
                "state": "started",
                "rank": 2,
                "duration_bucket": "medium",
            },
            {
                "source_kind": "idea",
                "title": "Idea One",
                "state": "idea",
                "rank": 4,
                "duration_bucket": "marathon",
            },
        ]
        for seed in seeds:
            response = client.post("/api/unified-queue/entries", json=seed)
            assert response.status_code == 200

        filtered = client.get(
            "/api/v1/queues/printer-main/entries",
            params={
                "state": "todo,ready",
                "source_kind": "catalog_model,working_group",
                "sort": "rank:asc",
                "limit": 10,
                "offset": 0,
            },
        )
        assert filtered.status_code == 200
        payload = filtered.json()
        assert payload["success"] is True
        assert payload["printer_id"] == "printer-main"
        assert payload["pagination"]["total"] == 2
        assert [entry["source_ref"] for entry in payload["entries"]] == ["wg-1", "cat-1"]

        paged = client.get(
            "/api/v1/queues/printer-main/entries",
            params={"sort": "rank:asc", "limit": 2, "offset": 1},
        )
        assert paged.status_code == 200
        page_payload = paged.json()
        assert page_payload["pagination"]["count"] == 2
        assert page_payload["pagination"]["total"] == 4
        assert page_payload["pagination"]["has_more"] is True

        duration_sorted = client.get(
            "/api/v1/queues/printer-main/entries",
            params={"sort": "duration_bucket:desc", "limit": 10, "offset": 0},
        )
        assert duration_sorted.status_code == 200
        ordered_states = [entry["duration_bucket"] for entry in duration_sorted.json()["entries"]]
        assert ordered_states[0] == "unknown" or ordered_states[0] == "marathon"
    finally:
        client.__exit__(None, None, None)


def test_queue_entries_v1_validation_errors(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        bad_state = client.get("/api/v1/queues/p1/entries", params={"state": "todo,wat"})
        assert bad_state.status_code == 400

        bad_source = client.get("/api/v1/queues/p1/entries", params={"source_kind": "catalog_model,bad"})
        assert bad_source.status_code == 400

        bad_sort = client.get("/api/v1/queues/p1/entries", params={"sort": "priority:asc"})
        assert bad_sort.status_code == 400

        bad_limit = client.get("/api/v1/queues/p1/entries", params={"limit": 0})
        assert bad_limit.status_code == 400
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_creates_entry_and_returns_location(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "model-id-123",
                "copies": 1,
                "duration_bucket": "2-4h",
                "ams_fit": True,
                "overnight_fit": False,
            },
        )
        assert create_response.status_code == 201
        assert "location" in {key.lower() for key in create_response.headers.keys()}

        payload = create_response.json()
        assert payload["success"] is True
        assert payload["contract"] == "unified-queue.v1"
        assert payload["printer_id"] == "p1"
        assert payload["entry"]["queue_entry_id"].startswith("uqe-")
        assert payload["entry"]["source_kind"] == "catalog_model"
        assert payload["entry"]["source_id"] == "model-id-123"
        assert payload["entry"]["copies"] == 1
        assert payload["entry"]["duration_bucket"] == "medium"
        assert payload["entry"]["ams_ready_score"] == 100
        assert payload["entry"]["overnight_fit_score"] == 0
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_validation_and_unified_only_behavior(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        missing_source = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "copies": 1,
            },
        )
        assert missing_source.status_code == 400
        assert missing_source.json()["error"] == "validation_error"

        unsupported_legacy_fields = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "model-id-legacy",
                "queue_status": "queued",
            },
        )
        assert unsupported_legacy_fields.status_code == 400
        legacy_payload = unsupported_legacy_fields.json()
        assert legacy_payload["error"] == "validation_error"
        assert "unsupported_fields" in legacy_payload
        assert "queue_status" in legacy_payload["unsupported_fields"]
    finally:
        client.__exit__(None, None, None)


def test_queue_delete_v1_returns_204_and_removes_entry(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        # Create an entry to delete
        create_response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "model-to-delete",
                "copies": 1,
            },
        )
        assert create_response.status_code == 201
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        # Confirm it exists
        get_response = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert get_response.status_code == 200

        # Delete via v1 endpoint
        delete_response = client.delete(f"/api/v1/queues/p1/entries/{entry_id}")
        assert delete_response.status_code == 204
        assert delete_response.content == b""

        # Confirm it is gone
        get_after = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert get_after.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_queue_delete_v1_returns_404_for_nonexistent_entry(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        delete_response = client.delete("/api/v1/queues/p1/entries/uqe-doesnotexist")
        assert delete_response.status_code == 404
        payload = delete_response.json()
        assert payload["success"] is False
        assert payload["error"] == "not_found"
        assert payload["queue_entry_id"] == "uqe-doesnotexist"
        assert payload["printer_id"] == "p1"
    finally:
        client.__exit__(None, None, None)


def test_queue_delete_v1_printer_id_is_cosmetic(tmp_path: Path) -> None:
    """printer_id in path is accepted for v1 compat but does not scope the delete."""
    client, _db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/queues/printer-a/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "cross-printer-model",
                "copies": 2,
            },
        )
        assert create_response.status_code == 201
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        # Delete using a different printer_id — should still succeed
        delete_response = client.delete(f"/api/v1/queues/printer-b/entries/{entry_id}")
        assert delete_response.status_code == 204
        assert delete_response.content == b""
    finally:
        client.__exit__(None, None, None)

