"""Tests for /api/slicer/jobs CRUD and lifecycle (Workstream B / Slice 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def _make_settings(db_path: Path) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.example",
        db_path=db_path,
        refresh_ttl_seconds=300,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="0.0.0",
        image_revision="test",
        image_created="2024-01-01T00:00:00Z",
        use_slicer_api=False,
        bambu_studio_api_url="http://bambu-studio-api:3000",
    )


def _create_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    return client


def _create_draft(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {
        "source_kind": "local_file",
        "archive_intent": "create_new",
        **overrides,
    }
    resp = client.post("/api/slicer/jobs", json=body)
    assert resp.status_code == 201
    return resp.json()


# ---------- Create ----------


class TestCreateJob:
    def test_create_draft_minimal(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job = _create_draft(client)
            assert job["status"] == "draft"
            assert job["source_kind"] == "local_file"
            assert job["archive_intent"] == "create_new"
            assert job["workflow_kind"] == "historical_backfill"
            assert len(job["job_id"]) == 12
        finally:
            client.__exit__(None, None, None)

    def test_create_draft_full(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job = _create_draft(
                client,
                workflow_kind="manual",
                source_ref="test-ref",
                local_model_id="mdl-001",
                working_file_path="/models/box.3mf",
                requested_print_started_at="2026-01-15T10:00:00Z",
                requested_print_completed_at="2026-01-15T12:00:00Z",
                requested_print_timezone="America/Chicago",
                date_override_strategy="operator_supplied",
                selected_file_path="/files/box.stl",
                selected_plate_key="plate_1",
                selected_plate_index=0,
                source_file_name="box.3mf",
                attach_source_after_create=True,
                overrides={"layer_height": 0.2},
            )
            assert job["source_ref"] == "test-ref"
            assert job["local_model_id"] == "mdl-001"
            assert job["requested_print_timezone"] == "America/Chicago"
            assert job["attach_source_after_create"] is True
            assert job["overrides"] == {"layer_height": 0.2}
        finally:
            client.__exit__(None, None, None)

    def test_create_missing_required_field(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.post("/api/slicer/jobs", json={"source_kind": "local_file"})
            assert resp.status_code == 400
            assert "archive_intent" in resp.json()["error"]
        finally:
            client.__exit__(None, None, None)


# ---------- Read ----------


class TestReadJob:
    def test_get_existing(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.get(f"/api/slicer/jobs/{created['job_id']}")
            assert resp.status_code == 200
            assert resp.json()["job_id"] == created["job_id"]
        finally:
            client.__exit__(None, None, None)

    def test_get_not_found(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.get("/api/slicer/jobs/nonexistent")
            assert resp.status_code == 404
        finally:
            client.__exit__(None, None, None)


# ---------- List ----------


class TestListJobs:
    def test_list_empty(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.get("/api/slicer/jobs")
            assert resp.status_code == 200
            body = resp.json()
            assert body["items"] == []
            assert body["total"] == 0
        finally:
            client.__exit__(None, None, None)

    def test_list_with_items(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            _create_draft(client)
            _create_draft(client)
            body = client.get("/api/slicer/jobs").json()
            assert body["total"] == 2
            assert len(body["items"]) == 2
        finally:
            client.__exit__(None, None, None)

    def test_list_filter_by_status(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            _create_draft(client)
            body = client.get("/api/slicer/jobs?status=draft").json()
            assert body["total"] == 1
            body2 = client.get("/api/slicer/jobs?status=committed").json()
            assert body2["total"] == 0
        finally:
            client.__exit__(None, None, None)

    def test_list_invalid_status(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.get("/api/slicer/jobs?status=bogus")
            assert resp.status_code == 400
        finally:
            client.__exit__(None, None, None)

    def test_list_pagination(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            for _ in range(3):
                _create_draft(client)
            body = client.get("/api/slicer/jobs?limit=2&offset=0").json()
            assert len(body["items"]) == 2
            assert body["total"] == 3
            body2 = client.get("/api/slicer/jobs?limit=2&offset=2").json()
            assert len(body2["items"]) == 1
        finally:
            client.__exit__(None, None, None)


# ---------- Update ----------


class TestUpdateJob:
    def test_patch_draft(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.patch(
                f"/api/slicer/jobs/{created['job_id']}",
                json={"source_ref": "updated-ref", "requested_print_timezone": "US/Eastern"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["source_ref"] == "updated-ref"
            assert body["requested_print_timezone"] == "US/Eastern"
        finally:
            client.__exit__(None, None, None)

    def test_patch_non_draft_rejected(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            # Transition away from draft
            client.post(
                f"/api/slicer/jobs/{created['job_id']}/transition",
                json={"status": "pending_validation"},
            )
            resp = client.patch(
                f"/api/slicer/jobs/{created['job_id']}",
                json={"source_ref": "nope"},
            )
            assert resp.status_code == 409
        finally:
            client.__exit__(None, None, None)

    def test_patch_not_found(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.patch("/api/slicer/jobs/nonexistent", json={"source_ref": "x"})
            assert resp.status_code == 404
        finally:
            client.__exit__(None, None, None)


# ---------- Transition ----------


class TestTransitionJob:
    def test_draft_to_pending_validation(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.post(
                f"/api/slicer/jobs/{created['job_id']}/transition",
                json={"status": "pending_validation"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "pending_validation"
        finally:
            client.__exit__(None, None, None)

    def test_full_happy_path(self, tmp_path: Path) -> None:
        """draft → pending_validation → validated → slicing → sliced → committing → committed"""
        client = _create_client(tmp_path)
        try:
            job = _create_draft(client)
            jid = job["job_id"]
            transitions = [
                ("pending_validation", {}),
                ("validated", {}),
                ("slicing", {"worker_provider": "bambu_studio", "worker_job_id": "w123"}),
                ("sliced", {"sliced_output_path": "/out/test.gcode", "sliced_output_sha256": "abc123"}),
                ("committing", {"commit_request": {"archive_id": 42}}),
                ("committed", {"created_archive_id": 42, "result_summary": {"ok": True}}),
            ]
            for status, payload in transitions:
                resp = client.post(
                    f"/api/slicer/jobs/{jid}/transition",
                    json={"status": status, **payload},
                )
                assert resp.status_code == 200, f"Failed transition to {status}: {resp.json()}"
                assert resp.json()["status"] == status

            final = client.get(f"/api/slicer/jobs/{jid}").json()
            assert final["status"] == "committed"
            assert final["completed_at"] is not None
            assert final["worker_provider"] == "bambu_studio"
            assert final["sliced_output_path"] == "/out/test.gcode"
            assert final["result_summary"] == {"ok": True}
        finally:
            client.__exit__(None, None, None)

    def test_invalid_transition_rejected(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.post(
                f"/api/slicer/jobs/{created['job_id']}/transition",
                json={"status": "committed"},  # draft → committed is invalid
            )
            assert resp.status_code == 409
        finally:
            client.__exit__(None, None, None)

    def test_failure_records_error(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.post(
                f"/api/slicer/jobs/{created['job_id']}/transition",
                json={"status": "failed", "last_error": "Slicer crashed"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "failed"
            assert body["last_error"] == "Slicer crashed"
            assert body["completed_at"] is not None
        finally:
            client.__exit__(None, None, None)

    def test_failed_to_draft_retry(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            jid = created["job_id"]
            client.post(f"/api/slicer/jobs/{jid}/transition", json={"status": "failed", "last_error": "oops"})
            resp = client.post(f"/api/slicer/jobs/{jid}/transition", json={"status": "draft"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "draft"
            # Error should be cleared on non-failure transition
            assert resp.json()["last_error"] is None
        finally:
            client.__exit__(None, None, None)

    def test_missing_status_field(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.post(
                f"/api/slicer/jobs/{created['job_id']}/transition", json={},
            )
            assert resp.status_code == 400
        finally:
            client.__exit__(None, None, None)

    def test_validation_warnings_persisted(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            jid = created["job_id"]
            warnings = [{"field": "date", "msg": "Date is in the future"}]
            resp = client.post(
                f"/api/slicer/jobs/{jid}/transition",
                json={"status": "pending_validation", "validation_warnings": warnings},
            )
            assert resp.status_code == 200
            assert resp.json()["validation_warnings"] == warnings
        finally:
            client.__exit__(None, None, None)


# ---------- Delete ----------


class TestDeleteJob:
    def test_delete_draft(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            resp = client.delete(f"/api/slicer/jobs/{created['job_id']}")
            assert resp.status_code == 204
            # Confirm gone
            resp2 = client.get(f"/api/slicer/jobs/{created['job_id']}")
            assert resp2.status_code == 404
        finally:
            client.__exit__(None, None, None)

    def test_delete_not_found(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.delete("/api/slicer/jobs/nonexistent")
            assert resp.status_code == 404
        finally:
            client.__exit__(None, None, None)

    def test_delete_non_deletable_rejected(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            jid = created["job_id"]
            # Move to pending_validation (non-deletable)
            client.post(f"/api/slicer/jobs/{jid}/transition", json={"status": "pending_validation"})
            resp = client.delete(f"/api/slicer/jobs/{jid}")
            assert resp.status_code == 409
        finally:
            client.__exit__(None, None, None)

    def test_delete_failed_allowed(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            created = _create_draft(client)
            jid = created["job_id"]
            client.post(f"/api/slicer/jobs/{jid}/transition", json={"status": "failed", "last_error": "x"})
            resp = client.delete(f"/api/slicer/jobs/{jid}")
            assert resp.status_code == 204
        finally:
            client.__exit__(None, None, None)
