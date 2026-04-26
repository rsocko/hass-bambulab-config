"""Tests for Phase B #1148: Manyfold upload adapter for intake queue."""

import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
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
                "upload-002",
                "uploaded_unverified",  # Verified
                '[]',
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
        response = test_client.post(
            "/api/intake/uploads/upload-002/upload-to-manyfold?collection_id=42",
            json={"collection_name": "Tools"},
        )
        assert response.status_code == 200
        payload = response.json()
        
        assert payload["success"] is True
        assert payload["upload_id"] == "upload-002"
        assert payload["manyfold_response"]["collection_id"] == 42
        assert payload["manyfold_response"]["collection_name"] == "Tools"
        assert payload["files_uploaded"] == []
        assert "adapter_version" in payload["meta"]


def test_manyfold_upload_adapter_with_collection_name_parameter(tmp_path: Path) -> None:
    """Upload to Manyfold accepts collection_name parameter."""
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
                "upload-003",
                "uploaded_unverified",
                '[]',
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
        response = test_client.post(
            "/api/intake/uploads/upload-003/upload-to-manyfold?collection_name=Gridfinity",
        )
        assert response.status_code == 200
        payload = response.json()
        
        assert payload["success"] is True
        assert payload["manyfold_response"]["collection_name"] == "Gridfinity"
