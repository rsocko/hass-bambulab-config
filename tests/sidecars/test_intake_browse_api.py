"""Tests for Phase B #1147: Filesystem browse API for intake queue."""

from pathlib import Path
import os
import zipfile
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        catalog_base_url="http://localhost:8314",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
    )


def test_intake_browse_shows_virtual_root_with_allowlist_paths(monkeypatch, tmp_path: Path) -> None:
    """Browse root returns virtual listing of allowlist paths."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    
    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", f"{models_dir},{storage_dir}")
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    with TestClient(app) as test_client:
        response = test_client.get("/api/intake/browse")
        assert response.status_code == 200
        payload = response.json()
        
        assert payload["success"] is True
        assert payload["path"] == "/"
        assert payload["is_root"] is True
        assert payload["type"] == "virtual_root"
        
        paths = {entry["path"] for entry in payload["entries"]}
        assert str(models_dir) in paths
        assert str(storage_dir) in paths


def test_intake_browse_lists_folder_contents(monkeypatch, tmp_path: Path) -> None:
    """Browse folder returns file/folder listing."""
    test_dir = tmp_path / "models"
    test_dir.mkdir()
    
    file1 = test_dir / "model1.3mf"
    file1.write_bytes(b"content1")
    file2 = test_dir / "model2.stl"
    file2.write_bytes(b"content2")
    subfolder = test_dir / "subfolder"
    subfolder.mkdir()
    
    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", str(test_dir))
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    with TestClient(app) as test_client:
        response = test_client.get(f"/api/intake/browse?path={test_dir}")
        assert response.status_code == 200
        payload = response.json()
        
        assert payload["success"] is True
        assert payload["path"] == str(test_dir)
        assert payload["type"] == "folder"
        assert payload["entry_count"] == 3
        
        entries_by_name = {e["name"]: e for e in payload["entries"]}
        assert "model1.3mf" in entries_by_name
        assert entries_by_name["model1.3mf"]["type"] == "file"
        assert entries_by_name["model1.3mf"]["extension"] == ".3mf"
        assert entries_by_name["model1.3mf"]["size_bytes"] == 8
        
        assert "subfolder" in entries_by_name
        assert entries_by_name["subfolder"]["type"] == "folder"


def test_intake_browse_enforces_allowlist(monkeypatch, tmp_path: Path) -> None:
    """Browse rejects paths outside allowlist."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    disallowed_dir = tmp_path / "disallowed"
    disallowed_dir.mkdir()
    
    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", str(allowed_dir))
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    with TestClient(app) as test_client:
        response = test_client.get(f"/api/intake/browse?path={disallowed_dir}")
        assert response.status_code == 403
        assert response.json()["error"] == "path_not_allowed"


def test_intake_browse_handles_missing_path(monkeypatch, tmp_path: Path) -> None:
    """Browse returns 404 for non-existent paths."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    
    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", str(allowed_dir))
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    with TestClient(app) as test_client:
        response = test_client.get(f"/api/intake/browse?path={allowed_dir}/nonexistent")
        assert response.status_code == 404
        assert response.json()["error"] == "path_not_found"


def test_intake_browse_rejects_file_paths(monkeypatch, tmp_path: Path) -> None:
    """Browse returns 400 when given a file path instead of folder."""
    test_dir = tmp_path / "models"
    test_dir.mkdir()
    test_file = test_dir / "model.3mf"
    test_file.write_bytes(b"content")
    
    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", str(test_dir))
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    
    with TestClient(app) as test_client:
        response = test_client.get(f"/api/intake/browse?path={test_file}")
        assert response.status_code == 400
        assert response.json()["error"] == "not_a_directory"


def test_intake_browse_allows_zip_as_virtual_folder(monkeypatch, tmp_path: Path) -> None:
    """Browse accepts .zip file paths and returns virtual archive entries."""
    test_dir = tmp_path / "models"
    test_dir.mkdir()
    archive_path = test_dir / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("parts/base.3mf", b"mesh")
        archive.writestr("parts/docs/readme.md", b"notes")

    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", str(test_dir))

    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as test_client:
        response = test_client.get(f"/api/intake/browse?path={archive_path}")
        assert response.status_code == 200
        payload = response.json()

        assert payload["success"] is True
        assert payload["virtual_archive"] is True
        assert payload["archive_source_path"] == str(archive_path)
        assert payload["entry_count"] == 1
        assert payload["entries"][0]["name"] == "parts"
        assert payload["entries"][0]["type"] == "folder"
        assert payload["entries"][0]["selectable"] is False


def test_intake_browse_allows_zip_virtual_nested_navigation(monkeypatch, tmp_path: Path) -> None:
    """Virtual archive browse supports nested folder navigation via :: paths."""
    test_dir = tmp_path / "models"
    test_dir.mkdir()
    archive_path = test_dir / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("parts/base.3mf", b"mesh")
        archive.writestr("parts/docs/readme.md", b"notes")

    monkeypatch.setenv("BAMBULAB_INTAKE_ALLOWLIST", str(test_dir))

    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as test_client:
        response = test_client.get(f"/api/intake/browse?path={archive_path}::parts")
        assert response.status_code == 200
        payload = response.json()

        assert payload["success"] is True
        assert payload["virtual_archive"] is True
        names = {entry["name"] for entry in payload["entries"]}
        assert "base.3mf" in names
        assert "docs" in names
        base_entry = next(entry for entry in payload["entries"] if entry["name"] == "base.3mf")
        assert base_entry["type"] == "file"
        assert base_entry["selectable"] is False
