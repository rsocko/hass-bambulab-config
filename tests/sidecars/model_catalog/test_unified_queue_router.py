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


# ---------------------------------------------------------------------------
# PATCH /api/v1/queues/{printer_id}/reorder — batch rank reorder
# ---------------------------------------------------------------------------


def test_reorder_v1_applies_rank_moves_and_normalizes(tmp_path: Path) -> None:
    """Creating 3 entries with explicit ranks, reordering them, verifies sequential ranks."""
    client, _db_path = _create_client(tmp_path)
    try:
        ids: list[str] = []
        for i in range(3):
            r = client.post(
                "/api/v1/queues/printer-x/add",
                json={"source_kind": "catalog_model", "source_id": f"model-{i}", "rank": i},
            )
            assert r.status_code == 201
            ids.append(r.json()["entry"]["queue_entry_id"])

        # Verify initial ranks 0, 1, 2
        list_r = client.get("/api/v1/queues/printer-x/entries")
        assert list_r.status_code == 200
        initial_entries = list_r.json()["entries"]
        initial_ranks = {e["queue_entry_id"]: e["rank"] for e in initial_entries}
        assert initial_ranks[ids[0]] == 0
        assert initial_ranks[ids[1]] == 1
        assert initial_ranks[ids[2]] == 2

        # Move entry 0 to rank 99 (should be normalized back to 2)
        reorder_r = client.patch(
            "/api/v1/queues/printer-x/reorder",
            json={"moves": [{"id": ids[0], "new_rank": 99}]},
        )
        assert reorder_r.status_code == 200
        data = reorder_r.json()
        assert data["success"] is True
        assert data["contract"] == "unified-queue.v1"
        assert data["printer_id"] == "printer-x"
        assert isinstance(data["moved_count"], int)
        assert isinstance(data["normalization_adjustments"], int)
        assert isinstance(data["moves"], list)

        # Verify ranks are still sequential 0,1,2
        list_r2 = client.get("/api/v1/queues/printer-x/entries")
        assert list_r2.status_code == 200
        final_entries = list_r2.json()["entries"]
        final_ranks = sorted(e["rank"] for e in final_entries)
        assert final_ranks == [0, 1, 2]

        # id[0] should now be last (rank 2)
        rank_map = {e["queue_entry_id"]: e["rank"] for e in final_entries}
        assert rank_map[ids[0]] == 2
        assert rank_map[ids[1]] == 0
        assert rank_map[ids[2]] == 1
    finally:
        client.__exit__(None, None, None)


def test_reorder_v1_returns_404_for_missing_entry(tmp_path: Path) -> None:
    """If any move references a nonexistent entry ID, 404 is returned with missing_ids."""
    client, _db_path = _create_client(tmp_path)
    try:
        r = client.post(
            "/api/v1/queues/printer-x/add",
            json={"source_kind": "catalog_model", "source_id": "real-model"},
        )
        assert r.status_code == 201
        real_id = r.json()["entry"]["queue_entry_id"]

        reorder_r = client.patch(
            "/api/v1/queues/printer-x/reorder",
            json={"moves": [{"id": real_id, "new_rank": 0}, {"id": "ghost-entry-id", "new_rank": 1}]},
        )
        assert reorder_r.status_code == 404
        data = reorder_r.json()
        assert data["error"] == "not_found"
        assert "ghost-entry-id" in data["missing_ids"]
    finally:
        client.__exit__(None, None, None)


def test_reorder_v1_empty_moves_rejected(tmp_path: Path) -> None:
    """An empty moves array returns 400."""
    client, _db_path = _create_client(tmp_path)
    try:
        reorder_r = client.patch(
            "/api/v1/queues/printer-x/reorder",
            json={"moves": []},
        )
        assert reorder_r.status_code == 400
        data = reorder_r.json()
        assert data["error"] == "validation_error"
    finally:
        client.__exit__(None, None, None)


