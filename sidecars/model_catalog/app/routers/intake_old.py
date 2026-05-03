# sidecars/model_catalog/app/routers/intake.py
"""
Intake queue, upload, and publish workflow endpoints.

This router handles:
- Intake item submission and workflow (submit, validate, defer, reject, group)
- Intake queue upload management (create, list, delete, status transitions)
- Browser-based file upload staging
- Server filesystem browsing for source selection
- Publishing intake uploads to local authority catalog
- Manyfold upload adapter (transition)
- Post-upload source cleanup
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from sqlite3 import connect
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..settings import Settings

from ..state import AppState

from .._helpers import (
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_timestamp_iso,
    _bulk_utc_now_iso,
    _coerce_bool,
    _collect_intake_source_files_in_folder,
    _configured_intake_source_roots,
    _is_path_within_roots,
    _model_photo_storage_root,
    _windows_launch_enabled,
)

from ..local_models import (
    create_local_model,
    read_local_model,
    update_local_model,
    create_model_asset,
    list_model_assets,
)

from ..db import (
    derive_manyfold_model_key,
    read_model_field,
    read_model_fields,
    set_model_field,
)

from ..services import (
    get_all_indexed_file_hashes,
)
from ..services.model_detail_service import build_model_detail_response
from ..services.shared_helpers import (
    _resolve_local_asset_storage_path,
    _serialize_project_row,
    _serialize_working_group,
    _sha256_file,
    _slugify_title,
)

from ..manyfold import (
    ManyfoldClient,
    _model_ref_from_payload,
    canonicalize_model_url,
)
from . import models as models_router


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
    "cleanup_done": {"failed"},  # can fail even after cleanup
    "cleanup_failed": {"cleanup_pending", "failed"},  # can retry or fail
    "failed": set(),  # terminal state
}



# ==================== INTAKE-ONLY HELPER FUNCTIONS ====================


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

def _local_model_id_exists(*, db_path: Path, local_model_id: str) -> bool:
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT id FROM model_catalog_entries WHERE local_model_id = ? AND archived_at IS NULL",
            (local_model_id,),
        ).fetchone()
        return row is not None
    finally:
        connection.close()

def _generate_short_stable_id() -> str:
    """Generate a short stable suffix for model IDs (first 8 chars of UUID4)."""
    return str(uuid.uuid4()).replace("-", "")[:8]

def _ensure_unique_local_model_id(*, db_path: Path, preferred: str) -> str:
    """Generate a unique local model ID using format: <name-slug>--<shortid>.
    
    The local_model_id is immutable and used as the folder name for model assets.
    Format: {slug}--{shortid}, e.g., 'gridfinity-bin--a1b2c3d4'.
    
    Args:
        db_path: Path to the model catalog database
        preferred: Preferred model name/title to derive slug from
    
    Returns:
        Unique local model ID in format name-slug--shortid
    """
    slug = _slugify_title(preferred) or "model"
    short_id = _generate_short_stable_id()
    candidate = f"{slug}--{short_id}"
    
    # Safety check for collisions (extremely unlikely with UUID-based suffix)
    counter = 2
    while _local_model_id_exists(db_path=db_path, local_model_id=candidate):
        short_id = _generate_short_stable_id()
        candidate = f"{slug}--{short_id}"
        counter += 1
        if counter > 100:
            # Fallback: use counter suffix if somehow we hit many collisions
            candidate = f"{slug}--{short_id}-{counter}"
    
    return candidate

def _normalize_local_asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in LOCAL_IMPORT_IMAGE_EXTENSIONS:
        return "image"
    if suffix in LOCAL_IMPORT_MODEL_EXTENSIONS:
        return suffix.lstrip(".")
    if suffix in LOCAL_IMPORT_DOCUMENT_EXTENSIONS:
        return suffix.lstrip(".") or "document"
    return suffix.lstrip(".") or "file"

def _normalize_local_asset_role(*, asset_type: str, has_preview: bool, has_primary: bool, preview_selected: bool) -> str:
    if preview_selected:
        return "preview"
    if asset_type == "image":
        return "supporting" if has_preview else "preview"
    if asset_type in {"3mf", "stl", "obj", "step", "gcode"}:
        return "supporting" if has_primary else "primary"
    if asset_type in {"pdf", "md", "txt", "csv", "json", "yaml", "yml", "document"}:
        return "documentation"
    return "supporting"

def _unique_asset_id(*, filename: str, file_hash: str, existing_ids: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "asset"
    hash_suffix = re.sub(r"[^a-z0-9]+", "", str(file_hash or "").lower())[:8] or "file"
    candidate = f"{stem}-{hash_suffix}"
    counter = 2
    while candidate in existing_ids:
        candidate = f"{stem}-{hash_suffix}-{counter}"
        counter += 1
    existing_ids.add(candidate)
    return candidate

def _unique_destination_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

def _copy_local_import_source(*, settings: Settings, local_model_id: str, source_path: Path) -> str:
    catalog_root = _model_photo_storage_root(settings)
    asset_root = catalog_root / local_model_id
    asset_root.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination_path(asset_root, source_path.name)
    shutil.copy2(source_path, destination)
    try:
        relative_path = destination.relative_to(catalog_root.resolve())
        return str(relative_path).replace("\\", "/")
    except ValueError:
        return str(destination).replace("\\", "/")

def _expand_intake_source_entries(*, source_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
            candidate_paths = _collect_intake_source_files_in_folder(source_path, recurse=recurse)

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
                source_metadata = _bulk_path_source_metadata(file_path, stat_result)
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
                    "source_metadata": source_metadata,
                    "file_hash": file_hash,
                    "size_bytes": int(stat_result.st_size),
                }
            )
            seen_paths.add(normalized_path)

    return expanded, warnings

def _append_intake_publish_history(*, db_path: Path, model_ref: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    existing = read_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history")
    history = existing if isinstance(existing, list) else []
    history.append(entry)
    trimmed = history[-20:]
    set_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history", field_value=trimmed)
    return trimmed

class IntakeSourceValidationError(ValueError):
    def __init__(self, *, error: str, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.detail = detail

def _normalize_intake_cleanup_policy(value: object | None) -> str:
    cleanup_policy = str(value or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        return "keep"
    return cleanup_policy

def _validate_intake_source_entries(source_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source_entries, list) or len(source_entries) == 0:
        raise IntakeSourceValidationError(
            error="invalid_payload",
            message="source_entries must be a non-empty list of {type, path, recurse?}",
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
            
            # Check if caller provided pre-captured browser timestamp
            browser_mtime_ms = entry.get("file_last_modified_ms")
            if browser_mtime_ms is not None and isinstance(browser_mtime_ms, (int, float)):
                # Use browser-supplied timestamp (convert ms → seconds)
                entry_source_metadata = {
                    "source_mtime": _bulk_timestamp_iso(float(browser_mtime_ms) / 1000.0),
                    "source_ctime": _bulk_timestamp_iso(stat_result.st_ctime),
                }
                # Preserve birthtime on Windows/macOS if available
                birthtime = getattr(stat_result, "st_birthtime", None)
                if birthtime is not None:
                    entry_source_metadata["source_birthtime"] = _bulk_timestamp_iso(birthtime)
            else:
                # Fallback: use filesystem stat for all timestamps (Server mode, or missing browser timestamp)
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
            "source_mtime": entry_source_metadata["source_mtime"],
            "source_ctime": entry_source_metadata["source_ctime"],
            "source_birthtime": entry_source_metadata.get("source_birthtime"),
            "source_size_bytes": int(stat_result.st_size) if entry_type == "file" else None,
        }
        for extra_key in ("source_type", "original_filename", "relative_path", "upload_id"):
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

def _read_existing_working_hashes(db_path: Path) -> set[str]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hash FROM working_items WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''"
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    finally:
        connection.close()

def _lineage_payload_for_model(*, db_path: Path, model_ref: str) -> dict[str, Any]:
    fields = read_model_fields(db_path=db_path, model_ref=model_ref) or {}
    lineage = fields.get("lineage") if isinstance(fields.get("lineage"), dict) else {}
    publish_history = fields.get("intake_publish_history")
    if not isinstance(publish_history, list):
        publish_history = []
    return {
        "model_ref": model_ref,
        "project_id": fields.get("project_id"),
        "published_from_group_id": fields.get("published_from_group_id"),
        "publish_outcome": fields.get("publish_outcome"),
        "lineage": lineage,
        "publish_history": publish_history,
    }

def _intake_item_state_from_upload_status(status: str) -> str:
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
        # Fetch current upload
        row = connection.execute(
            "SELECT id, status, upload_id FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not row:
            return False, f"Upload not found: {upload_id}"
        
        current_status = row["status"]
        
        # Validate transition
        if new_status not in VALID_STATUS_TRANSITIONS.get(current_status, set()):
            return False, f"Invalid transition from {current_status} to {new_status}"
        
        # Update status with appropriate timestamp
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
        
        # Log event for audit trail
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



# ==================== ROUTER HELPER FUNCTIONS ====================

def _existing_working_slugs(connection: Any) -> set[str]:
    rows = connection.execute("SELECT slug FROM working_groups").fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}

def _unique_slug(connection: Any, title: str) -> str:
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

def _windows_root_from_assets_host(settings: Settings) -> str | None:
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip().replace("\\", "/")
    if not assets_root_host:
        return None
    normalized = assets_root_host
    marker_index = normalized.lower().find("/mnt/c")
    if marker_index < 0:
        return None
    normalized = normalized[marker_index:]
    parts = [part for part in normalized.split("/") if part]
    if len(parts) < 2:
        return None
    drive_letter = str(parts[1] or "").strip().upper()
    if drive_letter != "C":
        return None
    tail = parts[2:]
    if not tail:
        return "C:\\"
    return "C:\\" + "\\".join(tail)

def _container_assets_path_to_windows(path_value: str | None, settings: Settings) -> str | None:
    if not _windows_launch_enabled(settings):
        return None

    windows_root = _windows_root_from_assets_host(settings)
    if not windows_root:
        return None

    normalized = str(path_value or "").strip().replace("\\", "/")
    if not normalized:
        return None
    if normalized != "/assets" and not normalized.startswith("/assets/"):
        return None

    relative = normalized[len("/assets"):].lstrip("/")
    target = PureWindowsPath(windows_root)
    if not relative:
        return str(target)
    for segment in [item for item in relative.split("/") if item]:
        target = target / segment
    return str(target)

def _launch_context_for_path(path_value: str | None, settings: Settings) -> dict[str, Any]:
    container_path = str(path_value or "").strip()
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip()
    launch_enabled = _windows_launch_enabled(settings)
    windows_path = _container_assets_path_to_windows(container_path, settings)

    reason: str | None = None
    if not launch_enabled:
        reason = "assets_root_host_not_mnt_c"
    elif not windows_path:
        reason = "path_outside_assets_mount"

    return {
        "container_path": container_path,
        "assets_root_host": assets_root_host,
        "windows_launch_enabled": launch_enabled,
        "can_launch_file": bool(windows_path),
        "can_open_in_explorer": bool(windows_path),
        "windows_path": windows_path,
        "reason": reason,
    }

def _normalized_filename_stem(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    stem = re.sub(r"\.[a-z0-9]{1,8}$", "", normalized)
    stem = re.sub(r"[^a-z0-9]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()

def _extract_string_values(payload: Any, field_names: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in field_names and isinstance(value, str) and value.strip():
                values.append(value.strip())
            values.extend(_extract_string_values(value, field_names))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_extract_string_values(item, field_names))
    return values

def _extract_model_hashes(payload: dict[str, Any]) -> set[str]:
    return {
        value.lower()
        for value in _extract_string_values(payload, {"source_hash", "source_sha256", "sha256", "content_hash"})
        if value
    }



# ==================== ENDPOINTS ====================

# ========== INTAKE ITEM WORKFLOW API (Wave 2 / #1080) ==========

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

    roots = _configured_intake_source_roots(request.app.state.model_catalog.settings)
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
            if roots and not _is_path_within_roots(source_path, roots):
                created_items.append(
                    {
                        "item_id": None,
                        "source_path": source_path_text,
                        "state": "validated_warning",
                        "validation": {
                            "validation_state": "missing_source",
                            "warnings": [{"code": "path_not_allowed", "message": "Path is outside the configured intake source roots"}],
                        },
                    }
                )
                continue

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
            source_metadata = _bulk_path_source_metadata(source_path, stat_result)
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
                        "source_mtime": source_metadata.get("source_mtime"),
                        "source_ctime": source_metadata.get("source_ctime"),
                        "source_birthtime": source_metadata.get("source_birthtime"),
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
            # Keep grouping idempotent even when the same file hash already exists
            # in another working group (global unique index on working_items.file_hash).
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
                    json.dumps(file_item.get("source_metadata") or {}),
                ),
            )
            added_items += 1

        connection.execute(
            "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
            ("grouped_new" if action == "create_working_group" else "grouped_existing", f"Grouped to working_group_id={group_id}", now_iso, item_id),
        )

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        connection.commit()
        
        # Serialize before closing connection since _serialize_working_group queries related tables
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

# ========== INTAKE QUEUE API (Phase 1.5 follow-up) ==========

@router.post("/api/intake/uploads")
def intake_queue_post_upload(request: Request, payload: dict[str, Any]) -> Any:
    """
    Add a new upload to the intake queue.
    
    Source contract supports:
    - explicit file uploads: { type: "file", path: "/path/to/file.3mf" }
    - folder entries: { type: "folder", path: "/path/to/folder", recurse: true }
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
    cleanup_policy = _normalize_intake_cleanup_policy(payload.get("cleanup_policy"))
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
        if relative_path.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
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

