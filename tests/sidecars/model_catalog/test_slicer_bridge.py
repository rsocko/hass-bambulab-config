"""Tests for slicer_bridge.py and POST /api/slicer/jobs/{job_id}/execute."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.slicer_bridge import (
    SliceEnqueueResult,
    SliceOutputResult,
    SlicePollResult,
    SlicerTimeoutError,
    SlicerUpstreamError,
    enqueue_slice,
    poll_slice,
    cleanup_slice,
    poll_until_terminal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(db_path: Path, *, use_slicer: bool = True, assets_root: Path | None = None) -> Settings:
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
        use_slicer_api=use_slicer,
        bambu_studio_api_url="http://bambu-studio-api:3000",
        slicer_async_poll_interval_seconds=0.01,  # fast for tests
        slicer_async_max_wait_seconds=5,
        model_catalog_assets_root=assets_root,
    )


def _create_client(tmp_path: Path, *, use_slicer: bool = True, assets_root: Path | None = None) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path, use_slicer=use_slicer, assets_root=assets_root))
    client = TestClient(app)
    client.__enter__()
    return client


def _create_draft_with_file(
    client: TestClient, tmp_path: Path, **overrides: Any,
) -> tuple[dict[str, Any], Path]:
    """Create a draft job and a fake source .3mf file."""
    source_file = tmp_path / "test_model.3mf"
    source_file.write_bytes(b"fake-3mf-content-for-testing")

    body = {
        "source_kind": "local_file",
        "archive_intent": "create_new",
        "working_file_path": str(source_file),
        **overrides,
    }
    resp = client.post("/api/slicer/jobs", json=body)
    assert resp.status_code == 201
    return resp.json(), source_file


# Reusable mock results

_MOCK_ENQUEUE = SliceEnqueueResult(
    request_id="test-uuid-1234",
    status="pending",
    status_url="/slice-async/test-uuid-1234",
)

_MOCK_POLL_COMPLETED = SlicePollResult(
    request_id="test-uuid-1234",
    status="completed",
    metadata={"printTime": 3600, "filamentUsedG": 25.5, "filamentUsedMm": 8500},
    download_url="/slice-async/test-uuid-1234/result",
)

_MOCK_POLL_FAILED = SlicePollResult(
    request_id="test-uuid-1234",
    status="failed",
    error_message="OrcaSlicer crashed during slicing",
)


def _mock_retrieve_output(*, base_url, request_id, dest_path, timeout=300.0):
    """Write fake sliced output and return a result."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    content = b"sliced-gcode-3mf-content"
    dest_path.write_bytes(content)
    return SliceOutputResult(
        output_path=dest_path,
        sha256=hashlib.sha256(content).hexdigest(),
        content_length=len(content),
        metadata={"print_time_seconds": 3600.0, "filament_used_g": 25.5},
    )


# ---------------------------------------------------------------------------
# Bridge unit tests
# ---------------------------------------------------------------------------


