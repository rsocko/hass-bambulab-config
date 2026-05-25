import json
import sqlite3
import base64
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from sidecars.model_catalog.app.routers.intake_verification import _normalize_indexed_conflicts


def _make_settings(db_path: Path, source_root: Path, working_root: Path, curated_root: Path) -> Settings:
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
        publish_payload = publish_working.json()
        working_folder_slug = str(publish_payload.get("working_folder_slug") or "").strip()
        assert working_folder_slug, "publish-to-working should return working_folder_slug"

        created_groups = publish_payload.get("created_groups") or []
        assert created_groups, "publish-to-working should return at least one created group"
        folder_path = Path(str(created_groups[0]["folder_path"]))
        assert folder_path.is_dir()

        modelmeta_path = folder_path / ".modelmeta.json"
        assert modelmeta_path.is_file(), ".modelmeta.json sidecar must exist"
        modelmeta = json.loads(modelmeta_path.read_text(encoding="utf-8"))
        assert str(modelmeta.get("imported_at") or "")
        timestamp_summary = modelmeta.get("source_timestamp_summary") or {}
        assert str(timestamp_summary.get("earliest_source_mtime") or "")
        assert str(timestamp_summary.get("latest_source_ctime") or "")

        modelmeta_files = modelmeta.get("files") or []
        assert modelmeta_files, ".modelmeta.json should record per-file metadata"
        first_file_meta = modelmeta_files[0]
        assert str(first_file_meta.get("source_mtime") or "")
        assert str(first_file_meta.get("source_ctime") or "")

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
                                WHERE entity_type = 'catalog_model' AND entity_id = ?
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
        publish_payload = publish_response.json()
        working_folder_slugs = publish_payload.get("working_folder_slugs") or []
        assert working_folder_slugs, "publish-by-destination should return working_folder_slugs"

        created_groups = publish_payload.get("group_results") or []
        assert created_groups, "publish-by-destination should return at least one group_result"
        folder_path = Path(str(created_groups[0]["folder_path"]))
        assert folder_path.is_dir()

        modelmeta_path = folder_path / ".modelmeta.json"
        assert modelmeta_path.is_file()
        modelmeta = json.loads(modelmeta_path.read_text(encoding="utf-8"))
        modelmeta_files = modelmeta.get("files") or []
        assert modelmeta_files, ".modelmeta.json should record per-file metadata"
        source_metadata = modelmeta_files[0]

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


def test_publish_to_working_keep_policy_preserves_source_files(tmp_path: Path) -> None:
    """When cleanup_policy is 'keep', source files must remain in the inbox after publish."""
    client, source_root = _create_client(tmp_path)
    working_root = tmp_path / "working"
    try:
        folder = source_root / "pennants"
        folder.mkdir()
        (folder / "model.3mf").write_bytes(b"model-data")
        (folder / "plate.stl").write_bytes(b"plate-data")
        sub = folder / "images"
        sub.mkdir()
        (sub / "preview.png").write_bytes(b"png-data")

        enqueue = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "folder", "path": str(folder)}],
            },
        )
        assert enqueue.status_code == 200
        upload_id = enqueue.json()["upload_id"]

        publish = client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-working",
            json={"title": "Pennants"},
        )
        assert publish.status_code == 200

        # Source files must still exist (policy=keep)
        assert (folder / "model.3mf").exists(), "source model.3mf should remain with keep policy"
        assert (folder / "plate.stl").exists(), "source plate.stl should remain with keep policy"
        assert (sub / "preview.png").exists(), "source preview.png should remain with keep policy"

        # Destination files must also exist
        working_groups = list(working_root.iterdir())
        assert len(working_groups) >= 1
        dest_files = list(working_groups[0].rglob("*"))
        dest_file_names = {f.name for f in dest_files if f.is_file()}
        assert "model.3mf" in dest_file_names
        assert "plate.stl" in dest_file_names
        assert "preview.png" in dest_file_names
    finally:
        client.__exit__(None, None, None)


