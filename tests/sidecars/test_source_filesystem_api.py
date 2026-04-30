"""Tests for issue #1147: Source filesystem browse/select API."""

from pathlib import Path
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path, source_roots: list[Path] | None = None) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id=None,
        manyfold_client_secret=None,
        manyfold_oauth_scopes=None,
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-28T00:00:00Z",
        source_filesystem_roots=tuple(source_roots or []),
    )


def _make_app(tmp_path: Path, roots: list[Path]) -> FastAPI:
    settings = _build_settings(tmp_path, roots)
    bootstrap_database(settings.db_path)
    return create_app(settings=settings)


# ===== GET /api/source-filesystems =====

def test_list_source_filesystems_returns_configured_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()

    app = _make_app(tmp_path, [root_a, root_b])
    with TestClient(app) as client:
        response = client.get("/api/source-filesystems")
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["root_count"] == 2
    root_paths = {r["path"] for r in payload["roots"]}
    assert str(root_a) in root_paths
    assert str(root_b) in root_paths


def test_list_source_filesystems_marks_inaccessible_roots(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    ghost_root = tmp_path / "ghost"  # does NOT exist

    app = _make_app(tmp_path, [real_root, ghost_root])
    with TestClient(app) as client:
        response = client.get("/api/source-filesystems")
    assert response.status_code == 200
    payload = response.json()

    by_path = {r["path"]: r for r in payload["roots"]}
    assert by_path[str(real_root)]["accessible"] is True
    assert by_path[str(ghost_root)]["accessible"] is False


def test_list_source_filesystems_includes_child_count(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "file1.3mf").write_bytes(b"a")
    (root / "file2.stl").write_bytes(b"b")
    (root / "subdir").mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get("/api/source-filesystems")
    payload = response.json()

    assert payload["roots"][0]["child_count"] == 3


def test_list_source_filesystems_empty_when_no_roots(tmp_path: Path) -> None:
    app = _make_app(tmp_path, [])
    with TestClient(app) as client:
        response = client.get("/api/source-filesystems")
    assert response.status_code == 200
    payload = response.json()
    assert payload["root_count"] == 0
    assert payload["roots"] == []


def test_create_app_loads_source_roots_from_env_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "assets"
    root.mkdir()

    monkeypatch.setenv("MODEL_CATALOG_DB_PATH", str(tmp_path / "model_catalog.db"))
    monkeypatch.setenv("MODEL_CATALOG_AUTHORITY_MODE", "local")
    monkeypatch.delenv("SOURCE_FILESYSTEM_ROOTS", raising=False)

    app = create_app()

    monkeypatch.setenv("SOURCE_FILESYSTEM_ROOTS", str(root))

    with TestClient(app) as client:
        response = client.get("/api/source-filesystems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["root_count"] == 1
    assert payload["roots"][0]["path"] == str(root)


# ===== GET /api/source-filesystems/browse =====

def test_browse_virtual_root_lists_configured_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()

    app = _make_app(tmp_path, [root_a, root_b])
    with TestClient(app) as client:
        response = client.get("/api/source-filesystems/browse")
    assert response.status_code == 200
    payload = response.json()

    assert payload["is_root"] is True
    assert payload["type"] == "virtual_root"
    paths = {e["path"] for e in payload["entries"]}
    assert str(root_a) in paths
    assert str(root_b) in paths


def test_browse_lists_folder_contents(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "model.3mf").write_bytes(b"content")
    sub = root / "sub"
    sub.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={root}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["entry_count"] == 2
    by_name = {e["name"]: e for e in payload["entries"]}
    assert by_name["model.3mf"]["type"] == "file"
    assert by_name["model.3mf"]["extension"] == ".3mf"
    assert by_name["sub"]["type"] == "folder"


def test_browse_enforces_allowlist_rejects_outside_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    other = tmp_path / "other"
    other.mkdir()

    app = _make_app(tmp_path, [allowed])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={other}")
    assert response.status_code == 403
    assert response.json()["error"] == "path_not_allowed"


def test_browse_prevents_path_traversal_above_root(tmp_path: Path) -> None:
    """Resolved path must be within an allowlisted root; parent of root is rejected."""
    root = tmp_path / "allowed"
    root.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        # Navigate to parent of allowed root
        response = client.get(f"/api/source-filesystems/browse?path={root.parent}")
    assert response.status_code == 403
    assert response.json()["error"] == "path_not_allowed"


def test_browse_returns_404_for_missing_path(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={root}/nonexistent")
    assert response.status_code == 404
    assert response.json()["error"] == "path_not_found"


def test_browse_returns_400_for_file_path(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    f = root / "model.3mf"
    f.write_bytes(b"x")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={f}")
    assert response.status_code == 400
    assert response.json()["error"] == "not_a_directory"


def test_browse_includes_parent_path_within_root(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    sub = root / "sub"
    sub.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={sub}")
    payload = response.json()

    assert payload["parent_path"] == str(root)


def test_browse_no_parent_path_when_at_root(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={root}")
    payload = response.json()

    # Parent of root is tmp_path which is outside the allowlist
    assert payload["parent_path"] is None


def test_browse_skips_hidden_files(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / ".hidden").write_bytes(b"x")
    (root / "visible.3mf").write_bytes(b"x")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.get(f"/api/source-filesystems/browse?path={root}")
    payload = response.json()

    names = {e["name"] for e in payload["entries"]}
    assert "visible.3mf" in names
    assert ".hidden" not in names


# ===== POST /api/source-filesystems/select =====

def test_select_single_file_creates_queue_item(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    f = root / "model.3mf"
    f.write_bytes(b"3mf content")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": str(f)}]},
        )
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["status"] == "queued"
    assert payload["selection_count"] == 1
    assert payload["expanded_file_count"] == 1
    assert "upload_id" in payload


def test_select_creates_retrievable_queue_entry(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    f = root / "model.3mf"
    f.write_bytes(b"content")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        select_response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": str(f)}]},
        )
        upload_id = select_response.json()["upload_id"]

        list_response = client.get("/api/intake/uploads")
    assert list_response.status_code == 200
    uploads = list_response.json()["uploads"]
    ids = {u["upload_id"] for u in uploads}
    assert upload_id in ids


def test_select_folder_with_recurse_expands_file_count(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.3mf").write_bytes(b"a")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.stl").write_bytes(b"b")
    (sub / "c.stl").write_bytes(b"c")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "folder", "path": str(root), "recurse": True}]},
        )
    assert response.status_code == 200
    payload = response.json()

    assert payload["success"] is True
    assert payload["selection_count"] == 1
    assert payload["expanded_file_count"] == 3  # a.3mf + b.stl + c.stl


def test_select_folder_without_recurse_counts_top_level_only(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.3mf").write_bytes(b"a")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.stl").write_bytes(b"b")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "folder", "path": str(root), "recurse": False}]},
        )
    assert response.status_code == 200
    payload = response.json()

    assert payload["expanded_file_count"] == 1  # only a.3mf, sub not expanded


