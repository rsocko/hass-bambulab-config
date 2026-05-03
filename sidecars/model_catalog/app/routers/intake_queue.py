"""
Intake queue upload management endpoints.

Handles:
- Queue state machine (queued → uploading → uploaded_unverified → verified → cleanup_* → failed)
- Queue lifecycle (create, list, delete, status transitions)
- Browser-based file upload staging
- Server filesystem browsing for source selection
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path, PurePosixPath
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..settings import Settings
from ..state import AppState

from .._helpers import (
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_timestamp_iso,
    _bulk_utc_now_iso,
    _coerce_bool,
    _coerce_int,
    _collect_intake_source_files_in_folder,
    _configured_intake_source_roots,
    _is_path_within_roots,
)

router = APIRouter(tags=["intake"])


# ==================== CONSTANTS ====================

BROWSER_INTAKE_UPLOAD_STORAGE_DIR = "intake_browser_uploads"

LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
LOCAL_IMPORT_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"}
LOCAL_IMPORT_DOCUMENT_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json", ".yaml", ".yml"}

# Valid state transitions for intake queue uploads
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"uploading", "failed"},
    "uploading": {"uploaded_unverified", "failed"},
    "uploaded_unverified": {"verified", "failed"},
    "verified": {"cleanup_pending", "failed"},
    "cleanup_pending": {"cleanup_done", "cleanup_failed", "failed"},
    "cleanup_done": {"failed"},
    "cleanup_failed": {"cleanup_pending", "failed"},
    "failed": set(),
}


# ==================== HELPER FUNCTIONS ====================

def _browser_intake_upload_storage_root(settings: Settings) -> Path:
    return (settings.db_path.parent / BROWSER_INTAKE_UPLOAD_STORAGE_DIR).resolve()


def _sanitize_browser_upload_relative_path(relative_path: str | None, fallback_name: str) -> Path:
    raw_value = str(relative_path or "").strip().replace("\\", "/")
    fallback = Path(Path(fallback_name or "upload.bin").name or "upload.bin")
    if not raw_value:
        return fallback

    candidate = PurePosixPath(raw_value)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        return fallback

    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts:
        return fallback

    sanitized = Path(*parts)
    if sanitized.name in {"", ".", ".."}:
        return fallback
    return sanitized


def _browser_upload_stage_directories(settings: Settings, source_entries: list[dict[str, Any]]) -> list[Path]:
    storage_root = _browser_intake_upload_storage_root(settings)
    directories: set[Path] = set()
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("source_type") or "").strip().lower() != "browser_upload":
            continue

        upload_id = str(entry.get("upload_id") or "").strip()
        if upload_id:
            directories.add((storage_root / upload_id).resolve())
            continue

        entry_path_raw = str(entry.get("path") or "").strip()
        if not entry_path_raw:
            continue
        entry_path = Path(entry_path_raw).expanduser().resolve()
        if not entry_path.is_relative_to(storage_root):
            continue
        relative_path = entry_path.relative_to(storage_root)
        if relative_path.parts:
            directories.add((storage_root / relative_path.parts[0]).resolve())

    return sorted(directories)


def _normalize_intake_cleanup_policy(value: object | None) -> str:
    cleanup_policy = str(value or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        return "keep"
    return cleanup_policy


def _normalize_browser_intake_cleanup_policy(value: object | None) -> str:
    _ = value
    # Browser uploads are always ephemeral staging files that should be
    # removed after successful materialization into local/working storage.
    return "delete_on_verified"


class IntakeSourceValidationError(ValueError):
    def __init__(self, *, error: str, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.detail = detail


def _validate_intake_source_entries(source_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source_entries, list) or len(source_entries) == 0:
        raise IntakeSourceValidationError(
            error="invalid_payload",
            message="source_entries must be a non-empty list of {type, path, recurse?, max_depth?}",
        )

    validated_entries: list[dict[str, Any]] = []
    for entry in source_entries:
        if not isinstance(entry, dict):
            raise IntakeSourceValidationError(
                error="invalid_source_entry",
                message="Each source_entry must be an object",
            )

        entry_type = str(entry.get("type") or "").strip().lower()
        entry_path = str(entry.get("path") or "").strip()
        if entry_type not in {"file", "folder"}:
            raise IntakeSourceValidationError(
                error="invalid_source_type",
                message=f"source_entry.type must be 'file' or 'folder', got '{entry_type}'",
            )
        if not entry_path:
            raise IntakeSourceValidationError(
                error="invalid_source_path",
                message="source_entry.path is required",
            )

        resolved_path = Path(entry_path).expanduser().resolve()
        if not resolved_path.exists():
            raise IntakeSourceValidationError(
                error="source_not_found",
                message=f"source_entry.path does not exist: {entry_path}",
            )
        if entry_type == "file" and not resolved_path.is_file():
            raise IntakeSourceValidationError(
                error="source_is_not_file",
                message=f"source_entry marked as 'file' but path is not a file: {entry_path}",
            )
        if entry_type == "folder" and not resolved_path.is_dir():
            raise IntakeSourceValidationError(
                error="source_is_not_folder",
                message=f"source_entry marked as 'folder' but path is not a directory: {entry_path}",
            )
        if entry_type == "file" and resolved_path.suffix.lower() not in (SUPPORTED_WORKING_FILE_EXTENSIONS | LOCAL_IMPORT_IMAGE_EXTENSIONS):
            raise IntakeSourceValidationError(
                error="unsupported_file_type",
                message=f"Unsupported file type for intake: {resolved_path.name}",
            )

        try:
            stat_result = resolved_path.stat()
            
            browser_mtime_ms = entry.get("file_last_modified_ms")
            if browser_mtime_ms is not None and isinstance(browser_mtime_ms, (int, float)):
                entry_source_metadata = {
                    "source_mtime": _bulk_timestamp_iso(float(browser_mtime_ms) / 1000.0),
                    "source_ctime": _bulk_timestamp_iso(stat_result.st_ctime),
                }
                birthtime = getattr(stat_result, "st_birthtime", None)
                if birthtime is not None:
                    entry_source_metadata["source_birthtime"] = _bulk_timestamp_iso(birthtime)
            else:
                from .._helpers import _bulk_path_source_metadata
                entry_source_metadata = _bulk_path_source_metadata(resolved_path, stat_result)
        except (OSError, PermissionError) as error:
            raise IntakeSourceValidationError(
                error="source_stat_error",
                message=f"source_entry.path metadata could not be read: {entry_path}",
                detail=str(error),
            ) from error

        validated_entry = {
            "type": entry_type,
            "path": str(resolved_path),
            "recurse": _coerce_bool(entry.get("recurse", True)) if entry_type == "folder" else False,
            "max_depth": _coerce_int(entry.get("max_depth")) if entry_type == "folder" else None,
            "source_mtime": entry_source_metadata["source_mtime"],
            "source_ctime": entry_source_metadata["source_ctime"],
            "source_birthtime": entry_source_metadata.get("source_birthtime"),
            "source_size_bytes": int(stat_result.st_size) if entry_type == "file" else None,
        }
        for extra_key in ("source_type", "original_filename", "relative_path", "upload_id", "group_title_source", "group_title"):
            extra_value = entry.get(extra_key)
            if extra_value not in {None, ""}:
                validated_entry[extra_key] = extra_value
        validated_entries.append(validated_entry)

    return validated_entries


def _create_intake_queue_upload_record(
    *,
    db_path: Path,
    validated_entries: list[dict[str, Any]],
    cleanup_policy: str,
) -> tuple[str, str]:
    upload_id = str(uuid.uuid4())
    now_iso = _bulk_utc_now_iso()

    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                "queued",
                json.dumps(validated_entries),
                "unverified",
                cleanup_policy,
                now_iso,
                now_iso,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return upload_id, now_iso


def _transition_queue_status(
    db_path: Path,
    upload_id: str,
    new_status: str,
    event_type: str = "status_change",
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Transition an intake queue upload to a new status with audit logging.
    
    Returns (success: bool, error_message: str | None)
    """
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id, status, upload_id FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not row:
            return False, f"Upload not found: {upload_id}"
        
        current_status = row["status"]
        
        if new_status not in VALID_STATUS_TRANSITIONS.get(current_status, set()):
            return False, f"Invalid transition from {current_status} to {new_status}"
        
        now_iso = _bulk_utc_now_iso()
        timestamp_field = None
        if new_status == "uploading":
            timestamp_field = "uploaded_at"
        elif new_status == "verified":
            timestamp_field = "verified_at"
        elif new_status in ("cleanup_done", "cleanup_failed"):
            timestamp_field = "cleanup_done_at"
        
        update_clause = "status = ?, updated_at = ?"
        params: list[Any] = [new_status, now_iso]
        
        if timestamp_field:
            update_clause += f", {timestamp_field} = ?"
            params.append(now_iso)
        
        if error_message and new_status == "failed":
            error_payload = {"error": error_message}
            update_clause += ", error_json = ?"
            params.append(json.dumps(error_payload))
        
        params.append(upload_id)
        
        connection.execute(
            f"UPDATE intake_queue_uploads SET {update_clause} WHERE upload_id = ?",
            params,
        )
        
        event_payload = {
            "upload_id": upload_id,
            "from_status": current_status,
            "to_status": new_status,
            "transition_at": now_iso,
        }
        if error_message:
            event_payload["error"] = error_message
        if metadata:
            event_payload["metadata"] = metadata
        
        connection.execute(
            """
            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                "intake_queue_upload",
                upload_id,
                json.dumps(event_payload),
                now_iso,
            ),
        )
        
        connection.commit()
        return True, None
        
    except Exception as e:
        return False, f"State transition error: {str(e)}"
    finally:
        connection.close()


def _expand_source_entries_to_files(source_entries: list[dict[str, Any]]) -> list[Path]:
    files: list[Path] = []
    for entry in source_entries:
        entry_type = str(entry.get("type") or "").strip().lower()
        resolved = Path(str(entry.get("path") or "").strip()).expanduser().resolve()
        if entry_type == "file":
            if resolved.exists() and resolved.is_file():
                files.append(resolved)
            continue
        if entry_type != "folder" or not resolved.exists() or not resolved.is_dir():
            continue
        recurse = _coerce_bool(entry.get("recurse", True))
        max_depth = _coerce_int(entry.get("max_depth"))
        files.extend(_collect_intake_source_files_in_folder(resolved, recurse=recurse, max_depth=max_depth))
    return files


def _record_queue_event(*, request: Request, upload_id: str, event_type: str, payload: dict[str, Any]) -> None:
    connection = connect(request.app.state.model_catalog.settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                "intake_queue_upload",
                upload_id,
                json.dumps(payload),
                _bulk_utc_now_iso(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


# ==================== ENDPOINTS ====================

@router.post("/api/intake/uploads")
def intake_queue_post_upload(request: Request, payload: dict[str, Any]) -> Any:
    """
    Add a new upload to the intake queue.
    
    Source contract supports:
    - explicit file uploads: { type: "file", path: "/path/to/file.3mf" }
    - folder entries: { type: "folder", path: "/path/to/folder", recurse: true, max_depth: 3 }
    - mixed batches: array of above mixed together
    
    Returns upload_id for tracking, plus queue status lifecycle.
    """
    state: AppState = request.app.state.model_catalog
    
    source_entries = payload.get("source_entries") or []
    cleanup_policy = _normalize_intake_cleanup_policy(payload.get("cleanup_policy"))

    try:
        validated_entries = _validate_intake_source_entries(source_entries)
    except IntakeSourceValidationError as error:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": error.error,
                "message": error.message,
                **({"detail": error.detail} if error.detail else {}),
            },
        )

    upload_id, now_iso = _create_intake_queue_upload_record(
        db_path=state.settings.db_path,
        validated_entries=validated_entries,
        cleanup_policy=cleanup_policy,
    )

    return {
        "success": True,
        "upload_id": upload_id,
        "status": "queued",
        "verification_status": "unverified",
        "cleanup_policy": cleanup_policy,
        "source_entry_count": len(validated_entries),
        "created_at": now_iso,
    }


@router.post("/api/intake/uploads/browser")
async def intake_queue_post_browser_upload(request: Request) -> Any:
    state: AppState = request.app.state.model_catalog
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Browser upload payload must be valid JSON.",
            },
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "Browser upload payload must be a JSON object.",
            },
        )

    browser_files = payload.get("browser_files") or []
    cleanup_policy = _normalize_browser_intake_cleanup_policy(payload.get("cleanup_policy"))
    warnings: list[dict[str, Any]] = []
    source_entries: list[dict[str, Any]] = []

    parsed_selections = payload.get("server_selections") or []
    if parsed_selections and not isinstance(parsed_selections, list):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_server_selections",
                "message": "server_selections must be a list.",
            },
        )
    source_entries.extend([entry for entry in parsed_selections if isinstance(entry, dict)])

    if not browser_files and not source_entries:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_browser_files",
                "message": "Select at least one browser file or server selection before submitting.",
            },
        )

    staged_upload_id = str(uuid.uuid4())
    staged_root = _browser_intake_upload_storage_root(state.settings) / staged_upload_id
    staged_root.mkdir(parents=True, exist_ok=True)

    for index, upload in enumerate(browser_files):
        if not isinstance(upload, dict):
            warnings.append(
                {
                    "code": "invalid_browser_file",
                    "message": "Skipped malformed browser upload entry.",
                }
            )
            continue

        filename = Path(str(upload.get("filename") or "")).name or f"upload-{index + 1}.bin"
        relative_path = _sanitize_browser_upload_relative_path(
            str(upload.get("relative_path") or ""),
            filename,
        )
        if relative_path.suffix.lower() not in (SUPPORTED_WORKING_FILE_EXTENSIONS | LOCAL_IMPORT_IMAGE_EXTENSIONS):
            warnings.append(
                {
                    "code": "unsupported_file_type",
                    "message": f"Skipped unsupported browser upload: {filename}",
                    "filename": filename,
                }
            )
            continue

        destination = (staged_root / relative_path).resolve()
        if not destination.is_relative_to(staged_root.resolve()):
            warnings.append(
                {
                    "code": "invalid_relative_path",
                    "message": f"Skipped browser upload with unsafe path: {filename}",
                    "filename": filename,
                }
            )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded_content = str(upload.get("content_base64") or "").strip()
        if not encoded_content:
            warnings.append(
                {
                    "code": "empty_upload",
                    "message": f"Skipped empty browser upload: {filename}",
                    "filename": filename,
                }
            )
            continue

        try:
            file_bytes = base64.b64decode(encoded_content, validate=True)
        except (binascii.Error, ValueError):
            warnings.append(
                {
                    "code": "invalid_base64",
                    "message": f"Skipped browser upload with invalid base64 content: {filename}",
                    "filename": filename,
                }
            )
            continue
        if not file_bytes:
            warnings.append(
                {
                    "code": "empty_upload",
                    "message": f"Skipped empty browser upload: {filename}",
                    "filename": filename,
                }
            )
            continue

        destination.write_bytes(file_bytes)
        source_entries.append(
            {
                "type": "file",
                "path": str(destination),
                "source_type": "browser_upload",
                "original_filename": filename,
                "relative_path": str(relative_path).replace("\\", "/"),
                "upload_id": staged_upload_id,
                "file_last_modified_ms": upload.get("file_last_modified_ms"),
                "group_title_source": upload.get("group_title_source"),
                "group_title": upload.get("group_title"),
            }
        )

    if not source_entries:
        shutil.rmtree(staged_root, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_supported_sources",
                "message": "No supported intake sources remained after browser upload filtering.",
                "warnings": warnings,
            },
        )

    try:
        validated_entries = _validate_intake_source_entries(source_entries)
    except IntakeSourceValidationError as error:
        shutil.rmtree(staged_root, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": error.error,
                "message": error.message,
                **({"detail": error.detail} if error.detail else {}),
                "warnings": warnings,
            },
        )

    upload_id, now_iso = _create_intake_queue_upload_record(
        db_path=state.settings.db_path,
        validated_entries=validated_entries,
        cleanup_policy=cleanup_policy,
    )

    return {
        "success": True,
        "upload_id": upload_id,
        "status": "queued",
        "verification_status": "unverified",
        "cleanup_policy": cleanup_policy,
        "source_entry_count": len(validated_entries),
        "browser_file_count": len([entry for entry in validated_entries if entry.get("source_type") == "browser_upload"]),
        "warnings": warnings,
        "created_at": now_iso,
    }


@router.get("/api/intake/uploads")
def intake_queue_get_uploads(request: Request, status: str | None = None, limit: int | None = None) -> Any:
    """
    List intake queue uploads with optional status filter.
    
    Status values: queued, uploading, uploaded_unverified, verified, 
                   cleanup_pending, cleanup_done, cleanup_failed, failed
    """
    state: AppState = request.app.state.model_catalog
    
    limit_int = min(int(limit or 50), 1000)
    status_filter = str(status or "").strip().lower() if status else None
    valid_statuses = {
        "queued", "uploading", "uploaded_unverified", "verified",
        "cleanup_pending", "cleanup_done", "cleanup_failed", "failed"
    }
    if status_filter and status_filter not in valid_statuses:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_status",
                "message": f"status must be one of: {', '.join(sorted(valid_statuses))}",
            },
        )
    
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        if status_filter:
            rows = connection.execute(
                """
                SELECT id, upload_id, status, verification_status, cleanup_policy,
                       created_at, updated_at, uploaded_at, verified_at, cleanup_done_at,
                       (SELECT COUNT(*) FROM json_each(source_entries_json)) as source_entry_count,
                       (SELECT COUNT(*) FROM json_each(file_hashes_json)) as file_count
                FROM intake_queue_uploads
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status_filter, limit_int),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, upload_id, status, verification_status, cleanup_policy,
                       created_at, updated_at, uploaded_at, verified_at, cleanup_done_at,
                       (SELECT COUNT(*) FROM json_each(source_entries_json)) as source_entry_count,
                       (SELECT COUNT(*) FROM json_each(file_hashes_json)) as file_count
                FROM intake_queue_uploads
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit_int,),
            ).fetchall()
        
        uploads = []
        for row in rows:
            uploads.append({
                "id": row["id"],
                "upload_id": row["upload_id"],
                "status": row["status"],
                "verification_status": row["verification_status"],
                "cleanup_policy": row["cleanup_policy"],
                "source_entry_count": row["source_entry_count"],
                "file_count": row["file_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "uploaded_at": row["uploaded_at"],
                "verified_at": row["verified_at"],
                "cleanup_done_at": row["cleanup_done_at"],
            })
    finally:
        connection.close()
    
    return {
        "success": True,
        "status_filter": status_filter,
        "upload_count": len(uploads),
        "uploads": uploads,
    }


@router.delete("/api/intake/uploads/{upload_id}")
def intake_queue_delete_upload(request: Request, upload_id: str) -> Any:
    """
    Delete an upload from the intake queue.
    
    Only allows deletion of queued uploads (not uploading/verified).
    """
    state: AppState = request.app.state.model_catalog
    
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id, status, source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not row:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "upload_not_found",
                    "message": f"No upload found with id: {upload_id}",
                },
            )
        
        current_status = row["status"]
        if current_status not in {"queued", "failed"}:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "cannot_delete_status",
                    "message": f"Cannot delete upload with status '{current_status}'. Only 'queued' and 'failed' uploads can be deleted.",
                },
            )
        
        connection.execute(
            "DELETE FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        )
        connection.commit()
    finally:
        connection.close()

    source_entries = json.loads(str(row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list):
        source_entries = []
    for stage_dir in _browser_upload_stage_directories(state.settings, source_entries):
        shutil.rmtree(stage_dir, ignore_errors=True)
    
    return {
        "success": True,
        "upload_id": upload_id,
        "deleted": True,
    }


@router.put("/api/intake/uploads/{upload_id}/status")
def intake_queue_update_status(request: Request, upload_id: str, payload: dict[str, Any]) -> Any:
    """
    Update the status of an intake queue upload.
    
    Transitions through the state machine with audit logging:
    - queued → uploading
    - uploading → uploaded_unverified
    - uploaded_unverified → verified
    - verified → cleanup_pending
    - cleanup_pending → cleanup_done or cleanup_failed
    - (any) → failed (on error)
    
    Payload: { "status": "new_status", "error": "optional error message" }
    """
    state: AppState = request.app.state.model_catalog
    
    new_status = str(payload.get("status") or "").strip().lower()
    error_message = str(payload.get("error") or "").strip() or None
    metadata = payload.get("metadata")
    
    if not new_status:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_status",
                "message": "Payload must include 'status' field",
            },
        )
    
    valid_statuses = {
        "queued", "uploading", "uploaded_unverified", "verified",
        "cleanup_pending", "cleanup_done", "cleanup_failed", "failed"
    }
    if new_status not in valid_statuses:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_status",
                "message": f"status must be one of: {', '.join(sorted(valid_statuses))}",
            },
        )
    
    success, error = _transition_queue_status(
        db_path=state.settings.db_path,
        upload_id=upload_id,
        new_status=new_status,
        event_type="manual_status_transition",
        error_message=error_message,
        metadata=metadata,
    )
    
    if not success:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": error,
            },
        )
    
    return {
        "success": True,
        "upload_id": upload_id,
        "new_status": new_status,
        "updated_at": _bulk_utc_now_iso(),
    }