# ========== INTAKE BROWSE API (Phase 1.5 #1147) ==========

@router.get("/api/intake/browse")
def intake_browse_folder(request: Request, path: str | None = None) -> Any:
    """
    Browse server filesystem for file/folder selection with allowlist validation.
    
    Returns folder structure for UI-based source selection. Respects:
    - Allowlist paths from settings (BAMBULAB_INTAKE_ALLOWLIST env var)
    - Returns file/folder metadata for UI tree rendering
    """
    import os
    state: AppState = request.app.state.model_catalog
    
    # Parse allowlist from settings (comma-separated paths)
    allowlist_raw = os.environ.get("BAMBULAB_INTAKE_ALLOWLIST", "/models,/storage")
    allowlist_paths = [
        Path(p.strip()).expanduser().resolve()
        for p in allowlist_raw.split(",")
        if p.strip()
    ]
    
    # Determine browse root
    browse_path = None
    if not path or path.strip() == "/":
        # Show allowlist roots as virtual children
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
    
    # Validate allowlist
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
    
    # List directory contents
    entries = []
    
    try:
        for item in sorted(browse_path.iterdir()):
            # Skip hidden files/folders on Unix
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
                    "has_children": is_dir,  # Could deep-check, but just mark as potential
                }
                
                # Add file extension for filtering
                if not is_dir:
                    entry["extension"] = item.suffix.lower()
                
                entries.append(entry)
            except (OSError, PermissionError):
                # Skip inaccessible entries
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
    
    # Compute parent path (if not root)
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
    }