class TestEnqueueSlice:
    def test_enqueue_success(self, tmp_path: Path) -> None:
        source = tmp_path / "model.3mf"
        source.write_bytes(b"test-3mf")

        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "requestId": "abc-123",
            "status": "pending",
            "statusUrl": "/slice-async/abc-123",
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            result = enqueue_slice(
                base_url="http://slicer:3000",
                file_path=source,
            )

        assert result.request_id == "abc-123"
        assert result.status == "pending"
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "/slice-async" in call_kwargs[0][0]

    def test_enqueue_400_raises(self, tmp_path: Path) -> None:
        source = tmp_path / "model.3mf"
        source.write_bytes(b"test-3mf")

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"message": "Missing file"}
        mock_resp.text = '{"message": "Missing file"}'

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            with pytest.raises(SlicerUpstreamError) as exc_info:
                enqueue_slice(base_url="http://slicer:3000", file_path=source)
        assert exc_info.value.status_code == 400

    def test_enqueue_passes_overrides(self, tmp_path: Path) -> None:
        source = tmp_path / "model.3mf"
        source.write_bytes(b"test-3mf")

        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "requestId": "xyz", "status": "pending", "statusUrl": "",
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            enqueue_slice(
                base_url="http://slicer:3000",
                file_path=source,
                overrides={"printer": "Bambu Lab X1C", "plate": "0"},
            )

        call_kwargs = mock_client.post.call_args
        data = call_kwargs[1]["data"]
        assert data["printer"] == "Bambu Lab X1C"
        assert data["plate"] == "0"

    def test_enqueue_passes_multi_filament_override(self, tmp_path: Path) -> None:
        source = tmp_path / "model.3mf"
        source.write_bytes(b"test-3mf")

        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.json.return_value = {
            "requestId": "xyz", "status": "pending", "statusUrl": "",
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            enqueue_slice(
                base_url="http://slicer:3000",
                file_path=source,
                overrides={"filaments": "Bambu PLA Basic @BBL P1S;Bambu PETG Basic @BBL P1S"},
            )

        call_kwargs = mock_client.post.call_args
        data = call_kwargs[1]["data"]
        assert data["filaments"] == "Bambu PLA Basic @BBL P1S;Bambu PETG Basic @BBL P1S"


class TestPollSlice:
    def test_poll_completed(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "requestId": "abc-123",
            "status": "completed",
            "metadata": {"printTime": 1200},
            "downloadUrl": "/slice-async/abc-123/result",
        }

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            result = poll_slice(base_url="http://slicer:3000", request_id="abc-123")

        assert result.status == "completed"
        assert result.metadata == {"printTime": 1200}

    def test_poll_404_raises(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"message": "Job not found"}
        mock_resp.text = '{"message": "Job not found"}'

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            with pytest.raises(SlicerUpstreamError) as exc_info:
                poll_slice(base_url="http://slicer:3000", request_id="nope")
        assert exc_info.value.status_code == 404


class TestCleanupSlice:
    def test_cleanup_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.delete.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            assert cleanup_slice(base_url="http://slicer:3000", request_id="abc") is True

    def test_cleanup_not_found(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.delete.return_value = mock_resp

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            assert cleanup_slice(base_url="http://slicer:3000", request_id="abc") is False

    def test_cleanup_connection_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.delete.side_effect = Exception("Connection refused")

        with patch("app.slicer_bridge.httpx.Client", return_value=mock_client):
            assert cleanup_slice(base_url="http://slicer:3000", request_id="abc") is False


class TestPollUntilTerminal:
    def test_completes_after_two_polls(self) -> None:
        pending = SlicePollResult(request_id="x", status="processing")
        completed = SlicePollResult(
            request_id="x", status="completed",
            metadata={"printTime": 600},
        )

        with patch(
            "app.slicer_bridge.poll_slice",
            side_effect=[pending, completed],
        ), patch("app.slicer_bridge.time.sleep"):
            result = poll_until_terminal(
                base_url="http://slicer:3000",
                request_id="x",
                poll_interval=0.01,
                max_wait=10.0,
            )

        assert result.status == "completed"

    def test_timeout_raises(self) -> None:
        pending = SlicePollResult(request_id="x", status="processing")

        with patch(
            "app.slicer_bridge.poll_slice", return_value=pending,
        ), patch(
            "app.slicer_bridge.time.monotonic", side_effect=[0.0, 100.0],
        ):
            with pytest.raises(SlicerTimeoutError):
                poll_until_terminal(
                    base_url="http://slicer:3000",
                    request_id="x",
                    poll_interval=0.01,
                    max_wait=5.0,
                )


# ---------------------------------------------------------------------------
# Execute endpoint tests
# ---------------------------------------------------------------------------


class TestExecuteJob:
    def test_execute_success(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, source_file = _create_draft_with_file(client, tmp_path)
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_COMPLETED),
                patch("app.routers.slicer.retrieve_output", side_effect=_mock_retrieve_output),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 200
            result = resp.json()
            assert result["status"] == "sliced"
            assert result["worker_provider"] == "bambu-studio"
            assert result["worker_job_id"] == "test-uuid-1234"
            assert result["sliced_output_path"] is not None
            assert result["sliced_output_sha256"] is not None
            assert result["source_sha256"] is not None
            assert result["result_summary"]["content_length"] > 0
        finally:
            client.__exit__(None, None, None)

    def test_execute_slicer_disabled(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path, use_slicer=False)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            resp = client.post(f"/api/slicer/jobs/{job['job_id']}/execute")
            assert resp.status_code == 503
        finally:
            client.__exit__(None, None, None)

    def test_execute_job_not_found(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            resp = client.post("/api/slicer/jobs/nonexistent/execute")
            assert resp.status_code == 404
        finally:
            client.__exit__(None, None, None)

    def test_execute_rejects_non_3mf_source(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            source_file = tmp_path / "test_model.stl"
            source_file.write_bytes(b"fake-stl-content-for-testing")

            resp = client.post(
                "/api/slicer/jobs",
                json={
                    "source_kind": "local_file",
                    "archive_intent": "create_new",
                    "working_file_path": str(source_file),
                },
            )
            assert resp.status_code == 201
            job_id = resp.json()["job_id"]

            with patch("app.routers.slicer.enqueue_slice") as enqueue_mock:
                execute_resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert execute_resp.status_code == 400
            assert ".3mf" in execute_resp.json()["error"]
            enqueue_mock.assert_not_called()
        finally:
            client.__exit__(None, None, None)

    def test_execute_wrong_status(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            # Transition draft → slicing (now allowed)
            resp = client.post(
                f"/api/slicer/jobs/{job['job_id']}/transition",
                json={"status": "slicing"},
            )
            assert resp.status_code == 200

            # Try execute on a slicing job — should 409
            resp = client.post(f"/api/slicer/jobs/{job['job_id']}/execute")
            assert resp.status_code == 409
        finally:
            client.__exit__(None, None, None)

    def test_execute_no_working_file(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            # Create draft without working_file_path
            body = {"source_kind": "local_file", "archive_intent": "create_new"}
            resp = client.post("/api/slicer/jobs", json=body)
            assert resp.status_code == 201
            job_id = resp.json()["job_id"]

            resp = client.post(f"/api/slicer/jobs/{job_id}/execute")
            assert resp.status_code == 400
            assert "working_file_path" in resp.json()["error"]
        finally:
            client.__exit__(None, None, None)

    def test_execute_source_file_missing(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            body = {
                "source_kind": "local_file",
                "archive_intent": "create_new",
                "working_file_path": str(tmp_path / "does_not_exist.3mf"),
            }
            resp = client.post("/api/slicer/jobs", json=body)
            assert resp.status_code == 201
            job_id = resp.json()["job_id"]

            resp = client.post(f"/api/slicer/jobs/{job_id}/execute")
            assert resp.status_code == 400
            assert "not found" in resp.json()["error"]
        finally:
            client.__exit__(None, None, None)

    def test_execute_relative_storage_path_resolves_from_curated_assets_root(self, tmp_path: Path) -> None:
        assets_root = tmp_path / "assets" / "Model Catalog"
        source_file = assets_root / "demo-model" / "test_model.3mf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake-3mf-content-for-testing")

        client = _create_client(tmp_path, assets_root=assets_root)
        try:
            resp = client.post(
                "/api/slicer/jobs",
                json={
                    "source_kind": "local_file",
                    "archive_intent": "create_new",
                    "local_model_id": "demo-model",
                    "working_file_path": "demo-model/test_model.3mf",
                    "source_file_name": "test_model.3mf",
                },
            )
            assert resp.status_code == 201
            job_id = resp.json()["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_COMPLETED),
                patch("app.routers.slicer.retrieve_output", side_effect=_mock_retrieve_output),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                execute_resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert execute_resp.status_code == 200
            assert execute_resp.json()["status"] == "sliced"
        finally:
            client.__exit__(None, None, None)

    def test_execute_upstream_failure(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_FAILED),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 502
            result = resp.json()
            assert result["status"] == "failed"
            assert "crashed" in result["last_error"]
        finally:
            client.__exit__(None, None, None)

    def test_execute_bridge_error(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            job_id = job["job_id"]

            with (
                patch(
                    "app.routers.slicer.enqueue_slice",
                    side_effect=SlicerUpstreamError("Connection refused", status_code=None),
                ),
                patch("app.routers.slicer.cleanup_slice", return_value=False),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 502
            assert "Connection refused" in resp.json()["error"]

            # Verify job is marked failed
            job_resp = client.get(f"/api/slicer/jobs/{job_id}")
            assert job_resp.json()["status"] == "failed"
        finally:
            client.__exit__(None, None, None)

    def test_execute_timeout(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch(
                    "app.routers.slicer.poll_until_terminal",
                    side_effect=SlicerTimeoutError("timed out"),
                ),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 502
            assert "timed out" in resp.json()["error"]
        finally:
            client.__exit__(None, None, None)

    def test_execute_cleanup_always_called(self, tmp_path: Path) -> None:
        """Verify cleanup_slice is called even when slicing fails."""
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            job_id = job["job_id"]

            mock_cleanup = MagicMock(return_value=True)
            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_FAILED),
                patch("app.routers.slicer.cleanup_slice", mock_cleanup),
            ):
                client.post(f"/api/slicer/jobs/{job_id}/execute")

            mock_cleanup.assert_called_once_with(
                base_url="http://bambu-studio-api:3000",
                request_id="test-uuid-1234",
            )
        finally:
            client.__exit__(None, None, None)

    def test_execute_uses_selected_plate_index_as_plate_override(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path, selected_plate_index=2)
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE) as mock_enqueue,
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_COMPLETED),
                patch("app.routers.slicer.retrieve_output", side_effect=_mock_retrieve_output),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 200
            assert mock_enqueue.call_args.kwargs["overrides"]["plate"] == "2"
        finally:
            client.__exit__(None, None, None)

    def test_execute_forwards_multi_filament_override(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(
                client,
                tmp_path,
                overrides={
                    "filament_overrides": [
                        {"slot_index": 0, "profile_name": "Bambu PLA Basic @BBL P1S"},
                        {"slot_index": 1, "profile_name": "Bambu PETG Basic @BBL P1S"},
                    ],
                    "filaments": "Bambu PLA Basic @BBL P1S;Bambu PETG Basic @BBL P1S",
                },
            )
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE) as mock_enqueue,
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_COMPLETED),
                patch("app.routers.slicer.retrieve_output", side_effect=_mock_retrieve_output),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 200
        finally:
            client.__exit__(None, None, None)

    def test_execute_estimate_only_discards_output_but_keeps_metadata(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(
                client,
                tmp_path,
                archive_intent="estimate_only",
            )
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_COMPLETED),
                patch("app.routers.slicer.retrieve_output", side_effect=_mock_retrieve_output),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert resp.status_code == 200
            result = resp.json()
            assert result["status"] == "sliced"
            assert result["archive_intent"] == "estimate_only"
            assert result["sliced_output_path"] is None
            assert result["sliced_output_sha256"] is None
            assert result["result_summary"]["estimate_only"] is True
            assert result["result_summary"]["artifact_retained"] is False
            assert result["result_summary"]["estimated_print_time_seconds"] == 3600.0
        finally:
            client.__exit__(None, None, None)

    def test_execute_estimate_only_updates_matching_unified_queue_entry(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            queue_resp = client.post(
                "/api/unified-queue/entries",
                json={
                    "source_kind": "catalog_model",
                    "source_id": "model-123",
                    "title": "Queue Target",
                    "estimate_metadata": {
                        "manual": {
                            "minutes": 120,
                        },
                    },
                },
            )
            assert queue_resp.status_code == 200
            queue_entry_id = queue_resp.json()["entry"]["queue_entry_id"]

            job, _ = _create_draft_with_file(
                client,
                tmp_path,
                archive_intent="estimate_only",
                local_model_id="model-123",
                overrides={
                    "printer": "Bambu Lab P1S 0.4 nozzle",
                    "preset": "0.20mm Standard @BBL P1S",
                    "filament": "Bambu PLA Basic @BBL P1S",
                },
            )
            job_id = job["job_id"]

            with (
                patch("app.routers.slicer.enqueue_slice", return_value=_MOCK_ENQUEUE),
                patch("app.routers.slicer.poll_until_terminal", return_value=_MOCK_POLL_COMPLETED),
                patch("app.routers.slicer.retrieve_output", side_effect=_mock_retrieve_output),
                patch("app.routers.slicer.cleanup_slice", return_value=True),
            ):
                execute_resp = client.post(f"/api/slicer/jobs/{job_id}/execute")

            assert execute_resp.status_code == 200
            execute_body = execute_resp.json()
            assert execute_body["result_summary"]["queue_entry_ids_updated"] == [queue_entry_id]

            queue_get = client.get(f"/api/unified-queue/entries/{queue_entry_id}")
            assert queue_get.status_code == 200
            queue_entry = queue_get.json()["entry"]
            assert queue_entry["estimate_metadata"]["manual"]["minutes"] == 120
            assert queue_entry["estimate_metadata"]["slicer"]["minutes"] == 60
            assert queue_entry["estimate_metadata"]["slicer"]["status"] == "fresh"
            assert queue_entry["estimate_metadata"]["slicer"]["profile_key"] is not None
            assert queue_entry["estimate_metadata"]["slicer"]["source_sha256"] is not None
        finally:
            client.__exit__(None, None, None)

            assert resp.status_code == 200
            assert mock_enqueue.call_args.kwargs["overrides"]["filaments"] == "Bambu PLA Basic @BBL P1S;Bambu PETG Basic @BBL P1S"
        finally:
            client.__exit__(None, None, None)

    def test_draft_to_slicing_transition_allowed(self, tmp_path: Path) -> None:
        """Verify that the draft → slicing transition was added."""
        client = _create_client(tmp_path)
        try:
            job, _ = _create_draft_with_file(client, tmp_path)
            resp = client.post(
                f"/api/slicer/jobs/{job['job_id']}/transition",
                json={"status": "slicing"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "slicing"
        finally:
            client.__exit__(None, None, None)