def test_publish_by_destination_requires_override_for_validated_warning(tmp_path: Path) -> None:
    """Validated warning uploads require override_warning to publish by destination."""
    client, source_root = _create_client(tmp_path)
    try:
        first_file = source_root / "existing.3mf"
        first_file.write_bytes(b"duplicate-content")

        first_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(first_file)}],
            },
        )
        assert first_upload.status_code == 200
        first_upload_id = first_upload.json()["upload_id"]

        first_publish = client.post(
            f"/api/intake/uploads/{first_upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "working", "title": "Existing"}]},
        )
        assert first_publish.status_code == 200

        duplicate_file = source_root / "existing-copy.3mf"
        duplicate_file.write_bytes(b"duplicate-content")

        second_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(duplicate_file)}],
            },
        )
        assert second_upload.status_code == 200
        second_upload_id = second_upload.json()["upload_id"]

        second_validate = client.post(f"/api/intake/items/{second_upload_id}/validate")
        assert second_validate.status_code == 200
        assert second_validate.json()["validation"]["validation_state"] == "duplicate_candidate"

        publish_without_override = client.post(
            f"/api/intake/uploads/{second_upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "working", "title": "Duplicate"}]},
        )
        assert publish_without_override.status_code == 409
        assert publish_without_override.json().get("error") == "override_required_for_warning_state"

        publish_with_override = client.post(
            f"/api/intake/uploads/{second_upload_id}/publish-by-destination",
            json={
                "group_destinations": [{"destination": "working", "title": "Duplicate"}],
                "override_warning": True,
            },
        )
        assert publish_with_override.status_code == 200
        assert publish_with_override.json().get("success") is True
    finally:
        client.__exit__(None, None, None)


def test_validation_action_choices_are_persisted_for_review(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    db_path = tmp_path / "model_catalog.db"
    try:
        baseline_file = source_root / "baseline.3mf"
        baseline_file.write_bytes(b"same-bytes")

        baseline_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(baseline_file)}],
            },
        )
        assert baseline_upload.status_code == 200
        baseline_upload_id = baseline_upload.json()["upload_id"]

        baseline_publish = client.post(
            f"/api/intake/uploads/{baseline_upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "working", "title": "Baseline"}]},
        )
        assert baseline_publish.status_code == 200

        duplicate_file = source_root / "duplicate.3mf"
        duplicate_file.write_bytes(b"same-bytes")

        duplicate_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(duplicate_file)}],
            },
        )
        assert duplicate_upload.status_code == 200
        duplicate_upload_id = duplicate_upload.json()["upload_id"]

        validate_response = client.post(f"/api/intake/items/{duplicate_upload_id}/validate")
        assert validate_response.status_code == 200
        assert validate_response.json()["validation"]["validation_state"] == "duplicate_candidate"

        validation_payload = validate_response.json()["validation"]
        duplicate_check = next(
            (
                check for check in (validation_payload.get("checks") or [])
                if str(check.get("key") or "") in {"duplicate_scan", "batch_duplicate_scan"}
                and isinstance(check.get("findings"), list)
                and check.get("findings")
            ),
            None,
        )
        assert duplicate_check is not None
        finding = duplicate_check["findings"][0]
        finding_key = "|".join(
            [
                str(duplicate_check.get("key") or ""),
                str(finding.get("path") or ""),
                str(finding.get("filename") or ""),
                str(finding.get("violation_code") or ""),
                "0",
            ]
        ).lower()

        save_action = client.post(
            f"/api/intake/items/{duplicate_upload_id}/validation-actions",
            json={
                "finding_key": finding_key,
                "decision": "allow_duplicate",
                "check_key": str(duplicate_check.get("key") or ""),
                "source_path": str(finding.get("path") or ""),
                "source_name": str(finding.get("filename") or ""),
            },
        )
        assert save_action.status_code == 200
        assert save_action.json().get("validation_action_count") == 1

        item_response = client.get(f"/api/intake/items/{duplicate_upload_id}")
        assert item_response.status_code == 200
        decision_note_raw = item_response.json()["item"].get("decision_note")
        parsed_note = json.loads(str(decision_note_raw or "{}"))
        assert isinstance(parsed_note.get("warnings"), list)
        actions = parsed_note.get("validation_actions") or []
        assert len(actions) == 1
        assert actions[0].get("decision") == "allow_duplicate"
        assert actions[0].get("finding_key") == finding_key

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            event_row = connection.execute(
                """
                SELECT payload_json
                FROM model_catalog_events
                WHERE entity_type = 'intake_queue_upload'
                  AND entity_id = ?
                  AND event_type = 'intake_validation_action_set'
                ORDER BY id DESC
                LIMIT 1
                """,
                (duplicate_upload_id,),
            ).fetchone()
        assert event_row is not None
        event_payload = json.loads(str(event_row["payload_json"] or "{}"))
        assert event_payload.get("decision") == "allow_duplicate"
        assert event_payload.get("finding_key") == finding_key
    finally:
        client.__exit__(None, None, None)


