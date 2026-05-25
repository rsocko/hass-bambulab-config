"""Tests for Phase 2 of intake sidecar enrichment: README-as-asset publish.

When the wizard's Organize-step "Attach README" opt-in is forwarded as
``destination_plan["attach_source_readme"] = True`` for a curated destination,
the publish-by-destination endpoint must copy each unique source-folder
``README.md`` into the new Catalog item even when the user only selected
specific files from that folder (so the README is not naturally part of the
planned group's file list).

Re-read happens at publish time so the attached asset is the canonical,
untruncated file (the plan-preview payload may have been clipped).
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from sidecars.model_catalog.app.local_models import list_model_assets


def _make_settings(*, db_path: Path, intake_root: Path, curated_root: Path) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.example",
        db_path=db_path,
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="test",
        image_revision="test",
        image_created="test",
        intake_source_roots=(intake_root.resolve(),),
        working_files_root=intake_root.resolve(),
        model_catalog_assets_root=curated_root.resolve(),
    )


def _build_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    intake_root = tmp_path / "inbox"
    curated_root = tmp_path / "curated"
    intake_root.mkdir(parents=True, exist_ok=True)
    curated_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "model_catalog.db"
    settings = _make_settings(
        db_path=db_path, intake_root=intake_root, curated_root=curated_root
    )
    app = create_app(settings=settings)
    client = TestClient(app)
    client.__enter__()
    return client, intake_root, curated_root


def _seed_upload(client: TestClient, source_entries: list[dict]) -> str:
    response = client.post(
        "/api/intake/uploads",
        json={"cleanup_policy": "keep", "source_entries": source_entries},
    )
    assert response.status_code == 200, response.text
    return response.json()["upload_id"]


def test_attach_source_readme_pulls_in_readme_for_file_selection(tmp_path: Path) -> None:
    """User selects a specific file (not the whole folder). The README from the
    parent folder must still be attached when ``attach_source_readme=True``."""
    client, intake_root, _curated_root = _build_client(tmp_path)
    try:
        folder = intake_root / "gridfinity-bin"
        folder.mkdir(parents=True, exist_ok=True)
        stl_path = folder / "bin.stl"
        stl_path.write_bytes(b"solid bin\nendsolid bin\n")
        readme_text = "# Gridfinity Bin\n\nLong-form notes about printing this bin.\n" * 40
        (folder / "README.md").write_text(readme_text, encoding="utf-8")

        # File-typed source entry: README.md is NOT in group_files.
        upload_id = _seed_upload(
            client,
            [{"type": "file", "path": str(stl_path)}],
        )

        response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "group_destinations": [
                    {
                        "destination": "curated",
                        "model_name": "Gridfinity Bin",
                        "attach_source_readme": True,
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        result = body["group_results"][0]
        attached = result.get("attached_readmes") or []
        assert len(attached) == 1, attached
        assert attached[0]["filename"] == "README.md"

        local_model_id = result["local_model_id"]
        assets = list_model_assets(
            db_path=tmp_path / "model_catalog.db",
            local_model_id=local_model_id,
        )
        readme_assets = [
            a for a in assets if str(getattr(a, "asset_filename", "")) == "README.md"
        ]
        assert len(readme_assets) == 1
        readme_asset = readme_assets[0]
        assert str(getattr(readme_asset, "asset_type", "")) == "md"
        assert str(getattr(readme_asset, "asset_role", "")) == "documentation"
        stored_path = (tmp_path / "curated") / str(
            getattr(readme_asset, "storage_path", "")
        )
        assert stored_path.is_file()
        assert stored_path.read_text(encoding="utf-8") == readme_text
    finally:
        client.__exit__(None, None, None)


def test_attach_source_readme_default_off_does_not_pull_in_readme(tmp_path: Path) -> None:
    """File-typed selection without the flag: README is not attached."""
    client, intake_root, _curated_root = _build_client(tmp_path)
    try:
        folder = intake_root / "no-attach"
        folder.mkdir(parents=True, exist_ok=True)
        stl_path = folder / "part.stl"
        stl_path.write_bytes(b"solid p\nendsolid p\n")
        (folder / "README.md").write_text("# Hidden\n", encoding="utf-8")

        upload_id = _seed_upload(
            client,
            [{"type": "file", "path": str(stl_path)}],
        )
        response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "group_destinations": [
                    {"destination": "curated", "model_name": "No Attach"}
                ],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["group_results"][0]
        assert result.get("attached_readmes") in (None, [])
        assets = list_model_assets(
            db_path=tmp_path / "model_catalog.db",
            local_model_id=result["local_model_id"],
        )
        assert not any(
            str(getattr(a, "asset_filename", "")) == "README.md" for a in assets
        )
    finally:
        client.__exit__(None, None, None)


def test_attach_source_readme_skips_when_no_readme_present(tmp_path: Path) -> None:
    """Flag enabled but folder has no README -> no error, no attachment."""
    client, intake_root, _curated_root = _build_client(tmp_path)
    try:
        folder = intake_root / "no-readme-here"
        folder.mkdir(parents=True, exist_ok=True)
        stl_path = folder / "thing.stl"
        stl_path.write_bytes(b"solid t\nendsolid t\n")

        upload_id = _seed_upload(
            client,
            [{"type": "file", "path": str(stl_path)}],
        )
        response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "group_destinations": [
                    {
                        "destination": "curated",
                        "model_name": "No Readme",
                        "attach_source_readme": True,
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["group_results"][0]
        assert result.get("attached_readmes") in (None, [])
        assert result.get("failed_file_count", 0) == 0
    finally:
        client.__exit__(None, None, None)


def test_attach_source_readme_dedupes_when_readme_already_in_group(tmp_path: Path) -> None:
    """When the user selected the whole folder (so README is already in
    group_files), the explicit attach must not produce a duplicate asset."""
    client, intake_root, _curated_root = _build_client(tmp_path)
    try:
        folder = intake_root / "full-folder"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "thing.stl").write_bytes(b"solid t\nendsolid t\n")
        (folder / "README.md").write_text("# Already imported\n", encoding="utf-8")

        upload_id = _seed_upload(
            client,
            [{"type": "folder", "path": str(folder), "recurse": True}],
        )
        response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "group_destinations": [
                    {
                        "destination": "curated",
                        "model_name": "Full Folder",
                        "attach_source_readme": True,
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()["group_results"][0]
        assets = list_model_assets(
            db_path=tmp_path / "model_catalog.db",
            local_model_id=result["local_model_id"],
        )
        readme_assets = [
            a for a in assets if str(getattr(a, "asset_filename", "")) == "README.md"
        ]
        assert len(readme_assets) == 1
    finally:
        client.__exit__(None, None, None)