@router.get("/api/intake/browse")
def intake_browse_folder(request: Request, path: str | None = None, max_depth: int | None = None) -> Any:
    """
    Browse server filesystem for file/folder selection with allowlist validation.
    
    Returns folder structure for UI-based source selection. Respects:
    - Allowlist paths from settings (BAMBULAB_INTAKE_ALLOWLIST env var)
    - max_depth to limit recursion
    - Returns file/folder metadata for UI tree rendering
    """
    state: AppState = request.app.state.model_catalog
    
    allowlist_raw = os.environ.get("BAMBULAB_INTAKE_ALLOWLIST", "/models,/storage")
    allowlist_paths = [
        Path(p.strip()).expanduser().resolve()
        for p in allowlist_raw.split(",")
        if p.strip()
    ]
    
    browse_path = None
    if not path or path.strip() == "/":
        return {
            "success": True,
            "path": "/",
            "is_root": True,
            "type": "virtual_root",
            "entries": [
                {
                    "path": str(allowed_root),
                    "name": allowed_root.name or str(allowed_root),
                    "type": "folder",
                    "accessible": allowed_root.exists(),
                    "has_children": allowed_root.is_dir() if allowed_root.exists() else False,
                }
                for allowed_root in allowlist_paths
            ],
        }
    else:
        browse_path = Path(path).expanduser().resolve()
    
    if browse_path is not None:
        is_allowed = any(
            browse_path == allowed or browse_path.is_relative_to(allowed)
            for allowed in allowlist_paths
        )
        if not is_allowed:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "path_not_allowed",
                    "message": f"Path '{path}' is not in allowlist. Allowed: {', '.join(str(p) for p in allowlist_paths)}",
                },
            )
    
    if browse_path is None or not browse_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": f"Path does not exist: {path}",
            },
        )
    
    if not browse_path.is_dir():
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "not_a_directory",
                "message": f"Path is not a directory: {path}",
            },
        )
    
    max_depth_int = max(0, max_depth or 0)
    entries = []
    
    try:
        for item in sorted(browse_path.iterdir()):
            if item.name.startswith("."):
                continue
            
            try:
                is_dir = item.is_dir()
                size_bytes = None
                if not is_dir:
                    try:
                        size_bytes = item.stat().st_size
                    except (OSError, PermissionError):
                        pass
                
                entry = {
                    "path": str(item),
                    "name": item.name,
                    "type": "folder" if is_dir else "file",
                    "size_bytes": size_bytes,
                    "has_children": is_dir,
                }
                
                if not is_dir:
                    entry["extension"] = item.suffix.lower()
                
                entries.append(entry)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError) as e:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "permission_denied",
                "message": f"Cannot access directory: {str(e)}",
            },
        )
    
    parent_path = None
    if browse_path != browse_path.parent:
        parent_candidate = browse_path.parent
        is_parent_allowed = any(
            parent_candidate == allowed or parent_candidate.is_relative_to(allowed)
            for allowed in allowlist_paths
        )
        if is_parent_allowed:
            parent_path = str(parent_candidate)
    
    return {
        "success": True,
        "path": str(browse_path),
        "name": browse_path.name or str(browse_path),
        "type": "folder",
        "parent_path": parent_path,
        "is_root": False,
        "entry_count": len(entries),
        "entries": entries,
        "max_depth": max_depth_int,
    }