def test_batch_validation_action_pair_decision_is_persisted(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        first_file = source_root / "batch-a.3mf"
        second_file = source_root / "batch-b.3mf"
        first_file.write_bytes(b"same-batch-bytes")
        second_file.write_bytes(b"same-batch-bytes")

        upload_response = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [
                    {"type": "file", "path": str(first_file)},
                    {"type": "file", "path": str(second_file)},
                ],
            },
        )
        assert upload_response.status_code == 200
        upload_id = upload_response.json()["upload_id"]

        validate_response = client.post(f"/api/intake/items/{upload_id}/validate")
        assert validate_response.status_code == 200
        validation = validate_response.json().get("validation") or {}
        assert validation.get("validation_state") == "duplicate_candidate"

        batch_check = next(
            (
                check for check in (validation.get("checks") or [])
                if str(check.get("key") or "") == "batch_duplicate_scan"
                and isinstance(check.get("findings"), list)
                and check.get("findings")
            ),
            None,
        )
        assert batch_check is not None
        finding = batch_check["findings"][0]
        finding_key = "|".join(
            [
                str(batch_check.get("key") or ""),
                str(finding.get("path") or ""),
                str(finding.get("filename") or ""),
                str(finding.get("violation_code") or ""),
                "0",
            ]
        ).lower()

        conflict = None
        if isinstance(finding.get("conflicts_with"), list) and finding.get("conflicts_with"):
            candidate = finding.get("conflicts_with")[0]
            if isinstance(candidate, dict):
                conflict = candidate

        save_action = client.post(
            f"/api/intake/items/{upload_id}/validation-actions",
            json={
                "finding_key": finding_key,
                "decision": "keep_both",
                "check_key": "batch_duplicate_scan",
                "source_path": str(finding.get("path") or ""),
                "source_name": str(finding.get("filename") or ""),
                "target_path": str((conflict or {}).get("path") or ""),
                "target_name": str((conflict or {}).get("filename") or ""),
            },
        )
        assert save_action.status_code == 200
        assert save_action.json().get("validation_action_count") == 1

        item_response = client.get(f"/api/intake/items/{upload_id}")
        assert item_response.status_code == 200
        parsed_note = json.loads(str(item_response.json()["item"].get("decision_note") or "{}"))
        actions = parsed_note.get("validation_actions") or []
        assert len(actions) == 1
        assert actions[0].get("decision") == "keep_both"
        assert actions[0].get("check_key") == "batch_duplicate_scan"
    finally:
        client.__exit__(None, None, None)