def test_select_folder_with_max_depth(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    (root / "top.3mf").write_bytes(b"t")
    d1 = root / "d1"
    d1.mkdir()
    (d1 / "l1.stl").write_bytes(b"l")
    d2 = d1 / "d2"
    d2.mkdir()
    (d2 / "l2.stl").write_bytes(b"l2")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "folder", "path": str(root), "recurse": True, "max_depth": 1}]},
        )
    payload = response.json()

    # top.3mf + d1/l1.stl; d2/l2.stl is at depth 2, excluded
    assert payload["expanded_file_count"] == 2


def test_select_mixed_batch(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    f1 = root / "file1.3mf"
    f1.write_bytes(b"f1")
    sub = root / "sub"
    sub.mkdir()
    (sub / "f2.stl").write_bytes(b"f2")
    (sub / "f3.stl").write_bytes(b"f3")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={
                "selections": [
                    {"type": "file", "path": str(f1)},
                    {"type": "folder", "path": str(sub), "recurse": False},
                ]
            },
        )
    payload = response.json()

    assert payload["success"] is True
    assert payload["selection_count"] == 2
    assert payload["expanded_file_count"] == 3  # 1 file + 2 in folder


def test_select_rejects_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    f = outside / "model.3mf"
    f.write_bytes(b"x")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": str(f)}]},
        )
    assert response.status_code == 403
    assert response.json()["error"] == "path_not_allowed"