# ========== SOURCE FILESYSTEM API (#1147) ==========
# (Handlers moved to routers/source_filesystems.py)

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
        files.extend(_collect_intake_source_files_in_folder(resolved, recurse=recurse))
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

def _build_cleanup_stub(*, upload_id: str, file_path: Path, uploaded_row: dict[str, Any] | None) -> str:
    lines = [
        "[MODEL_CATALOG_UPLOAD_STUB_V1]",
        f"upload_id={upload_id}",
        f"source_path={file_path}",
    ]
    if uploaded_row:
        local_model_id = str(uploaded_row.get("local_model_id") or "").strip()
        local_asset_id = str(uploaded_row.get("local_asset_id") or uploaded_row.get("asset_id") or "").strip()
        local_storage_path = str(uploaded_row.get("local_storage_path") or uploaded_row.get("storage_path") or "").strip()
        model_ref = str(uploaded_row.get("manyfold_model_ref") or "").strip()
        file_ref = str(uploaded_row.get("manyfold_file_ref") or "").strip()
        model_url = str(uploaded_row.get("manyfold_model_url") or "").strip()
        file_url = str(uploaded_row.get("manyfold_file_url") or "").strip()
        if local_model_id:
            lines.append(f"local_model_id={local_model_id}")
        if local_asset_id:
            lines.append(f"local_asset_id={local_asset_id}")
        if local_storage_path:
            lines.append(f"local_storage_path={local_storage_path}")
        if model_ref:
            lines.append(f"manyfold_model_ref={model_ref}")
        if file_ref:
            lines.append(f"manyfold_file_ref={file_ref}")
        if model_url:
            lines.append(f"manyfold_model_url={model_url}")
        if file_url:
            lines.append(f"manyfold_file_url={file_url}")
    lines.append("status=source_replaced_after_verified_publish")
    return "\n".join(lines) + "\n"

