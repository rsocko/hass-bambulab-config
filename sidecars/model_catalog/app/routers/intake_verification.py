"""
Intake verification workflow endpoints.

Handles:
- Intake item submission and workflow (submit, validate, defer, reject, group)
- Item lifecycle in working groups
- Validation state tracking
- Action eligibility enforcement
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..state import AppState
from .._helpers import (
    _bulk_utc_now_iso,
    _coerce_bool,
    _coerce_int,
    _collect_intake_source_files_in_folder,
    _configured_working_files_roots,
    _normalize_path_compare_key,
)
from ..services import get_all_indexed_file_hashes
from ..services.shared_helpers import _serialize_working_group, _sha256_file, _slugify_title
from ..services.intake_eligibility_service import ActionEligibility

from .intake_queue import (
    _expand_source_entries_to_files,
    _record_queue_event,
    _browser_upload_stage_directories,
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    LOCAL_IMPORT_IMAGE_EXTENSIONS,
)

router = APIRouter(tags=["intake"])


# ==================== HELPER FUNCTIONS ====================

def _get_intake_item_row(db_path: Path, item_id: str) -> dict[str, Any] | None:
    """Fetch a single intake item row from database."""
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                   source_entries_json, file_hashes_json, error_json,
                   created_at, updated_at
            FROM intake_queue_uploads
            WHERE upload_id = ?
            """,
            (item_id,),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        connection.close()


def _build_intake_item_response(item_row: dict[str, Any]) -> dict[str, Any]:
    """Build a response payload for an intake item with eligibility information."""
    current_state = str(item_row.get("inbox_state") or "submitted").strip().lower()
    eligibility = ActionEligibility.build_allowed_actions_payload(current_state)

    return {
        "item_id": item_row["upload_id"],
        "status": item_row["status"],
        "state": current_state,
        "verification_status": item_row["verification_status"],
        "cleanup_policy": item_row["cleanup_policy"],
        "is_terminal": eligibility["is_terminal"],
        "is_active_queue": eligibility["is_active_queue"],
        "allowed_actions": eligibility["allowed_actions"],
        "state_display_name": eligibility["state_display_name"],
        "created_at": item_row["created_at"],
        "updated_at": item_row["updated_at"],
    }


def _check_action_eligibility(item_row: dict[str, Any], action: str, override: bool = False) -> tuple[bool, str | None]:
    """
    Check if an action is eligible for the current item state.
    
    Returns (is_eligible: bool, reason_code: str | None).
    """
    current_state = str(item_row.get("inbox_state") or "submitted").strip().lower()
    
    # Check basic eligibility
    is_eligible, reason = ActionEligibility.validate_action_eligibility(current_state, action)
    if not is_eligible:
        return False, reason
    
    # Check override requirement for warning state
    if action in {ActionEligibility.GROUP_NEW, ActionEligibility.GROUP_EXISTING}:
        is_valid_override, override_reason = ActionEligibility.validate_override_for_warning_state(
            current_state, action, override
        )
        if not is_valid_override:
            return False, override_reason
    
    return True, None

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
def _default_group_title(source_entries: list[dict[str, Any]], expanded_files: list[dict[str, Any]]) -> str:
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        hinted_title = str(entry.get("group_title") or "").strip()
        if hinted_title:
            return hinted_title

    first_entry = source_entries[0] if source_entries else {}
    first_entry_path = Path(str(first_entry.get("path") or "")) if isinstance(first_entry, dict) else Path()
    title_source = str(first_entry.get("group_title_source") or "").strip().lower().replace("_", "-") if isinstance(first_entry, dict) else ""

    if title_source == "folder" and str(first_entry.get("type") or "") == "folder":
        return first_entry_path.name or str(first_entry_path) or "Working Group"

    if title_source == "first-file":
        return Path(expanded_files[0]["filename"]).stem or "Working Group"

    if str(first_entry.get("type") or "") == "folder":
        return first_entry_path.name or str(first_entry_path) or "Working Group"

    return Path(expanded_files[0]["filename"]).stem or "Working Group"


