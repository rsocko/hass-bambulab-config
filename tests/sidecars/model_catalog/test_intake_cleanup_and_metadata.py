import json
import sqlite3
import base64
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None


def _make_settings(db_path: Path, source_root: Path, working_root: Path, curated_root: Path) -> Settings:
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
        working_files_root=working_root.resolve(),
        model_catalog_assets_root=curated_root.resolve(),
    )


def _create_client(tmp_path: Path) -> tuple[TestClient, Path]:
    source_root = tmp_path / "inbox"
    working_root = tmp_path / "working"
    curated_root = tmp_path / "curated"
    source_root.mkdir(parents=True, exist_ok=True)
    working_root.mkdir(parents=True, exist_ok=True)
    curated_root.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "model_catalog.db"
    app = create_app(
        settings=_make_settings(db_path, source_root, working_root, curated_root),
        manyfold_client=FakeManyfoldClient(),
    )
    client = TestClient(app)
    client.__enter__()
    return client, source_root


def test_cleanup_delete_respects_exclusions_and_prunes_empty_subfolders(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        batch = source_root / "batch-partial"
        keep_folder = batch / "keep-sub"
        prune_folder = batch / "prune-sub"
        keep_folder.mkdir(parents=True, exist_ok=True)
        prune_folder.mkdir(parents=True, exist_ok=True)

        included_root_file = batch / "imported-root.3mf"
        included_prune_file = prune_folder / "imported-prune.stl"
        excluded_file = keep_folder / "excluded.3mf"

        included_root_file.write_bytes(b"root")
        included_prune_file.write_bytes(b"prune")
        excluded_file.write_bytes(b"keep")

        create_response = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "delete_on_verified",
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(batch),
                        "recurse": True,
                        "excluded_items": [
                            str(excluded_file),
                            str(keep_folder) + "/",
                        ],
                    }
                ],
            },
        )
        assert create_response.status_code == 200
        upload_id = create_response.json()["upload_id"]

        publish_response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "cleanup_policy": "delete_on_verified",
                "group_destinations": [{"destination": "working", "title": "Partial"}],
            },
        )
        assert publish_response.status_code == 200

        cleanup_payload = publish_response.json()
        assert cleanup_payload["success"] is True
        assert cleanup_payload["cleanup"]["policy"] == "delete_on_verified"
        assert str(cleanup_payload.get("status") or "") in {"cleanup_done", "verified"}

        assert excluded_file.exists(), "Excluded files must remain untouched"
        assert keep_folder.exists(), "Excluded folders must remain untouched"
        assert not included_root_file.exists(), "Imported source file should be removed/moved"
        assert not included_prune_file.exists(), "Imported nested source file should be removed/moved"
        assert not prune_folder.exists(), "Empty folders created by imported-only files should be removed"
        assert batch.exists(), "Root folder remains because excluded content still exists"
    finally:
        client.__exit__(None, None, None)


def test_cleanup_delete_recursively_removes_empty_selected_folder(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        batch = source_root / "batch-empty"
        nested = batch / "nested"
        nested.mkdir(parents=True, exist_ok=True)
        imported_file = nested / "model.3mf"
        imported_file.write_bytes(b"model")

        create_response = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "delete_on_verified",
                "source_entries": [{"type": "folder", "path": str(batch), "recurse": True}],
            },
        )
        assert create_response.status_code == 200
        upload_id = create_response.json()["upload_id"]

        publish_response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "cleanup_policy": "delete_on_verified",
                "group_destinations": [{"destination": "working", "title": "Recursive"}],
            },
        )
        assert publish_response.status_code == 200

        cleanup_payload = publish_response.json()

        assert cleanup_payload["success"] is True
        assert not batch.exists(), "Selected folder should be removed when all descendants were imported/deleted"
        assert source_root.exists(), "Managed intake root itself must not be removed"

        deleted_source_dirs = cleanup_payload["cleanup"].get("deleted_source_dirs") or []
        assert any(Path(path).name == "nested" for path in deleted_source_dirs)
        assert any(Path(path).name == "batch-empty" for path in deleted_source_dirs)
    finally:
        client.__exit__(None, None, None)