def test_indexed_duplicate_conflict_includes_preview_url(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    db_path = tmp_path / "model_catalog.db"
    expected_preview_url = "https://example.com/previews/duplicate-thumb.jpg"
    try:
        baseline_file = source_root / "indexed-duplicate.3mf"
        baseline_file.write_bytes(b"baseline-bytes")

        baseline_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(baseline_file)}],
            },
        )
        assert baseline_upload.status_code == 200
        baseline_upload_id = baseline_upload.json()["upload_id"]

        baseline_publish = client.post(
            f"/api/intake/uploads/{baseline_upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "curated", "title": "Indexed Baseline"}]},
        )
        assert baseline_publish.status_code == 200

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                UPDATE model_catalog_assets
                SET preview_url = ?
                WHERE asset_filename = ?
                """,
                (expected_preview_url, baseline_file.name),
            )
            connection.commit()

        incoming_duplicate = source_root / "indexed-duplicate.3mf"
        incoming_duplicate.write_bytes(b"incoming-different-bytes")

        duplicate_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(incoming_duplicate)}],
            },
        )
        assert duplicate_upload.status_code == 200
        duplicate_upload_id = duplicate_upload.json()["upload_id"]

        validate_response = client.post(f"/api/intake/items/{duplicate_upload_id}/validate")
        assert validate_response.status_code == 200
        validation_payload = validate_response.json().get("validation") or {}

        indexed_conflicts: list[dict[str, object]] = []
        for check in validation_payload.get("checks") or []:
            findings = check.get("findings") if isinstance(check, dict) else None
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                conflicts = finding.get("conflicts_with")
                if not isinstance(conflicts, list):
                    continue
                for conflict in conflicts:
                    if not isinstance(conflict, dict):
                        continue
                    if str(conflict.get("scope") or "").strip().lower() != "indexed":
                        continue
                    if str(conflict.get("parent_kind") or "").strip().lower() != "catalog_model":
                        continue
                    indexed_conflicts.append(conflict)

        assert indexed_conflicts, "Expected at least one indexed catalog conflict"
        assert any(
            str(conflict.get("preview_url") or "").strip() == expected_preview_url
            for conflict in indexed_conflicts
        )
    finally:
        client.__exit__(None, None, None)


def test_indexed_image_conflict_falls_back_to_model_asset_download_url(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    db_path = tmp_path / "model_catalog.db"
    try:
        baseline_image = source_root / "instructions torso.jpg"
        baseline_image.write_bytes(b"baseline-image")

        baseline_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(baseline_image)}],
            },
        )
        assert baseline_upload.status_code == 200
        baseline_upload_id = baseline_upload.json()["upload_id"]

        baseline_publish = client.post(
            f"/api/intake/uploads/{baseline_upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "curated", "title": "Image Baseline"}]},
        )
        assert baseline_publish.status_code == 200

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                UPDATE model_catalog_assets
                SET preview_url = NULL
                WHERE asset_filename = ?
                """,
                (baseline_image.name,),
            )
            connection.commit()

        incoming_image = source_root / "instructions torso (1).jpg"
        incoming_image.write_bytes(b"incoming-image")

        duplicate_upload = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(incoming_image)}],
            },
        )
        assert duplicate_upload.status_code == 200
        duplicate_upload_id = duplicate_upload.json()["upload_id"]

        validate_response = client.post(f"/api/intake/items/{duplicate_upload_id}/validate")
        assert validate_response.status_code == 200
        validation_payload = validate_response.json().get("validation") or {}

        indexed_conflicts: list[dict[str, object]] = []
        for check in validation_payload.get("checks") or []:
            findings = check.get("findings") if isinstance(check, dict) else None
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                conflicts = finding.get("conflicts_with")
                if not isinstance(conflicts, list):
                    continue
                for conflict in conflicts:
                    if not isinstance(conflict, dict):
                        continue
                    if str(conflict.get("scope") or "").strip().lower() != "indexed":
                        continue
                    if str(conflict.get("parent_kind") or "").strip().lower() != "catalog_model":
                        continue
                    indexed_conflicts.append(conflict)

        assert indexed_conflicts, "Expected at least one indexed catalog conflict"
        assert any(
            str(conflict.get("preview_url") or "").startswith("/api/models/")
            and "/download" in str(conflict.get("preview_url") or "")
            for conflict in indexed_conflicts
        )
    finally:
        client.__exit__(None, None, None)


