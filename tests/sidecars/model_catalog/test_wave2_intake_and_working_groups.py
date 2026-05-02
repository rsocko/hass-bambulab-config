from pathlib import Path
import base64
import json
import sqlite3
from datetime import datetime, timezone
import time

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app
from app.settings import Settings


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None


def _make_settings(db_path: Path, source_root: Path) -> Settings:
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
        intake_source_roots=(source_root.resolve(),),
        working_files_root=source_root.resolve(),
    )

def _make_settings_with_roots(db_path: Path, source_roots: tuple[Path, ...]) -> Settings:
    resolved_roots = tuple(root.resolve() for root in source_roots)
    working_root = next((root for root in resolved_roots if root.name.lower() == "model working files"), resolved_roots[-1] if resolved_roots else None)
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
        intake_source_roots=resolved_roots,
        working_files_root=working_root,
    )


def _create_client(tmp_path: Path, source_root: Path) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path, source_root), manyfold_client=FakeManyfoldClient())
    client = TestClient(app)
    client.__enter__()
    return client


def _create_client_with_roots(tmp_path: Path, source_roots: tuple[Path, ...]) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings_with_roots(db_path, source_roots), manyfold_client=FakeManyfoldClient())
    client = TestClient(app)
    client.__enter__()
    return client
    return client


def test_working_files_reindex_and_list(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    model_file = source_root / "Football_Holder.3mf"
    model_file.write_bytes(b"3mf-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        reindex_response = client.post(
            "/api/working-files/reindex",
            json={"compute_hashes": True, "recurse": True},
        )
        assert reindex_response.status_code == 200
        reindex_payload = reindex_response.json()
        assert reindex_payload["success"] is True
        assert reindex_payload["discovered"] == 1
        assert reindex_payload["inserted"] == 1

        list_response = client.get("/api/working-files", params={"q": "football"})
    finally:
        client.__exit__(None, None, None)

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["success"] is True
    assert list_payload["pagination"]["total"] == 1
    assert list_payload["files"][0]["file_name_raw"] == "Football_Holder.3mf"
    assert list_payload["files"][0]["sha256_hash"]


def test_working_group_crud_items_and_links(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    model_file = source_root / "Bracket_v2.stl"
    model_file.write_bytes(b"stl-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        create_group = client.post(
            "/api/working-groups",
            json={"title": "Bracket Group", "stage": "draft"},
        )
        assert create_group.status_code == 200
        group_payload = create_group.json()
        group_id = group_payload["group"]["id"]

        add_item = client.post(
            f"/api/working-groups/{group_id}/items",
            json={"file_path": str(model_file), "item_role": "primary"},
        )
        assert add_item.status_code == 200

        add_link = client.post(
            f"/api/working-groups/{group_id}/links",
            json={"model_ref": "test-model-ref", "link_role": "related", "metadata": {"source": "test"}},
        )
        assert add_link.status_code == 200

        reverse_lookup = client.get("/api/models/test-model-ref/working-groups")
    finally:
        client.__exit__(None, None, None)

    assert reverse_lookup.status_code == 200
    reverse_payload = reverse_lookup.json()
    assert reverse_payload["success"] is True
    assert reverse_payload["group_count"] == 1
    assert reverse_payload["groups"][0]["id"] == group_id
    assert len(reverse_payload["groups"][0]["items"]) == 1
    assert len(reverse_payload["groups"][0]["links"]) == 1


def test_intake_submit_validate_and_group(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    source_file = source_root / "router_mount.step"
    source_file.write_bytes(b"step-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        submit_response = client.post(
            "/api/intake/submit",
            json={
                "items": [{"source_path": str(source_file), "source_type": "filesystem_action"}],
                "auto_validate": True,
                "cleanup_policy": "keep",
            },
        )
        assert submit_response.status_code == 200
        submit_payload = submit_response.json()
        assert submit_payload["success"] is True
        assert submit_payload["created_count"] == 1

        item = submit_payload["items"][0]
        item_id = item["item_id"]
        assert item["state"] in {"validated_ready", "validated_warning"}
        assert item["validation"]["validation_state"] in {"ready", "duplicate_candidate"}

        validate_response = client.post(f"/api/intake/items/{item_id}/validate")
        assert validate_response.status_code == 200

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group", "title": "Router Mount Group"},
        )
        assert group_response.status_code == 200
        group_payload = group_response.json()
        assert group_payload["success"] is True
        assert group_payload["state"] == "grouped_new"
        assert group_payload["working_group_id"] > 0
        assert group_payload["added_items"] >= 1

        detail_response = client.get(f"/api/intake/items/{item_id}")
    finally:
        client.__exit__(None, None, None)

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["success"] is True
    assert detail_payload["item"]["state"] == "grouped_new"

    decoded_note = detail_payload["item"]["decision_note"]
    assert isinstance(decoded_note, str)
    assert "working_group_id" in decoded_note


def test_intake_group_duplicate_hash_is_handled_without_500(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    source_file = source_root / "duplicate_fixture.3mf"
    source_file.write_bytes(b"same-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        seed_group_response = client.post(
            "/api/working-groups",
            json={"title": "Seed Group", "stage": "draft"},
        )
        assert seed_group_response.status_code == 200
        seed_group_id = seed_group_response.json()["group"]["id"]

        seed_item_response = client.post(
            f"/api/working-groups/{seed_group_id}/items",
            json={"file_path": str(source_file), "item_role": "primary"},
        )
        assert seed_item_response.status_code == 200

        submit_response = client.post(
            "/api/intake/submit",
            json={
                "items": [{"source_path": str(source_file), "source_type": "filesystem_action"}],
                "auto_validate": True,
                "cleanup_policy": "keep",
            },
        )
        assert submit_response.status_code == 200
        item_id = submit_response.json()["items"][0]["item_id"]

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group", "title": "Duplicate Candidate Group"},
        )
        assert group_response.status_code == 200
        payload = group_response.json()
        assert payload["success"] is True
        assert payload["state"] == "grouped_new"
        assert payload["working_group_id"] > 0
        assert payload["duplicate_items"] >= 1
    finally:
        client.__exit__(None, None, None)


def test_folder_selection_ignores_unsupported_files_during_validate_and_group(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    folder = source_root / "Model Working Files"
    folder.mkdir()
    (folder / "usable_part.3mf").write_bytes(b"3mf-bytes")
    (folder / "notes.txt").write_text("ignore me", encoding="utf-8")

    client = _create_client(tmp_path, source_root)
    try:
        select_response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "folder", "path": str(folder), "recurse": True}]},
        )
        assert select_response.status_code == 200
        assert select_response.json()["expanded_file_count"] == 1
        item_id = select_response.json()["upload_id"]

        validate_response = client.post(f"/api/intake/items/{item_id}/validate")
        assert validate_response.status_code == 200
        validate_payload = validate_response.json()
        assert validate_payload["validation"]["validation_state"] == "ready"

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group", "title": "Folder Intake Group"},
        )
        assert group_response.status_code == 200
        group_payload = group_response.json()
        assert group_payload["added_items"] == 1
        assert group_payload["duplicate_items"] == 0
        assert group_payload["warnings"] == []
    finally:
        client.__exit__(None, None, None)
