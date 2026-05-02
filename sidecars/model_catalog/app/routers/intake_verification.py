"""
Intake verification workflow endpoints.

Handles:
- Intake item submission and workflow (submit, validate, defer, reject, group)
- Item lifecycle in working groups
- Validation state tracking
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..state import AppState
from .._helpers import _bulk_utc_now_iso, _coerce_bool, _coerce_int, _collect_intake_source_files_in_folder
from ..services import get_all_indexed_file_hashes
from ..services.shared_helpers import _serialize_working_group, _sha256_file, _slugify_title

from .intake_queue import (
    _expand_source_entries_to_files,
    _record_queue_event,
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    LOCAL_IMPORT_IMAGE_EXTENSIONS,
)

router = APIRouter(tags=["intake"])


# ==================== HELPER FUNCTIONS ====================

def _expand_intake_source_entries(*, source_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand source entries into individual files with validation."""
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for entry in source_entries:
        entry_type = str(entry.get("type") or "").strip().lower()
        source_path_raw = str(entry.get("path") or "").strip()
        if entry_type not in {"file", "folder"} or not source_path_raw:
            continue

        source_path = Path(source_path_raw).expanduser().resolve()
        if entry_type == "file":
            candidate_paths = [source_path]
        else:
            recurse = _coerce_bool(entry.get("recurse", True))
            max_depth = _coerce_int(entry.get("max_depth"))
            candidate_paths = _collect_intake_source_files_in_folder(source_path, recurse=recurse, max_depth=max_depth)

        for file_path in sorted(candidate_paths):
            normalized_path = str(file_path.resolve())
            if normalized_path in seen_paths:
                continue
            if file_path.suffix.lower() not in (SUPPORTED_WORKING_FILE_EXTENSIONS | LOCAL_IMPORT_IMAGE_EXTENSIONS):
                warnings.append(
                    {
                        "code": "unsupported_type",
                        "message": f"Unsupported extension: {file_path.suffix.lower() or '<none>'}",
                        "path": normalized_path,
                    }
                )
                continue
            if not file_path.exists() or not file_path.is_file():
                warnings.append(
                    {
                        "code": "missing_source",
                        "message": f"Source file not found: {file_path}",
                        "path": normalized_path,
                    }
                )
                continue

            try:
                stat_result = file_path.stat()
                file_hash = _sha256_file(file_path).lower()
            except (OSError, PermissionError) as exc:
                warnings.append(
                    {
                        "code": "source_unreadable",
                        "message": f"Could not read source file: {file_path} ({exc})",
                        "path": normalized_path,
                    }
                )
                continue

            expanded.append(
                {
                    "path": normalized_path,
                    "filename": file_path.name,
                    "entry_type": entry_type,
                    "source_entry": entry,
                    "file_hash": file_hash,
                    "size_bytes": int(stat_result.st_size),
                }
            )
            seen_paths.add(normalized_path)

    return expanded, warnings


