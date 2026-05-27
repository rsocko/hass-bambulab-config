"""Tests for Slice 5 — POST /api/slicer/jobs/{job_id}/commit-archive."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.bambuddy_bridge import (
    ArchiveUploadResult,
    ArchivePatchResult,
    BambuddyUpstreamError,
    SourceAttachResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        use_slicer_api=True,
        bambu_studio_api_url="http://bambu-studio-api:3000",
        slicer_async_poll_interval_seconds=0.01,
        slicer_async_max_wait_seconds=5,
    )


def _create_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    return client


def _create_sliced_job(
    client: TestClient, tmp_path: Path, **overrides: Any,
) -> tuple[dict[str, Any], Path, Path]:
    """Create a job in 'sliced' state with fake output file.

    Returns (job_dict, source_file_path, sliced_output_path).
    """
    source_file = tmp_path / "test_model.3mf"
    source_file.write_bytes(b"fake-3mf-source-content")

    sliced_output = tmp_path / "slicer-output" / "test_model.gcode.3mf"
    sliced_output.parent.mkdir(parents=True, exist_ok=True)
    sliced_output.write_bytes(b"fake-sliced-gcode-3mf-content")

    body = {
        "source_kind": "local_file",
        "archive_intent": "create_new",
        "working_file_path": str(source_file),
        **overrides,
    }
    resp = client.post("/api/slicer/jobs", json=body)
    assert resp.status_code == 201
    job = resp.json()
    job_id = job["job_id"]

    # Transition draft → slicing → sliced
    resp = client.post(
        f"/api/slicer/jobs/{job_id}/transition",
        json={
            "status": "slicing",
            "worker_provider": "bambu-studio",
            "worker_job_id": "test-worker-id",
            "source_sha256": hashlib.sha256(b"fake-3mf-source-content").hexdigest(),
        },
    )
    assert resp.status_code == 200

    sha = hashlib.sha256(b"fake-sliced-gcode-3mf-content").hexdigest()
    resp = client.post(
        f"/api/slicer/jobs/{job_id}/transition",
        json={
            "status": "sliced",
            "sliced_output_path": str(sliced_output),
            "sliced_output_sha256": sha,
        },
    )
    assert resp.status_code == 200
    return resp.json(), source_file, sliced_output


# Reusable commit request body
_COMMIT_BODY = {
    "bambuddy_base_url": "http://bambuddy.example",
    "bambuddy_api_key": "test-key",
    "printer_id": 42,
}

_MOCK_UPLOAD = ArchiveUploadResult(
    archive_id=1001,
    raw_response={"id": 1001, "status": "ok"},
)

_MOCK_PATCH = ArchivePatchResult(
    archive_id=1001,
    raw_response={"id": 1001, "patched": True},
)

_MOCK_SOURCE = SourceAttachResult(
    archive_id=1001,
    filename="test_model.3mf",
    raw_response={"filename": "test_model.3mf"},
)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestCommitArchiveHappyPath:
    """Slice 5 acceptance: sliced → committing → committed."""

    @patch("app.routers.slicer.upload_archive", return_value=_MOCK_UPLOAD)
    def test_basic_commit(self, mock_upload, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        job, _, sliced_output = _create_sliced_job(client, tmp_path)

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 200
        result = resp.json()

        assert result["status"] == "committed"
        assert result["created_archive_id"] == 1001
        assert result["completed_at"] is not None
        assert result["result_summary"]["created_archive_id"] == 1001
        mock_upload.assert_called_once()

    @patch("app.routers.slicer.upload_archive", return_value=_MOCK_UPLOAD)
    @patch("app.routers.slicer.patch_archive", return_value=_MOCK_PATCH)
    def test_commit_with_metadata_patch(
        self, mock_patch, mock_upload, tmp_path: Path,
    ) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        body = {
            **_COMMIT_BODY,
            "patch_metadata": {
                "started_at": "2025-01-15T10:00:00Z",
                "completed_at": "2025-01-15T12:30:00Z",
                "tags": "filament:PLA,color:red",
            },
        }
        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=body,
        )
        assert resp.status_code == 200
        result = resp.json()

        assert result["status"] == "committed"
        mock_patch.assert_called_once()
        call_kwargs = mock_patch.call_args[1]
        assert call_kwargs["archive_id"] == 1001
        assert call_kwargs["patch_body"]["started_at"] == "2025-01-15T10:00:00Z"


class TestCommitArchiveTimestampOverride:
    """Acceptance: archive commit uses reviewed historical date, not now."""

    @patch("app.routers.slicer.upload_archive", return_value=_MOCK_UPLOAD)
    @patch("app.routers.slicer.patch_archive", return_value=_MOCK_PATCH)
    def test_historical_timestamp_override(
        self, mock_patch, mock_upload, tmp_path: Path,
    ) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        body = {
            **_COMMIT_BODY,
            "patch_metadata": {
                "started_at": "2024-06-01T08:00:00-04:00",
                "completed_at": "2024-06-01T09:30:00-04:00",
            },
        }
        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=body,
        )
        assert resp.status_code == 200

        # Verify PATCH was called with the historical timestamps
        call_kwargs = mock_patch.call_args[1]
        assert call_kwargs["patch_body"]["started_at"] == "2024-06-01T08:00:00-04:00"
        assert call_kwargs["patch_body"]["completed_at"] == "2024-06-01T09:30:00-04:00"


class TestCommitArchiveEstimateOnly:
    def test_estimate_only_job_cannot_commit(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        try:
            job, _, _ = _create_sliced_job(
                client,
                tmp_path,
                archive_intent="estimate_only",
            )

            resp = client.post(
                f"/api/slicer/jobs/{job['job_id']}/commit-archive",
                json=_COMMIT_BODY,
            )

            assert resp.status_code == 409
            assert "estimate-only" in resp.json()["error"]
        finally:
            client.__exit__(None, None, None)


class TestCommitArchiveSourceAttachment:
    """Acceptance: source-only provenance is a separate explicit step."""

    @patch("app.routers.slicer.upload_archive", return_value=_MOCK_UPLOAD)
    @patch("app.routers.slicer.attach_source", return_value=_MOCK_SOURCE)
    def test_source_attached_when_enabled(
        self, mock_source, mock_upload, tmp_path: Path,
    ) -> None:
        client = _create_client(tmp_path)
        job, source_file, _ = _create_sliced_job(
            client, tmp_path, attach_source_after_create=True,
        )

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 200
        result = resp.json()

        assert result["status"] == "committed"
        assert result["result_summary"]["source_response"] is not None
        mock_source.assert_called_once()
        call_kwargs = mock_source.call_args[1]
        assert call_kwargs["archive_id"] == 1001
        assert call_kwargs["source_3mf_path"] == source_file

    @patch("app.routers.slicer.upload_archive", return_value=_MOCK_UPLOAD)
    def test_source_not_attached_when_disabled(
        self, mock_upload, tmp_path: Path,
    ) -> None:
        """Default: no source attachment unless explicitly requested."""
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 200
        result = resp.json()

        assert result["status"] == "committed"
        # No source_response in result_summary
        assert "source_response" not in result["result_summary"]


class TestCommitArchiveIdempotency:
    """Acceptance: retries must not silently create duplicate archives."""

    @patch("app.routers.slicer.upload_archive", return_value=_MOCK_UPLOAD)
    def test_retry_returns_existing_result(
        self, mock_upload, tmp_path: Path,
    ) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        # First commit
        resp1 = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "committed"

        # Second commit (retry) — should return existing, not re-upload
        resp2 = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "committed"
        assert resp2.json()["created_archive_id"] == 1001

        # Upload should have been called only once
        assert mock_upload.call_count == 1


class TestCommitArchiveStatusGuard:
    """Non-sliced jobs should be rejected."""

    def test_draft_rejected(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        # Create a draft job (don't advance to sliced)
        source_file = tmp_path / "model.3mf"
        source_file.write_bytes(b"content")
        resp = client.post("/api/slicer/jobs", json={
            "source_kind": "local_file",
            "archive_intent": "create_new",
            "working_file_path": str(source_file),
        })
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        resp = client.post(
            f"/api/slicer/jobs/{job_id}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 409
        assert "must be 'sliced'" in resp.json()["error"]

    def test_nonexistent_job_404(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        resp = client.post(
            "/api/slicer/jobs/does-not-exist/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 404


class TestCommitArchiveMissingOutput:
    """Sliced output must exist on disk."""

    def test_missing_output_file(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        job, _, sliced_output = _create_sliced_job(client, tmp_path)

        # Delete the sliced output
        sliced_output.unlink()

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["error"]


class TestCommitArchiveFailureHandling:
    """Bambuddy errors should transition job to failed."""

    @patch(
        "app.routers.slicer.upload_archive",
        side_effect=BambuddyUpstreamError("Connection refused", status_code=503),
    )
    def test_upload_failure_transitions_to_failed(
        self, mock_upload, tmp_path: Path,
    ) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json=_COMMIT_BODY,
        )
        assert resp.status_code == 502

        # Verify job is now failed
        get_resp = client.get(f"/api/slicer/jobs/{job['job_id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "failed"
        assert "Connection refused" in get_resp.json()["last_error"]


class TestCommitArchiveRetryAfterFailure:
    """Acceptance: retry after forced Bambuddy failure."""

    def test_retry_succeeds_after_failure(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        # First attempt: Bambuddy fails
        with patch(
            "app.routers.slicer.upload_archive",
            side_effect=BambuddyUpstreamError("Server down", status_code=503),
        ):
            resp = client.post(
                f"/api/slicer/jobs/{job['job_id']}/commit-archive",
                json=_COMMIT_BODY,
            )
            assert resp.status_code == 502

        # Job is now failed
        get_resp = client.get(f"/api/slicer/jobs/{job['job_id']}")
        assert get_resp.json()["status"] == "failed"

        # Reset: failed → draft → slicing → sliced
        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/transition",
            json={"status": "draft"},
        )
        assert resp.status_code == 200

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/transition",
            json={"status": "slicing", "worker_provider": "bambu-studio"},
        )
        assert resp.status_code == 200

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/transition",
            json={
                "status": "sliced",
                "sliced_output_path": job["sliced_output_path"],
                "sliced_output_sha256": job["sliced_output_sha256"],
            },
        )
        assert resp.status_code == 200

        # Second attempt: Bambuddy succeeds
        with patch(
            "app.routers.slicer.upload_archive",
            return_value=_MOCK_UPLOAD,
        ):
            resp = client.post(
                f"/api/slicer/jobs/{job['job_id']}/commit-archive",
                json=_COMMIT_BODY,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "committed"
            assert resp.json()["created_archive_id"] == 1001


class TestCommitArchiveValidation:
    """Request body validation."""

    def test_missing_bambuddy_url(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json={"printer_id": 1},
        )
        assert resp.status_code == 400
        assert "bambuddy_base_url" in resp.json()["error"]

    def test_missing_printer_id(self, tmp_path: Path) -> None:
        client = _create_client(tmp_path)
        job, _, _ = _create_sliced_job(client, tmp_path)

        resp = client.post(
            f"/api/slicer/jobs/{job['job_id']}/commit-archive",
            json={"bambuddy_base_url": "http://example.com"},
        )
        assert resp.status_code == 400
        assert "printer_id" in resp.json()["error"]
