"""Tests for the new /api/working-files/* folder-based endpoints (PR C of
working-groups deprecation) and the HTTP 410 responses on the legacy
/api/working-groups/* + /api/working-files/explorer endpoints.

See: docs/features/model_catalog/planning/working-groups-deprecation.md §6.4
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------


def _make_settings(*, db_path: Path, working_root: Path | None) -> Settings:
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
        working_files_root=working_root.resolve() if working_root else None,
    )


def _build_client(tmp_path: Path, *, with_root: bool = True) -> tuple[TestClient, Path | None]:
    working_root: Path | None = None
    if with_root:
        working_root = tmp_path / "working"
        working_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path=db_path, working_root=working_root))
    client = TestClient(app)
    client.__enter__()
    return client, working_root


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_inventory_row(
    db_path: Path,
    *,
    source_path: Path,
    root_path: Path,
    size: int = 1024,
    extension: str | None = None,
) -> int:
    """Seed a working_file_inventory row that mirrors what the reindex would
    produce for a real file on disk."""
    source_path.parent.mkdir(parents=True, exist_ok=True)
    if not source_path.exists():
        source_path.write_bytes(b"x" * size)
    canonical = str(source_path.resolve())
    raw = str(source_path)
    compare_key = canonical.lower()
    name_raw = source_path.name
    name_base = source_path.stem
    ext = (extension or source_path.suffix or "").lower()
    now = _iso_now()
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO working_file_inventory (
                source_path_raw,
                source_path_canonical,
                source_path_compare_key,
                file_name_raw,
                file_name_base_hint,
                file_extension,
                file_size_bytes,
                sha256_hash,
                source_mtime,
                source_ctime,
                source_birthtime,
                validation_state,
                warnings_json,
                detected_at,
                last_seen_at,
                root_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 'ready', '[]', ?, ?, ?)
            """,
            (
                raw,
                canonical,
                compare_key,
                name_raw,
                name_base,
                ext,
                size,
                now,
                now,
                now,
                now,
                now,
                str(root_path.resolve()),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid or 0)
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# /api/working-files/tree
# ---------------------------------------------------------------------------