def _read_existing_working_hashes(db_path: Path) -> set[str]:
    """Get all file hashes from existing working items."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hash FROM working_items WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''"
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    finally:
        connection.close()


def _intake_item_state_from_upload_status(status: str) -> str:
    """Map queue status to inbox state."""
    normalized = str(status or "").strip().lower()
    if normalized == "queued":
        return "submitted"
    if normalized in {"uploading", "uploaded_unverified"}:
        return "processing"
    if normalized == "verified":
        return "validated_ready"
    if normalized == "cleanup_pending":
        return "grouping"
    if normalized == "cleanup_done":
        return "grouped"
    if normalized == "cleanup_failed":
        return "validated_warning"
    if normalized == "failed":
        return "rejected"
    return "submitted"


def _existing_working_slugs(connection: Any) -> set[str]:
    """Get all existing working group slugs."""
    rows = connection.execute("SELECT slug FROM working_groups").fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _unique_slug(connection: Any, title: str) -> str:
    """Generate a unique slug for a new working group."""
    base = _slugify_title(title)
    existing = _existing_working_slugs(connection)
    if base not in existing:
        return base
    counter = 2
    while True:
        candidate = f"{base}-{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


# ==================== ENDPOINTS ====================

@router.post("/api/intake/submit")
def intake_submit(request: Request, payload: dict[str, Any]) -> Any:
    """
    Submit one or more intake items into inbox workflow.

    Payload:
      items: [{ source_path, source_type? }]
      auto_validate: bool (default true)
      cleanup_policy: keep|delete_on_verified|replace_with_stub
    """
    state: AppState = request.app.state.model_catalog
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "invalid_payload", "message": "items must be a non-empty list"},
        )

    auto_validate = _coerce_bool(payload.get("auto_validate", True))
    cleanup_policy = str(payload.get("cleanup_policy") or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        cleanup_policy = "keep"

    now_iso = _bulk_utc_now_iso()
    created_items: list[dict[str, Any]] = []
    pending_events: list[dict[str, Any]] = []
    existing_hashes = get_all_indexed_file_hashes(state.settings.db_path) if auto_validate else set()

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            source_path_text = str(raw_item.get("source_path") or raw_item.get("path") or "").strip()
            source_type = str(raw_item.get("source_type") or "filesystem_action").strip().lower() or "filesystem_action"
            if not source_path_text:
                continue

            source_path = Path(source_path_text).expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                created_items.append(
                    {
                        "item_id": None,
                        "source_path": source_path_text,
                        "state": "validated_warning",
                        "validation": {
                            "validation_state": "missing_source",
                            "warnings": [{"code": "missing_source", "message": "Source file not found"}],
                        },
                    }
                )
                continue

            suffix = source_path.suffix.lower()
            if suffix not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                created_items.append(
                    {
                        "item_id": None,
                        "source_path": str(source_path),
                        "state": "validated_warning",
                        "validation": {
                            "validation_state": "unsupported_type",
                            "warnings": [{"code": "unsupported_type", "message": f"Unsupported extension: {suffix}"}],
                        },
                    }
                )
                continue

            stat_result = source_path.stat()
            file_hash = None
            validation_state = "ready"
            warnings: list[dict[str, Any]] = []
            if auto_validate:
                try:
                    file_hash = _sha256_file(source_path).lower()
                except (OSError, PermissionError):
                    validation_state = "missing_source"
                    warnings.append({"code": "hash_failed", "message": "Could not compute file hash"})
                if file_hash and file_hash in existing_hashes:
                    validation_state = "duplicate_candidate"
                    warnings.append({"code": "working_group_hash_match", "message": "Hash matched an existing working item"})

            upload_id = str(uuid.uuid4())
            source_entries_json = json.dumps(
                [
                    {
                        "type": "file",
                        "path": str(source_path),
                        "source_type": source_type,
                        "source_size_bytes": int(stat_result.st_size),
                    }
                ]
            )
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, source_entries_json, file_hashes_json,
                    verification_status, cleanup_policy, created_at, updated_at,
                    inbox_state, decision_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    "queued",
                    source_entries_json,
                    json.dumps([file_hash] if file_hash else []),
                    "pass" if validation_state == "ready" else "unverified",
                    cleanup_policy,
                    now_iso,
                    now_iso,
                    _intake_item_state_from_upload_status("verified" if validation_state == "ready" else "cleanup_failed"),
                    None,
                ),
            )

            if auto_validate:
                pending_events.append(
                    {
                        "upload_id": upload_id,
                        "event_type": "intake_item_validated",
                        "payload": {
                            "upload_id": upload_id,
                            "validation_state": validation_state,
                            "warnings": warnings,
                            "source_path": str(source_path),
                        },
                    }
                )

            created_items.append(
                {
                    "item_id": upload_id,
                    "source_path": str(source_path),
                    "state": "validated_ready" if validation_state == "ready" else "validated_warning",
                    "validation": {
                        "validation_state": validation_state,
                        "warnings": warnings,
                    },
                }
            )

        connection.commit()
    finally:
        connection.close()

    for event in pending_events:
        _record_queue_event(
            request=request,
            upload_id=str(event["upload_id"]),
            event_type=str(event["event_type"]),
            payload=dict(event["payload"]),
        )

    return {
        "success": True,
        "created_count": len([item for item in created_items if item.get("item_id")]),
        "items": created_items,
    }


@router.get("/api/intake/items")
def list_intake_items(request: Request, limit: int | None = None, offset: int | None = None, state_filter: str | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    limit_value = max(1, min(int(limit or 100), 1000))
    offset_value = max(0, int(offset or 0))

    where_clauses = ["1=1"]
    params: list[Any] = []
    if state_filter and state_filter.strip():
        where_clauses.append("inbox_state = ?")
        params.append(state_filter.strip())
    where_sql = " AND ".join(where_clauses)

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS cnt FROM intake_queue_uploads WHERE {where_sql}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                   source_entries_json, file_hashes_json, error_json,
                   created_at, updated_at, uploaded_at, verified_at, cleanup_done_at, decision_note
            FROM intake_queue_uploads
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit_value, offset_value],
        ).fetchall()
    finally:
        connection.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        source_entries = json.loads(str(row["source_entries_json"] or "[]"))
        source_entry = source_entries[0] if isinstance(source_entries, list) and source_entries else {}
        normalized_state = str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or ""))
        items.append(
            {
                "item_id": row["upload_id"],
                "status": row["status"],
                "state": normalized_state,
                "verification_status": row["verification_status"],
                "cleanup_policy": row["cleanup_policy"],
                "source_entry": source_entry,
                "file_hashes": json.loads(str(row["file_hashes_json"] or "[]")),
                "error": json.loads(str(row["error_json"] or "null")),
                "decision_note": row["decision_note"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "uploaded_at": row["uploaded_at"],
                "verified_at": row["verified_at"],
                "cleanup_done_at": row["cleanup_done_at"],
            }
        )

    return {
        "success": True,
        "pagination": {
            "limit": limit_value,
            "offset": offset_value,
            "total": int(total_row["cnt"] if total_row else 0),
        },
        "items": items,
    }


@router.get("/api/intake/items/{item_id}")
def get_intake_item(request: Request, item_id: str) -> Any:
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                   source_entries_json, file_hashes_json, manyfold_file_ids_json, error_json,
                   created_at, updated_at, uploaded_at, verified_at, cleanup_done_at, decision_note
            FROM intake_queue_uploads
            WHERE upload_id = ?
            """,
            (item_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})

    source_entries = json.loads(str(row["source_entries_json"] or "[]"))
    return {
        "success": True,
        "item": {
            "item_id": row["upload_id"],
            "status": row["status"],
            "state": str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or "")),
            "verification_status": row["verification_status"],
            "cleanup_policy": row["cleanup_policy"],
            "source_entries": source_entries,
            "file_hashes": json.loads(str(row["file_hashes_json"] or "[]")),
            "manyfold_file_ids": json.loads(str(row["manyfold_file_ids_json"] or "[]")),
            "error": json.loads(str(row["error_json"] or "null")),
            "decision_note": row["decision_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "uploaded_at": row["uploaded_at"],
            "verified_at": row["verified_at"],
            "cleanup_done_at": row["cleanup_done_at"],
        },
    }