def test_select_rejects_traversal_above_root(tmp_path: Path) -> None:
    """Path that resolves outside allowlisted root must be blocked."""
    root = tmp_path / "allowed"
    root.mkdir()
    # Construct a path that tries to escape via ..
    escape_path = str(root / ".." / "escape.3mf")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": escape_path}]},
        )
    # Either 403 (allowlist blocked) or 400 (source_not_found after resolution) — must not succeed
    assert response.status_code in {400, 403}
    assert response.json()["success"] is False


def test_select_rejects_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": str(root / "ghost.3mf")}]},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "source_not_found"


def test_select_rejects_empty_selections(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": []},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_payload"


def test_select_rejects_when_no_roots_configured(tmp_path: Path) -> None:
    app = _make_app(tmp_path, [])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": "/some/file.3mf"}]},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "no_roots_configured"


def test_select_respects_cleanup_policy(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    f = root / "file.3mf"
    f.write_bytes(b"x")

    app = _make_app(tmp_path, [root])
    with TestClient(app) as client:
        response = client.post(
            "/api/source-filesystems/select",
            json={
                "selections": [{"type": "file", "path": str(f)}],
                "cleanup_policy": "delete_on_verified",
            },
        )
        upload_id = response.json()["upload_id"]

        list_response = client.get("/api/intake/uploads")
    uploads = {u["upload_id"]: u for u in list_response.json()["uploads"]}
    assert uploads[upload_id]["cleanup_policy"] == "delete_on_verified"


def test_select_source_metadata_stored_in_queue(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    f = root / "file.3mf"
    f.write_bytes(b"content")

    settings = _build_settings(tmp_path, [root])
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)
    with TestClient(app) as client:
        select_resp = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "file", "path": str(f)}]},
        )
        upload_id = select_resp.json()["upload_id"]

    # Verify source_entries stored in DB contain expected metadata
    from sqlite3 import connect as _connect
    conn = _connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    import json as _json
    entries = _json.loads(row[0])
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "file"
    assert entry["path"] == str(f)
    assert "source_mtime" in entry
    assert "source_ctime" in entry


def test_select_publish_to_local_uses_same_curated_sink(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    model_file = root / "selected-model.3mf"
    model_file.write_bytes(b"selected model")
    preview_file = root / "selected-preview.png"
    preview_file.write_bytes(b"\x89PNG\r\n\x1a\nselected preview")

    settings = _build_settings(tmp_path, [root])
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        select_response = client.post(
            "/api/source-filesystems/select",
            json={
                "selections": [
                    {"type": "file", "path": str(model_file)},
                    {"type": "file", "path": str(preview_file)},
                ]
            },
        )
        assert select_response.status_code == 200
        upload_id = select_response.json()["upload_id"]

        publish_response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-local",
            json={
                "model_name": "Selected Local Model",
                "preview_source_path": str(preview_file),
            },
        )
        assert publish_response.status_code == 200
        payload = publish_response.json()
        assert payload["success"] is True
        assert payload["status"] == "verified"
        assert payload["imported_asset_count"] == 2
        assert payload["legacy_adapter"]["authoritative"] is False
        assert payload["legacy_adapter"]["status"] == "transition_only"

        detail_response = client.get(f"/api/models/{payload['local_model_id']}/detail")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["model"]["name"] == "Selected Local Model"
        assert len(detail_payload["model"]["files"]) == 2
        assert detail_payload["model"]["preview_file_id"] is not None
        assert detail_payload["model"]["source_origin"] == "intake_queue"
        assert detail_payload["model"]["source_origin_url"] == f"intake://uploads/{upload_id}"