def test_tree_empty_root_returns_no_groups_and_zero_loose(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        response = client.get("/api/working-files/tree")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["root_path"] == str(root.resolve())
    assert payload["groups"] == []
    assert payload["loose"] == {
        "file_count": 0,
        "size_bytes": 0,
        "last_seen_at": None,
    }


def test_tree_with_loose_and_groups(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        db_path = tmp_path / "model_catalog.db"

        # Loose file at the working root.
        _insert_inventory_row(
            db_path,
            source_path=root / "loose-design.3mf",
            root_path=root,
            size=2048,
        )
        # Group "alpha" with a 3mf and an stl.
        alpha = root / "alpha"
        alpha.mkdir()
        _insert_inventory_row(
            db_path, source_path=alpha / "part-a.3mf", root_path=root, size=1000
        )
        _insert_inventory_row(
            db_path, source_path=alpha / "part-a.stl", root_path=root, size=500
        )
        # Group "beta" with a sidecar README.
        beta = root / "beta"
        beta.mkdir()
        (beta / "README.md").write_text("hello", encoding="utf-8")
        _insert_inventory_row(
            db_path, source_path=beta / "thing.3mf", root_path=root, size=300
        )

        response = client.get("/api/working-files/tree")
    finally:
        client.__exit__(None, None, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["loose"]["file_count"] == 1
    assert payload["loose"]["size_bytes"] == 2048

    groups_by_slug = {g["slug"]: g for g in payload["groups"]}
    assert set(groups_by_slug) == {"alpha", "beta"}
    assert groups_by_slug["alpha"]["file_count"] == 2
    assert groups_by_slug["alpha"]["count_3mf"] == 1
    assert groups_by_slug["alpha"]["size_bytes"] == 1500
    assert groups_by_slug["beta"]["has_readme"] is True
    assert groups_by_slug["alpha"]["has_readme"] is False


def test_tree_returns_400_when_no_root_configured(tmp_path: Path) -> None:
    client, _root = _build_client(tmp_path, with_root=False)
    try:
        response = client.get("/api/working-files/tree")
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"] == "no_root"


# ---------------------------------------------------------------------------
# /api/working-files/loose
# ---------------------------------------------------------------------------


def test_loose_endpoint_returns_only_root_level_files(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        db_path = tmp_path / "model_catalog.db"
        _insert_inventory_row(db_path, source_path=root / "loose-1.3mf", root_path=root)
        _insert_inventory_row(db_path, source_path=root / "loose-2.stl", root_path=root)
        sub = root / "group-a"
        sub.mkdir()
        _insert_inventory_row(db_path, source_path=sub / "in-group.3mf", root_path=root)

        response = client.get("/api/working-files/loose")
    finally:
        client.__exit__(None, None, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["pagination"]["total"] == 2
    names = {f["file_name_raw"] for f in payload["files"]}
    assert names == {"loose-1.3mf", "loose-2.stl"}


def test_loose_endpoint_honors_limit_and_offset(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        db_path = tmp_path / "model_catalog.db"
        for i in range(5):
            _insert_inventory_row(
                db_path, source_path=root / f"loose-{i}.3mf", root_path=root
            )

        response = client.get("/api/working-files/loose?limit=2&offset=1")
    finally:
        client.__exit__(None, None, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["pagination"] == {"limit": 2, "offset": 1, "total": 5}
    assert len(payload["files"]) == 2


# ---------------------------------------------------------------------------
# /api/working-files/groups/{folder_slug}
# ---------------------------------------------------------------------------


def test_group_detail_with_sidecar(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        db_path = tmp_path / "model_catalog.db"
        group = root / "alpha"
        group.mkdir()
        (group / ".modelmeta.json").write_text(
            json.dumps({"display_name": "Alpha"}), encoding="utf-8"
        )
        (group / "README.md").write_text("# alpha", encoding="utf-8")
        _insert_inventory_row(
            db_path, source_path=group / "a.3mf", root_path=root, size=10
        )
        _insert_inventory_row(
            db_path, source_path=group / "a.stl", root_path=root, size=20
        )
        # Nested subfolder file.
        sub = group / "nested"
        sub.mkdir()
        _insert_inventory_row(
            db_path, source_path=sub / "nested.3mf", root_path=root, size=30
        )

        response = client.get("/api/working-files/groups/alpha")
    finally:
        client.__exit__(None, None, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["folder_slug"] == "alpha"
    assert payload["counts"]["file_count"] == 3
    assert payload["counts"]["count_3mf"] == 2
    assert payload["counts"]["count_other"] == 1
    assert payload["counts"]["size_bytes"] == 60
    assert payload["sidecar"]["modelmeta"] == {"display_name": "Alpha"}
    assert payload["sidecar"]["readme"].startswith("# alpha")
    subfolder_paths = {s["path"] for s in payload["subfolders"]}
    assert "nested" in subfolder_paths


def test_group_detail_missing_folder_returns_404(tmp_path: Path) -> None:
    client, _root = _build_client(tmp_path)
    try:
        response = client.get("/api/working-files/groups/does-not-exist")
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"] == "folder_not_found"


def test_group_detail_rejects_invalid_slug(tmp_path: Path) -> None:
    client, _root = _build_client(tmp_path)
    try:
        # Dot-prefixed slugs (hidden folders / sidecar dirs) are rejected by
        # the slug guard with HTTP 400 before any disk lookup.
        response = client.get("/api/working-files/groups/.hidden")
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_folder_slug"


# ---------------------------------------------------------------------------
# /api/working-files/groups/{folder_slug}/files
# ---------------------------------------------------------------------------


def test_group_files_mode_files_returns_flat_list(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        db_path = tmp_path / "model_catalog.db"
        group = root / "alpha"
        group.mkdir()
        _insert_inventory_row(db_path, source_path=group / "a.3mf", root_path=root)
        _insert_inventory_row(db_path, source_path=group / "a.stl", root_path=root)
        sub = group / "nested"
        sub.mkdir()
        _insert_inventory_row(db_path, source_path=sub / "n.3mf", root_path=root)

        response = client.get("/api/working-files/groups/alpha/files?mode=files")
    finally:
        client.__exit__(None, None, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["mode"] == "files"
    assert payload["pagination"]["total"] == 3
    assert len(payload["files"]) == 3


def test_group_files_mode_folders_groups_by_subfolder(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        db_path = tmp_path / "model_catalog.db"
        group = root / "alpha"
        group.mkdir()
        _insert_inventory_row(db_path, source_path=group / "root-file.3mf", root_path=root)
        sub_a = group / "sub-a"
        sub_a.mkdir()
        _insert_inventory_row(db_path, source_path=sub_a / "x.3mf", root_path=root)
        _insert_inventory_row(db_path, source_path=sub_a / "y.stl", root_path=root)
        sub_b = group / "sub-b"
        sub_b.mkdir()
        _insert_inventory_row(db_path, source_path=sub_b / "z.3mf", root_path=root)

        response = client.get("/api/working-files/groups/alpha/files?mode=folders")
    finally:
        client.__exit__(None, None, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["mode"] == "folders"
    folders_by_path = {f["path"]: f for f in payload["folders"]}
    # "" represents files directly under the group folder.
    assert folders_by_path[""]["file_count"] == 1
    assert folders_by_path["sub-a"]["file_count"] == 2
    assert folders_by_path["sub-b"]["file_count"] == 1
    assert payload["pagination"]["total_files"] == 4


def test_group_files_invalid_mode_returns_400(tmp_path: Path) -> None:
    client, root = _build_client(tmp_path)
    try:
        assert root is not None
        (root / "alpha").mkdir()
        response = client.get("/api/working-files/groups/alpha/files?mode=bogus")
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_mode"


# ---------------------------------------------------------------------------
# Deprecation: HTTP 410 on legacy endpoints
# ---------------------------------------------------------------------------


def _assert_gone(response) -> None:
    assert response.status_code == 410
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"] == "endpoint_gone"
    assert any(
        "/api/working-files/tree" in entry for entry in payload.get("new_endpoints", [])
    )
    assert response.headers.get("Deprecation") == "true"
    assert "successor-version" in (response.headers.get("Link") or "")


def test_explorer_endpoint_returns_410(tmp_path: Path) -> None:
    client, _root = _build_client(tmp_path)
    try:
        response = client.get("/api/working-files/explorer")
    finally:
        client.__exit__(None, None, None)
    _assert_gone(response)


# Each tuple: (method, path, json_body_or_none).
LEGACY_GONE_ENDPOINTS: list[tuple[str, str, dict | None]] = [
    ("POST", "/api/working-groups/memberships/batch-add", {}),
    ("POST", "/api/working-groups/memberships/batch-remove", {}),
    ("POST", "/api/working-groups/1/reorganize", {}),
    ("POST", "/api/working-groups", {}),
    ("GET", "/api/working-groups", None),
    ("GET", "/api/working-groups/1", None),
    ("PATCH", "/api/working-groups/1", {}),
    ("DELETE", "/api/working-groups/1", None),
    ("POST", "/api/working-groups/1/items", {}),
    ("DELETE", "/api/working-groups/1/items/2", None),
    ("POST", "/api/working-groups/1/links", {}),
    ("GET", "/api/working-groups/1/links", None),
    ("DELETE", "/api/working-groups/1/links/2", None),
    ("GET", "/api/models/some-ref/working-groups", None),
    ("POST", "/api/working-groups/bulk-discover", {}),
    ("POST", "/working-groups/bulk-discover", {}),
    ("POST", "/api/working-groups/bulk-import", {}),
    ("POST", "/working-groups/bulk-import", {}),
]


@pytest.mark.parametrize("method,path,body", LEGACY_GONE_ENDPOINTS)
def test_legacy_working_groups_endpoints_return_410(
    tmp_path: Path, method: str, path: str, body: dict | None
) -> None:
    client, _root = _build_client(tmp_path)
    try:
        if method == "GET":
            response = client.get(path)
        elif method == "DELETE":
            response = client.delete(path)
        elif method == "PATCH":
            response = client.patch(path, json=body or {})
        else:
            response = client.post(path, json=body or {})
    finally:
        client.__exit__(None, None, None)
    _assert_gone(response)
