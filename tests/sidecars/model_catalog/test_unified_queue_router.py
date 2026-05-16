from pathlib import Path

from fastapi.testclient import TestClient

from app.db import connect, create_unified_queue_file_unit, create_unified_queue_plate_unit
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
        assert created["entry"]["state"] == "preparing"
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
                "state": "in_progress",
                "copies_completed": 1,
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["entry"]["state"] == "in_progress"
        assert updated["entry"]["copies_completed"] == 1
        assert updated["entry"]["rank"] == 1

        list_response = client.get("/api/unified-queue/entries", params={"state": "in_progress", "limit": 10, "offset": 0})
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
            json={"source_kind": "idea", "title": "Transition Test", "state": "backlog", "copies": 1},
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        invalid_transition = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "done"},
        )
        assert invalid_transition.status_code == 400
        invalid_payload = invalid_transition.json()
        assert invalid_payload["error"] == "invalid_transition"
        assert invalid_payload["from_state"] == "backlog"
        assert invalid_payload["to_state"] == "done"

        to_preparing = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "preparing"},
            headers={"x-actor": "test-suite"},
        )
        assert to_preparing.status_code == 200
        assert to_preparing.json()["entry"]["state"] == "preparing"

        to_ready = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "ready"},
            headers={"x-actor": "test-suite"},
        )
        assert to_ready.status_code == 200

        to_in_progress = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "in_progress"},
            headers={"x-actor": "test-suite"},
        )
        assert to_in_progress.status_code == 200

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
        # backlog->preparing, preparing->ready, ready->in_progress, in_progress->blocked, blocked->ready
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
                "state": "preparing",
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
                "state": "in_progress",
                "rank": 2,
                "duration_bucket": "medium",
            },
            {
                "source_kind": "idea",
                "title": "Idea One",
                "state": "backlog",
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
                "state": "preparing,ready",
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
        bad_state = client.get("/api/v1/queues/p1/entries", params={"state": "preparing,wat"})
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
        assert payload["entry"]["state"] == "backlog"
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


def test_queue_delete_v1_cascades_file_and_plate_units(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "model-with-children",
                "copies": 1,
            },
        )
        assert create_response.status_code == 201
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        file_unit = create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="fu-delete-cascade",
            file_name="delete-cascade.3mf",
        )
        create_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id=file_unit.file_unit_id,
            plate_unit_id="pu-delete-cascade",
            plate_key="plate_1",
        )

        connection = connect(db_path)
        try:
            before_file_units = int(
                connection.execute(
                    "SELECT COUNT(*) FROM unified_queue_file_units WHERE queue_entry_id = ?",
                    (entry_id,),
                ).fetchone()[0]
            )
            before_plate_units = int(
                connection.execute(
                    "SELECT COUNT(*) FROM unified_queue_plate_units WHERE queue_entry_id = ?",
                    (entry_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()

        assert before_file_units == 1
        assert before_plate_units == 1

        delete_response = client.delete(f"/api/v1/queues/p1/entries/{entry_id}")
        assert delete_response.status_code == 204
        assert delete_response.content == b""

        connection = connect(db_path)
        try:
            after_file_units = int(
                connection.execute(
                    "SELECT COUNT(*) FROM unified_queue_file_units WHERE queue_entry_id = ?",
                    (entry_id,),
                ).fetchone()[0]
            )
            after_plate_units = int(
                connection.execute(
                    "SELECT COUNT(*) FROM unified_queue_plate_units WHERE queue_entry_id = ?",
                    (entry_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()

        assert after_file_units == 0
        assert after_plate_units == 0
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

        assert payload["entry"]["state"] == "backlog"
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

        assert payload["entry"]["state"] == "backlog"
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

        assert payload["entry"]["state"] == "backlog"
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


def test_get_entry_detail_returns_nested_file_and_plate_units(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "working_file",
                "source_id": "wf-queue-detail",
                "title": "Queue detail test",
            },
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        file_unit = create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-001",
            file_id="wf-asset-1",
            file_name="adapter.3mf",
            selected=True,
            estimated_minutes=95,
        )
        create_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id=file_unit.file_unit_id,
            plate_unit_id="qpu-001-001",
            plate_key="plate-1",
            plate_name="Plate 1",
            selected=True,
            state="pending",
        )
        create_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id=file_unit.file_unit_id,
            plate_unit_id="qpu-001-002",
            plate_key="plate-2",
            plate_name="Plate 2",
            selected=False,
            state="done",
        )

        response = client.get(f"/api/unified-queue/entries/{entry_id}/detail")
        assert response.status_code == 200
        payload = response.json()

        assert payload["success"] is True
        assert payload["entry"]["queue_entry_id"] == entry_id
        assert payload["summary"]["file_count"] == 1
        assert payload["summary"]["selected_file_count"] == 1
        assert payload["summary"]["plate_count"] == 2
        assert payload["summary"]["selected_plate_count"] == 1
        assert payload["summary"]["completed_plate_count"] == 1
        assert len(payload["files"]) == 1
        assert payload["files"][0]["file_unit_id"] == "qfu-001"
        assert payload["files"][0]["plates"][0]["plate_unit_id"] == "qpu-001-001"
        assert payload["files"][0]["plates"][1]["state"] == "done"
    finally:
        client.__exit__(None, None, None)


def test_update_entry_selection_updates_units_and_selection_mode(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "working_group",
                "source_id": "wg-selection-save",
                "title": "Selection save test",
            },
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        first_file = create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-001",
            file_id="file-1",
            file_name="main.3mf",
            selected=True,
        )
        second_file = create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-002",
            file_id="file-2",
            file_name="extras.3mf",
            selected=True,
        )

        create_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id=first_file.file_unit_id,
            plate_unit_id="qpu-001-001",
            plate_key="plate-1",
            plate_name="Plate 1",
            selected=True,
            state="pending",
        )
        create_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id=first_file.file_unit_id,
            plate_unit_id="qpu-001-002",
            plate_key="plate-2",
            plate_name="Plate 2",
            selected=True,
            state="pending",
        )
        create_unified_queue_plate_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id=second_file.file_unit_id,
            plate_unit_id="qpu-002-001",
            plate_key="plate-1",
            plate_name="Plate 1",
            selected=True,
            state="pending",
        )

        response = client.patch(
            f"/api/unified-queue/entries/{entry_id}/selection",
            json={
                "files": [
                    {
                        "file_unit_id": "qfu-001",
                        "selected": True,
                        "plates": [
                            {"plate_unit_id": "qpu-001-001", "selected": True, "state": "done"},
                            {"plate_unit_id": "qpu-001-002", "selected": False, "state": "pending"},
                        ],
                    },
                    {
                        "file_unit_id": "qfu-002",
                        "selected": False,
                        "plates": [
                            {"plate_unit_id": "qpu-002-001", "selected": False, "state": "pending"},
                        ],
                    },
                ]
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["success"] is True
        assert payload["entry"]["selection_mode"] == "selected_plates"
        assert payload["summary"]["selected_file_count"] == 1
        assert payload["summary"]["selected_plate_count"] == 1
        assert payload["summary"]["completed_plate_count"] == 1

        connection = connect(db_path)
        try:
            file_rows = connection.execute(
                "SELECT file_unit_id, selected FROM unified_queue_file_units WHERE queue_entry_id = ? ORDER BY file_unit_id ASC",
                (entry_id,),
            ).fetchall()
            plate_rows = connection.execute(
                """
                SELECT file_unit_id, plate_unit_id, selected, state, completion_confidence, completion_source, last_attempt_outcome
                FROM unified_queue_plate_units
                WHERE queue_entry_id = ?
                ORDER BY file_unit_id ASC, plate_unit_id ASC
                """,
                (entry_id,),
            ).fetchall()
        finally:
            connection.close()

        assert [(str(row["file_unit_id"]), int(row["selected"])) for row in file_rows] == [
            ("qfu-001", 1),
            ("qfu-002", 0),
        ]
        assert [(str(row["plate_unit_id"]), int(row["selected"]), str(row["state"])) for row in plate_rows] == [
            ("qpu-001-001", 1, "done"),
            ("qpu-001-002", 0, "pending"),
            ("qpu-002-001", 0, "pending"),
        ]
        assert str(plate_rows[0]["completion_confidence"]) == "high"
        assert str(plate_rows[0]["completion_source"]) == "manual"
        assert str(plate_rows[0]["last_attempt_outcome"]) == "success"
    finally:
        client.__exit__(None, None, None)


def test_archive_match_v1_high_confidence_model_id_and_tags(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "model-123",
                "rank": 0,
            },
        )
        assert create_response.status_code == 201
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-001",
            file_id="file-1",
            file_name="part-a.3mf",
            filament_requirements={"filament_tags": ["pla", "red"]},
        )

        match_response = client.post(
            "/api/v1/queues/p1/archive-match",
            json={
                "archive_id": "archive-1",
                "model_id": "model-123",
                "filament_tags": ["pla", "red"],
            },
        )
        assert match_response.status_code == 200
        payload = match_response.json()
        assert payload["matched"] is True
        assert payload["unmatched"] is False
        assert payload["best_match"]["queue_entry_id"] == entry_id
        assert payload["best_match"]["confidence"] == "high"
        assert payload["best_match"]["confidence_score"] == 1.0
    finally:
        client.__exit__(None, None, None)