def test_publish_persists_source_and_import_timestamps(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    db_path = tmp_path / "model_catalog.db"
    try:
        source_file = source_root / "timestamped.3mf"
        source_file.write_bytes(b"timestamp")

        upload_working = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(source_file)}],
            },
        )
        assert upload_working.status_code == 200
        working_upload_id = upload_working.json()["upload_id"]

        publish_working = client.post(
            f"/api/intake/uploads/{working_upload_id}/publish-to-working",
            json={"title": "Timestamp Group"},
        )
        assert publish_working.status_code == 200
        working_group_id = int(publish_working.json()["working_group_id"])

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            group_row = connection.execute(
                "SELECT discovery_metadata_json FROM working_groups WHERE id = ?",
                (working_group_id,),
            ).fetchone()
            assert group_row is not None
            group_metadata = json.loads(str(group_row["discovery_metadata_json"] or "{}"))
            assert str(group_metadata.get("imported_at") or "")
            timestamp_summary = group_metadata.get("source_timestamp_summary") or {}
            assert str(timestamp_summary.get("earliest_source_mtime") or "")
            assert str(timestamp_summary.get("latest_source_ctime") or "")

            item_row = connection.execute(
                "SELECT source_metadata_json FROM working_items WHERE working_group_id = ?",
                (working_group_id,),
            ).fetchone()
            assert item_row is not None
            source_metadata = json.loads(str(item_row["source_metadata_json"] or "{}"))
            assert str(source_metadata.get("source_mtime") or "")
            assert str(source_metadata.get("source_ctime") or "")

        source_file_2 = source_root / "timestamped-local.3mf"
        source_file_2.write_bytes(b"timestamp-local")
        upload_local = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(source_file_2)}],
            },
        )
        assert upload_local.status_code == 200
        local_upload_id = upload_local.json()["upload_id"]

        publish_local = client.post(
            f"/api/intake/uploads/{local_upload_id}/publish-by-destination",
            json={
                "cleanup_policy": "keep",
                "group_destinations": [{"destination": "curated", "model_name": "Timestamp Local"}],
            },
        )
        assert publish_local.status_code == 200
        local_model_id = str((publish_local.json().get("curated_model_ids") or [""])[0])
        assert local_model_id

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            fields_rows = connection.execute(
                """
                SELECT field_key, field_value_json
                                FROM model_catalog_custom_fields
                                WHERE entity_type = 'manyfold_model' AND entity_id = ?
                                    AND field_namespace = 'model_catalog'
                                    AND field_key IN ('intake_source_timestamp_summary', 'intake_imported_at')
                """,
                (local_model_id,),
            ).fetchall()

        fields = {
            str(row["field_key"]): json.loads(str(row["field_value_json"] or "null"))
            for row in fields_rows
        }
        assert str(fields.get("intake_imported_at") or "")
        summary = fields.get("intake_source_timestamp_summary") or {}
        assert str(summary.get("earliest_source_mtime") or "")
        assert str(summary.get("latest_source_ctime") or "")
    finally:
        client.__exit__(None, None, None)


def test_browser_upload_preserves_original_last_modified_metadata(tmp_path: Path) -> None:
    client, _source_root = _create_client(tmp_path)
    db_path = tmp_path / "model_catalog.db"
    try:
        # 2026-03-15T10:00:00Z in epoch ms
        browser_last_modified_ms = 1773578400000
        browser_upload = client.post(
            "/api/intake/uploads/browser",
            json={
                "browser_files": [
                    {
                        "filename": "browser-intake.3mf",
                        "relative_path": "folder/browser-intake.3mf",
                        "content_base64": base64.b64encode(b"browser-intake").decode("ascii"),
                        "file_last_modified_ms": browser_last_modified_ms,
                    }
                ]
            },
        )
        assert browser_upload.status_code == 200
        upload_id = browser_upload.json()["upload_id"]

        publish_response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "working", "title": "Browser Metadata"}]},
        )
        assert publish_response.status_code == 200
        working_group_id = int((publish_response.json().get("working_group_ids") or [0])[0])
        assert working_group_id > 0

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            upload_row = connection.execute(
                "SELECT source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
            assert upload_row is not None
            source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
            assert isinstance(source_entries, list) and source_entries
            staged_source_path = Path(str(source_entries[0].get("path") or ""))
            staged_upload_dir = staged_source_path.parent.parent

            item_row = connection.execute(
                "SELECT source_metadata_json FROM working_items WHERE working_group_id = ?",
                (working_group_id,),
            ).fetchone()
            assert item_row is not None
            source_metadata = json.loads(str(item_row["source_metadata_json"] or "{}"))

        # Browser client timestamp should be captured as source_mtime rather than staging mtime.
        expected_source_mtime = (
            datetime.fromtimestamp(browser_last_modified_ms / 1000.0, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        assert str(source_metadata.get("source_mtime") or "") == expected_source_mtime
        assert str(source_metadata.get("source_ctime") or "")
        assert not staged_upload_dir.exists(), "Browser intake staging directory should be removed after publish"
    finally:
        client.__exit__(None, None, None)
