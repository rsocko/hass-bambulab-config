"""Tests for Phase B #1148: Manyfold upload adapter for intake queue."""

import hashlib
import json
import sqlite3
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.manyfold import MANYFOLD_API_ACCEPT, ManyfoldClient
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path, source_roots: list[Path] | None = None) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="client-id",
        manyfold_client_secret="client-secret",
        manyfold_oauth_scopes="public read",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
        source_filesystem_roots=tuple(source_roots or []),
    )


def _build_manyfold_client(
    *,
    file_name: str,
    file_bytes: bytes,
    verification_hash: str | None,
    collection_id: int = 42,
    collection_name: str = "Tools",
    returned_file_name: str | None = None,
    returned_size: int | None = None,
) -> ManyfoldClient:
    model_public_id = "model-900"
    model_url = "/models/900"
    file_id = "file-900"
    file_url = f"{model_url}/model_files/{file_id}"
    download_url = f"{file_url}.3mf?download=true"
    expected_size = len(file_bytes)
    response_file_name = returned_file_name or file_name
    response_size = returned_size if returned_size is not None else expected_size

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})

        if request.method == "GET" and request.url.path == "/collections.json":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": collection_id,
                            "@id": f"/collections/{collection_name.lower()}",
                            "name": collection_name,
                        }
                    ]
                },
            )

        if request.method == "POST" and request.url.path == "/models.json":
            assert request.headers.get("Authorization") == "Bearer token-123"
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            assert request.headers.get("Content-Type") == "application/json"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["name"]
            return httpx.Response(
                200,
                json={
                    "id": 900,
                    "public_id": model_public_id,
                    "url": model_url,
                    "name": payload["name"],
                },
            )

        if request.method == "POST" and request.url.path == f"/models/{model_public_id}/files":
            assert request.headers.get("Authorization") == "Bearer token-123"
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            return httpx.Response(
                200,
                json={
                    "id": file_id,
                    "@id": file_url,
                    "filename": response_file_name,
                    "contentUrl": download_url,
                    "size": response_size,
                },
            )

        if request.method == "GET" and request.url.path == f"/models/{model_public_id}.json":
            file_row = {
                "id": file_id,
                "@id": file_url,
                "filename": response_file_name,
                "contentUrl": download_url,
                "size": response_size,
            }
            if verification_hash:
                file_row["source_sha256"] = verification_hash
            return httpx.Response(
                200,
                json={
                    "id": 900,
                    "public_id": model_public_id,
                    "url": model_url,
                    "hasPart": [file_row],
                },
            )

        if request.method == "GET" and request.url.path == f"/models/{model_public_id}/model_files":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": file_id,
                            "@id": file_url,
                            "filename": response_file_name,
                            "contentUrl": download_url,
                            "size": response_size,
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    return ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )


def test_manyfold_upload_adapter_requires_upload_exists(tmp_path: Path) -> None:
    """Upload to Manyfold fails for non-existent upload."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads/nonexistent/upload-to-manyfold",
            json={"collection_id": 1},
        )
        assert response.status_code == 404
        assert response.json()["error"] == "upload_not_found"


def test_manyfold_upload_adapter_requires_verified_state(tmp_path: Path) -> None:
    """Upload to Manyfold requires upload to be in verified state."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-001",
                "queued",  # Not verified yet
                '[]',
                "unverified",
                "keep",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads/upload-001/upload-to-manyfold",
            json={"collection_id": 1},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "upload_not_verified"