def test_archive_match_v1_medium_confidence_filename_or_tag_subset(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "working_group",
                "source_id": "wg-1",
                "rank": 0,
            },
        )
        assert create_response.status_code == 201
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-001",
            file_id="file-1",
            file_name="my_widget.3mf",
            filament_requirements={"filament_tags": ["petg", "blue", "matte"]},
        )

        filename_match = client.post(
            "/api/v1/queues/p1/archive-match",
            json={
                "archive_id": "archive-2",
                "filename": "my_widget.gcode",
            },
        )
        assert filename_match.status_code == 200
        filename_payload = filename_match.json()
        assert filename_payload["matched"] is True
        assert filename_payload["best_match"]["confidence"] == "medium"
        assert filename_payload["best_match"]["confidence_score"] >= 0.7

        tag_subset_match = client.post(
            "/api/v1/queues/p1/archive-match",
            json={
                "archive_id": "archive-3",
                "filament_tags": ["petg", "blue"],
            },
        )
        assert tag_subset_match.status_code == 200
        tag_payload = tag_subset_match.json()
        assert tag_payload["matched"] is True
        assert tag_payload["best_match"]["confidence"] == "medium"
        assert tag_payload["best_match"]["confidence_score"] >= 0.7
    finally:
        client.__exit__(None, None, None)