@router.post("/api/intake/items/{item_id}/validate")
def validate_intake_item(request: Request, item_id: str) -> Any:
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT upload_id, source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
            (item_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})

    source_entries = json.loads(str(row["source_entries_json"] or "[]"))
    warnings: list[dict[str, Any]] = []
    validation_state = "ready"

    expanded_files, expansion_warnings = _expand_intake_source_entries(
        source_entries=[entry for entry in source_entries if isinstance(entry, dict)]
    )
    warnings.extend(expansion_warnings)
    warning_codes = {str(warning.get("code") or "").strip().lower() for warning in expansion_warnings if isinstance(warning, dict)}
    if "missing_source" in warning_codes or "source_unreadable" in warning_codes:
        validation_state = "missing_source"
    elif "unsupported_type" in warning_codes and not expanded_files:
        validation_state = "unsupported_type"
    elif expansion_warnings:
        validation_state = "source_warning"

    existing_hashes = _read_existing_working_hashes(state.settings.db_path)
    file_hashes: list[str] = []
    for file_item in expanded_files:
        file_hash = str(file_item.get("file_hash") or "").strip().lower()
        if not file_hash:
            continue
        file_hashes.append(file_hash)
        if file_hash in existing_hashes:
            validation_state = "duplicate_candidate"
            warnings.append(
                {
                    "code": "working_group_hash_match",
                    "message": "Hash matched an existing working item.",
                    "sha256": file_hash,
                }
            )

    if not expanded_files and validation_state == "ready":
        validation_state = "needs_manual_grouping"
        warnings.append({"code": "needs_manual_grouping", "message": "No files resolved from source entries."})

    next_inbox_state = "validated_ready" if validation_state == "ready" else "validated_warning"
    connection = connect(state.settings.db_path)
    try:
        connection.execute(
            """
            UPDATE intake_queue_uploads
            SET file_hashes_json = ?,
                verification_status = ?,
                inbox_state = ?,
                decision_note = ?,
                updated_at = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps(file_hashes),
                "pass" if validation_state == "ready" else "unverified",
                next_inbox_state,
                json.dumps(warnings) if warnings else None,
                _bulk_utc_now_iso(),
                item_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    _record_queue_event(
        request=request,
        upload_id=item_id,
        event_type="intake_item_validated",
        payload={
            "validation_state": validation_state,
            "warnings": warnings,
            "file_hash_count": len(file_hashes),
        },
    )

    return {
        "success": True,
        "item_id": item_id,
        "state": next_inbox_state,
        "validation": {
            "validation_state": validation_state,
            "warnings": warnings,
            "file_hash_count": len(file_hashes),
        },
    }


@router.post("/api/intake/items/{item_id}/defer")
def defer_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    payload = payload or {}
    note = str(payload.get("note") or "Deferred by operator").strip() or "Deferred by operator"
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    try:
        row = connection.execute("SELECT upload_id FROM intake_queue_uploads WHERE upload_id = ?", (item_id,)).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})
        connection.execute(
            "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
            ("deferred", note, _bulk_utc_now_iso(), item_id),
        )
        connection.commit()
    finally:
        connection.close()
    _record_queue_event(request=request, upload_id=item_id, event_type="intake_item_deferred", payload={"note": note})
    return {"success": True, "item_id": item_id, "state": "deferred", "note": note}


@router.post("/api/intake/items/{item_id}/reject")
def reject_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    payload = payload or {}
    note = str(payload.get("note") or "Rejected by operator").strip() or "Rejected by operator"
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    try:
        row = connection.execute("SELECT upload_id FROM intake_queue_uploads WHERE upload_id = ?", (item_id,)).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})
        connection.execute(
            "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
            ("rejected", note, _bulk_utc_now_iso(), item_id),
        )
        connection.commit()
    finally:
        connection.close()
    _record_queue_event(request=request, upload_id=item_id, event_type="intake_item_rejected", payload={"note": note})
    return {"success": True, "item_id": item_id, "state": "rejected", "note": note}


@router.post("/api/intake/items/{item_id}/group")
def group_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    payload = payload or {}
    action = str(payload.get("action") or "create_working_group").strip().lower()
    if action not in {"create_working_group", "attach_existing_working_group"}:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_action", "message": "action must be create_working_group or attach_existing_working_group"})

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    response_payload: dict[str, Any] | None = None
    event_payload: dict[str, Any] | None = None
    try:
        row = connection.execute(
            "SELECT upload_id, source_entries_json, inbox_state FROM intake_queue_uploads WHERE upload_id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})

        source_entries = json.loads(str(row["source_entries_json"] or "[]"))
        expanded_files, expansion_warnings = _expand_intake_source_entries(
            source_entries=[entry for entry in source_entries if isinstance(entry, dict)]
        )
        if not expanded_files:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_files",
                    "message": "Intake item has no resolved files to group",
                    "warnings": expansion_warnings,
                },
            )

        now_iso = _bulk_utc_now_iso()
        if action == "create_working_group":
            title = str(payload.get("title") or "").strip() or Path(expanded_files[0]["filename"]).stem or "Working Group"
            stage = str(payload.get("stage") or "draft").strip() or "draft"
            folder_hint = str(payload.get("folder_hint") or Path(str(expanded_files[0]["path"])).parent).strip() or None
            notes = str(payload.get("notes") or "Imported from intake workflow").strip() or None
            slug = _unique_slug(connection, title)
            connection.execute(
                """
                INSERT INTO working_groups (
                    slug, title, stage, notes, primary_file_path, folder_hint,
                    related_manyfold_model_id, created_at, updated_at,
                    discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    title,
                    stage,
                    notes,
                    str(expanded_files[0]["path"]),
                    folder_hint,
                    None,
                    now_iso,
                    now_iso,
                    folder_hint,
                    "intake",
                    now_iso,
                    json.dumps({"source": "intake", "upload_id": item_id}),
                ),
            )
            group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
        else:
            group_id = int(payload.get("working_group_id") or 0)
            if group_id <= 0:
                return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "working_group_id is required for attach_existing_working_group"})
            existing_group = connection.execute("SELECT id FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if existing_group is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "working_group_not_found", "message": f"Working group not found: {group_id}"})

        added_items = 0
        duplicate_items = 0
        for index, file_item in enumerate(expanded_files):
            file_path = str(file_item["path"])
            file_hash = str(file_item.get("file_hash") or "").strip().lower() or None
            existing_item = connection.execute(
                "SELECT id FROM working_items WHERE working_group_id = ? AND file_path = ?",
                (group_id, file_path),
            ).fetchone()
            if existing_item is not None:
                duplicate_items += 1
                continue
            if file_hash:
                existing_hash_match = connection.execute(
                    "SELECT id FROM working_items WHERE file_hash = ?",
                    (file_hash,),
                ).fetchone()
                if existing_hash_match is not None:
                    duplicate_items += 1
                    continue
            item_role = "primary" if index == 0 and action == "create_working_group" else "supporting"
            connection.execute(
                """
                INSERT INTO working_items (
                    working_group_id, file_path, item_role, created_at, updated_at,
                    file_hash, file_size, source_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    file_path,
                    item_role,
                    now_iso,
                    now_iso,
                    file_hash,
                    int(file_item.get("size_bytes") or 0) or None,
                    json.dumps({}),
                ),
            )
            added_items += 1

        connection.execute(
            "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
            ("grouped_new" if action == "create_working_group" else "grouped_existing", f"Grouped to working_group_id={group_id}", now_iso, item_id),
        )

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        connection.commit()
        
        serialized_group = _serialize_working_group(connection, group_row, state.settings)
        
        event_payload = {
            "upload_id": item_id,
            "action": action,
            "working_group_id": group_id,
            "added_items": added_items,
            "duplicate_items": duplicate_items,
            "warnings": expansion_warnings,
        }
        response_payload = {
            "success": True,
            "item_id": item_id,
            "state": "grouped_new" if action == "create_working_group" else "grouped_existing",
            "working_group_id": group_id,
            "added_items": added_items,
            "duplicate_items": duplicate_items,
            "warnings": expansion_warnings,
            "group": serialized_group,
        }
    finally:
        connection.close()

    if event_payload is not None:
        _record_queue_event(
            request=request,
            upload_id=item_id,
            event_type="intake_item_grouped",
            payload=event_payload,
        )
    return response_payload