def test_normalize_indexed_conflicts_preserves_preview_url() -> None:
    normalized = _normalize_indexed_conflicts(
        [
            {
                "scope": "indexed",
                "parent_kind": "catalog_model",
                "parent_name": "Soundwave - Transformers",
                "path": "instructions torso.jpg",
                "filename": "instructions torso.jpg",
                "label": "Catalog model 'Soundwave - Transformers' -> instructions torso.jpg",
                "preview_url": "/api/models/soundwave-transformers--94944ffc/files/instructions-torso-0386f557/download",
            }
        ]
    )

    assert len(normalized) == 1
    conflict = normalized[0]
    assert conflict.get("preview_url") == "/api/models/soundwave-transformers--94944ffc/files/instructions-torso-0386f557/download"


def _seed_initial_working_folder(client: TestClient, source_root: Path, *, filename: str, content: bytes, title: str) -> tuple[str, Path]:
    """Helper: publish a single file to working files and return (folder_slug, folder_path)."""
    seed_file = source_root / filename
    seed_file.write_bytes(content)
    enqueue = client.post(
        "/api/intake/uploads",
        json={
            "cleanup_policy": "keep",
            "source_entries": [{"type": "file", "path": str(seed_file)}],
        },
    )
    assert enqueue.status_code == 200, enqueue.text
    upload_id = enqueue.json()["upload_id"]
    publish = client.post(
        f"/api/intake/uploads/{upload_id}/publish-to-working",
        json={"title": title},
    )
    assert publish.status_code == 200, publish.text
    payload = publish.json()
    slug = str(payload.get("working_folder_slug") or "").strip()
    assert slug
    folder_path = Path(str((payload.get("created_groups") or [{}])[0].get("folder_path") or ""))
    assert folder_path.is_dir()
    return slug, folder_path


def test_publish_to_existing_working_folder_appends_files_and_merges_sidecar(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        slug, folder_path = _seed_initial_working_folder(
            client, source_root, filename="seed.3mf", content=b"seed-data", title="Append Target"
        )
        original_sidecar = json.loads((folder_path / ".modelmeta.json").read_text(encoding="utf-8"))
        original_imported_at = str(original_sidecar.get("imported_at") or "")
        assert original_imported_at
        original_display_title = str(original_sidecar.get("display_title") or "")
        original_primary = str(original_sidecar.get("primary_file") or "")
        assert len(original_sidecar.get("files") or []) == 1

        # Second publish: append a new file into the existing folder.
        append_file = source_root / "addition.stl"
        append_file.write_bytes(b"addition-data")
        enqueue2 = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(append_file)}],
            },
        )
        assert enqueue2.status_code == 200
        upload_id2 = enqueue2.json()["upload_id"]

        publish2 = client.post(
            f"/api/intake/uploads/{upload_id2}/publish-to-working",
            json={"title": "Should Be Ignored", "target_folder_slug": slug},
        )
        assert publish2.status_code == 200, publish2.text
        payload2 = publish2.json()
        assert payload2.get("working_folder_slug") == slug
        created_groups2 = payload2.get("created_groups") or []
        assert created_groups2 and created_groups2[0].get("folder_slug") == slug
        assert int(created_groups2[0].get("added_items") or 0) == 1

        # Sidecar should now have both files and preserved metadata.
        merged_sidecar = json.loads((folder_path / ".modelmeta.json").read_text(encoding="utf-8"))
        assert merged_sidecar.get("display_title") == original_display_title
        assert merged_sidecar.get("imported_at") == original_imported_at
        assert merged_sidecar.get("primary_file") == original_primary
        assert str(merged_sidecar.get("last_import_at") or "")
        files_entries = merged_sidecar.get("files") or []
        assert len(files_entries) == 2
        filenames = {Path(str(entry.get("path") or "")).name for entry in files_entries}
        assert "seed.3mf" in filenames
        assert "addition.stl" in filenames

        import_history = merged_sidecar.get("import_history") or []
        assert len(import_history) == 1
        assert int(import_history[0].get("added_file_count") or 0) == 1

        # Both files are physically present.
        present = {p.name for p in folder_path.rglob("*") if p.is_file()}
        assert "seed.3mf" in present
        assert "addition.stl" in present
    finally:
        client.__exit__(None, None, None)