def _move_files_to_working_group(
    *, 
    expanded_files: list[dict[str, Any]], 
    working_group_id: int,
    working_group_slug: str | None,
    settings: Any
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """
    Move files from their source locations to the working files folder.
    
    Returns:
        (moved_files, errors) where:
        - moved_files: List of (source_path, destination_path) tuples for successfully moved files
        - errors: List of error dicts with 'path' and 'message' keys
    """
    moved_files: list[tuple[str, str]] = []
    errors: list[dict[str, Any]] = []
    
    # Get working files root directory
    working_files_roots = _configured_working_files_roots(settings)
    if not working_files_roots:
        errors.append({
            "code": "no_working_files_root",
            "message": "No working files root configured in settings"
        })
        return moved_files, errors
    
    working_files_root = working_files_roots[0]
    folder_name = str(working_group_slug or "").strip() or str(working_group_id)
    group_folder = working_files_root / folder_name
    
    # Create group folder if it doesn't exist
    try:
        group_folder.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as exc:
        errors.append({
            "code": "mkdir_failed",
            "message": f"Failed to create working group folder: {exc}"
        })
        return moved_files, errors
    
    # Move each file to the group folder
    reserved_paths: set[str] = set()
    for file_item in expanded_files:
        source_path_str = str(file_item.get("path") or "").strip()
        if not source_path_str:
            continue
        
        source_path = Path(source_path_str).resolve()
        
        # Verify source exists
        if not source_path.exists() or not source_path.is_file():
            errors.append({
                "code": "source_missing",
                "path": source_path_str,
                "message": f"Source file not found: {source_path_str}"
            })
            continue
        
        # Generate unique destination path (avoid conflicts)
        dest_name = source_path.name
        dest_path = group_folder / dest_name
        dest_key = _normalize_path_compare_key(str(dest_path.resolve()))
        
        # If file already exists, append a counter
        if dest_path.exists() or dest_key in reserved_paths:
            stem = source_path.stem
            suffix = source_path.suffix
            counter = 2
            while True:
                next_dest_name = f"{stem}-{counter}{suffix}"
                next_dest_path = group_folder / next_dest_name
                next_key = _normalize_path_compare_key(str(next_dest_path.resolve()))
                if not next_dest_path.exists() and next_key not in reserved_paths:
                    dest_path = next_dest_path
                    break
                counter += 1
        
        reserved_paths.add(_normalize_path_compare_key(str(dest_path.resolve())))
        
        # Move the file
        try:
            shutil.move(str(source_path), str(dest_path))
            moved_files.append((source_path_str, str(dest_path.resolve())))
        except (OSError, PermissionError, shutil.Error) as exc:
            errors.append({
                "code": "move_failed",
                "path": source_path_str,
                "message": f"Failed to move file: {exc}"
            })
    
    return moved_files, errors


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


@router.post("/api/intake/preview-batch")
def preview_intake_batch(request: Request, payload: dict[str, Any] | None = None) -> Any:
    """
    Preview what will happen if source entries are expanded and grouped.
    
    Shows:
    - Total files that will be imported
    - Warnings about missing sources, duplicates, etc.
    - Impact of grouping strategy
    - Whether files are already in working groups (duplicates)
    """
    payload = payload or {}
    source_entries = payload.get("source_entries") or []
    if not isinstance(source_entries, list):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "source_entries must be a list",
            },
        )

    state: AppState = request.app.state.model_catalog
    
    # Expand files from source entries (same logic as validate)
    expanded_files, expansion_warnings = _expand_intake_source_entries(
        source_entries=[entry for entry in source_entries if isinstance(entry, dict)]
    )

    # Check for duplicates in existing working groups
    existing_hashes = _read_existing_working_hashes(state.settings.db_path)
    duplicate_hashes: list[dict[str, Any]] = []
    unique_hashes: list[str] = []
    
    for file_item in expanded_files:
        file_hash = str(file_item.get("file_hash") or "").strip().lower()
        if not file_hash:
            continue
        if file_hash in existing_hashes:
            duplicate_hashes.append({
                "filename": str(file_item.get("filename", "")).strip(),
                "file_path": str(file_item.get("path", "")).strip(),
                "file_hash": file_hash,
                "status": "already_in_working_group",
            })
        else:
            unique_hashes.append(file_hash)

    # Analyze grouping impact
    source_entry_count = len([e for e in source_entries if isinstance(e, dict)])
    folder_entries = sum(1 for e in source_entries if isinstance(e, dict) and e.get("type") == "folder")
    file_entries = source_entry_count - folder_entries

    return {
        "success": True,
        "contract": "intake-preview-batch.v1alpha1",
        "source_entries": {
            "total": source_entry_count,
            "files": file_entries,
            "folders": folder_entries,
        },
        "files": {
            "expanded_total": len(expanded_files),
            "unique_hashes": len(unique_hashes),
            "duplicate_hashes": len(duplicate_hashes),
            "duplicate_details": duplicate_hashes,
        },
        "warnings": expansion_warnings,
        "grouping_impact": {
            "recommended_strategy": "group_by_root" if folder_entries > 0 else "single_group",
            "strategy_explanation": (
                "Group by root: Creates one working group per top-level source path. "
                "Single group: All files in one working group."
            ),
            "file_count_by_strategy": {
                "single_group": len(expanded_files),
                "group_by_root": source_entry_count,
                "group_by_folder": len(set(str(Path(f["path"]).parent) for f in expanded_files)),
            },
        },
        "can_publish_directly": (
            len(expanded_files) > 0 and 
            len(duplicate_hashes) == 0 and 
            len([w for w in expansion_warnings if w.get("code") in {"missing_source", "source_unreadable"}]) == 0
        ),
        "next_actions": [
            "queue" if not expanded_files else "preview_or_queue",
            "execute_now" if len(expanded_files) > 0 and len(duplicate_hashes) == 0 else None,
        ],
    }