def test_folder_selection_group_uses_queued_title_hint_when_title_omitted(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    folder = source_root / "router-mount"
    folder.mkdir()
    (folder / "plate-a.3mf").write_bytes(b"3mf-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        select_response = client.post(
            "/api/source-filesystems/select",
            json={
                "selections": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                        "group_title_source": "custom",
                        "group_title": "Router Mount Family",
                    }
                ]
            },
        )
        assert select_response.status_code == 200
        item_id = select_response.json()["upload_id"]

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group"},
        )
        assert group_response.status_code == 200
        working_group_id = group_response.json()["working_group_id"]

        groups_response = client.get("/api/working-groups")
        assert groups_response.status_code == 200
        created_group = next(group for group in groups_response.json()["groups"] if group["id"] == working_group_id)
        assert created_group["title"] == "Router Mount Family"
    finally:
        client.__exit__(None, None, None)


def test_file_selection_group_uses_queued_title_hint_when_title_omitted(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    first_file = source_root / "router_mount_plate.3mf"
    second_file = source_root / "router_mount_brace.stl"
    first_file.write_bytes(b"plate-bytes")
    second_file.write_bytes(b"brace-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        select_response = client.post(
            "/api/source-filesystems/select",
            json={
                "selections": [
                    {
                        "type": "file",
                        "path": str(first_file),
                        "group_title_source": "custom",
                        "group_title": "Router Mount Batch",
                    },
                    {
                        "type": "file",
                        "path": str(second_file),
                        "group_title_source": "custom",
                        "group_title": "Router Mount Batch",
                    },
                ]
            },
        )
        assert select_response.status_code == 200
        item_id = select_response.json()["upload_id"]

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group"},
        )
        assert group_response.status_code == 200
        working_group_id = group_response.json()["working_group_id"]

        groups_response = client.get("/api/working-groups")
        assert groups_response.status_code == 200
        created_group = next(group for group in groups_response.json()["groups"] if group["id"] == working_group_id)
        assert created_group["title"] == "Router Mount Batch"
    finally:
        client.__exit__(None, None, None)