def test_publish_by_destination_target_folder_slug_appends_into_existing_folder(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        slug, folder_path = _seed_initial_working_folder(
            client, source_root, filename="origin.3mf", content=b"origin", title="Existing Group"
        )

        new_file = source_root / "extra.3mf"
        new_file.write_bytes(b"extra")
        enqueue = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(new_file)}],
            },
        )
        assert enqueue.status_code == 200
        upload_id = enqueue.json()["upload_id"]

        publish = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={
                "cleanup_policy": "keep",
                "group_destinations": [
                    {
                        "destination": "working",
                        "title": "Anything",
                        "target_folder_slug": slug,
                    }
                ],
            },
        )
        assert publish.status_code == 200, publish.text
        body = publish.json()
        group_results = body.get("group_results") or []
        assert group_results and group_results[0].get("folder_slug") == slug
        assert group_results[0].get("match_mode") == "appended"

        merged_sidecar = json.loads((folder_path / ".modelmeta.json").read_text(encoding="utf-8"))
        assert len(merged_sidecar.get("files") or []) == 2
    finally:
        client.__exit__(None, None, None)


def test_working_files_folders_endpoint_lists_and_filters_folders(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        alpha_slug, _ = _seed_initial_working_folder(
            client, source_root, filename="alpha-bracket.3mf", content=b"alpha", title="Alpha Bracket"
        )
        beta_slug, _ = _seed_initial_working_folder(
            client, source_root, filename="beta-widget.3mf", content=b"beta", title="Beta Widget"
        )

        list_all = client.get("/api/working-files/folders")
        assert list_all.status_code == 200
        all_body = list_all.json()
        assert all_body.get("success") is True
        folders = all_body.get("folders") or []
        assert len(folders) >= 2
        slugs = {str(f.get("slug") or "") for f in folders}
        assert alpha_slug in slugs
        assert beta_slug in slugs
        # Each entry exposes the minimum picker fields.
        first = folders[0]
        for key in ("slug", "name", "display_title", "folder_path", "has_modelmeta"):
            assert key in first

        filtered = client.get("/api/working-files/folders", params={"q": "alpha"})
        assert filtered.status_code == 200
        filtered_slugs = {str(f.get("slug") or "") for f in filtered.json().get("folders") or []}
        assert alpha_slug in filtered_slugs
        assert beta_slug not in filtered_slugs
    finally:
        client.__exit__(None, None, None)


def test_publish_to_existing_working_folder_rejects_unknown_slug(tmp_path: Path) -> None:
    client, source_root = _create_client(tmp_path)
    try:
        source_file = source_root / "lonely.3mf"
        source_file.write_bytes(b"lonely")
        enqueue = client.post(
            "/api/intake/uploads",
            json={
                "cleanup_policy": "keep",
                "source_entries": [{"type": "file", "path": str(source_file)}],
            },
        )
        assert enqueue.status_code == 200
        upload_id = enqueue.json()["upload_id"]

        publish = client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-working",
            json={"title": "Whatever", "target_folder_slug": "nope-does-not-exist"},
        )
        assert publish.status_code == 500
        body = publish.json()
        assert body.get("success") is False
        assert "nope-does-not-exist" in str(body.get("message") or "")
    finally:
        client.__exit__(None, None, None)