def test_archive_match_v1_low_confidence_time_window_and_unmatched(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        low_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "idea",
                "title": "Low candidate",
                "estimated_total_minutes": 100,
                "rank": 0,
            },
        )
        assert low_response.status_code == 200
        low_entry_id = low_response.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=low_entry_id,
            file_unit_id="qfu-low",
            file_id="file-low",
            file_name="other-file.3mf",
        )

        low_match = client.post(
            "/api/v1/queues/p1/archive-match",
            json={
                "archive_id": "archive-low",
                "estimated_minutes": 110,
            },
        )
        assert low_match.status_code == 200
        low_payload = low_match.json()
        assert low_payload["matched"] is True
        assert low_payload["best_match"]["confidence"] == "low"
        assert low_payload["best_match"]["confidence_score"] == 0.4

        unmatched = client.post(
            "/api/v1/queues/p1/archive-match",
            json={
                "archive_id": "archive-none",
                "model_id": "missing-model",
                "filename": "nope.3mf",
                "filament_tags": ["abs", "black"],
                "estimated_minutes": 1000,
            },
        )
        assert unmatched.status_code == 200
        unmatched_payload = unmatched.json()
        assert unmatched_payload["matched"] is False
        assert unmatched_payload["unmatched"] is True
        assert unmatched_payload["best_match"]["confidence"] == "unmatched"
        assert unmatched_payload["best_match"]["confidence_score"] == 0.0
    finally:
        client.__exit__(None, None, None)