def _run_source_cleanup(
    *,
    request: Request,
    upload_id: str,
    uploaded_rows: list[dict[str, Any]] | None = None,
) -> tuple[bool, dict[str, Any]]:
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        upload_row = connection.execute(
            "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    finally:
        connection.close()

    if upload_row is None:
        return False, {
            "success": False,
            "error": "upload_not_found",
            "message": f"Upload not found: {upload_id}",
        }

    cleanup_policy = str(upload_row["cleanup_policy"] or "keep").strip().lower()
    current_status = str(upload_row["status"] or "").strip().lower()
    verification_status = str(upload_row["verification_status"] or "").strip().lower()
    if cleanup_policy == "keep":
        return True, {
            "success": True,
            "upload_id": upload_id,
            "status": current_status,
            "cleanup": {
                "policy": cleanup_policy,
                "status": "skipped",
                "skipped": True,
                "reason": "policy_keep",
                "processed_count": 0,
                "failed_count": 0,
                "results": [],
            },
        }

    if verification_status != "pass":
        return False, {
            "success": False,
            "error": "cleanup_requires_verified_upload",
            "message": f"Cleanup requires verification_status=pass, got '{verification_status or 'unknown'}'.",
        }

    if current_status not in {"verified", "cleanup_failed"}:
        return False, {
            "success": False,
            "error": "cleanup_status_invalid",
            "message": f"Cleanup can only run from 'verified' or 'cleanup_failed', got '{current_status}'.",
        }

    source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list):
        source_entries = []
    files_to_cleanup = _expand_source_entries_to_files([entry for entry in source_entries if isinstance(entry, dict)])
    if not files_to_cleanup:
        return False, {
            "success": False,
            "error": "cleanup_no_files",
            "message": "Upload queue entry did not resolve to any files for cleanup.",
        }

    roots = _configured_intake_source_roots(request.app.state.model_catalog.settings)
    managed_roots = roots + [_browser_intake_upload_storage_root(state.settings)]
    browser_stage_dirs = _browser_upload_stage_directories(state.settings, source_entries)

    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "cleanup_pending",
        event_type="cleanup_started",
        metadata={
            "policy": cleanup_policy,
            "source_count": len(files_to_cleanup),
        },
    )
    if not transitioned:
        return False, {
            "success": False,
            "error": "cleanup_status_transition_failed",
            "message": transition_error or "Could not transition cleanup to pending.",
        }

    uploaded_by_path = {
        str(Path(str(row.get("source_path") or "")).expanduser().resolve()): row
        for row in (uploaded_rows or [])
        if isinstance(row, dict)
    }

    processed_count = 0
    failure_messages: list[str] = []
    results: list[dict[str, Any]] = []
    for file_path in files_to_cleanup:
        resolved = file_path.expanduser().resolve()
        result: dict[str, Any] = {
            "path": str(resolved),
            "policy": cleanup_policy,
        }
        if not _is_path_within_roots(resolved, managed_roots):
            result.update({"success": False, "reason": "path_not_allowed"})
            failure_messages.append(f"{resolved}: outside managed intake roots")
            results.append(result)
            continue
        if not resolved.exists() or not resolved.is_file():
            result.update({"success": False, "reason": "missing_source"})
            failure_messages.append(f"{resolved}: source file missing")
            results.append(result)
            continue

        try:
            if cleanup_policy == "delete_on_verified":
                resolved.unlink()
                result.update({"success": True, "action": "deleted"})
            else:
                stub_text = _build_cleanup_stub(
                    upload_id=upload_id,
                    file_path=resolved,
                    uploaded_row=uploaded_by_path.get(str(resolved)),
                )
                resolved.write_text(stub_text, encoding="utf-8")
                result.update({"success": True, "action": "replaced_with_stub"})
            processed_count += 1
        except OSError as exc:
            result.update({"success": False, "reason": "write_error", "detail": str(exc)})
            failure_messages.append(f"{resolved}: {exc}")
        results.append(result)

    final_status = "cleanup_done" if not failure_messages else "cleanup_failed"
    if final_status == "cleanup_done" and cleanup_policy == "delete_on_verified":
        for stage_dir in browser_stage_dirs:
            shutil.rmtree(stage_dir, ignore_errors=True)
    _transition_queue_status(
        state.settings.db_path,
        upload_id,
        final_status,
        event_type="cleanup_result",
        metadata={
            "policy": cleanup_policy,
            "processed_count": processed_count,
            "failed_count": len(failure_messages),
            "results": results,
        },
    )
    _record_queue_event(
        request=request,
        upload_id=upload_id,
        event_type="intake_cleanup_summary",
        payload={
            "upload_id": upload_id,
            "policy": cleanup_policy,
            "status": final_status,
            "processed_count": processed_count,
            "failed_count": len(failure_messages),
            "results": results,
        },
    )

    summary = {
        "policy": cleanup_policy,
        "status": final_status,
        "skipped": False,
        "processed_count": processed_count,
        "failed_count": len(failure_messages),
        "results": results,
    }
    if failure_messages:
        summary["message"] = "; ".join(failure_messages)
    return True, {
        "success": True,
        "upload_id": upload_id,
        "status": final_status,
        "cleanup": summary,
    }

# ========== MANYFOLD UPLOAD ADAPTER (Phase 1.5 #1148) ==========