def test_manyfold_upload_adapter_accepts_verified_upload(tmp_path: Path) -> None:
    """Upload to Manyfold succeeds for verified upload."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = tmp_path / "widget.3mf"
    source_bytes = b"verified-widget"
    source_file.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-26T10:00:00Z"
        connection.execute(
            """
            INSERT INTO working_groups (
                slug, title, stage, notes, primary_file_path, folder_hint,
                related_manyfold_model_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "verified-upload",
                "Verified Upload",
                "draft",
                None,
                str(source_file),
                str(tmp_path),
                None,
                now,
                now,
            ),
        )
        working_group_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO working_items (
                working_group_id, file_path, item_role, created_at, updated_at,
                file_hash, file_size, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                working_group_id,
                str(source_file),
                "primary",
                now,
                now,
                source_hash,
                len(source_bytes),
                "{}",
            ),
        )
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-002",
                "uploaded_unverified",  # Verified
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "keep",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        original_client = app.state.manyfold_client
        original_client.close()
        mock_client = _build_manyfold_client(file_name=source_file.name, file_bytes=source_bytes, verification_hash=source_hash)
        app.state.manyfold_client = mock_client
        response = test_client.post(
            "/api/intake/uploads/upload-002/upload-to-manyfold?collection_id=42",
            json={"collection_name": "Tools"},
        )
        assert response.status_code == 200
        payload = response.json()
        
        assert payload["success"] is True
        assert payload["upload_id"] == "upload-002"
        assert payload["status"] == "verified"
        assert payload["verification_status"] == "pass"
        assert payload["cleanup"]["status"] == "skipped"
        assert payload["manyfold_response"]["collection_id"] == 42
        assert payload["manyfold_response"]["collection_name"] == "Tools"
        assert payload["manyfold_response"]["collection_ref"] == "/collections/tools"
        assert len(payload["files_uploaded"]) == 1
        uploaded = payload["files_uploaded"][0]
        assert uploaded["manyfold_model_ref"] == "model-900"
        assert uploaded["manyfold_file_ref"] == "file-900"
        assert uploaded["manyfold_model_url"] == "http://manyfold.test/models/900"
        assert uploaded["manyfold_file_url"] == "http://manyfold.test/models/900/model_files/file-900.3mf?download=true"
        assert uploaded["verification_method"] == "hash"
        assert "adapter_version" in payload["meta"]
        mock_client.close()

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        upload_row = connection.execute(
            "SELECT status, verification_status, file_hashes_json, manyfold_file_ids_json, verified_at FROM intake_queue_uploads WHERE upload_id = ?",
            ("upload-002",),
        ).fetchone()
        assert upload_row is not None
        assert upload_row["status"] == "verified"
        assert upload_row["verification_status"] == "pass"
        assert json.loads(str(upload_row["file_hashes_json"])) == [source_hash]
        assert json.loads(str(upload_row["manyfold_file_ids_json"])) == ["file-900"]
        assert upload_row["verified_at"] is not None

        working_item = connection.execute(
            "SELECT source_metadata_json FROM working_items WHERE file_hash = ?",
            (source_hash,),
        ).fetchone()
        assert working_item is not None
        metadata = json.loads(str(working_item["source_metadata_json"]))
        destination = metadata["manyfold_destination"]
        assert destination["upload_id"] == "upload-002"
        assert destination["verification_status"] == "pass"
        assert destination["manyfold_model_ref"] == "model-900"
        assert destination["manyfold_file_ref"] == "file-900"
        assert destination["canonical_model_url"] == "http://manyfold.test/models/900"
        assert destination["canonical_file_url"] == "http://manyfold.test/models/900/model_files/file-900.3mf?download=true"
    finally:
        connection.close()


