"""
Intake workflow routers - combined from focused sub-modules.

This module re-exports all intake endpoints from specialized routers:
- intake_queue: Queue state machine and upload management
- intake_verification: Item validation and working group creation
- intake_cleanup: Source file cleanup operations

Publishing operations (publish-to-local, upload-to-manyfold) remain here.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from sqlite3 import connect
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..settings import Settings
from ..state import AppState
from .._helpers import (
    _bulk_utc_now_iso,
    _coerce_bool,
    _coerce_int,
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
from ..services.model_detail_service import build_model_detail_response
from ..services.intake_eligibility_service import ActionEligibility
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

# Import sub-routers
from .intake_queue import router as intake_queue_router
from .intake_verification import router as intake_verification_router
from .intake_cleanup import router as intake_cleanup_router
from .intake_queue import (
    _browser_intake_upload_storage_root,
    _browser_upload_stage_directories,
    _expand_source_entries_to_files,
    _record_queue_event,
    _transition_queue_status,
    VALID_STATUS_TRANSITIONS,
)
from .intake_cleanup import _build_cleanup_stub, _run_source_cleanup
from .intake_verification import _default_group_title

# Create combined router
router = APIRouter(tags=["intake"])

# Include all sub-routers
router.include_router(intake_queue_router)
router.include_router(intake_verification_router)
router.include_router(intake_cleanup_router)


# ==================== PUBLISHING ENDPOINTS ====================

# Helper functions for publishing logic

def _generate_short_stable_id() -> str:
    """Generate a short stable suffix for model IDs."""
    return str(uuid.uuid4()).replace("-", "")[:8]


def _ensure_unique_local_model_id(*, db_path: Path, preferred: str) -> str:
    """Generate a unique local model ID using format: <name-slug>--<shortid>."""
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

    slug = _slugify_title(preferred) or "model"
    short_id = _generate_short_stable_id()
    candidate = f"{slug}--{short_id}"
    
    counter = 2
    while _local_model_id_exists(db_path=db_path, local_model_id=candidate):
        short_id = _generate_short_stable_id()
        candidate = f"{slug}--{short_id}"
        counter += 1
        if counter > 100:
            candidate = f"{slug}--{short_id}-{counter}"
    
    return candidate


def _normalize_local_asset_type(path: Path) -> str:
    LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    LOCAL_IMPORT_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"}
    LOCAL_IMPORT_DOCUMENT_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json", ".yaml", ".yml"}
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


def _copy_local_import_source(*, settings: Settings, local_model_id: str, source_path: Path) -> str:
    import shutil
    catalog_root = _model_photo_storage_root(settings)
    asset_root = catalog_root / local_model_id
    asset_root.mkdir(parents=True, exist_ok=True)
    
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
    
    destination = _unique_destination_path(asset_root, source_path.name)
    shutil.copy2(source_path, destination)
    try:
        relative_path = destination.relative_to(catalog_root.resolve())
        return str(relative_path).replace("\\", "/")
    except ValueError:
        return str(destination).replace("\\", "/")


def _expand_intake_source_entries(*, source_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand source entries into individual files."""
    from ..services.shared_helpers import _sha256_file
    from .._helpers import _bulk_path_source_metadata
    
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    SUPPORTED_WORKING_FILE_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".gcode"}
    LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    for entry in source_entries:
        entry_type = str(entry.get("type") or "").strip().lower()
        source_path_raw = str(entry.get("path") or "").strip()
        if entry_type not in {"file", "folder"} or not source_path_raw:
            continue

        source_path = Path(source_path_raw).expanduser().resolve()
        if entry_type == "file":
            candidate_paths = [source_path]
        else:
            from .._helpers import _collect_intake_source_files_in_folder
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
                    "source_metadata": _bulk_path_source_metadata(file_path, stat_result),
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


# Windows launch helpers

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
    from pathlib import PureWindowsPath
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


# Publishing endpoints