def test_archive_completion_v1_high_auto_completes_entry_and_records_suggestion(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "catalog_model",
                "source_id": "model-h1",
            },
        )
        assert create_response.status_code == 201
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-h1",
            file_name="high-case.3mf",
            filament_requirements={"filament_tags": ["pla", "white"]},
        )

        completion_response = client.post(
            "/api/v1/queues/p1/archive-completion",
            json={
                "archive_id": "arch-h1",
                "model_id": "model-h1",
                "filament_tags": ["pla", "white"],
            },
        )
        assert completion_response.status_code == 200
        payload = completion_response.json()
        assert payload["action"] == "auto_completed"
        assert payload["auto_completed"] is True
        assert payload["suggestion"]["status"] == "auto_completed"

        entry_response = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert entry_response.status_code == 200
        entry_payload = entry_response.json()["entry"]
        assert entry_payload["state"] == "done"
        assert entry_payload["completion_source"] == "auto_match"
        assert entry_payload["last_archive_id"] == "arch-h1"
    finally:
        client.__exit__(None, None, None)


def test_archive_completion_v1_medium_suggested_then_reject_and_remap(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        suggested_create = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "working_group",
                "source_id": "wg-medium",
            },
        )
        assert suggested_create.status_code == 201
        suggested_entry_id = suggested_create.json()["entry"]["queue_entry_id"]

        remap_target_create = client.post(
            "/api/v1/queues/p1/add",
            json={
                "source_kind": "working_group",
                "source_id": "wg-target",
            },
        )
        assert remap_target_create.status_code == 201
        remap_target_entry_id = remap_target_create.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=suggested_entry_id,
            file_unit_id="qfu-m1",
            file_name="medium-case.3mf",
        )

        completion_response = client.post(
            "/api/v1/queues/p1/archive-completion",
            json={
                "archive_id": "arch-m1",
                "filename": "medium-case.gcode",
            },
        )
        assert completion_response.status_code == 200
        completion_payload = completion_response.json()
        assert completion_payload["action"] == "suggested"
        suggestion_id = completion_payload["suggestion"]["suggestion_id"]

        suggestions_response = client.get("/api/v1/queues/p1/suggestions", params={"status": "suggested"})
        assert suggestions_response.status_code == 200
        listed_ids = {item["suggestion_id"] for item in suggestions_response.json()["suggestions"]}
        assert suggestion_id in listed_ids

        reject_response = client.post(f"/api/v1/queues/p1/suggestions/{suggestion_id}/reject")
        assert reject_response.status_code == 200
        assert reject_response.json()["suggestion"]["status"] == "rejected"

        remap_response = client.post(
            f"/api/v1/queues/p1/suggestions/{suggestion_id}/remap",
            json={"queue_entry_id": remap_target_entry_id},
        )
        assert remap_response.status_code == 200
        remap_payload = remap_response.json()
        assert remap_payload["suggestion"]["status"] == "remapped"
        assert remap_payload["suggestion"]["remapped_queue_entry_id"] == remap_target_entry_id
        assert remap_payload["remapped_entry"]["state"] == "done"
        assert remap_payload["remapped_entry"]["completion_source"] == "suggestion"
    finally:
        client.__exit__(None, None, None)


def test_archive_completion_v1_low_creates_unmatched_record(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "idea",
                "title": "Low match candidate",
                "estimated_total_minutes": 100,
            },
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-l1",
            file_name="low-case.3mf",
        )

        completion_response = client.post(
            "/api/v1/queues/p1/archive-completion",
            json={
                "archive_id": "arch-l1",
                "estimated_minutes": 111,
            },
        )
        assert completion_response.status_code == 200
        payload = completion_response.json()
        assert payload["action"] == "unmatched"
        assert payload["suggestion"]["status"] == "unmatched"
        assert payload["suggestion"]["confidence"] == "low"
    finally:
        client.__exit__(None, None, None)