@router.get("/api/intake/items/{item_id}")
def get_intake_item(request: Request, item_id: str) -> Any:
    """Get a single intake item with full details and action eligibility."""
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
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    current_state = str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or ""))
    eligibility = ActionEligibility.build_allowed_actions_payload(current_state)
    source_entries = json.loads(str(row["source_entries_json"] or "[]"))

    return {
        "success": True,
        "item": {
            "item_id": row["upload_id"],
            "status": row["status"],
            "state": current_state,
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
            # Action eligibility
            "is_terminal": eligibility["is_terminal"],
            "is_active_queue": eligibility["is_active_queue"],
            "allowed_actions": eligibility["allowed_actions"],
            "state_display_name": eligibility["state_display_name"],
        },
    }


@router.post("/api/intake/items/{item_id}/validate")
def validate_intake_item(request: Request, item_id: str) -> Any:
    """
    Validate an intake item (run quality checks and resolve files).
    
    Allowed states: submitted, validated_ready, validated_warning, deferred.
    Returns HTTP 409 if state is terminal.
    """
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
            (item_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    row = dict(row)

    # Check action eligibility
    is_eligible, reason_code = _check_action_eligibility(row, ActionEligibility.VALIDATE)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot validate item in state '{row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": row.get("inbox_state"),
                **_build_intake_item_response(row),
            },
        )

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

    # Fetch updated row to build response with eligibility
    updated_row = _get_intake_item_row(state.settings.db_path, item_id)

    return {
        "success": True,
        "item_id": item_id,
        "state": next_inbox_state,
        "validation": {
            "validation_state": validation_state,
            "warnings": warnings,
            "file_hash_count": len(file_hashes),
        },
        **_build_intake_item_response(updated_row),
    }


@router.post("/api/intake/items/{item_id}/defer")
def defer_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Defer an intake item (park for later review).
    
    Allowed states: submitted, validated_ready, validated_warning.
    Terminal states: returns 409 Conflict.
    """
    payload = payload or {}
    note = str(payload.get("note") or "Deferred by operator").strip() or "Deferred by operator"
    state: AppState = request.app.state.model_catalog

    # Fetch current item
    item_row = _get_intake_item_row(state.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    # Check action eligibility
    is_eligible, reason_code = _check_action_eligibility(item_row, ActionEligibility.DEFER)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot defer item in state '{item_row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": item_row.get("inbox_state"),
                **_build_intake_item_response(item_row),
            },
        )

    # Update database
    connection = connect(state.settings.db_path)
    try:
        now_iso = _bulk_utc_now_iso()
        connection.execute(
            "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
            ("deferred", note, now_iso, item_id),
        )
        connection.commit()
    finally:
        connection.close()

    # Log event
    _record_queue_event(
        request=request,
        upload_id=item_id,
        event_type="intake_item_deferred",
        payload={"note": note},
    )

    # Refresh and return updated item
    updated_row = _get_intake_item_row(state.settings.db_path, item_id)
    return {
        "success": True,
        **_build_intake_item_response(updated_row),
        "decision_note": note,
    }


@router.post("/api/intake/items/{item_id}/reject")
def reject_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Reject an intake item (terminal state).
    
    Allowed states: submitted, validated_ready, validated_warning, deferred.
    Creates a terminal state; no further intake actions allowed.
    """
    payload = payload or {}
    note = str(payload.get("note") or "Rejected by operator").strip() or "Rejected by operator"
    state: AppState = request.app.state.model_catalog

    # Fetch current item
    item_row = _get_intake_item_row(state.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    # Check action eligibility
    is_eligible, reason_code = _check_action_eligibility(item_row, ActionEligibility.REJECT)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot reject item in state '{item_row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": item_row.get("inbox_state"),
                **_build_intake_item_response(item_row),
            },
        )

    # Update database (set to terminal state)
    connection = connect(state.settings.db_path)
    try:
        now_iso = _bulk_utc_now_iso()
        connection.execute(
            """
            UPDATE intake_queue_uploads 
            SET inbox_state = ?, decision_note = ?, updated_at = ?,
                terminal_action = 'rejected', terminal_at = ?
            WHERE upload_id = ?
            """,
            ("rejected", note, now_iso, now_iso, item_id),
        )
        connection.commit()
    finally:
        connection.close()

    # Log event
    _record_queue_event(
        request=request,
        upload_id=item_id,
        event_type="intake_item_rejected",
        payload={"note": note},
    )

    # Refresh and return updated item
    updated_row = _get_intake_item_row(state.settings.db_path, item_id)
    return {
        "success": True,
        **_build_intake_item_response(updated_row),
        "decision_note": note,
        "terminal": True,
    }