@router.post("/api/intake/uploads/{upload_id}/publish-to-local")
def intake_upload_publish_to_local(request: Request, upload_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Publish a queued or reviewed intake upload into the local-authority curated catalog.
    
    Transitions from validated_ready → published_to_catalog (terminal state).
    This is the authoritative post-Manyfold sink for reviewed queue/source inputs.
    """
    payload = payload or {}
    state: AppState = request.app.state.model_catalog

    connection = connect(state.settings.db_path)
    connection.row_factory = __import__("sqlite3").Row
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

    # Get current state (prioritize inbox_state for new state machine)
    current_state = str(upload_row["inbox_state"] or "").strip().lower() or "submitted"
    current_status = str(upload_row["status"] or "").strip().lower()
    
    # Check eligibility: can publish from submitted, validated_ready, or deferred states
    is_eligible, reason_code = ActionEligibility.validate_action_eligibility(current_state, ActionEligibility.PUBLISH_CATALOG)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot publish item in state '{current_state}': {reason_code}",
                "upload_id": upload_id,
                "current_state": current_state,
                "allowed_actions": ActionEligibility.build_allowed_actions_payload(current_state).get("allowed_actions", []),
            },
        )

    # Also check backward compat with old status field (for transition functions)
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

    default_title = requested_model_name or _default_group_title(source_entries, expanded_files) or upload_id
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
            now_iso = _bulk_utc_now_iso()
            success_connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?, verification_status = ?, updated_at = ?,
                    terminal_action = ?, terminal_at = ?,
                    terminal_result_id = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps([item["file_hash"] for item in imported_assets]),
                    "pass",
                    now_iso,
                    "published_to_catalog",
                    now_iso,
                    local_model_id,
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
        # Terminal state metadata
        "terminal": True,
        "state": "published_to_catalog",
        "is_terminal": True,
        "allowed_actions": [],
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
    try:
        from sqlite3 import Row
        connection.row_factory = Row
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
    
    client = request.app.state.manyfold_client

    # Get source entries and expand to files
    source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list):
        source_entries = []
    
    files_to_upload = _expand_source_entries_to_files([entry for entry in source_entries if isinstance(entry, dict)])
    if not files_to_upload:
        error_message = "Upload queue entry did not resolve to any readable files."
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="manyfold_upload_failed",
            error_message=error_message,
        )
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

    # Upload files to Manyfold
    uploaded_rows: list[dict[str, Any]] = []
    file_hashes: list[str] = []
    manyfold_file_ids: list[str] = []
    verification_methods: list[str] = []

    try:
        for file_path in files_to_upload:
            file_bytes = file_path.read_bytes()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            file_size = len(file_bytes)
            
            # Get baseline of existing models
            baseline_model_keys = set()
            try:
                baseline_payloads = client.list_model_payloads()
                for p in baseline_payloads:
                    if isinstance(p, dict):
                        key = derive_manyfold_model_key(
                            manyfold_model_url=str(p.get("url") or p.get("@id") or "").strip() or None,
                            manyfold_model_public_id=str(p.get("public_id") or p.get("slug") or "").strip() or None,
                            manyfold_model_id=str(p.get("id") or "").strip() or None,
                        )
                        baseline_model_keys.add(key)
            except Exception:
                pass  # Ignore errors getting baseline
            
            # Determine content type
            suffix = file_path.suffix.lower()
            content_type = {
                ".3mf": "model/3mf",
                ".stl": "model/stl",
                ".obj": "model/obj",
                ".step": "model/step",
                ".stp": "model/step",
            }.get(suffix, "application/octet-stream")
            
            # Upload file to Manyfold
            uploaded_file_ref = client.upload_file(
                filename=file_path.name,
                content=file_bytes,
                content_type=content_type,
            )
            
            # Create model in Manyfold
            client.create_model_from_uploads(
                name=file_path.stem,
                collection_ref=collection_ref,
                uploaded_files=[uploaded_file_ref],
            )
            
            # Poll for the created model
            model_payload = None
            for attempt in range(6):  # Poll up to 6 times with 1 second delay
                try:
                    payloads = client.list_model_payloads()
                    for payload in payloads:
                        if not isinstance(payload, dict):
                            continue
                        payload_key = derive_manyfold_model_key(
                            manyfold_model_url=str(payload.get("url") or payload.get("@id") or "").strip() or None,
                            manyfold_model_public_id=str(payload.get("public_id") or payload.get("slug") or "").strip() or None,
                            manyfold_model_id=str(payload.get("id") or "").strip() or None,
                        )
                        if payload_key not in baseline_model_keys:
                            model_payload = payload
                            break
                    if model_payload:
                        break
                except Exception:
                    pass
                
                if attempt < 5:
                    time.sleep(1)
            
            # Extract model information
            model_id = None
            model_ref = None
            model_url = None
            file_ref = None
            file_url = None
            verification_method = "hash"
            
            if model_payload and isinstance(model_payload, dict):
                model_id = str(model_payload.get("id") or "").strip() or None
                model_url = str(model_payload.get("url") or model_payload.get("@id") or "").strip()
                if model_url and not model_url.startswith("http"):
                    model_url = canonicalize_model_url(state.settings.manyfold_base_url, model_url, fallback_model_id=model_id)
                model_ref = _model_ref_from_payload(model_payload)
                
                # Fetch model detail to get file information
                try:
                    if model_ref:
                        model_detail = client.get_model_detail(model_ref)
                        if model_detail and isinstance(model_detail, dict):
                            has_part = model_detail.get("hasPart")
                            if isinstance(has_part, list) and len(has_part) > 0:
                                file_row = has_part[0]
                                file_ref = str(file_row.get("id") or "").strip() or None
                                file_url_from_detail = str(file_row.get("@id") or file_row.get("url") or "").strip()
                                if file_url_from_detail and file_url_from_detail.startswith("http"):
                                    file_url = file_url_from_detail
                except Exception:
                    pass  # Ignore errors fetching model detail
            
            # Build file URL if we don't have it yet
            if file_ref and not file_url and model_url:
                file_url = f"{model_url.rstrip('/')}/model_files/{quote(file_ref, safe='')}"
            
            file_hashes.append(file_hash)
            if file_ref:
                manyfold_file_ids.append(file_ref)
            verification_methods.append(verification_method)
            
            uploaded_rows.append({
                "source_path": str(file_path),
                "filename": file_path.name,
                "sha256": file_hash,
                "size_bytes": file_size,
                "manyfold_model_ref": model_ref,
                "manyfold_model_id": model_id,
                "manyfold_model_url": model_url,
                "manyfold_file_ref": file_ref,
                "manyfold_file_url": file_url,
                "verification_method": verification_method,
            })
    except Exception as exc:
        # Update upload with failure status
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

    # Update upload with success status
    verified_at = _bulk_utc_now_iso()
    success_connection = connect(state.settings.db_path)
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

    # Transition queue status
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

    return {
        "success": True,
        "upload_id": upload_id,
        "status": "verified",
        "verification_status": "pass",
        "manyfold_response": {
            "collection_id": collection_id,
            "collection_name": collection_name,
            "collection_ref": collection_ref,
            "uploaded_count": len(uploaded_rows),
        },
        "files_uploaded": uploaded_rows,
        "cleanup": {
            "policy": str(upload_row["cleanup_policy"] or "keep").strip().lower(),
            "status": "skipped",
            "skipped": True,
            "reason": "policy_keep",
            "processed_count": 0,
            "failed_count": 0,
            "results": [],
        },
        "meta": {
            "adapter_version": "1.2",
            "verification_methods": verification_methods,
            "verified_at": verified_at,
        },
    }


# Backward-compatible helper exports used by tests and monkeypatches

_browser_intake_upload_storage_root = _browser_intake_upload_storage_root
_browser_upload_stage_directories = _browser_upload_stage_directories
_expand_source_entries_to_files = _expand_source_entries_to_files
_record_queue_event = _record_queue_event
_transition_queue_status = _transition_queue_status
_build_cleanup_stub = _build_cleanup_stub
_run_source_cleanup = _run_source_cleanup
VALID_STATUS_TRANSITIONS = VALID_STATUS_TRANSITIONS