@router.post("/api/intake/uploads/{upload_id}/publish-to-local")
def intake_upload_publish_to_local(request: Request, upload_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Publish a queued or reviewed intake upload into the local-authority curated catalog.

    This is the authoritative post-Manyfold sink for reviewed queue/source inputs.
    Legacy /upload-to-manyfold remains available only as a transition adapter.
    """
    payload = payload or {}
    state: AppState = request.app.state.model_catalog

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        upload_row = connection.execute(
            "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    finally:
        connection.close()

    if upload_row is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "upload_not_found",
                "message": f"Upload not found: {upload_id}",
            },
        )

    current_status = str(upload_row["status"] or "").strip().lower()
    if current_status != "queued":
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "upload_not_publishable",
                "message": (
                    f"Upload is in '{current_status}' state. Only 'queued' uploads can be "
                    "published to local authority."
                ),
                "upload_id": upload_id,
            },
        )

    source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list) or not source_entries:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "upload_has_no_sources",
                "message": "Upload does not contain any source entries.",
                "upload_id": upload_id,
            },
        )

    expanded_files, expansion_warnings = _expand_intake_source_entries(source_entries=source_entries)
    if not expanded_files:
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="local_publish_failed",
            error_message="Upload did not resolve to any readable supported files.",
        )
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_files_to_publish",
                "message": "Upload did not resolve to any readable supported files.",
                "upload_id": upload_id,
                "warnings": expansion_warnings,
            },
        )

    if not expanded_files:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "upload_has_no_files",
                "message": "Upload source entries did not resolve to any files.",
                "upload_id": upload_id,
            },
        )

    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "uploading",
        event_type="local_publish_started",
        metadata={"source_entry_count": len(source_entries), "file_count": len(expanded_files)},
    )
    if not transitioned:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": transition_error or "Could not transition upload to uploading.",
                "upload_id": upload_id,
            },
        )

    requested_model_ref = str(payload.get("model_ref") or payload.get("local_model_id") or "").strip()
    requested_model_name = str(payload.get("model_name") or "").strip()
    requested_description = str(payload.get("description") or "").strip()
    requested_tags = payload.get("tags") if isinstance(payload.get("tags"), list) else None
    requested_collection_names = payload.get("collection_names") if isinstance(payload.get("collection_names"), list) else None
    requested_creator_name = str(payload.get("creator_name") or "").strip() or None
    requested_created_by = str(payload.get("created_by") or "intake_queue").strip() or "intake_queue"
    requested_source_origin = str(payload.get("source_origin") or "intake_queue").strip() or "intake_queue"
    requested_source_origin_url = str(payload.get("source_origin_url") or f"intake://uploads/{upload_id}").strip()
    requested_preview_source_path = str(payload.get("preview_source_path") or "").strip()

    default_title = requested_model_name or Path(expanded_files[0]["filename"]).stem or upload_id
    local_model_id = requested_model_ref
    target_entry = read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id) if local_model_id else None
    created_model = False

    if target_entry is None:
        preferred_model_id = local_model_id or _slugify_title(default_title) or upload_id
        local_model_id = _ensure_unique_local_model_id(db_path=state.settings.db_path, preferred=preferred_model_id)
        target_entry = create_local_model(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            model_name=default_title,
            model_description=requested_description or None,
            creator_name=requested_creator_name,
            created_by=requested_created_by,
            collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
            tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
            keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
            source_origin=requested_source_origin,
            source_origin_url=requested_source_origin_url or None,
        )
        created_model = True
    else:
        target_entry = update_local_model(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            model_name=default_title if requested_model_name else None,
            model_description=requested_description or None,
            creator_name=requested_creator_name,
            created_by=requested_created_by,
            collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
            tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
            keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
            source_origin=requested_source_origin,
            source_origin_url=requested_source_origin_url or None,
        )

    if target_entry is None:
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="local_publish_failed",
            error_message="Could not create or update local model.",
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "local_publish_failed",
                "message": "Could not create or update local model.",
                "upload_id": upload_id,
            },
        )

    existing_assets = list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
    existing_asset_ids = {
        str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
        for asset in existing_assets
        if str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
    }
    existing_hashes = {
        str(getattr(asset, "file_hash", "") or "").strip().lower()
        for asset in existing_assets
        if str(getattr(asset, "file_hash", "") or "").strip()
    }
    has_preview = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "preview" for asset in existing_assets)
    has_primary = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "primary" for asset in existing_assets)

    imported_assets: list[dict[str, Any]] = []
    duplicate_skipped: list[dict[str, Any]] = []
    failed_files: list[dict[str, Any]] = []
    preview_source_normalized = requested_preview_source_path.lower() if requested_preview_source_path else None

    for file_item in expanded_files:
        source_path = Path(str(file_item["path"])).resolve()
        file_hash = str(file_item["file_hash"] or "").strip().lower()
        if file_hash in existing_hashes:
            duplicate_skipped.append(
                {
                    "source_path": str(source_path),
                    "filename": source_path.name,
                    "sha256": file_hash,
                    "reason": "duplicate_hash",
                }
            )
            continue

        try:
            storage_path = _copy_local_import_source(
                settings=state.settings,
                local_model_id=local_model_id,
                source_path=source_path,
            )
            asset_type = _normalize_local_asset_type(source_path)
            preview_selected = bool(preview_source_normalized and str(source_path).lower() == preview_source_normalized)
            asset_role = _normalize_local_asset_role(
                asset_type=asset_type,
                has_preview=has_preview,
                has_primary=has_primary,
                preview_selected=preview_selected,
            )
            asset_id = _unique_asset_id(filename=source_path.name, file_hash=file_hash, existing_ids=existing_asset_ids)
            asset = create_model_asset(
                db_path=state.settings.db_path,
                local_model_id=local_model_id,
                asset_id=asset_id,
                asset_filename=source_path.name,
                asset_type=asset_type,
                storage_path=storage_path,
                asset_role=asset_role,
                file_size_bytes=int(file_item["size_bytes"]),
                file_hash=file_hash,
                preview_url=None,
                geometry_bounds=None,
            )
            existing_hashes.add(file_hash)
            has_preview = has_preview or asset_role == "preview"
            has_primary = has_primary or asset_role == "primary"
            imported_assets.append(
                {
                    "local_model_id": local_model_id,
                    "local_asset_id": asset.asset_id,
                    "local_storage_path": asset.storage_path,
                    "asset_id": asset.asset_id,
                    "filename": asset.asset_filename,
                    "asset_type": asset.asset_type,
                    "asset_role": asset.asset_role,
                    "sort_order": asset.sort_order,
                    "storage_path": asset.storage_path,
                    "file_hash": asset.file_hash,
                    "source_path": str(source_path),
                    "source_entry_type": file_item.get("entry_type"),
                }
            )
        except Exception as exc:
            failed_files.append(
                {
                    "source_path": str(source_path),
                    "filename": source_path.name,
                    "message": str(exc),
                }
            )

    publish_history = _append_intake_publish_history(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        entry={
            "upload_id": upload_id,
            "published_at": _bulk_utc_now_iso(),
            "created_model": created_model,
            "imported_asset_count": len(imported_assets),
            "duplicate_skipped_count": len(duplicate_skipped),
            "failed_file_count": len(failed_files),
            "source_entries": source_entries,
        },
    )
    set_model_field(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        field_key="intake_queue_upload_id",
        field_value=upload_id,
    )
    set_model_field(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        field_key="intake_source_entries",
        field_value=source_entries,
    )
    set_model_field(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        field_key="internal_notes",
        field_value=f"Imported from intake upload {upload_id}",
    )

    if imported_assets:
        success_connection = connect(state.settings.db_path)
        try:
            success_connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?, verification_status = ?, updated_at = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps([item["file_hash"] for item in imported_assets]),
                    "pass",
                    _bulk_utc_now_iso(),
                    upload_id,
                ),
            )
            success_connection.commit()
        finally:
            success_connection.close()

        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "uploaded_unverified",
            event_type="local_publish_materialized",
            metadata={
                "local_model_id": local_model_id,
                "imported_asset_count": len(imported_assets),
                "duplicate_skipped_count": len(duplicate_skipped),
                "failed_file_count": len(failed_files),
            },
        )
        if transitioned:
            transitioned, transition_error = _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "verified",
                event_type="local_publish_verified",
                metadata={
                    "local_model_id": local_model_id,
                    "publish_history_count": len(publish_history),
                },
            )
    else:
        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="local_publish_failed",
            error_message="No assets were imported into the local model.",
            metadata={
                "local_model_id": local_model_id,
                "duplicate_skipped_count": len(duplicate_skipped),
                "failed_file_count": len(failed_files),
            },
        )

    if not transitioned:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": transition_error or "Could not finalize local publish state.",
                "upload_id": upload_id,
                "local_model_id": local_model_id,
            },
        )

    cleanup_result = {
        "policy": str(upload_row["cleanup_policy"] or "keep").strip().lower(),
        "status": "skipped",
        "skipped": True,
        "reason": "policy_keep",
        "processed_count": 0,
        "failed_count": 0,
        "results": [],
    }
    effective_status = "verified"
    if imported_assets and cleanup_result["policy"] != "keep":
        cleanup_ok, cleanup_payload = _run_source_cleanup(request=request, upload_id=upload_id, uploaded_rows=imported_assets)
        if not cleanup_ok:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": cleanup_payload.get("error") or "cleanup_failed",
                    "message": cleanup_payload.get("message") or "Cleanup could not be started.",
                    "upload_id": upload_id,
                    "local_model_id": local_model_id,
                },
            )
        cleanup_result = cleanup_payload["cleanup"]
        effective_status = str(cleanup_payload["status"])

    detail_payload = build_model_detail_response(
        state,
        request.app.state.manyfold_client,
        local_model_id,
        include_debug=False,
        request=request,
        helpers=models_router._model_detail_service_helpers(),
    )
    if detail_payload.get("success") is False:
        detail_payload = None

    return {
        "success": True,
        "contract": "intake-publish-local.v1alpha1",
        "upload_id": upload_id,
        "status": effective_status,
        "verification_status": "pass",
        "local_model_id": local_model_id,
        "model_ref": local_model_id,
        "created_model": created_model,
        "imported_asset_count": len(imported_assets),
        "duplicate_skipped_count": len(duplicate_skipped),
        "failed_file_count": len(failed_files),
        "imported_assets": imported_assets,
        "duplicate_skipped": duplicate_skipped,
        "failed_files": failed_files,
        "warnings": expansion_warnings,
        "cleanup": cleanup_result,
        "legacy_adapter": {
            "upload_to_manyfold_route": f"/api/intake/uploads/{quote(upload_id, safe='')}/upload-to-manyfold",
            "authoritative": False,
            "status": "transition_only",
        },
        "model": detail_payload.get("model") if isinstance(detail_payload, dict) else None,
        "enrichment": detail_payload.get("enrichment") if isinstance(detail_payload, dict) else None,
    }

@router.post("/api/intake/uploads/{upload_id}/upload-to-manyfold")
async def intake_upload_to_manyfold(
    upload_id: str,
    request: Request,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> Any:
    """
    Upload files from verified intake upload to Manyfold library.
    
    Streams file from local filesystem directly to Manyfold server.
    Handles multipart form submission with file hash verification.
    
    Query Parameters:
    - collection_id: Target collection ID (optional)
    - collection_name: Target collection name (optional, overrides ID lookup)
    
    JSON Body (optional):
    - collection_id: Target collection ID
    - collection_name: Target collection name
    
    Response:
    - upload_record: Updated intake upload status
    - manyfold_response: Manyfold's response metadata
    - files_uploaded: List of files successfully uploaded
    """
    state: AppState = request.app.state.model_catalog
    
    # Try to get collection info from request body first, then query params
    try:
        body = await request.json()
        if body.get("collection_id"):
            collection_id = body["collection_id"]
        if body.get("collection_name"):
            collection_name = body["collection_name"]
    except Exception:
        pass  # No JSON body or parsing error, use query params
    
    # Verify upload exists and is in verified state
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        upload_row = connection.execute(
            "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not upload_row:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "upload_not_found",
                    "message": f"Upload not found: {upload_id}",
                },
            )
        
        if upload_row["status"] != "uploaded_unverified":
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "upload_not_verified",
                    "message": f"Upload is in '{upload_row['status']}' state. Only unverified uploads can be uploaded to Manyfold.",
                },
            )
    finally:
        connection.close()
    
    client: ManyfoldClient = request.app.state.manyfold_client

    def _guess_content_type(file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        return {
            ".3mf": "model/3mf",
            ".stl": "model/stl",
            ".obj": "model/obj",
            ".step": "model/step",
            ".stp": "model/step",
            ".gcode": "text/x.gcode",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "application/octet-stream")

    def _normalized_filename(value: str | None) -> str:
        return Path(str(value or "").strip()).name.lower()

    def _candidate_size(row: Any) -> int | None:
        if not isinstance(row, dict):
            return None
        for key in ("byteSize", "contentSize", "size", "size_bytes"):
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _candidate_names(row: Any) -> set[str]:
        names: set[str] = set()
        if isinstance(row, dict):
            for key in ("filename", "original_filename", "name", "title"):
                normalized = _normalized_filename(str(row.get(key) or ""))
                if normalized:
                    names.add(normalized)
            for key in ("contentUrl", "url", "@id"):
                raw_value = str(row.get(key) or "").strip()
                if not raw_value:
                    continue
                parsed_path = urlsplit(raw_value).path or raw_value
                normalized = _normalized_filename(parsed_path)
                if normalized:
                    names.add(normalized)
        return names

    def _candidate_name_stems(row: Any) -> set[str]:
        stems: set[str] = set()
        if isinstance(row, dict):
            for key in ("filename", "original_filename", "name", "title"):
                normalized = _normalized_filename_stem(str(row.get(key) or ""))
                if normalized:
                    stems.add(normalized)
            for key in ("contentUrl", "url", "@id"):
                raw_value = str(row.get(key) or "").strip()
                if not raw_value:
                    continue
                parsed_path = urlsplit(raw_value).path or raw_value
                normalized = _normalized_filename_stem(parsed_path)
                if normalized:
                    stems.add(normalized)
        return stems

    def _verify_uploaded_file(
        *,
        model_ref: str,
        attached_file: dict[str, Any],
        expected_hash: str,
        expected_size: int,
        expected_name: str,
    ) -> tuple[bool, str, list[dict[str, Any]]]:
        candidate_rows: list[dict[str, Any]] = []
        if attached_file:
            candidate_rows.append(attached_file)

        model_detail: dict[str, Any] = {}
        try:
            model_detail = client.get_model_detail(model_ref)
        except Exception:
            model_detail = {}

        if model_detail:
            has_part = model_detail.get("hasPart")
            if isinstance(has_part, list):
                candidate_rows.extend(row for row in has_part if isinstance(row, dict))

        try:
            candidate_rows.extend(client.list_model_files(model_ref))
        except Exception:
            pass

        if expected_hash.lower() in _extract_model_hashes(model_detail or attached_file):
            return True, "hash", candidate_rows

        normalized_name = _normalized_filename(expected_name)
        normalized_stem = _normalized_filename_stem(expected_name)
        for row in candidate_rows:
            candidate_names = _candidate_names(row)
            candidate_stems = _candidate_name_stems(row)
            if normalized_name not in candidate_names and normalized_stem not in candidate_stems:
                continue
            candidate_size = _candidate_size(row)
            if candidate_size is not None and candidate_size == expected_size:
                return True, "size_name", candidate_rows

        if len(candidate_rows) == 1:
            candidate_size = _candidate_size(candidate_rows[0])
            if candidate_size is not None and candidate_size == expected_size:
                return True, "size_single_candidate", candidate_rows

        return False, "missing", candidate_rows

    def _canonical_file_url(model_url: str, attached_file: dict[str, Any], file_ref: str | None) -> str | None:
        raw_url = str(attached_file.get("contentUrl") or attached_file.get("url") or attached_file.get("@id") or "").strip()
        if raw_url:
            return canonicalize_model_url(state.settings.manyfold_base_url, raw_url)
        normalized_ref = str(file_ref or "").strip()
        if normalized_ref.startswith("/"):
            return canonicalize_model_url(state.settings.manyfold_base_url, normalized_ref)
        if normalized_ref:
            return f"{model_url.rstrip('/')}/model_files/{quote(normalized_ref, safe='')}"
        return None

    def _model_key_from_payload(payload: dict[str, Any]) -> str:
        return derive_manyfold_model_key(
            manyfold_model_url=str(payload.get("url") or payload.get("@id") or "").strip() or None,
            manyfold_model_public_id=str(payload.get("public_id") or payload.get("slug") or "").strip() or None,
            manyfold_model_id=str(payload.get("id") or "").strip() or None,
        )

    def _pick_matching_candidate_row(
        *,
        candidate_rows: list[dict[str, Any]],
        expected_name: str,
        expected_size: int,
    ) -> dict[str, Any] | None:
        normalized_name = _normalized_filename(expected_name)
        for row in candidate_rows:
            if normalized_name not in _candidate_names(row):
                continue
            candidate_size = _candidate_size(row)
            if candidate_size is None or candidate_size == expected_size:
                return row
        return candidate_rows[0] if candidate_rows else None

    def _find_verified_uploaded_model(
        *,
        baseline_model_keys: set[str],
        expected_hash: str,
        expected_size: int,
        expected_name: str,
        fallback_name: str,
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]], dict[str, Any] | None]:
        normalized_fallback_name = _normalized_filename(fallback_name)
        last_payloads: list[dict[str, Any]] = []
        saw_materialized_candidate = False
        for attempt in range(12):
            payloads = client.list_model_payloads()
            last_payloads = payloads
            candidate_payloads = [
                payload
                for payload in payloads
                if _model_key_from_payload(payload) not in baseline_model_keys
            ]
            if not candidate_payloads:
                candidate_payloads = [
                    payload
                    for payload in payloads
                    if _normalized_filename(str(payload.get("name") or "")) == normalized_fallback_name
                ]

            if not candidate_payloads:
                html_payloads = client.list_model_payloads_from_html(order="recent")
                candidate_payloads = [
                    payload
                    for payload in html_payloads
                    if _normalized_filename(str(payload.get("name") or "")) == normalized_fallback_name
                ]

            for candidate_payload in candidate_payloads:
                model_ref = _model_ref_from_payload(candidate_payload)
                if not model_ref:
                    continue
                verified, verification_method, candidate_rows = _verify_uploaded_file(
                    model_ref=model_ref,
                    attached_file={},
                    expected_hash=expected_hash,
                    expected_size=expected_size,
                    expected_name=expected_name,
                )
                if candidate_rows:
                    saw_materialized_candidate = True
                if not verified:
                    continue
                matched_row = _pick_matching_candidate_row(
                    candidate_rows=candidate_rows,
                    expected_name=expected_name,
                    expected_size=expected_size,
                )
                return candidate_payload, verification_method, candidate_rows, matched_row

            if saw_materialized_candidate:
                break

            if attempt < 11:
                time.sleep(1)

        raise RuntimeError(
            f"Manyfold verification failed for {expected_name}; no created model matched uploaded content after polling {len(last_payloads)} candidates."
        )

    def _write_working_item_refs(
        *,
        file_path: Path,
        file_hash: str,
        model_ref: str,
        file_ref: str | None,
        canonical_model_url: str,
        canonical_file_url: str | None,
        verification_method: str,
        verified_at: str,
    ) -> None:
        write_connection = connect(state.settings.db_path)
        write_connection.row_factory = sqlite3.Row
        try:
            rows = write_connection.execute(
                """
                SELECT id, source_metadata_json
                FROM working_items
                WHERE file_hash = ? OR file_path = ?
                """,
                (file_hash, str(file_path)),
            ).fetchall()
            for row in rows:
                try:
                    metadata = json.loads(str(row["source_metadata_json"] or "{}"))
                except json.JSONDecodeError:
                    metadata = {}
                metadata["manyfold_destination"] = {
                    "upload_id": upload_id,
                    "verification_status": "pass",
                    "verification_method": verification_method,
                    "verified_at": verified_at,
                    "manyfold_model_ref": model_ref,
                    "manyfold_file_ref": file_ref,
                    "canonical_model_url": canonical_model_url,
                    "canonical_file_url": canonical_file_url,
                }
                write_connection.execute(
                    "UPDATE working_items SET source_metadata_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(metadata), verified_at, int(row["id"])),
                )
            write_connection.commit()
        finally:
            write_connection.close()

    source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list):
        source_entries = []
    files_to_upload = _expand_source_entries_to_files([entry for entry in source_entries if isinstance(entry, dict)])
    if not files_to_upload:
        error_message = "Upload queue entry did not resolve to any readable files."
        failed, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="manyfold_upload_failed",
            error_message=error_message,
        )
        if not failed and transition_error:
            error_message = f"{error_message} {transition_error}"
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_files_to_upload",
                "message": error_message,
            },
        )

    try:
        collection_ref = client.resolve_collection_ref(collection_id=collection_id, collection_name=collection_name)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "collection_not_found",
                "message": str(exc),
            },
        )

    uploaded_rows: list[dict[str, Any]] = []
    file_hashes: list[str] = []
    manyfold_file_ids: list[str] = []
    verification_methods: list[str] = []

    try:
        for file_path in files_to_upload:
            file_bytes = file_path.read_bytes()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            file_size = len(file_bytes)
            baseline_model_keys = {
                _model_key_from_payload(payload)
                for payload in client.list_model_payloads()
            }
            uploaded_file_ref = client.upload_file(
                filename=file_path.name,
                content=file_bytes,
                content_type=_guess_content_type(file_path),
            )
            client.create_model_from_uploads(
                name=file_path.stem,
                collection_ref=collection_ref,
                uploaded_files=[uploaded_file_ref],
            )
            model_payload, verification_method, _candidate_rows, attached_file = _find_verified_uploaded_model(
                baseline_model_keys=baseline_model_keys,
                expected_hash=file_hash,
                expected_size=file_size,
                expected_name=file_path.name,
                fallback_name=file_path.stem,
            )
            model_id = str(model_payload.get("id") or "").strip() or None
            model_ref = _model_ref_from_payload(model_payload)
            if not model_ref:
                raise RuntimeError(f"Manyfold create_model did not return a usable model reference for {file_path.name}.")
            canonical_model_url = canonicalize_model_url(
                state.settings.manyfold_base_url,
                str(model_payload.get("url") or model_payload.get("@id") or "").strip(),
                fallback_model_id=model_id,
            )
            file_ref = str(attached_file.get("id") or attached_file.get("@id") or attached_file.get("url") or "").strip() or None
            verified_at = _bulk_utc_now_iso()
            canonical_file_url = _canonical_file_url(canonical_model_url, attached_file or {}, file_ref)
            _write_working_item_refs(
                file_path=file_path,
                file_hash=file_hash,
                model_ref=model_ref,
                file_ref=file_ref,
                canonical_model_url=canonical_model_url,
                canonical_file_url=canonical_file_url,
                verification_method=verification_method,
                verified_at=verified_at,
            )
            file_hashes.append(file_hash)
            if file_ref:
                manyfold_file_ids.append(file_ref)
            verification_methods.append(verification_method)
            uploaded_rows.append(
                {
                    "source_path": str(file_path),
                    "filename": file_path.name,
                    "sha256": file_hash,
                    "size_bytes": file_size,
                    "manyfold_model_ref": model_ref,
                    "manyfold_model_id": model_id,
                    "manyfold_model_url": canonical_model_url,
                    "manyfold_file_ref": file_ref,
                    "manyfold_file_url": canonical_file_url,
                    "verification_method": verification_method,
                }
            )
    except Exception as exc:
        failure_connection = connect(state.settings.db_path)
        try:
            failure_connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?, manyfold_file_ids_json = ?, verification_status = ?, updated_at = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps(file_hashes),
                    json.dumps(manyfold_file_ids),
                    "failed",
                    _bulk_utc_now_iso(),
                    upload_id,
                ),
            )
            failure_connection.commit()
        finally:
            failure_connection.close()
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="manyfold_upload_failed",
            error_message=str(exc),
            metadata={
                "uploaded_count": len(uploaded_rows),
                "file_hashes": file_hashes,
                "manyfold_file_ids": manyfold_file_ids,
            },
        )
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": "manyfold_upload_failed",
                "message": str(exc),
                "upload_id": upload_id,
                "files_uploaded": uploaded_rows,
            },
        )

    verified_at = _bulk_utc_now_iso()
    success_connection = connect(state.settings.db_path)
    success_connection.row_factory = sqlite3.Row
    try:
        success_connection.execute(
            """
            UPDATE intake_queue_uploads
            SET file_hashes_json = ?, manyfold_file_ids_json = ?, verification_status = ?, updated_at = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps(file_hashes),
                json.dumps(manyfold_file_ids),
                "pass",
                verified_at,
                upload_id,
            ),
        )
        success_connection.commit()
    finally:
        success_connection.close()

    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "verified",
        event_type="manyfold_upload_verified",
        metadata={
            "uploaded_count": len(uploaded_rows),
            "file_hashes": file_hashes,
            "manyfold_file_ids": manyfold_file_ids,
            "verification_methods": verification_methods,
        },
    )
    if not transitioned:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": transition_error or "Could not transition upload to verified.",
                "upload_id": upload_id,
            },
        )

    cleanup_result = {
        "policy": str(upload_row["cleanup_policy"] or "keep").strip().lower(),
        "status": "skipped",
        "skipped": True,
        "reason": "policy_keep",
        "processed_count": 0,
        "failed_count": 0,
        "results": [],
    }
    effective_status = "verified"
    if cleanup_result["policy"] != "keep":
        cleanup_ok, cleanup_payload = _run_source_cleanup(request=request, upload_id=upload_id, uploaded_rows=uploaded_rows)
        if not cleanup_ok:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": cleanup_payload.get("error") or "cleanup_failed",
                    "message": cleanup_payload.get("message") or "Cleanup could not be started.",
                    "upload_id": upload_id,
                    "files_uploaded": uploaded_rows,
                },
            )
        cleanup_result = cleanup_payload["cleanup"]
        effective_status = str(cleanup_payload["status"])

    return {
        "success": True,
        "upload_id": upload_id,
        "status": effective_status,
        "verification_status": "pass",
        "manyfold_response": {
            "collection_id": collection_id,
            "collection_name": collection_name,
            "collection_ref": collection_ref,
            "uploaded_count": len(uploaded_rows),
        },
        "files_uploaded": uploaded_rows,
        "cleanup": cleanup_result,
        "meta": {
            "adapter_version": "1.2",
            "verification_methods": verification_methods,
            "verified_at": verified_at,
        },
    }

@router.post("/api/intake/uploads/{upload_id}/cleanup")
def intake_cleanup_upload(request: Request, upload_id: str) -> Any:
    """Run or retry post-upload source cleanup for a verified upload."""
    cleanup_ok, payload = _run_source_cleanup(request=request, upload_id=upload_id)
    if not cleanup_ok:
        error = str(payload.get("error") or "cleanup_failed")
        status_code = 404 if error == "upload_not_found" else 409
        return JSONResponse(
            status_code=status_code,
            content=payload,
        )
    return payload