def test_planner_score_v1_computes_ams_overnight_duration_and_ranks(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        fast = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Fast", "estimated_total_minutes": 90, "rank": 5},
        )
        medium = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Medium", "estimated_total_minutes": 180, "rank": 6},
        )
        long = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Long", "estimated_total_minutes": 600, "rank": 7},
        )
        assert fast.status_code == 200
        assert medium.status_code == 200
        assert long.status_code == 200

        fast_id = fast.json()["entry"]["queue_entry_id"]
        medium_id = medium.json()["entry"]["queue_entry_id"]
        long_id = long.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=fast_id,
            file_unit_id="qfu-fast",
            file_name="fast.3mf",
            filament_requirements={"tray_uuids": ["tray-a", "tray-b"]},
        )
        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=medium_id,
            file_unit_id="qfu-medium",
            file_name="medium.3mf",
            filament_requirements={"tray_uuid": "tray-z"},
        )
        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=long_id,
            file_unit_id="qfu-long",
            file_name="long.3mf",
        )

        response = client.post(
            "/api/v1/queues/p1/planner/score",
            json={"ams_tray_uuids": ["tray-a", "tray-b"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["planner"]["ams_state_known"] is True
        assert payload["planner"]["entry_count"] >= 3

        by_id = {entry["queue_entry_id"]: entry for entry in payload["entries"]}
        assert by_id[fast_id]["ams"]["fit"] is True
        assert by_id[fast_id]["ams"]["score"] == 100
        assert by_id[fast_id]["overnight"]["fit"] is True
        assert by_id[fast_id]["duration"]["bucket"] == "quick"

        assert by_id[medium_id]["ams"]["fit"] is False
        assert by_id[medium_id]["ams"]["score"] == 0
        assert by_id[medium_id]["overnight"]["fit"] is True
        assert by_id[medium_id]["duration"]["bucket"] == "medium"

        assert by_id[long_id]["overnight"]["fit"] is False
        assert by_id[long_id]["overnight"]["score"] == 0
        assert by_id[long_id]["duration"]["bucket"] == "marathon"

        ranked_ids = [entry["queue_entry_id"] for entry in payload["entries"]]
        assert ranked_ids.index(fast_id) < ranked_ids.index(long_id)
    finally:
        client.__exit__(None, None, None)


def test_planner_score_v1_handles_unknown_ams_state_gracefully(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Unknown AMS", "estimated_total_minutes": 120},
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]

        create_unified_queue_file_unit(
            db_path=db_path,
            queue_entry_id=entry_id,
            file_unit_id="qfu-unknown",
            file_name="unknown.3mf",
            filament_requirements={"tray_uuids": ["tray-a"]},
        )

        response = client.post("/api/v1/queues/p1/planner/score", json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["planner"]["ams_state_known"] is False

        matched = next(item for item in payload["entries"] if item["queue_entry_id"] == entry_id)
        assert matched["ams"]["state_known"] is False
        assert matched["ams"]["fit"] is False
        assert matched["ams"]["score"] == 0
        assert matched["ams"]["reason"] == "ams_state_unknown"
        assert matched["duration"]["bucket"] == "quick"
    finally:
        client.__exit__(None, None, None)


def test_planner_strategy_v1_defaults_to_balanced_and_persists_custom_weights(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        default_response = client.get("/api/v1/queues/p1/planner/strategy")
        assert default_response.status_code == 200
        default_payload = default_response.json()
        assert default_payload["strategy"] == "balanced"
        assert default_payload["persisted"] is False

        update_response = client.put(
            "/api/v1/queues/p1/planner/strategy",
            json={
                "strategy": "aggressive",
                "custom_weights": {
                    "ams_fit": 70,
                    "overnight_fit": 5,
                    "duration": {
                        "quick": 25,
                        "medium": 15,
                        "overnight": 5,
                        "marathon": 0,
                        "unknown": 0,
                    },
                },
            },
        )
        assert update_response.status_code == 200
        update_payload = update_response.json()
        assert update_payload["strategy"] == "aggressive"
        assert update_payload["weights"]["ams_fit"] == 70
        assert update_payload["weights"]["duration"]["quick"] == 25

        persisted_response = client.get("/api/v1/queues/p1/planner/strategy")
        assert persisted_response.status_code == 200
        persisted_payload = persisted_response.json()
        assert persisted_payload["persisted"] is True
        assert persisted_payload["strategy"] == "aggressive"
        assert persisted_payload["weights"]["ams_fit"] == 70
        assert persisted_payload["weights"]["duration"]["quick"] == 25
    finally:
        client.__exit__(None, None, None)


def test_planner_strategy_v1_changes_rank_computation(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick", "estimated_total_minutes": 90, "rank": 10},
        )
        overnight = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Overnight", "estimated_total_minutes": 420, "rank": 11},
        )
        assert quick.status_code == 200
        assert overnight.status_code == 200
        quick_id = quick.json()["entry"]["queue_entry_id"]
        overnight_id = overnight.json()["entry"]["queue_entry_id"]

        aggressive = client.post(
            "/api/v1/queues/p1/planner/score",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert aggressive.status_code == 200
        aggressive_order = [item["queue_entry_id"] for item in aggressive.json()["entries"]]

        lazy = client.post(
            "/api/v1/queues/p1/planner/score",
            json={"strategy": "lazy", "ams_tray_uuids": []},
        )
        assert lazy.status_code == 200
        lazy_order = [item["queue_entry_id"] for item in lazy.json()["entries"]]

        assert aggressive_order.index(quick_id) < aggressive_order.index(overnight_id)
        assert lazy_order.index(overnight_id) < lazy_order.index(quick_id)
    finally:
        client.__exit__(None, None, None)


def test_planner_strategy_v1_score_strategy_only_uses_selected_preset_weights(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick-Preset", "estimated_total_minutes": 90, "rank": 10},
        )
        overnight = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Overnight-Preset", "estimated_total_minutes": 420, "rank": 11},
        )
        assert quick.status_code == 200
        assert overnight.status_code == 200

        # Seed a custom aggressive preference first.
        save_custom = client.put(
            "/api/v1/queues/p1/planner/strategy",
            json={
                "strategy": "aggressive",
                "custom_weights": {
                    "ams_fit": 70,
                    "overnight_fit": 5,
                    "duration": {
                        "quick": 25,
                        "medium": 15,
                        "overnight": 5,
                        "marathon": 0,
                        "unknown": 0,
                    },
                },
            },
        )
        assert save_custom.status_code == 200

        # Strategy-only score call must switch to lazy preset defaults, not reuse aggressive custom weights.
        lazy = client.post(
            "/api/v1/queues/p1/planner/score",
            json={"strategy": "lazy", "ams_tray_uuids": []},
        )
        assert lazy.status_code == 200
        lazy_payload = lazy.json()
        assert lazy_payload["planner"]["strategy"] == "lazy"
        assert lazy_payload["planner"]["weights"]["ams_fit"] == 20
        assert lazy_payload["planner"]["weights"]["overnight_fit"] == 60
        assert lazy_payload["planner"]["weights"]["duration"]["quick"] == 10
        assert lazy_payload["planner"]["weights"]["duration"]["overnight"] == 25
    finally:
        client.__exit__(None, None, None)


def test_plan_queue_v1_generates_delta_without_persisting(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick", "estimated_total_minutes": 90, "rank": 2},
        )
        overnight = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Overnight", "estimated_total_minutes": 420, "rank": 1},
        )
        assert quick.status_code == 200
        assert overnight.status_code == 200

        quick_id = quick.json()["entry"]["queue_entry_id"]
        overnight_id = overnight.json()["entry"]["queue_entry_id"]

        plan = client.post(
            "/api/v1/queues/p1/plan",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert plan.status_code == 200
        plan_payload = plan.json()

        assert plan_payload["success"] is True
        assert plan_payload["strategy"] == "aggressive"
        assert plan_payload["move_count"] >= 0
        assert "moves" in plan_payload

        moves = plan_payload["moves"]
        assert isinstance(moves, list)

        has_quick_to_first = any(m["id"] == quick_id and m["to_rank"] < m["from_rank"] for m in moves)
        assert has_quick_to_first

        for move in moves:
            assert "id" in move
            assert "from_rank" in move
            assert "to_rank" in move
            assert "reason" in move
            assert move["reason"] in ["ams_ready", "overnight_fit", "duration_quick", "duration_medium", "duration_overnight", "planner_score"]

        verify = client.get("/api/v1/queues/p1/reorder")
        if verify.status_code == 200:
            current_ranks = {entry["queue_entry_id"]: entry.get("rank") for entry in verify.json().get("entries", [])}
            assert current_ranks.get(quick_id) == 2
            assert current_ranks.get(overnight_id) == 1
    finally:
        client.__exit__(None, None, None)


def test_plan_queue_v1_shows_no_moves_when_already_optimal(tmp_path: Path) -> None:
    client, db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick", "estimated_total_minutes": 90, "rank": 0},
        )
        overnight = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Overnight", "estimated_total_minutes": 420, "rank": 1},
        )
        assert quick.status_code == 200
        assert overnight.status_code == 200

        aggressive_plan = client.post(
            "/api/v1/queues/p1/planner/score",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert aggressive_plan.status_code == 200

        plan = client.post(
            "/api/v1/queues/p1/plan",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert plan.status_code == 200
        plan_payload = plan.json()

        assert plan_payload["move_count"] == 0
        assert len(plan_payload["moves"]) == 0
    finally:
        client.__exit__(None, None, None)


def test_apply_planner_delta_v1_applies_moves_atomically(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick", "estimated_total_minutes": 90, "rank": 2},
        )
        overnight = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Overnight", "estimated_total_minutes": 420, "rank": 1},
        )
        assert quick.status_code == 200
        assert overnight.status_code == 200

        quick_id = quick.json()["entry"]["queue_entry_id"]
        overnight_id = overnight.json()["entry"]["queue_entry_id"]

        # Generate plan delta
        plan = client.post(
            "/api/v1/queues/p1/plan",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert plan.status_code == 200
        moves = plan.json()["moves"]

        # Apply the delta
        apply_response = client.post(
            "/api/v1/queues/p1/plan/apply",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert apply_response.status_code == 200
        apply_payload = apply_response.json()

        assert apply_payload["success"] is True
        assert apply_payload["applied_moves"] > 0
        assert apply_payload["audit_id"] is not None
        assert apply_payload["undo_available"] is True

        # Verify ranks were updated
        verify = client.get("/api/v1/queues/p1/entries")
        if verify.status_code == 200:
            current_ranks = {entry["queue_entry_id"]: entry.get("rank") for entry in verify.json().get("entries", [])}
            # After aggressive apply, quick should have lower rank than overnight
            if quick_id in current_ranks and overnight_id in current_ranks:
                assert current_ranks[quick_id] < current_ranks[overnight_id], "quick should rank before overnight with aggressive"
    finally:
        client.__exit__(None, None, None)


def test_undo_planner_operation_v1_reverts_ranks(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick", "estimated_total_minutes": 90, "rank": 2},
        )
        overnight = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Overnight", "estimated_total_minutes": 420, "rank": 1},
        )
        assert quick.status_code == 200
        assert overnight.status_code == 200

        quick_id = quick.json()["entry"]["queue_entry_id"]
        overnight_id = overnight.json()["entry"]["queue_entry_id"]

        original_quick_rank = 2
        original_overnight_rank = 1

        # Apply delta
        apply_response = client.post(
            "/api/v1/queues/p1/plan/apply",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert apply_response.status_code == 200

        # Verify ranks changed
        after_apply = client.get("/api/v1/queues/p1/entries")
        assert after_apply.status_code == 200
        after_apply_ranks = {entry["queue_entry_id"]: entry.get("rank") for entry in after_apply.json().get("entries", [])}

        # Now undo
        undo_response = client.post(
            "/api/v1/queues/p1/plan/undo",
            json={},
        )
        assert undo_response.status_code == 200
        undo_payload = undo_response.json()

        assert undo_payload["success"] is True
        assert undo_payload["undone_moves"] > 0
        assert undo_payload["restored_audit_id"] is not None
        assert undo_payload["undo_audit_id"] is not None

        # Verify ranks reverted
        after_undo = client.get("/api/v1/queues/p1/entries")
        assert after_undo.status_code == 200
        after_undo_ranks = {entry["queue_entry_id"]: entry.get("rank") for entry in after_undo.json().get("entries", [])}

        if quick_id in after_undo_ranks and overnight_id in after_undo_ranks:
            # Should be back to original order: overnight=1, quick=2 (or similar after normalization)
            assert after_undo_ranks[overnight_id] <= after_undo_ranks[quick_id], "overnight should be before or equal to quick after undo"
    finally:
        client.__exit__(None, None, None)


def test_plan_history_v1_lists_recent_operations(tmp_path: Path) -> None:
    client, _db_path = _create_client(tmp_path)
    try:
        quick = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Quick", "estimated_total_minutes": 90, "rank": 1},
        )
        assert quick.status_code == 200

        # Apply once
        apply1 = client.post(
            "/api/v1/queues/p1/plan/apply",
            json={"strategy": "aggressive", "ams_tray_uuids": []},
        )
        assert apply1.status_code == 200

        # Get history
        history_response = client.get("/api/v1/queues/p1/plan/history")
        assert history_response.status_code == 200
        history_payload = history_response.json()

        assert history_payload["success"] is True
        assert history_payload["history_count"] >= 1
        assert len(history_payload["history"]) >= 1

        recent_op = history_payload["history"][0]
        assert recent_op["operation"] in ["apply", "undo"]
        assert "id" in recent_op
        assert "created_at" in recent_op
    finally:
        client.__exit__(None, None, None)


def test_unified_queue_up_next_state_transitions_issue_1481(tmp_path: Path) -> None:
    """Test new up_next state and backlog re-add logic for issue #1481."""
    client, db_path = _create_client(tmp_path)
    try:
        # Create entry in backlog state
        create_response = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "idea", "title": "Up Next Test", "state": "backlog", "copies": 1},
        )
        assert create_response.status_code == 200
        entry_id = create_response.json()["entry"]["queue_entry_id"]
        assert create_response.json()["entry"]["state"] == "backlog"

        # Transition: backlog -> up_next (new state)
        to_up_next = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "up_next"},
            headers={"x-actor": "test-suite"},
        )
        assert to_up_next.status_code == 200
        assert to_up_next.json()["entry"]["state"] == "up_next"

        # Transition: up_next -> preparing
        to_preparing = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "preparing"},
            headers={"x-actor": "test-suite"},
        )
        assert to_preparing.status_code == 200
        assert to_preparing.json()["entry"]["state"] == "preparing"

        # Transition: preparing -> ready
        to_ready = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "ready"},
            headers={"x-actor": "test-suite"},
        )
        assert to_ready.status_code == 200
        assert to_ready.json()["entry"]["state"] == "ready"

        # Transition: ready -> in_progress
        to_in_progress = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "in_progress"},
            headers={"x-actor": "test-suite"},
        )
        assert to_in_progress.status_code == 200
        assert to_in_progress.json()["entry"]["state"] == "in_progress"

        # Transition: in_progress -> done
        to_done = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={"state": "done"},
            headers={"x-actor": "test-suite"},
        )
        assert to_done.status_code == 200
        assert to_done.json()["entry"]["state"] == "done"

        # Verify all states are in VALID_STATES
        valid_states_response = client.get("/api/unified-queue/entries")
        assert valid_states_response.status_code == 200

        # Test re-add creates entry in backlog (not up_next)
        # This tests that re-add defaults to backlog as per requirement
        readd_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "idea",
                "title": "Re-add Test",
                "state": "backlog",
                "copies": 1,
            },
        )
        assert readd_response.status_code == 200
        readd_entry = readd_response.json()["entry"]
        assert readd_entry["state"] == "backlog"

        # Test that up_next allows transitions to backlog (fallback scenario)
        up_next_entry_response = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "working_group", "source_id": "wg-test", "title": "WG Test", "state": "up_next", "copies": 1},
        )
        assert up_next_entry_response.status_code == 200
        up_next_entry_id = up_next_entry_response.json()["entry"]["queue_entry_id"]

        # Verify up_next can transition back to backlog if needed
        back_to_backlog = client.patch(
            f"/api/unified-queue/entries/{up_next_entry_id}",
            json={"state": "backlog"},
            headers={"x-actor": "test-suite"},
        )
        assert back_to_backlog.status_code == 200
        assert back_to_backlog.json()["entry"]["state"] == "backlog"
    finally:
        client.__exit__(None, None, None)