def _create_idea(
    client: TestClient,
    *,
    local_model_id: str,
    model_name: str,
    notes: str | None = None,
    external_links: list | None = None,
    tags: list[str] | None = None,
    source_origin_url: str | None = None,
) -> None:
    body: dict = {
        "local_model_id": local_model_id,
        "model_name": model_name,
        "entity_type": "idea",
    }
    if notes is not None:
        body["notes"] = notes
    if external_links is not None:
        body["external_links"] = external_links
    if tags is not None:
        body["tags"] = tags
    if source_origin_url is not None:
        body["source_origin_url"] = source_origin_url
    response = client.post("/api/local/models", json=body)
    assert response.status_code == 200, response.text


def test_move_idea_to_working_files_creates_folder_and_deletes_idea(tmp_path: Path) -> None:
    client, _source_root = _create_client(tmp_path)
    working_root = tmp_path / "working"
    try:
        _create_idea(
            client,
            local_model_id="idea-move-1",
            model_name="Sketch For Bracket",
            notes="Some prototype notes.\nLine two.",
            external_links=[{"url": "https://example.com/ref", "label": "ref"}],
            tags=["bracket", "draft"],
        )

        response = client.post("/api/local/models/idea-move-1/move-to-working-files")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("success") is True
        slug = body.get("folder_slug")
        assert slug == "sketch-for-bracket"
        folder = working_root / slug
        assert folder.is_dir()

        meta_path = folder / ".modelmeta.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("display_title") == "Sketch For Bracket"
        assert meta.get("tags") == ["bracket", "draft"]
        assert meta.get("origin_url") == "https://example.com/ref"
        assert "thumbnail" not in meta

        readme = folder / "README.md"
        assert readme.is_file()
        readme_text = readme.read_text(encoding="utf-8")
        assert "Some prototype notes." in readme_text
        assert "Line two." in readme_text

        # Idea row is hard-deleted
        detail = client.get("/api/local/models/idea-move-1")
        assert detail.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_move_idea_rejects_non_idea_entity(tmp_path: Path) -> None:
    client, _source_root = _create_client(tmp_path)
    try:
        create = client.post(
            "/api/local/models",
            json={
                "local_model_id": "regular-model",
                "model_name": "Regular Model",
                "entity_type": "model",
            },
        )
        assert create.status_code == 200, create.text

        response = client.post("/api/local/models/regular-model/move-to-working-files")
        assert response.status_code == 409
        body = response.json()
        assert body.get("success") is False
        assert body.get("error") == "not_an_idea"
    finally:
        client.__exit__(None, None, None)


def test_move_idea_disambiguates_slug_on_collision(tmp_path: Path) -> None:
    client, _source_root = _create_client(tmp_path)
    working_root = tmp_path / "working"
    try:
        _create_idea(client, local_model_id="idea-a", model_name="Widget Concept")
        _create_idea(client, local_model_id="idea-b", model_name="Widget Concept")

        first = client.post("/api/local/models/idea-a/move-to-working-files")
        assert first.status_code == 200, first.text
        assert first.json().get("folder_slug") == "widget-concept"

        second = client.post("/api/local/models/idea-b/move-to-working-files")
        assert second.status_code == 200, second.text
        assert second.json().get("folder_slug") == "widget-concept-2"

        assert (working_root / "widget-concept").is_dir()
        assert (working_root / "widget-concept-2").is_dir()
    finally:
        client.__exit__(None, None, None)


def test_move_idea_returns_404_for_missing_model(tmp_path: Path) -> None:
    client, _source_root = _create_client(tmp_path)
    try:
        response = client.post("/api/local/models/does-not-exist/move-to-working-files")
        assert response.status_code == 404
        body = response.json()
        assert body.get("success") is False
        assert body.get("error") == "not_found"
    finally:
        client.__exit__(None, None, None)