@router.post("/api/intake/items/{item_id}/group")
def group_intake_item(request: Request, item_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Group an intake item into a working group (terminal state).
    
    Allowed states: validated_ready (always), validated_warning (with override=true).
    Terminal states: returns 409 Conflict.
    """
    state: AppState = request.app.state.model_catalog
    payload = payload or {}
    action = str(payload.get("action") or "create_working_group").strip().lower()
    if action not in {"create_working_group", "attach_existing_working_group"}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_action",
                "message": "action must be create_working_group or attach_existing_working_group",
            },
        )

    # Fetch current item
    item_row = _get_intake_item_row(state.settings.db_path, item_id)
    if item_row is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"},
        )

    # Map action to eligibility constant
    eligibility_action = ActionEligibility.GROUP_NEW if action == "create_working_group" else ActionEligibility.GROUP_EXISTING
    
    # Check action eligibility (includes override requirement for warning states)
    override = _coerce_bool(payload.get("override", False))
    is_eligible, reason_code = _check_action_eligibility(item_row, eligibility_action, override=override)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot group item in state '{item_row.get('inbox_state')}': {reason_code}",
                "item_id": item_id,
                "current_state": item_row.get("inbox_state"),
                **_build_intake_item_response(item_row),
            },
        )

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    response_payload: dict[str, Any] | None = None
    event_payload: dict[str, Any] | None = None
    try:
        source_entries = json.loads(str(item_row.get("source_entries_json") or "[]"))
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
            title = str(payload.get("title") or "").strip() or _default_group_title(source_entries, expanded_files)
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
                    None,
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
            group_slug = slug
        else:
            group_id = int(payload.get("working_group_id") or 0)
            if group_id <= 0:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_payload",
                        "message": "working_group_id is required for attach_existing_working_group",
                    },
                )
            existing_group = connection.execute("SELECT id, slug FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if existing_group is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "error": "working_group_not_found",
                        "message": f"Working group not found: {group_id}",
                    },
                )
            group_slug = str(existing_group["slug"] or "").strip() or None

        # Move files to working files folder
        moved_files, move_errors = _move_files_to_working_group(
            expanded_files=expanded_files,
            working_group_id=group_id,
            working_group_slug=group_slug,
            settings=state.settings
        )
        
        # Build a map of source -> destination paths
        source_to_dest = dict(moved_files)
        
        # Record move errors in expansion_warnings
        for error in move_errors:
            expansion_warnings.append(error)

        added_items = 0
        duplicate_items = 0
        primary_file_path: str | None = None
        for index, file_item in enumerate(expanded_files):
            original_path = str(file_item["path"])
            # Use the moved path if available, otherwise use original path
            file_path = source_to_dest.get(original_path, original_path)
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
            if item_role == "primary" and primary_file_path is None:
                primary_file_path = file_path
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

        if action == "create_working_group" and primary_file_path:
            connection.execute(
                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                (primary_file_path, now_iso, group_id),
            )

        # Set to terminal state with metadata
        terminal_action = "grouped_new" if action == "create_working_group" else "grouped_existing"
        connection.execute(
            """
            UPDATE intake_queue_uploads 
            SET inbox_state = ?, decision_note = ?, updated_at = ?,
                terminal_action = ?, terminal_at = ?,
                terminal_result_id = ?
            WHERE upload_id = ?
            """,
            (
                terminal_action,
                f"Grouped to working_group_id={group_id}",
                now_iso,
                terminal_action,
                now_iso,
                str(group_id),
                item_id,
            ),
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
            "state": terminal_action,
            "terminal": True,
            "working_group_id": group_id,
            "added_items": added_items,
            "duplicate_items": duplicate_items,
            "warnings": expansion_warnings,
            "group": serialized_group,
        }

        # Browser uploads stage into GUID directories; remove staging after files
        # are successfully moved and grouped.
        for stage_dir in _browser_upload_stage_directories(state.settings, source_entries):
            shutil.rmtree(stage_dir, ignore_errors=True)
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