def test_folder_selection_with_unreadable_file_returns_warning_instead_of_500(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    folder = source_root / "Model Working Files"
    folder.mkdir()
    good_file = folder / "good_part.3mf"
    bad_file = folder / "bad_part.3mf"
    good_file.write_bytes(b"good-bytes")
    bad_file.write_bytes(b"bad-bytes")

    original_sha256_file = main_module._sha256_file

    def flaky_sha256(path: Path) -> str:
        if path.name == "bad_part.3mf":
            raise OSError("simulated read failure")
        return original_sha256_file(path)

    monkeypatch.setattr(main_module, "_sha256_file", flaky_sha256)

    client = _create_client(tmp_path, source_root)
    try:
        select_response = client.post(
            "/api/source-filesystems/select",
            json={"selections": [{"type": "folder", "path": str(folder), "recurse": True}]},
        )
        assert select_response.status_code == 200
        assert select_response.json()["expanded_file_count"] == 2
        item_id = select_response.json()["upload_id"]

        validate_response = client.post(f"/api/intake/items/{item_id}/validate")
        assert validate_response.status_code == 200
        validate_payload = validate_response.json()
        assert validate_payload["state"] == "validated_warning"
        assert validate_payload["validation"]["validation_state"] == "missing_source"
        assert any(
            warning.get("code") == "source_unreadable"
            for warning in validate_payload["validation"].get("warnings", [])
        )

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group", "title": "Partial Folder Intake Group"},
        )
        assert group_response.status_code == 200
        group_payload = group_response.json()
        assert group_payload["added_items"] == 1
        assert any(warning.get("code") == "source_unreadable" for warning in group_payload["warnings"])
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_stages_and_validates_mixed_sources(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    server_file = source_root / "server_part.3mf"
    server_file.write_bytes(b"server-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "cleanup_policy": "keep",
                "server_selections": [
                    {"type": "file", "path": str(server_file)}
                ],
                "browser_files": [
                    {
                        "filename": "fresh_part.3mf",
                        "relative_path": "browser/fresh_part.3mf",
                        "content_base64": base64.b64encode(b"browser-bytes").decode("ascii"),
                    }
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["success"] is True
        assert upload_payload["source_entry_count"] == 2
        assert upload_payload["browser_file_count"] == 1
        assert upload_payload["warnings"] == []

        validate_response = client.post(f"/api/intake/items/{upload_payload['upload_id']}/validate")
        assert validate_response.status_code == 200
        validate_payload = validate_response.json()
        assert validate_payload["validation"]["validation_state"] == "ready"
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_group_uses_queued_title_hint_when_title_omitted(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "cleanup_policy": "keep",
                "browser_files": [
                    {
                        "filename": "router_mount_plate.3mf",
                        "relative_path": "Router Mount/router_mount_plate.3mf",
                        "content_base64": base64.b64encode(b"plate-bytes").decode("ascii"),
                        "group_title_source": "custom",
                        "group_title": "Router Mount Browser Batch",
                    },
                    {
                        "filename": "router_mount_brace.stl",
                        "relative_path": "Router Mount/router_mount_brace.stl",
                        "content_base64": base64.b64encode(b"brace-bytes").decode("ascii"),
                        "group_title_source": "custom",
                        "group_title": "Router Mount Browser Batch",
                    },
                ],
            },
        )
        assert upload_response.status_code == 200
        item_id = upload_response.json()["upload_id"]

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group"},
        )
        assert group_response.status_code == 200
        working_group_id = group_response.json()["working_group_id"]

        groups_response = client.get("/api/working-groups")
        assert groups_response.status_code == 200
        created_group = next(group for group in groups_response.json()["groups"] if group["id"] == working_group_id)
        assert created_group["title"] == "Router Mount Browser Batch"
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_defaults_cleanup_policy_to_delete_on_verified(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "browser_files": [
                    {
                        "filename": "fresh_part.3mf",
                        "relative_path": "browser/fresh_part.3mf",
                        "content_base64": base64.b64encode(b"browser-bytes").decode("ascii"),
                    }
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["cleanup_policy"] == "delete_on_verified"

        list_response = client.get("/api/intake/uploads")
        assert list_response.status_code == 200
        uploads = {upload["upload_id"]: upload for upload in list_response.json()["uploads"]}
        assert uploads[upload_payload["upload_id"]]["cleanup_policy"] == "delete_on_verified"
    finally:
        client.__exit__(None, None, None)


def test_delete_browser_upload_removes_staged_directory(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "cleanup_policy": "keep",
                "browser_files": [
                    {
                        "filename": "delete_me.3mf",
                        "relative_path": "browser/delete_me.3mf",
                        "content_base64": base64.b64encode(b"browser-bytes").decode("ascii"),
                    }
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_id = upload_response.json()["upload_id"]

        connection = sqlite3.connect(tmp_path / "model_catalog.db")
        try:
            row = connection.execute(
                "SELECT source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()

        assert row is not None
        source_entries = json.loads(row[0])
        stage_upload_id = source_entries[0]["upload_id"]
        stage_dir = main_module._browser_intake_upload_storage_root(client.app.state.model_catalog.settings) / stage_upload_id
        assert stage_dir.exists() is True

        delete_response = client.delete(f"/api/intake/uploads/{upload_id}")
        assert delete_response.status_code == 200
        assert stage_dir.exists() is False
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_preserves_file_last_modified_timestamp(tmp_path: Path) -> None:
    """Test that browser-supplied file_last_modified_ms is preserved in source_entries_json."""
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        # Use a timestamp from 1 day ago (any value, test just verifies it's used)
        # Unix timestamp for 1 day ago in milliseconds
        one_day_ago_seconds = int(time.time()) - (24 * 60 * 60)
        browser_mtime_ms = one_day_ago_seconds * 1000
        
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "cleanup_policy": "keep",
                "browser_files": [
                    {
                        "filename": "dated_part.3mf",
                        "relative_path": "browser/dated_part.3mf",
                        "content_base64": base64.b64encode(b"dated-bytes").decode("ascii"),
                        "file_last_modified_ms": browser_mtime_ms,
                    }
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["success"] is True
        upload_id = upload_payload["upload_id"]

        # Query the database to verify source_entries_json contains the browser timestamp
        connection = sqlite3.connect(tmp_path / "model_catalog.db")
        try:
            row = connection.execute(
                "SELECT source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()

        assert row is not None
        source_entries = json.loads(row[0])
        assert len(source_entries) == 1
        entry = source_entries[0]
        
        # Verify the browser timestamp was converted to ISO 8601 UTC format
        assert "source_mtime" in entry
        assert entry["source_mtime"].endswith("Z")
        # Parse the timestamp to verify it's valid ISO 8601
        parsed_mtime = datetime.fromisoformat(entry["source_mtime"].replace("Z", "+00:00"))
        # Verify it's close to the expected time (within a few seconds of 1 day ago)
        expected_time = datetime.fromtimestamp(one_day_ago_seconds, tz=timezone.utc)
        time_diff = abs((parsed_mtime - expected_time).total_seconds())
        assert time_diff < 2, f"Timestamp difference {time_diff} seconds is too large"
        
        assert "source_ctime" in entry
        # source_ctime comes from stat (staging time), should be recent
        assert entry["source_ctime"].endswith("Z")
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_falls_back_to_stat_without_file_last_modified(tmp_path: Path) -> None:
    """Test that browser uploads without file_last_modified_ms fall back to filesystem stat."""
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "cleanup_policy": "keep",
                "browser_files": [
                    {
                        "filename": "no_timestamp_part.3mf",
                        "relative_path": "browser/no_timestamp_part.3mf",
                        "content_base64": base64.b64encode(b"no-timestamp-bytes").decode("ascii"),
                        # No file_last_modified_ms field
                    }
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["success"] is True
        upload_id = upload_payload["upload_id"]

        # Query the database to verify source_entries_json contains stat-based timestamps
        connection = sqlite3.connect(tmp_path / "model_catalog.db")
        try:
            row = connection.execute(
                "SELECT source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()

        assert row is not None
        source_entries = json.loads(row[0])
        assert len(source_entries) == 1
        entry = source_entries[0]
        
        # Verify timestamps are present and in ISO 8601 UTC format
        assert "source_mtime" in entry
        assert "source_ctime" in entry
        # Both should be recent (from staging), not an arbitrary value
        assert entry["source_mtime"].endswith("Z")
        assert entry["source_ctime"].endswith("Z")
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_ignores_invalid_file_last_modified_type(tmp_path: Path) -> None:
    """Test that invalid file_last_modified_ms values are safely ignored."""
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        upload_response = client.post(
            "/api/intake/uploads/browser",
            json={
                "cleanup_policy": "keep",
                "browser_files": [
                    {
                        "filename": "invalid_timestamp_part.3mf",
                        "relative_path": "browser/invalid_timestamp_part.3mf",
                        "content_base64": base64.b64encode(b"invalid-timestamp-bytes").decode("ascii"),
                        "file_last_modified_ms": "not-a-number",  # Invalid type
                    }
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["success"] is True
        upload_id = upload_payload["upload_id"]

        # Query the database to verify it fell back to stat timestamps
        connection = sqlite3.connect(tmp_path / "model_catalog.db")
        try:
            row = connection.execute(
                "SELECT source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()

        assert row is not None
        source_entries = json.loads(row[0])
        assert len(source_entries) == 1
        entry = source_entries[0]
        
        # Should have used stat-based timestamps (fallback), not the invalid string
        assert "source_mtime" in entry
        assert entry["source_mtime"].endswith("Z")
    finally:
        client.__exit__(None, None, None)


def test_projects_can_be_assigned_to_working_groups_and_filtered(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)

    client = _create_client(tmp_path, source_root)
    try:
        project_response = client.post(
            "/api/projects",
            json={"title": "Gridfinity Family", "description": "Shared project context"},
        )
        assert project_response.status_code == 200
        project_payload = project_response.json()["project"]

        group_response = client.post(
            "/api/working-groups",
            json={"title": "Bit Holder Remix", "stage": "draft", "project_id": project_payload["id"]},
        )
        assert group_response.status_code == 200
        group_payload = group_response.json()["group"]
        assert group_payload["project_id"] == project_payload["id"]
        assert group_payload["project"]["title"] == "Gridfinity Family"

        filtered = client.get("/api/working-groups", params={"project_id": project_payload["id"]})
        assert filtered.status_code == 200
        filtered_payload = filtered.json()
        assert filtered_payload["pagination"]["total"] == 1
        assert filtered_payload["groups"][0]["id"] == group_payload["id"]

        project_detail = client.get(f"/api/projects/{project_payload['id']}")
    finally:
        client.__exit__(None, None, None)

    assert project_detail.status_code == 200
    project_detail_payload = project_detail.json()["project"]
    assert project_detail_payload["working_group_count"] == 1


def test_working_group_publish_to_local_persists_project_and_lineage(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    model_file = source_root / "bit_holder_v3.3mf"
    model_file.write_bytes(b"3mf-working-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        project_response = client.post(
            "/api/projects",
            json={"title": "Bit Holder Family"},
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["project"]["id"]

        create_group = client.post(
            "/api/working-groups",
            json={"title": "Bit Holder v3", "stage": "ready_to_publish", "project_id": project_id},
        )
        assert create_group.status_code == 200
        group_id = create_group.json()["group"]["id"]

        attach_item = client.post(
            f"/api/working-groups/{group_id}/items",
            json={"file_path": str(model_file), "item_role": "primary"},
        )
        assert attach_item.status_code == 200

        publish_response = client.post(
            f"/api/working-groups/{group_id}/publish-to-local",
            json={
                "publish_outcome": "new_canonical_revision",
                "model_name": "Bit Holder v3",
                "project_id": project_id,
                "lineage_type": "supersedes",
                "target_model_ref": "bit-holder-v3",
                "reconciliation_notes": "Promote the new canonical revision.",
            },
        )
        assert publish_response.status_code == 200
        publish_payload = publish_response.json()
        assert publish_payload["success"] is True
        assert publish_payload["project_id"] == project_id
        assert publish_payload["published_from_group_id"] == group_id
        assert publish_payload["lineage"]["lineage_type"] == "supersedes"
        assert publish_payload["model_ref"] == "bit-holder-v3"
        assert len(publish_payload["imported_assets"]) == 1

        lineage_response = client.get("/api/models/bit-holder-v3/lineage")
        assert lineage_response.status_code == 200
        lineage_payload = lineage_response.json()
        assert lineage_payload["project_id"] == project_id
        assert lineage_payload["published_from_group_id"] == group_id
        assert lineage_payload["publish_outcome"] == "new_canonical_revision"
        assert len(lineage_payload["publish_history"]) == 1

        working_group = client.get(f"/api/working-groups/{group_id}")
    finally:
        client.__exit__(None, None, None)

    assert working_group.status_code == 200
    working_group_payload = working_group.json()["group"]
    assert working_group_payload["project_id"] == project_id


def test_working_files_explorer_views_include_group_memberships(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    grouped_file = source_root / "grouped_part.3mf"
    grouped_file.write_bytes(b"grouped-bytes")
    ungrouped_file = source_root / "loose_part.stl"
    ungrouped_file.write_bytes(b"ungrouped-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        reindex_response = client.post("/api/working-files/reindex", json={"compute_hashes": True, "recurse": True})
        assert reindex_response.status_code == 200

        create_group = client.post("/api/working-groups", json={"title": "Explorer Group", "stage": "draft"})
        assert create_group.status_code == 200
        group_id = int(create_group.json()["group"]["id"])

        add_response = client.post(
            "/api/working-groups/memberships/batch-add",
            json={"group_id": group_id, "file_paths": [str(grouped_file)], "item_role": "primary", "allow_multi_group": True},
        )
        assert add_response.status_code == 200
        assert add_response.json()["summary"]["added"] == 1

        all_response = client.get("/api/working-files/explorer", params={"view": "all"})
        assert all_response.status_code == 200
        all_payload = all_response.json()
        assert all_payload["summary"]["all_count"] == 2
        assert any(len(file_row["group_memberships"]) == 1 for file_row in all_payload["files"])

        ungrouped_response = client.get("/api/working-files/explorer", params={"view": "ungrouped"})
        assert ungrouped_response.status_code == 200
        ungrouped_payload = ungrouped_response.json()
        assert ungrouped_payload["summary"]["ungrouped_count"] == 1
        assert ungrouped_payload["pagination"]["total"] == 1

        groups_response = client.get("/api/working-files/explorer", params={"view": "groups"})
    finally:
        client.__exit__(None, None, None)

    assert groups_response.status_code == 200
    groups_payload = groups_response.json()
    assert groups_payload["summary"]["group_count"] == 1
    assert groups_payload["groups"][0]["counts"]["count_3mf"] == 1


def test_working_files_explorer_all_and_ungrouped_ignore_inbox_inventory(tmp_path: Path) -> None:
    assets_root = tmp_path / "assets"
    inbox_root = assets_root / "Model Inbox"
    working_root = assets_root / "Model Working Files"
    inbox_root.mkdir(parents=True, exist_ok=True)
    working_root.mkdir(parents=True, exist_ok=True)

    inbox_file = inbox_root / "inbox-only.stl"
    inbox_file.write_bytes(b"inbox-bytes")
    working_grouped_file = working_root / "grouped-part.3mf"
    working_grouped_file.write_bytes(b"grouped-bytes")
    working_ungrouped_file = working_root / "loose-part.stl"
    working_ungrouped_file.write_bytes(b"loose-bytes")

    client = _create_client_with_roots(tmp_path, (inbox_root, working_root))
    try:
        reindex_response = client.post(
            "/api/working-files/reindex",
            json={"compute_hashes": True, "recurse": True, "roots": [str(working_root)]},
        )
        assert reindex_response.status_code == 200
        assert reindex_response.json()["discovered"] == 2

        create_group = client.post("/api/working-groups", json={"title": "Working Group", "stage": "draft"})
        assert create_group.status_code == 200
        group_id = int(create_group.json()["group"]["id"])

        add_response = client.post(
            "/api/working-groups/memberships/batch-add",
            json={"group_id": group_id, "file_paths": [str(working_grouped_file)], "item_role": "primary", "allow_multi_group": True},
        )
        assert add_response.status_code == 200
        assert add_response.json()["summary"]["added"] == 1

        all_response = client.get("/api/working-files/explorer", params={"view": "all"})
        assert all_response.status_code == 200
        all_payload = all_response.json()

        ungrouped_response = client.get("/api/working-files/explorer", params={"view": "ungrouped"})
        assert ungrouped_response.status_code == 200
        ungrouped_payload = ungrouped_response.json()
    finally:
        client.__exit__(None, None, None)

    all_paths = {file_row["source_path_canonical"] for file_row in all_payload["files"]}
    assert str(inbox_file.resolve()) not in all_paths
    assert all_payload["summary"]["all_count"] == 2
    assert all_payload["pagination"]["total"] == 2

    ungrouped_paths = {file_row["source_path_canonical"] for file_row in ungrouped_payload["files"]}
    assert str(inbox_file.resolve()) not in ungrouped_paths
    assert ungrouped_paths == {str(working_ungrouped_file.resolve())}
    assert ungrouped_payload["summary"]["ungrouped_count"] == 1
    assert ungrouped_payload["pagination"]["total"] == 1


def test_batch_add_memberships_allows_multi_group_with_hash_conflict(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    shared_file = source_root / "shared.3mf"
    shared_file.write_bytes(b"same-shared-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        first_group = client.post("/api/working-groups", json={"title": "Group A", "stage": "draft"})
        second_group = client.post("/api/working-groups", json={"title": "Group B", "stage": "draft"})
        assert first_group.status_code == 200
        assert second_group.status_code == 200
        group_a_id = int(first_group.json()["group"]["id"])
        group_b_id = int(second_group.json()["group"]["id"])

        add_a = client.post(
            "/api/working-groups/memberships/batch-add",
            json={"group_id": group_a_id, "file_paths": [str(shared_file)], "allow_multi_group": True},
        )
        assert add_a.status_code == 200
        assert add_a.json()["summary"]["added"] == 1

        add_b = client.post(
            "/api/working-groups/memberships/batch-add",
            json={"group_id": group_b_id, "file_paths": [str(shared_file)], "allow_multi_group": True},
        )
        assert add_b.status_code == 200
        add_b_payload = add_b.json()
        assert add_b_payload["summary"]["added"] == 1
        assert add_b_payload["results"][0]["warning"] == "hash_conflict_in_existing_group"

        group_b = client.get(f"/api/working-groups/{group_b_id}")
    finally:
        client.__exit__(None, None, None)

    assert group_b.status_code == 200
    assert len(group_b.json()["group"]["items"]) == 1


def test_reorganize_working_group_dry_run_and_execute(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    source_folder = source_root / "incoming"
    source_folder.mkdir(parents=True, exist_ok=True)
    source_file = source_folder / "move_me.3mf"
    source_file.write_bytes(b"move-me")

    client = _create_client(tmp_path, source_root)
    try:
        create_group = client.post("/api/working-groups", json={"title": "Move Group", "stage": "draft"})
        assert create_group.status_code == 200
        group_id = int(create_group.json()["group"]["id"])
        slug = str(create_group.json()["group"]["slug"])

        add_item = client.post(
            f"/api/working-groups/{group_id}/items",
            json={"file_path": str(source_file), "item_role": "primary"},
        )
        assert add_item.status_code == 200

        dry_run = client.post(f"/api/working-groups/{group_id}/reorganize", json={"execute": False})
        assert dry_run.status_code == 200
        dry_payload = dry_run.json()
        assert dry_payload["dry_run"] is True
        assert dry_payload["can_execute"] is True
        assert "operation_plan" in dry_payload
        assert dry_payload["collisions_detected"] == 0
        assert any(entry["action"] == "move" for entry in dry_payload["plan"])

        execute = client.post(f"/api/working-groups/{group_id}/reorganize", json={"execute": True})
        assert execute.status_code == 200
        execute_payload = execute.json()
        assert execute_payload["dry_run"] is False
        assert execute_payload["moved_count"] == 1
        assert execute_payload["collisions_detected"] == 0
        assert isinstance(execute_payload["audit_events"], list)

        expected_path = source_root / slug / source_file.name
        assert expected_path.exists() is True
        assert source_file.exists() is False
    finally:
        client.__exit__(None, None, None)


def test_reorganize_working_group_renames_when_destination_file_exists(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    source_folder = source_root / "incoming"
    source_folder.mkdir(parents=True, exist_ok=True)
    source_file = source_folder / "duplicate.3mf"
    source_file.write_bytes(b"new-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        create_group = client.post("/api/working-groups", json={"title": "Collision Group", "stage": "draft"})
        assert create_group.status_code == 200
        group_id = int(create_group.json()["group"]["id"])
        slug = str(create_group.json()["group"]["slug"])

        target_folder = source_root / slug
        target_folder.mkdir(parents=True, exist_ok=True)
        existing_destination = target_folder / source_file.name
        existing_destination.write_bytes(b"existing-bytes")

        add_item = client.post(
            f"/api/working-groups/{group_id}/items",
            json={"file_path": str(source_file), "item_role": "primary"},
        )
        assert add_item.status_code == 200

        dry_run = client.post(f"/api/working-groups/{group_id}/reorganize", json={"execute": False})
        assert dry_run.status_code == 200
        dry_payload = dry_run.json()
        assert dry_payload["dry_run"] is True
        assert dry_payload["can_execute"] is True
        assert dry_payload["collisions_detected"] == 1
        assert len(dry_payload["collision_renames"]) == 1
        assert any(entry.get("collision_renamed") is True for entry in dry_payload["operation_plan"])

        execute = client.post(f"/api/working-groups/{group_id}/reorganize", json={"execute": True})
        assert execute.status_code == 200
        execute_payload = execute.json()
        assert execute_payload["dry_run"] is False
        assert execute_payload["moved_count"] == 1
        assert execute_payload["collisions_detected"] == 1
        assert execute_payload["duplicate_hash_skipped_count"] == 0
        renamed_path = target_folder / "duplicate-2.3mf"
        assert renamed_path.exists() is True
        assert source_file.exists() is False
    finally:
        client.__exit__(None, None, None)


def test_reorganize_working_group_skips_duplicate_hash_in_target_folder(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    source_folder = source_root / "incoming"
    source_folder.mkdir(parents=True, exist_ok=True)
    source_file = source_folder / "same_content.3mf"
    source_bytes = b"identical-bytes"
    source_file.write_bytes(source_bytes)

    client = _create_client(tmp_path, source_root)
    try:
        create_group = client.post("/api/working-groups", json={"title": "Dupes Group", "stage": "draft"})
        assert create_group.status_code == 200
        group_id = int(create_group.json()["group"]["id"])
        slug = str(create_group.json()["group"]["slug"])

        target_folder = source_root / slug
        target_folder.mkdir(parents=True, exist_ok=True)
        existing_destination = target_folder / "existing_copy.3mf"
        existing_destination.write_bytes(source_bytes)

        add_item = client.post(
            f"/api/working-groups/{group_id}/items",
            json={"file_path": str(source_file), "item_role": "primary"},
        )
        assert add_item.status_code == 200

        dry_run = client.post(f"/api/working-groups/{group_id}/reorganize", json={"execute": False})
        assert dry_run.status_code == 200
        dry_payload = dry_run.json()
        assert dry_payload["dry_run"] is True
        assert dry_payload["can_execute"] is True
        assert dry_payload["duplicate_hash_skipped_count"] == 1
        assert len(dry_payload["duplicate_hash_skips"]) == 1
        assert any(entry.get("action") == "duplicate" for entry in dry_payload["operation_plan"])

        execute = client.post(f"/api/working-groups/{group_id}/reorganize", json={"execute": True})
        assert execute.status_code == 200
        execute_payload = execute.json()
        assert execute_payload["moved_count"] == 0
        assert execute_payload["duplicate_hash_skipped_count"] == 1
        assert source_file.exists() is True
        assert existing_destination.exists() is True
    finally:
        client.__exit__(None, None, None)


def test_batch_add_memberships_accepts_folder_path(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    folder = source_root / "bundle"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "part_a.3mf").write_bytes(b"a")
    (folder / "part_b.stl").write_bytes(b"b")
    (folder / "ignore.txt").write_text("ignored", encoding="utf-8")

    client = _create_client(tmp_path, source_root)
    try:
        create_group = client.post("/api/working-groups", json={"title": "Folder Group", "stage": "draft"})
        assert create_group.status_code == 200
        group_id = int(create_group.json()["group"]["id"])

        add_response = client.post(
            "/api/working-groups/memberships/batch-add",
            json={"group_id": group_id, "file_paths": [str(folder)], "allow_multi_group": True},
        )
        assert add_response.status_code == 200
        payload = add_response.json()
        assert payload["summary"]["added"] == 2

        group_detail = client.get(f"/api/working-groups/{group_id}")
    finally:
        client.__exit__(None, None, None)

    assert group_detail.status_code == 200
    assert len(group_detail.json()["group"]["items"]) == 2