def test_reorder_v1_duplicate_id_rejected(tmp_path: Path) -> None:
    """Providing the same entry ID twice in moves returns 400."""
    client, _db_path = _create_client(tmp_path)
    try:
        r = client.post(
            "/api/v1/queues/printer-x/add",
            json={"source_kind": "catalog_model", "source_id": "dup-model"},
        )
        assert r.status_code == 201
        entry_id = r.json()["entry"]["queue_entry_id"]

        reorder_r = client.patch(
            "/api/v1/queues/printer-x/reorder",
            json={"moves": [{"id": entry_id, "new_rank": 0}, {"id": entry_id, "new_rank": 1}]},
        )
        assert reorder_r.status_code == 400
        data = reorder_r.json()
        assert data["error"] == "validation_error"
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_quick_add_catalog_model_creates_all_file_plate_units(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.routers import unified_queue as unified_queue_router

    client, db_path = _create_client(tmp_path)
    try:
        seed = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "idea",
                "title": "Seed",
                "rank": 4,
            },
        )
        assert seed.status_code == 200

        def _fake_model_detail(*_args, **_kwargs):
            return {
                "success": True,
                "model": {
                    "name": "Catalog Quick Add",
                    "files": [
                        {"id": "asset-1", "filename": "multi.3mf", "file_type": "3mf"},
                        {"id": "asset-2", "filename": "single.stl", "file_type": "stl"},
                    ],
                },
            }

        def _fake_catalog_plates(*, request, model_ref, file_id, file_name, file_type):
            _ = request
            _ = model_ref
            _ = file_name
            _ = file_type
            if file_id == "asset-1":
                return [
                    {"plate_key": "1", "plate_name": "Plate 1"},
                    {"plate_key": "2", "plate_name": "Plate 2"},
                ]
            return [{"plate_key": "default", "plate_name": "Default Plate"}]

        monkeypatch.setattr(unified_queue_router, "build_model_detail_response", _fake_model_detail)
        monkeypatch.setattr(unified_queue_router, "_extract_catalog_file_plates", _fake_catalog_plates)

        response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "catalog-quick-1",
                "quick_add": True,
            },
        )
        assert response.status_code == 201
        payload = response.json()
        entry_id = payload["entry"]["queue_entry_id"]

        assert payload["entry"]["rank"] == 5
        assert payload["quick_add"]["enabled"] is True
        assert payload["quick_add"]["file_units_created"] == 2
        assert payload["quick_add"]["plate_units_created"] == 3
        assert payload["quick_add"]["duplicate_file_skips"] == 0
        assert payload["quick_add"]["duplicate_plate_skips"] == 0

        connection = connect(db_path)
        try:
            file_count = connection.execute(
                "SELECT COUNT(*) AS c FROM unified_queue_file_units WHERE queue_entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
            plate_count = connection.execute(
                "SELECT COUNT(*) AS c FROM unified_queue_plate_units WHERE queue_entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
        finally:
            connection.close()

        assert int(file_count) == 2
        assert int(plate_count) == 3
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_quick_add_working_group_dedupes_duplicate_files_and_plates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.routers import unified_queue as unified_queue_router

    client, db_path = _create_client(tmp_path)
    try:
        working_file = tmp_path / "duplicate.3mf"
        working_file.write_bytes(b"fake-3mf-content")

        now = "2026-05-10T00:00:00Z"
        connection = connect(db_path)
        try:
            connection.execute(
                "INSERT INTO working_groups (slug, title, stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("wg-quick", "WG Quick", "active", now, now),
            )
            group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

            connection.execute(
                "INSERT INTO working_items (working_group_id, file_path, item_role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (group_id, str(working_file), "supporting", now, now),
            )
            connection.execute(
                "INSERT INTO working_items (working_group_id, file_path, item_role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (group_id, str(working_file), "supporting", now, now),
            )
            connection.commit()
        finally:
            connection.close()

        def _fake_extract_plates(_package_bytes):
            return {
                "plates": [
                    {"id": "1", "name": "Plate 1"},
                    {"id": "1", "name": "Plate 1 duplicate"},
                    {"id": "2", "name": "Plate 2"},
                ]
            }

        monkeypatch.setattr(unified_queue_router, "extract_3mf_plates_metadata", _fake_extract_plates)

        response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "working_group",
                "source_id": str(group_id),
                "quick_add": True,
            },
        )
        assert response.status_code == 201
        payload = response.json()
        entry_id = payload["entry"]["queue_entry_id"]

        assert payload["quick_add"]["enabled"] is True
        assert payload["quick_add"]["file_units_created"] == 1
        assert payload["quick_add"]["plate_units_created"] == 2
        assert payload["quick_add"]["duplicate_file_skips"] == 1
        assert payload["quick_add"]["duplicate_plate_skips"] == 1

        verify = connect(db_path)
        try:
            file_count = verify.execute(
                "SELECT COUNT(*) AS c FROM unified_queue_file_units WHERE queue_entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
            plate_count = verify.execute(
                "SELECT COUNT(*) AS c FROM unified_queue_plate_units WHERE queue_entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
        finally:
            verify.close()

        assert int(file_count) == 1
        assert int(plate_count) == 2
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_advanced_add_selected_plates_creates_subset_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.routers import unified_queue as unified_queue_router

    client, db_path = _create_client(tmp_path)
    try:
        def _fake_model_detail(*_args, **_kwargs):
            return {
                "success": True,
                "model": {
                    "name": "Catalog Advanced Add",
                    "files": [
                        {"id": "asset-1", "filename": "multi.3mf", "file_type": "3mf"},
                        {"id": "asset-2", "filename": "single.stl", "file_type": "stl"},
                    ],
                },
            }

        def _fake_catalog_plates(*, request, model_ref, file_id, file_name, file_type):
            _ = request
            _ = model_ref
            _ = file_name
            _ = file_type
            if file_id == "asset-1":
                return [
                    {"plate_key": "1", "plate_name": "Plate 1"},
                    {"plate_key": "2", "plate_name": "Plate 2"},
                ]
            return [{"plate_key": "default", "plate_name": "Default Plate"}]

        monkeypatch.setattr(unified_queue_router, "build_model_detail_response", _fake_model_detail)
        monkeypatch.setattr(unified_queue_router, "_extract_catalog_file_plates", _fake_catalog_plates)

        response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "catalog-adv-1",
                "selection_mode": "selected_plates",
                "selected_files": [
                    {
                        "file_id": "asset-1",
                        "selected": True,
                        "plates": [
                            {"plate_id": "1", "selected": True},
                            {"plate_id": "2", "selected": False},
                        ],
                    },
                    {
                        "file_id": "asset-2",
                        "selected": False,
                    },
                ],
            },
        )
        assert response.status_code == 201
        payload = response.json()
        entry_id = payload["entry"]["queue_entry_id"]

        assert payload["entry"]["selection_mode"] == "selected_plates"
        assert payload["advanced_add"]["enabled"] is True
        assert payload["advanced_add"]["file_units_created"] == 1
        assert payload["advanced_add"]["plate_units_created"] == 1

        connection = connect(db_path)
        try:
            file_count = connection.execute(
                "SELECT COUNT(*) AS c FROM unified_queue_file_units WHERE queue_entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
            plate_count = connection.execute(
                "SELECT COUNT(*) AS c FROM unified_queue_plate_units WHERE queue_entry_id = ?",
                (entry_id,),
            ).fetchone()["c"]
        finally:
            connection.close()

        assert int(file_count) == 1
        assert int(plate_count) == 1
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_advanced_add_rejects_empty_file_plate_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.routers import unified_queue as unified_queue_router

    client, _db_path = _create_client(tmp_path)
    try:
        def _fake_model_detail(*_args, **_kwargs):
            return {
                "success": True,
                "model": {
                    "name": "Catalog Advanced Add",
                    "files": [{"id": "asset-1", "filename": "multi.3mf", "file_type": "3mf"}],
                },
            }

        monkeypatch.setattr(unified_queue_router, "build_model_detail_response", _fake_model_detail)

        response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "catalog-adv-2",
                "selection_mode": "selected_plates",
                "selected_files": [
                    {
                        "file_id": "asset-1",
                        "selected": False,
                    }
                ],
            },
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"] == "validation_error"
    finally:
        client.__exit__(None, None, None)


def test_queue_add_v1_advanced_add_rejects_invalid_file_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.routers import unified_queue as unified_queue_router

    client, _db_path = _create_client(tmp_path)
    try:
        def _fake_model_detail(*_args, **_kwargs):
            return {
                "success": True,
                "model": {
                    "name": "Catalog Advanced Add",
                    "files": [{"id": "asset-1", "filename": "multi.3mf", "file_type": "3mf"}],
                },
            }

        monkeypatch.setattr(unified_queue_router, "build_model_detail_response", _fake_model_detail)

        response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "catalog-adv-3",
                "selection_mode": "selected_files",
                "selected_files": [
                    {
                        "file_id": "asset-does-not-exist",
                        "selected": True,
                    }
                ],
            },
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"] == "validation_error"
        assert "not valid" in payload["message"]
    finally:
        client.__exit__(None, None, None)