def test_manyfold_upload_adapter_with_collection_name_parameter(tmp_path: Path) -> None:
    """Upload to Manyfold accepts collection_name parameter."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = tmp_path / "gridfinity.3mf"
    source_bytes = b"gridfinity"
    source_file.write_bytes(source_bytes)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-003",
                "uploaded_unverified",
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "keep",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        original_client = app.state.manyfold_client
        original_client.close()
        mock_client = _build_manyfold_client(
            file_name=source_file.name,
            file_bytes=source_bytes,
            verification_hash=hashlib.sha256(source_bytes).hexdigest(),
            collection_name="Gridfinity",
        )
        app.state.manyfold_client = mock_client
        response = test_client.post(
            "/api/intake/uploads/upload-003/upload-to-manyfold?collection_name=Gridfinity",
        )
        assert response.status_code == 200
        payload = response.json()
        
        assert payload["success"] is True
        assert payload["manyfold_response"]["collection_name"] == "Gridfinity"
        assert payload["manyfold_response"]["collection_ref"] == "/collections/gridfinity"
        mock_client.close()


def test_manyfold_upload_adapter_marks_failed_when_verification_cannot_match(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = tmp_path / "broken.3mf"
    source_bytes = b"broken-model"
    source_file.write_bytes(source_bytes)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-004",
                "uploaded_unverified",
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "keep",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_manyfold_upload_adapter_delete_policy_removes_source_after_verification(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    settings = _build_settings(tmp_path, [root])
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = root / "delete-me.3mf"
    source_bytes = b"delete-me"
    source_file.write_bytes(source_bytes)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-005",
                "uploaded_unverified",
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "delete_on_verified",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        original_client = app.state.manyfold_client
        original_client.close()
        mock_client = _build_manyfold_client(
            file_name=source_file.name,
            file_bytes=source_bytes,
            verification_hash=hashlib.sha256(source_bytes).hexdigest(),
        )
        app.state.manyfold_client = mock_client
        response = test_client.post("/api/intake/uploads/upload-005/upload-to-manyfold")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cleanup_done"
        assert payload["cleanup"]["status"] == "cleanup_done"
        assert payload["cleanup"]["processed_count"] == 1
        assert payload["cleanup"]["failed_count"] == 0
        mock_client.close()

    assert source_file.exists() is False

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT status, cleanup_done_at FROM intake_queue_uploads WHERE upload_id = ?",
            ("upload-005",),
        ).fetchone()
        assert row is not None
        assert row["status"] == "cleanup_done"
        assert row["cleanup_done_at"] is not None
    finally:
        connection.close()


def test_manyfold_upload_adapter_replace_policy_writes_stub(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    settings = _build_settings(tmp_path, [root])
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = root / "replace-me.3mf"
    source_bytes = b"replace-me"
    source_file.write_bytes(source_bytes)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-006",
                "uploaded_unverified",
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "replace_with_stub",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        original_client = app.state.manyfold_client
        original_client.close()
        mock_client = _build_manyfold_client(
            file_name=source_file.name,
            file_bytes=source_bytes,
            verification_hash=hashlib.sha256(source_bytes).hexdigest(),
        )
        app.state.manyfold_client = mock_client
        response = test_client.post("/api/intake/uploads/upload-006/upload-to-manyfold")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cleanup_done"
        assert payload["cleanup"]["results"][0]["action"] == "replaced_with_stub"
        mock_client.close()

    stub_text = source_file.read_text(encoding="utf-8")
    assert "[MODEL_CATALOG_UPLOAD_STUB_V1]" in stub_text
    assert "manyfold_model_ref=model-900" in stub_text
    assert "manyfold_file_ref=file-900" in stub_text


def test_manyfold_upload_adapter_cleanup_fails_outside_allowlisted_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    settings = _build_settings(tmp_path, [allowed_root])
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = outside_root / "outside.3mf"
    source_bytes = b"outside"
    source_file.write_bytes(source_bytes)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-007",
                "uploaded_unverified",
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "delete_on_verified",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        original_client = app.state.manyfold_client
        original_client.close()
        mock_client = _build_manyfold_client(
            file_name=source_file.name,
            file_bytes=source_bytes,
            verification_hash=hashlib.sha256(source_bytes).hexdigest(),
        )
        app.state.manyfold_client = mock_client
        response = test_client.post("/api/intake/uploads/upload-007/upload-to-manyfold")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cleanup_failed"
        assert payload["cleanup"]["status"] == "cleanup_failed"
        assert payload["cleanup"]["failed_count"] == 1
        assert payload["cleanup"]["results"][0]["reason"] == "path_not_allowed"
        mock_client.close()

    assert source_file.exists() is True

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT status FROM intake_queue_uploads WHERE upload_id = ?",
            ("upload-007",),
        ).fetchone()
        assert row is not None
        assert row["status"] == "cleanup_failed"
    finally:
        connection.close()


def test_intake_cleanup_endpoint_retries_cleanup_failed_upload(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    settings = _build_settings(tmp_path, [root])
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    source_file = root / "retry.3mf"
    source_file.write_bytes(b"retry")

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-008",
                "cleanup_failed",
                json.dumps([{"type": "file", "path": str(source_file)}]),
                "pass",
                "delete_on_verified",
                "2026-04-26T10:00:00Z",
                "2026-04-26T10:05:00Z",
                "2026-04-26T10:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        response = test_client.post("/api/intake/uploads/upload-008/cleanup")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cleanup_done"
        assert payload["cleanup"]["processed_count"] == 1

    assert source_file.exists() is False
