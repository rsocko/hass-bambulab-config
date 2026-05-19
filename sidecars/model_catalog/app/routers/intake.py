"""
Intake workflow routers - combined from focused sub-modules.

This module re-exports all intake endpoints from specialized routers:
- intake_queue: Queue state machine and upload management
- intake_verification: Item validation and working group creation
- intake_cleanup: Source file cleanup operations

Publishing operations (publish-to-local, upload-to-catalog) remain here.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
    LOCAL_IMPORT_DOCUMENT_EXTENSIONS,
    LOCAL_IMPORT_IMAGE_EXTENSIONS,
    SUPPORTED_INTAKE_FILE_EXTENSIONS,
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _compile_source_entry_exclusions,
    _coerce_bool,
    _is_excluded_source_file,
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
    derive_model_key,
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
from ..catalog_cache import (
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
    _normalize_terminal_actor,
    _expand_source_entries_to_files,
    _record_queue_event,
    _transition_queue_status,
    VALID_STATUS_TRANSITIONS,
)
from .intake_cleanup import _build_cleanup_stub, _run_source_cleanup, _run_publish_finalize, _remove_browser_upload_staging
from .intake_verification import _default_group_title, _plan_intake_groups

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
    suffix = path.suffix.lower()
    if suffix in LOCAL_IMPORT_IMAGE_EXTENSIONS:
        return "image"
    if suffix in SUPPORTED_WORKING_FILE_EXTENSIONS:
        return suffix.lstrip(".")
    if suffix in LOCAL_IMPORT_DOCUMENT_EXTENSIONS:
        return suffix.lstrip(".") or "document"
    return suffix.lstrip(".") or "file"


def _normalize_local_asset_role(*, asset_type: str, has_preview: bool, has_primary: bool, preview_selected: bool) -> str:
    if preview_selected:
        return "preview"
    if asset_type == "image":
        return "supporting" if has_preview else "preview"
    if asset_type in {"3mf", "stl", "obj", "step", "stp", "gcode", "zip"}:
        return "supporting" if has_primary else "primary"
    if asset_type in {
        "pdf", "md", "txt", "csv", "json", "yaml", "yml", "rtf",
        "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "document"
    }:
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


_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _sanitize_storage_segment(segment: str, *, fallback: str = "item") -> str:
    value = re.sub(r"[<>:\\|?*\x00-\x1f]", "_", str(segment or "").strip())
    value = value.rstrip(" .")
    if not value:
        value = fallback
    device_name = value.split(".", 1)[0].upper()
    if device_name in _WINDOWS_RESERVED_NAMES:
        value = f"{value}_"
    return value


def _normalized_relative_parts(relative_path: str | None) -> list[str]:
    raw_relative_path = str(relative_path or "").strip().replace("\\", "/")
    if not raw_relative_path:
        return []
    safe_parts = [part for part in raw_relative_path.split("/") if part not in {"", ".", ".."}]
    return [_sanitize_storage_segment(part, fallback="item") for part in safe_parts]


def _copy_local_import_source(
    *,
    settings: Settings,
    local_model_id: str,
    source_path: Path,
    relative_path: str | None = None,
    preserve_folder_structure: bool = True,
) -> str:
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
    
    destination_directory = asset_root
    destination_filename = source_path.name

    if preserve_folder_structure:
        safe_parts = _normalized_relative_parts(relative_path)
        if safe_parts:
            relative = Path(*safe_parts)
            destination_directory = (asset_root / relative.parent).resolve() if str(relative.parent) not in {"", "."} else asset_root
            destination_filename = _sanitize_storage_segment(relative.name or source_path.name, fallback=source_path.name)
            if not destination_directory.is_relative_to(asset_root.resolve()):
                destination_directory = asset_root
                destination_filename = _sanitize_storage_segment(source_path.name, fallback="file")

    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination_path(destination_directory, destination_filename)
    shutil.copy2(str(source_path), str(destination))
    try:
        relative_path = destination.relative_to(catalog_root.resolve())
        return str(relative_path).replace("\\", "/")
    except ValueError:
        return str(destination).replace("\\", "/")


def _move_file_to_working_directory(
    *,
    settings: Settings,
    working_group_slug: str,
    source_path: Path,
    relative_path: str | None = None,
    preserve_folder_structure: bool = True,
    cleanup_policy: str = "keep",
) -> str:
    """Copy or move a file from intake source to the Working Files directory structure.
    
    When *cleanup_policy* is ``"keep"`` the source file is **copied** so the
    original inbox location remains untouched.  For destructive policies
    (``"delete_on_verified"``, ``"replace_with_stub"``) the file is **moved**
    so the downstream cleanup step does not need to delete it separately.

    Returns the ABSOLUTE path to the destination file so it can be found by
    the inventory system.
    """
    import shutil
    from ..services.working_groups_service import _working_files_destination_root, _unique_destination_path
    
    working_root = _working_files_destination_root(settings)
    if not working_root:
        raise ValueError("No working files root configured")
    
    # Create directory for this working group
    group_dir = working_root / working_group_slug
    group_dir.mkdir(parents=True, exist_ok=True)
    
    destination_directory = group_dir
    destination_filename = source_path.name
    if preserve_folder_structure:
        safe_parts = _normalized_relative_parts(relative_path)
        if safe_parts:
            relative = Path(*safe_parts)
            destination_directory = (group_dir / relative.parent).resolve() if str(relative.parent) not in {"", "."} else group_dir
            destination_filename = _sanitize_storage_segment(relative.name or source_path.name, fallback=source_path.name)
            if not destination_directory.is_relative_to(group_dir.resolve()):
                destination_directory = group_dir
                destination_filename = _sanitize_storage_segment(source_path.name, fallback="file")

    destination_directory.mkdir(parents=True, exist_ok=True)
    # Find unique destination path
    destination = _unique_destination_path(destination_directory, destination_filename)
    
    # Copy when policy is "keep" so source inbox stays untouched;
    # move for destructive policies so cleanup doesn't double-delete.
    if cleanup_policy == "keep":
        shutil.copy2(str(source_path), str(destination))
    else:
        shutil.move(str(source_path), str(destination))
    
    # Return ABSOLUTE path so the destination file can be found by the inventory system
    return str(destination.resolve())


def _expand_intake_source_entries(*, source_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand source entries into individual files."""
    from ..services.shared_helpers import _sha256_file
    
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    exclusion_exact_keys, exclusion_folder_prefixes = _compile_source_entry_exclusions(source_entries)

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
            candidate_paths = _collect_intake_source_files_in_folder(source_path, recurse=recurse)

        for file_path in sorted(candidate_paths):
            normalized_path = str(file_path.resolve())
            if normalized_path in seen_paths:
                continue
            if _is_excluded_source_file(
                file_path=file_path,
                exclusion_exact_keys=exclusion_exact_keys,
                exclusion_folder_prefixes=exclusion_folder_prefixes,
            ):
                continue
            if file_path.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
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

            relative_path_value = ""
            if entry_type == "folder":
                try:
                    relative_path_value = str(file_path.relative_to(source_path)).replace("\\", "/")
                except ValueError:
                    relative_path_value = file_path.name
            else:
                relative_path_value = str(entry.get("relative_path") or "").strip().replace("\\", "/") or file_path.name

            source_metadata = _bulk_path_source_metadata(file_path, stat_result)
            if entry_type == "file":
                for key in ("source_mtime", "source_ctime", "source_birthtime"):
                    override_value = str(entry.get(key) or "").strip()
                    if override_value:
                        source_metadata[key] = override_value

            expanded.append(
                {
                    "path": normalized_path,
                    "filename": file_path.name,
                    "relative_path": relative_path_value,
                    "entry_type": entry_type,
                    "source_entry": entry,
                    "source_metadata": source_metadata,
                    "file_hash": file_hash,
                    "size_bytes": int(stat_result.st_size),
                }
            )
            seen_paths.add(normalized_path)

    return expanded, warnings


def _source_timestamp_summary(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Build min/max summary of source timestamps captured for a publish batch."""
    mtimes = [
        str((item.get("source_metadata") or {}).get("source_mtime") or "").strip()
        for item in files
        if isinstance(item, dict)
    ]
    ctimes = [
        str((item.get("source_metadata") or {}).get("source_ctime") or "").strip()
        for item in files
        if isinstance(item, dict)
    ]
    birthtimes = [
        str((item.get("source_metadata") or {}).get("source_birthtime") or "").strip()
        for item in files
        if isinstance(item, dict)
    ]
    mtimes = sorted([value for value in mtimes if value])
    ctimes = sorted([value for value in ctimes if value])
    birthtimes = sorted([value for value in birthtimes if value])

    summary: dict[str, Any] = {
        "file_count": len(files),
        "earliest_source_mtime": mtimes[0] if mtimes else None,
        "latest_source_mtime": mtimes[-1] if mtimes else None,
        "earliest_source_ctime": ctimes[0] if ctimes else None,
        "latest_source_ctime": ctimes[-1] if ctimes else None,
    }
    if birthtimes:
        summary["earliest_source_birthtime"] = birthtimes[0]
        summary["latest_source_birthtime"] = birthtimes[-1]
    return summary


def _append_intake_publish_history(*, db_path: Path, model_ref: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    existing = read_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history")
    history = existing if isinstance(existing, list) else []
    history.append(entry)
    trimmed = history[-20:]
    set_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history", field_value=trimmed)
    return trimmed


def _extract_grouping_preferences(source_entries: list[dict[str, Any]]) -> tuple[str, bool]:
    strategy = "none"
    preserve_folder_structure = True
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        if strategy == "none":
            strategy = _normalize_grouping_strategy(entry.get("grouping_strategy"))
        if "preserve_folder_structure" in entry:
            preserve_folder_structure = _coerce_bool(entry.get("preserve_folder_structure"))
    return strategy, preserve_folder_structure


def _build_publish_groups(
    *,
    source_entries: list[dict[str, Any]],
    expanded_files: list[dict[str, Any]],
    default_title: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan = _plan_intake_groups(source_entries=source_entries, expanded_files=expanded_files)
    planned_groups = [dict(group) for group in list(plan.get("groups") or [])]

    if not planned_groups and expanded_files:
        planned_groups = [
            {
                "title": default_title or _default_group_title(source_entries, expanded_files),
                "files": list(expanded_files),
                "strategy": "none",
                "preserve_folder_structure": True,
                "source_entries": list(source_entries),
            }
        ]

    for group in planned_groups:
        group_files = list(group.get("files") or [])
        if not str(group.get("title") or "").strip():
            group["title"] = default_title or _default_group_title(source_entries, group_files)

    return planned_groups, dict(plan.get("summary") or {})


def _planned_group_source_entries(group: dict[str, Any]) -> list[dict[str, Any]]:
    group_source_entries = group.get("source_entries")
    if isinstance(group_source_entries, list):
        return [entry for entry in group_source_entries if isinstance(entry, dict)]
    return []


def _publish_group_to_local_destination(
    *,
    state: AppState,
    upload_id: str,
    source_entries: list[dict[str, Any]],
    group: dict[str, Any],
    destination_plan: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    group_files = list(group.get("files") or [])
    if not group_files:
        return None, [], []

    requested_model_ref = str(destination_plan.get("model_ref") or destination_plan.get("local_model_id") or "").strip()
    requested_model_name = str(destination_plan.get("model_name") or group.get("title") or "").strip()
    requested_description = str(destination_plan.get("description") or "").strip()
    requested_tags = destination_plan.get("tags") if isinstance(destination_plan.get("tags"), list) else None
    requested_collection_names = destination_plan.get("collection_names") if isinstance(destination_plan.get("collection_names"), list) else None
    requested_creator_name = str(destination_plan.get("creator_name") or "").strip() or None
    requested_created_by = str(destination_plan.get("created_by") or "intake_queue").strip() or "intake_queue"
    requested_source_origin = str(destination_plan.get("source_origin") or "intake_queue").strip() or "intake_queue"
    requested_source_origin_url = str(destination_plan.get("source_origin_url") or f"intake://uploads/{upload_id}").strip()
    requested_preview_source_path = str(destination_plan.get("preview_source_path") or "").strip()
    group_title = str(group.get("title") or requested_model_name or "Working Group").strip() or "Working Group"
    preserve_folder_structure = _coerce_bool(group.get("preserve_folder_structure", True))
    grouping_strategy = str(group.get("strategy") or "none").strip() or "none"
    source_timestamp_summary = _source_timestamp_summary(group_files)

    local_model_id = requested_model_ref
    target_entry = read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id) if local_model_id else None
    created_model = False

    if target_entry is None:
        preferred_model_id = local_model_id or _slugify_title(group_title) or upload_id
        local_model_id = _ensure_unique_local_model_id(db_path=state.settings.db_path, preferred=preferred_model_id)
        create_local_model(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            model_name=requested_model_name or group_title,
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
        update_local_model(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            model_name=None,
            model_description=requested_description or None,
            creator_name=requested_creator_name,
            created_by=requested_created_by,
            collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
            tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
            keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
            source_origin=requested_source_origin,
            source_origin_url=requested_source_origin_url or None,
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
    preview_source_normalized = requested_preview_source_path.lower() if requested_preview_source_path else None

    imported_assets: list[dict[str, Any]] = []
    duplicate_skipped: list[dict[str, Any]] = []
    failed_files: list[dict[str, Any]] = []

    for file_item in group_files:
        source_path = Path(str(file_item["path"])).resolve()
        file_hash = str(file_item["file_hash"] or "").strip().lower()
        if file_hash in existing_hashes:
            duplicate_skipped.append({
                "source_path": str(source_path),
                "filename": source_path.name,
                "sha256": file_hash,
                "reason": "duplicate_hash",
            })
            continue

        try:
            storage_path = _copy_local_import_source(
                settings=state.settings,
                local_model_id=local_model_id,
                source_path=source_path,
                relative_path=str(file_item.get("relative_path") or "").strip() or source_path.name,
                preserve_folder_structure=preserve_folder_structure,
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
            imported_assets.append({
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
            })
        except Exception as exc:
            failed_files.append({
                "source_path": str(source_path),
                "filename": source_path.name,
                "message": str(exc),
                "local_model_id": local_model_id,
            })

    _append_intake_publish_history(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        entry={
            "upload_id": upload_id,
            "published_at": _bulk_utc_now_iso(),
            "source_timestamp_summary": source_timestamp_summary,
            "created_model": created_model,
            "grouping_strategy": grouping_strategy,
            "preserve_folder_structure": preserve_folder_structure,
            "imported_asset_count": len(imported_assets),
            "duplicate_skipped_count": len(duplicate_skipped),
            "failed_file_count": len(failed_files),
            "source_entries": source_entries,
        },
    )
    set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="intake_queue_upload_id", field_value=upload_id)
    set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="intake_source_entries", field_value=source_entries)
    set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="intake_source_timestamp_summary", field_value=source_timestamp_summary)
    set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="intake_imported_at", field_value=_bulk_utc_now_iso())
    set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="internal_notes", field_value=f"Imported from intake upload {upload_id}")

    return {
        "destination": "curated",
        "match_mode": "existing" if requested_model_ref else "new",
        "group_title": group_title,
        "grouping_strategy": grouping_strategy,
        "preserve_folder_structure": preserve_folder_structure,
        "local_model_id": local_model_id,
        "model_ref": local_model_id,
        "created_model": created_model,
        "imported_asset_count": len(imported_assets),
        "duplicate_skipped_count": len(duplicate_skipped),
        "failed_file_count": len(failed_files),
        "imported_assets": imported_assets,
        "duplicate_skipped": duplicate_skipped,
        "failed_files": failed_files,
    }, imported_assets, failed_files


def _publish_group_to_working_destination(
    *,
    state: AppState,
    upload_id: str,
    source_entries: list[dict[str, Any]],
    group: dict[str, Any],
    destination_plan: dict[str, Any],
    cleanup_policy: str = "keep",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    group_files = list(group.get("files") or [])
    if not group_files:
        return None, [], []

    from ..services.working_groups_service import _working_files_destination_root

    working_root = _working_files_destination_root(state.settings)
    if not working_root:
        raise ValueError("No working files root configured")

    requested_group_id = int(destination_plan.get("working_group_id") or 0)
    requested_stage = str(destination_plan.get("stage") or "draft").strip() or "draft"
    requested_notes = str(destination_plan.get("notes") or "").strip()
    group_title = str(destination_plan.get("title") or group.get("title") or "Working Group").strip() or "Working Group"
    group_strategy = str(group.get("strategy") or "none").strip() or "none"
    preserve_folder_structure = _coerce_bool(group.get("preserve_folder_structure", True))
    group_source_entries = _planned_group_source_entries(group) or source_entries
    source_timestamp_summary = _source_timestamp_summary(group_files)

    added_items = 0
    duplicate_items = 0
    primary_file_path = None
    working_group_id = requested_group_id if requested_group_id > 0 else None

    wg_connection = connect(state.settings.db_path)
    wg_connection.row_factory = __import__("sqlite3").Row
    try:
        now_iso = _bulk_utc_now_iso()
        if working_group_id is None:
            slug_base = _slugify_title(group_title) or f"import-{upload_id[:8]}"
            counter = 0
            candidate_slug = slug_base
            while wg_connection.execute("SELECT id FROM working_groups WHERE slug = ?", (candidate_slug,)).fetchone() is not None:
                counter += 1
                candidate_slug = f"{slug_base}-{counter}"
            group_folder_hint = str(Path(group_files[0]["path"]).parent) if group_files else None
            wg_connection.execute(
                """
                INSERT INTO working_groups (
                    slug, title, stage, notes, primary_file_path, folder_hint,
                    related_model_id, created_at, updated_at,
                    discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_slug,
                    group_title,
                    requested_stage,
                    requested_notes or f"Created from intake upload {upload_id}",
                    None,
                    group_folder_hint,
                    None,
                    now_iso,
                    now_iso,
                    group_folder_hint,
                    group_strategy,
                    now_iso,
                    json.dumps({
                        "source": "intake",
                        "upload_id": upload_id,
                        "imported_at": now_iso,
                        "source_timestamp_summary": source_timestamp_summary,
                        "grouping_strategy": group_strategy,
                        "preserve_folder_structure": preserve_folder_structure,
                        "group_title": group_title,
                        "group_source_entries": group_source_entries,
                    }),
                ),
            )
            working_group_id = int(wg_connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
        else:
            existing_group = wg_connection.execute("SELECT * FROM working_groups WHERE id = ?", (working_group_id,)).fetchone()
            if existing_group is None:
                raise LookupError(f"Working group not found: {working_group_id}")
            candidate_slug = str(existing_group["slug"] or "").strip()

        for file_item in group_files:
            source_file_path = Path(str(file_item["path"])).resolve()
            file_hash = str(file_item.get("file_hash") or "").strip().lower() or None
            existing_item = wg_connection.execute(
                "SELECT id FROM working_items WHERE working_group_id = ? AND file_hash = ?",
                (working_group_id, file_hash),
            ).fetchone() if file_hash else None
            if existing_item is not None:
                duplicate_items += 1
                continue
            if file_hash:
                existing_hash_match = wg_connection.execute("SELECT id FROM working_items WHERE file_hash = ?", (file_hash,)).fetchone()
                if existing_hash_match is not None:
                    duplicate_items += 1
                    continue
            moved_path = _move_file_to_working_directory(
                settings=state.settings,
                working_group_slug=candidate_slug,
                source_path=source_file_path,
                relative_path=str(file_item.get("relative_path") or "").strip() or source_file_path.name,
                preserve_folder_structure=preserve_folder_structure,
                cleanup_policy=cleanup_policy,
            )
            file_path = str(moved_path)
            item_role = "primary" if primary_file_path is None and requested_group_id <= 0 else "supporting"
            if primary_file_path is None:
                primary_file_path = file_path
            wg_connection.execute(
                """
                INSERT INTO working_items (
                    working_group_id, file_path, item_role, created_at, updated_at,
                    file_hash, file_size, source_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    working_group_id,
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

        if primary_file_path and requested_group_id <= 0:
            wg_connection.execute("UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?", (primary_file_path, now_iso, working_group_id))
        else:
            wg_connection.execute("UPDATE working_groups SET updated_at = ? WHERE id = ?", (now_iso, working_group_id))

        wg_connection.commit()
        group_row = wg_connection.execute("SELECT * FROM working_groups WHERE id = ?", (working_group_id,)).fetchone()
        serialized_group = _serialize_working_group(wg_connection, group_row, state.settings) if group_row else None
    finally:
        wg_connection.close()

    return {
        "destination": "working",
        "match_mode": "existing" if requested_group_id > 0 else "new",
        "group_title": group_title,
        "grouping_strategy": group_strategy,
        "preserve_folder_structure": preserve_folder_structure,
        "working_group_id": working_group_id,
        "added_items": added_items,
        "duplicate_items": duplicate_items,
        "group": serialized_group,
    }, [{
        "file_hash": str(file_item.get("file_hash") or "").strip().lower(),
        "source_path": str(file_item.get("path") or ""),
    } for file_item in group_files if str(file_item.get("file_hash") or "").strip()], []


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

@router.post("/api/intake/uploads/{upload_id}/publish-by-destination")
def intake_upload_publish_by_destination(request: Request, upload_id: str, payload: dict[str, Any] | None = None) -> Any:
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
        return JSONResponse(status_code=404, content={"success": False, "error": "upload_not_found", "message": f"Upload not found: {upload_id}"})

    current_state = str(upload_row["inbox_state"] or "").strip().lower() or "submitted"
    current_status = str(upload_row["status"] or "").strip().lower()
    is_eligible, reason_code = ActionEligibility.validate_action_eligibility(current_state, ActionEligibility.PUBLISH_CATALOG)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot commit item in state '{current_state}': {reason_code}",
                "upload_id": upload_id,
                "current_state": current_state,
                "allowed_actions": ActionEligibility.build_allowed_actions_payload(current_state).get("allowed_actions", []),
            },
        )
    if current_status != "queued":
        return JSONResponse(status_code=409, content={"success": False, "error": "upload_not_publishable", "message": f"Upload is in '{current_status}' state. Only 'queued' uploads can be committed by destination.", "upload_id": upload_id})

    source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list) or not source_entries:
        return JSONResponse(status_code=400, content={"success": False, "error": "upload_has_no_sources", "message": "Upload does not contain any source entries.", "upload_id": upload_id})

    expanded_files, expansion_warnings = _expand_intake_source_entries(source_entries=source_entries)
    if not expanded_files:
        return JSONResponse(status_code=400, content={"success": False, "error": "no_files_to_publish", "message": "Upload did not resolve to any readable supported files.", "upload_id": upload_id, "warnings": expansion_warnings})

    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "uploading",
        event_type="destination_publish_started",
        metadata={"source_entry_count": len(source_entries), "file_count": len(expanded_files)},
    )
    if not transitioned:
        return JSONResponse(status_code=409, content={"success": False, "error": "status_transition_failed", "message": transition_error or "Could not transition upload to uploading.", "upload_id": upload_id})

    planned_groups, plan_summary = _build_publish_groups(
        source_entries=source_entries,
        expanded_files=expanded_files,
        default_title=_default_group_title(source_entries, expanded_files) or upload_id,
    )
    destination_plans = payload.get("group_destinations") if isinstance(payload.get("group_destinations"), list) else []
    if len(destination_plans) != len(planned_groups):
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_group_destinations", "message": "group_destinations must include one entry for each planned group.", "upload_id": upload_id, "planned_group_count": len(planned_groups)})

    # Issue #1307: accept an optional cleanup_policy override in the payload so the
    # wizard's Commit step can change the policy without invalidating the prepared
    # upload + revalidating. Persist the new value on the upload row before any
    # downstream cleanup logic reads it.
    raw_cleanup_policy = payload.get("cleanup_policy")
    if isinstance(raw_cleanup_policy, str):
        candidate_policy = raw_cleanup_policy.strip().lower()
        if candidate_policy in {"keep", "delete_on_verified", "replace_with_stub"}:
            current_policy = str(upload_row["cleanup_policy"] or "keep").strip().lower()
            if candidate_policy != current_policy:
                policy_connection = connect(state.settings.db_path)
                try:
                    policy_connection.execute(
                        "UPDATE intake_queue_uploads SET cleanup_policy = ?, updated_at = ? WHERE upload_id = ?",
                        (candidate_policy, _bulk_utc_now_iso(), upload_id),
                    )
                    policy_connection.commit()
                finally:
                    policy_connection.close()
                # Refresh the in-memory row reference so any subsequent read in this
                # request sees the new value.
                refresh_connection = connect(state.settings.db_path)
                refresh_connection.row_factory = __import__("sqlite3").Row
                try:
                    upload_row = refresh_connection.execute(
                        "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
                        (upload_id,),
                    ).fetchone() or upload_row
                finally:
                    refresh_connection.close()

    results: list[dict[str, Any]] = []
    imported_rows: list[dict[str, Any]] = []
    failed_files: list[dict[str, Any]] = []
    curated_model_ids: list[str] = []
    working_group_ids: list[int] = []

    try:
        for index, group in enumerate(planned_groups):
            destination_plan = destination_plans[index] if isinstance(destination_plans[index], dict) else {}
            destination_kind = str(destination_plan.get("destination") or "curated").strip().lower()
            group_source_entries = _planned_group_source_entries(group) or source_entries
            if destination_kind == "working":
                group_result, group_rows, group_failures = _publish_group_to_working_destination(
                    state=state,
                    upload_id=upload_id,
                    source_entries=group_source_entries,
                    group=group,
                    destination_plan=destination_plan,
                    cleanup_policy=str(upload_row["cleanup_policy"] or "keep").strip().lower(),
                )
                if group_result is not None and group_result.get("working_group_id"):
                    working_group_ids.append(int(group_result["working_group_id"]))
            else:
                group_result, group_rows, group_failures = _publish_group_to_local_destination(
                    state=state,
                    upload_id=upload_id,
                    source_entries=group_source_entries,
                    group=group,
                    destination_plan=destination_plan,
                )
                if group_result is not None and group_result.get("local_model_id"):
                    curated_model_ids.append(str(group_result["local_model_id"]))
            if group_result is not None:
                group_result["group_index"] = index
                results.append(group_result)
            imported_rows.extend(group_rows)
            failed_files.extend(group_failures)
    except LookupError as exc:
        _transition_queue_status(state.settings.db_path, upload_id, "failed", event_type="destination_publish_failed", error_message=str(exc))
        return JSONResponse(status_code=404, content={"success": False, "error": "destination_lookup_failed", "message": str(exc), "upload_id": upload_id})
    except Exception as exc:
        _transition_queue_status(state.settings.db_path, upload_id, "failed", event_type="destination_publish_failed", error_message=str(exc))
        return JSONResponse(status_code=500, content={"success": False, "error": "destination_publish_failed", "message": str(exc), "upload_id": upload_id})

    now_iso = _bulk_utc_now_iso()
    success_connection = connect(state.settings.db_path)
    try:
        success_connection.execute(
            """
            UPDATE intake_queue_uploads
            SET file_hashes_json = ?, verification_status = ?, inbox_state = ?, updated_at = ?,
                terminal_action = ?, terminal_at = ?, terminal_actor = ?, terminal_result_id = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps([row.get("file_hash") for row in imported_rows if row.get("file_hash")]),
                "pass",
                "published_by_destination",
                now_iso,
                "published_by_destination",
                now_iso,
                _normalize_terminal_actor("wizard_direct"),
                json.dumps(
                    {
                        "kind": "destination_publish",
                        "curated_model_ids": curated_model_ids,
                        "working_group_ids": working_group_ids,
                        "group_results": [
                            {
                                "destination": str(result.get("destination") or "").strip().lower(),
                                "match_mode": str(result.get("match_mode") or "").strip().lower(),
                                "result_id": str(result.get("local_model_id") or result.get("working_group_id") or "").strip(),
                                "local_model_id": result.get("local_model_id"),
                                "working_group_id": result.get("working_group_id"),
                            }
                            for result in results
                            if isinstance(result, dict)
                        ],
                    }
                ),
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
        event_type="destination_publish_materialized",
        metadata={"curated_model_ids": curated_model_ids, "working_group_ids": working_group_ids, "group_count": len(results)},
    )
    if transitioned:
        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "verified",
            event_type="destination_publish_verified",
            metadata={"curated_model_ids": curated_model_ids, "working_group_ids": working_group_ids},
        )

    if not transitioned:
        _remove_browser_upload_staging(state.settings, source_entries)
        return JSONResponse(status_code=409, content={"success": False, "error": "status_transition_failed", "message": transition_error or "Could not finalize destination publish state.", "upload_id": upload_id})

    cleanup_ok, cleanup_result, effective_status = _run_publish_finalize(
        request=request,
        upload_id=upload_id,
        source_entries=source_entries,
        imported_rows=imported_rows,
        cleanup_policy=str(upload_row["cleanup_policy"] or "keep").strip().lower(),
    )
    if not cleanup_ok:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": cleanup_result.get("error") or "cleanup_failed",
                "message": cleanup_result.get("message") or "Cleanup could not be started.",
                "upload_id": upload_id,
            },
        )

    return {
        "success": True,
        "contract": "intake-publish-by-destination.v1alpha1",
        "upload_id": upload_id,
        "status": effective_status,
        "verification_status": "pass",
        "state": "published_by_destination",
        "is_terminal": True,
        "allowed_actions": [],
        "plan_summary": plan_summary,
        "warnings": expansion_warnings,
        "group_results": results,
        "curated_model_ids": curated_model_ids,
        "working_group_ids": working_group_ids,
        "failed_files": failed_files,
        "cleanup": cleanup_result,
    }

@router.post("/api/intake/uploads/{upload_id}/publish-to-local")
def intake_upload_publish_to_local(request: Request, upload_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Publish a queued or reviewed intake upload into the local-authority catalog.
    
    Transitions from validated_ready → published_to_catalog (terminal state).
    This is the authoritative intake sink for reviewed queue/source inputs.
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
    default_model_title = requested_model_name or _default_group_title(source_entries, expanded_files) or "Working Group"
    planned_groups, plan_summary = _build_publish_groups(
        source_entries=source_entries,
        expanded_files=expanded_files,
        default_title=default_model_title,
    )
    grouping_strategy = str(plan_summary.get("grouping_strategy") or "none")
    preserve_folder_structure = plan_summary.get("preserve_folder_structure")

    if len(planned_groups) > 1:
        if requested_model_ref:
            _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="local_publish_failed",
                error_message="Cannot publish grouped intake batch to a single requested model_ref.",
            )
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "grouped_publish_requires_auto_model_creation",
                    "message": "Grouped publish does not support model_ref override.",
                    "upload_id": upload_id,
                },
            )
        created_models: list[dict[str, Any]] = []
        imported_assets: list[dict[str, Any]] = []
        duplicate_skipped: list[dict[str, Any]] = []
        failed_files: list[dict[str, Any]] = []

        for group in planned_groups:
            group_title = str(group.get("title") or "").strip() or "Working Group"
            group_files = list(group.get("files") or [])
            group_strategy = str(group.get("strategy") or "none").strip() or "none"
            group_preserve_folder_structure = _coerce_bool(group.get("preserve_folder_structure", True))
            preferred_model_id = _slugify_title(group_title) or upload_id
            local_model_id = _ensure_unique_local_model_id(db_path=state.settings.db_path, preferred=preferred_model_id)

            model_entry = create_local_model(
                db_path=state.settings.db_path,
                local_model_id=local_model_id,
                model_name=group_title,
                model_description=requested_description or None,
                creator_name=requested_creator_name,
                created_by=requested_created_by,
                collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
                tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                source_origin=requested_source_origin,
                source_origin_url=requested_source_origin_url or None,
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
            preview_source_normalized = requested_preview_source_path.lower() if requested_preview_source_path else None

            group_imported_count = 0
            for file_item in group_files:
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
                        relative_path=str(file_item.get("relative_path") or "").strip() or source_path.name,
                        preserve_folder_structure=group_preserve_folder_structure,
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
                    group_imported_count += 1
                except Exception as exc:
                    failed_files.append(
                        {
                            "source_path": str(source_path),
                            "filename": source_path.name,
                            "message": str(exc),
                            "local_model_id": local_model_id,
                        }
                    )

            _append_intake_publish_history(
                db_path=state.settings.db_path,
                model_ref=local_model_id,
                entry={
                    "upload_id": upload_id,
                    "published_at": _bulk_utc_now_iso(),
                    "created_model": True,
                    "grouping_strategy": group_strategy,
                    "preserve_folder_structure": group_preserve_folder_structure,
                    "imported_asset_count": group_imported_count,
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

            created_models.append(
                {
                    "local_model_id": model_entry.local_model_id,
                    "model_name": model_entry.model_name,
                    "imported_asset_count": group_imported_count,
                }
            )

        if not imported_assets:
            _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="local_publish_failed",
                error_message="No assets were imported into local models.",
                metadata={
                    "grouping_strategy": grouping_strategy,
                    "preserve_folder_structure": preserve_folder_structure,
                    "failed_file_count": len(failed_files),
                },
            )
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "local_publish_failed",
                    "message": "No assets were imported into local models.",
                    "upload_id": upload_id,
                    "grouping_strategy": grouping_strategy,
                    "preserve_folder_structure": preserve_folder_structure,
                    "failed_files": failed_files,
                },
            )

        now_iso = _bulk_utc_now_iso()
        success_connection = connect(state.settings.db_path)
        try:
            success_connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?, verification_status = ?, inbox_state = ?, updated_at = ?,
                    terminal_action = ?, terminal_at = ?, terminal_actor = ?,
                    terminal_result_id = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps([item["file_hash"] for item in imported_assets]),
                    "pass",
                    "published_to_catalog",
                    now_iso,
                    "published_to_catalog",
                    now_iso,
                    _normalize_terminal_actor("queue_processed"),
                    str(created_models[0].get("local_model_id") or ""),
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
                "grouping_strategy": grouping_strategy,
                "preserve_folder_structure": preserve_folder_structure,
                "created_model_count": len(created_models),
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
                    "created_models": created_models,
                },
            )

        if not transitioned:
            _remove_browser_upload_staging(state.settings, source_entries)
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "status_transition_failed",
                    "message": transition_error or "Could not finalize local publish state.",
                    "upload_id": upload_id,
                },
            )

        cleanup_ok, cleanup_result, effective_status = _run_publish_finalize(
            request=request,
            upload_id=upload_id,
            source_entries=source_entries,
            imported_rows=imported_assets,
            cleanup_policy=str(upload_row["cleanup_policy"] or "keep").strip().lower(),
        )
        if not cleanup_ok:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": cleanup_result.get("error") or "cleanup_failed",
                    "message": cleanup_result.get("message") or "Cleanup could not be started.",
                    "upload_id": upload_id,
                },
            )

        return {
            "success": True,
            "contract": "intake-publish-local.v1alpha1",
            "upload_id": upload_id,
            "status": effective_status,
            "verification_status": "pass",
            "grouping_strategy": grouping_strategy,
            "preserve_folder_structure": preserve_folder_structure,
            "created_model_count": len(created_models),
            "created_models": created_models,
            "imported_asset_count": len(imported_assets),
            "duplicate_skipped_count": len(duplicate_skipped),
            "failed_file_count": len(failed_files),
            "imported_assets": imported_assets,
            "duplicate_skipped": duplicate_skipped,
            "failed_files": failed_files,
            "warnings": expansion_warnings,
            "cleanup": cleanup_result,
            "plan_summary": plan_summary,
            "terminal": True,
            "state": "published_to_catalog",
            "is_terminal": True,
            "allowed_actions": [],
            "legacy_adapter": {
                "upload_to_catalog_route": f"/api/intake/uploads/{quote(upload_id, safe='')}/upload-to-catalog",
                "authoritative": False,
                "status": "transition_only",
            },
            "model": None,
            "enrichment": None,
        }

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
                relative_path=str(file_item.get("relative_path") or "").strip() or source_path.name,
                preserve_folder_structure=preserve_folder_structure,
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
                SET file_hashes_json = ?, verification_status = ?, inbox_state = ?, updated_at = ?,
                    terminal_action = ?, terminal_at = ?, terminal_actor = ?,
                    terminal_result_id = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps([item["file_hash"] for item in imported_assets]),
                    "pass",
                    "published_to_catalog",
                    now_iso,
                    "published_to_catalog",
                    now_iso,
                    _normalize_terminal_actor("queue_processed"),
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
        _remove_browser_upload_staging(state.settings, source_entries)
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

    cleanup_ok, cleanup_result, effective_status = _run_publish_finalize(
        request=request,
        upload_id=upload_id,
        source_entries=source_entries,
        imported_rows=imported_assets,
        cleanup_policy=str(upload_row["cleanup_policy"] or "keep").strip().lower(),
    )
    if not cleanup_ok:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": cleanup_result.get("error") or "cleanup_failed",
                "message": cleanup_result.get("message") or "Cleanup could not be started.",
                "upload_id": upload_id,
                "local_model_id": local_model_id,
            },
        )

    detail_payload = build_model_detail_response(
        state,
        request.app.state.catalog_client,
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
        "grouping_strategy": grouping_strategy,
        "preserve_folder_structure": preserve_folder_structure,
        "plan_summary": plan_summary,
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
            "upload_to_catalog_route": f"/api/intake/uploads/{quote(upload_id, safe='')}/upload-to-catalog",
            "authoritative": False,
            "status": "transition_only",
        },
        "model": detail_payload.get("model") if isinstance(detail_payload, dict) else None,
        "enrichment": detail_payload.get("enrichment") if isinstance(detail_payload, dict) else None,
    }


@router.post("/api/intake/uploads/{upload_id}/publish-to-working")
def intake_upload_publish_to_working(request: Request, upload_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Publish a queued or reviewed intake upload into a working group.
    
    Transitions from validated_ready → grouped_new (terminal state).
    Creates a new working group from the intake upload's source entries.
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
    
    # Check eligibility: can publish to working from submitted, validated_ready, or deferred states
    is_eligible, reason_code = ActionEligibility.validate_action_eligibility(current_state, ActionEligibility.GROUP_NEW)
    if not is_eligible:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": reason_code,
                "message": f"Cannot group item in state '{current_state}': {reason_code}",
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
                    "published to working."
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
            event_type="working_group_publish_failed",
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
        event_type="working_group_publish_started",
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

    # Extract requested metadata
    requested_title = str(payload.get("title") or "").strip()
    requested_stage = str(payload.get("stage") or "draft").strip() or "draft"
    requested_notes = str(payload.get("notes") or "").strip()

    # Generate default title from source entries
    default_title = requested_title or _default_group_title(source_entries, expanded_files) or f"Import from {upload_id}"
    folder_hint = str(Path(expanded_files[0]["path"]).parent) if expanded_files else None
    planned_groups, plan_summary = _build_publish_groups(
        source_entries=source_entries,
        expanded_files=expanded_files,
        default_title=default_title,
    )
    grouping_strategy = str(plan_summary.get("grouping_strategy") or "none")
    preserve_folder_structure = plan_summary.get("preserve_folder_structure")

    # Check if working files root is configured BEFORE trying to move files
    from ..services.working_groups_service import _working_files_destination_root
    working_root = _working_files_destination_root(state.settings)
    if not working_root:
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="working_group_publish_failed",
            error_message="No working files root configured. Cannot publish to working files.",
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "working_files_root_not_configured",
                "message": "Server is not configured with a working files root directory. Contact administrator.",
                "upload_id": upload_id,
            },
        )

    # Create working group(s) and add items
    working_group_id = None
    added_items = 0
    duplicate_items = 0
    created_groups_meta: list[dict[str, Any]] = []

    wg_connection = connect(state.settings.db_path)
    wg_connection.row_factory = __import__("sqlite3").Row
    try:
        now_iso = _bulk_utc_now_iso()
        
        for group in planned_groups:
            group_files = list(group.get("files") or [])
            group_title = str(group.get("title") or "").strip() or default_title
            group_strategy = str(group.get("strategy") or "none").strip() or "none"
            group_preserve_folder_structure = _coerce_bool(group.get("preserve_folder_structure", True))
            slug_base = _slugify_title(group_title) or f"import-{upload_id[:8]}"

            counter = 0
            candidate_slug = slug_base
            while wg_connection.execute(
                "SELECT id FROM working_groups WHERE slug = ?", (candidate_slug,)
            ).fetchone() is not None:
                counter += 1
                candidate_slug = f"{slug_base}-{counter}"

            group_folder_hint = str(Path(group_files[0]["path"]).parent) if group_files else folder_hint

            wg_connection.execute(
                """
                INSERT INTO working_groups (
                    slug, title, stage, notes, primary_file_path, folder_hint,
                    related_model_id, created_at, updated_at,
                    discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_slug,
                    group_title,
                    requested_stage,
                    requested_notes or f"Created from intake upload {upload_id}",
                    None,
                    group_folder_hint,
                    None,
                    now_iso,
                    now_iso,
                    group_folder_hint,
                    group_strategy,
                    now_iso,
                    json.dumps(
                        {
                            "source": "intake",
                            "upload_id": upload_id,
                            "imported_at": now_iso,
                            "source_timestamp_summary": _source_timestamp_summary(group_files),
                            "grouping_strategy": group_strategy,
                            "preserve_folder_structure": group_preserve_folder_structure,
                            "group_title": group_title,
                        }
                    ),
                ),
            )
            created_group_id = int(wg_connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
            if working_group_id is None:
                working_group_id = created_group_id

            group_added_items = 0
            group_duplicate_items = 0
            primary_file_path = None
            for file_item in group_files:
                source_file_path = Path(str(file_item["path"])).resolve()
                file_hash = str(file_item.get("file_hash") or "").strip().lower() or None

                existing_item = wg_connection.execute(
                    "SELECT id FROM working_items WHERE working_group_id = ? AND file_hash = ?",
                    (created_group_id, file_hash),
                ).fetchone() if file_hash else None
                if existing_item is not None:
                    duplicate_items += 1
                    group_duplicate_items += 1
                    continue

                if file_hash:
                    existing_hash_match = wg_connection.execute(
                        "SELECT id FROM working_items WHERE file_hash = ?",
                        (file_hash,),
                    ).fetchone()
                    if existing_hash_match is not None:
                        duplicate_items += 1
                        group_duplicate_items += 1
                        continue

                moved_path = _move_file_to_working_directory(
                    settings=state.settings,
                    working_group_slug=candidate_slug,
                    source_path=source_file_path,
                    relative_path=str(file_item.get("relative_path") or "").strip() or source_file_path.name,
                    preserve_folder_structure=group_preserve_folder_structure,
                    cleanup_policy=str(upload_row["cleanup_policy"] or "keep").strip().lower(),
                )
                file_path = str(moved_path)
                item_role = "primary" if primary_file_path is None else "supporting"
                if primary_file_path is None:
                    primary_file_path = file_path

                wg_connection.execute(
                    """
                    INSERT INTO working_items (
                        working_group_id, file_path, item_role, created_at, updated_at,
                        file_hash, file_size, source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created_group_id,
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
                group_added_items += 1

            if primary_file_path:
                wg_connection.execute(
                    "UPDATE working_groups SET primary_file_path = ? WHERE id = ?",
                    (primary_file_path, created_group_id),
                )

            created_groups_meta.append(
                {
                    "working_group_id": created_group_id,
                    "slug": candidate_slug,
                    "title": group_title,
                    "added_items": group_added_items,
                    "duplicate_items": group_duplicate_items,
                }
            )
        
        # Update upload status
        wg_connection.execute(
            """
            UPDATE intake_queue_uploads
            SET file_hashes_json = ?, inbox_state = ?, updated_at = ?,
                terminal_action = ?, terminal_at = ?,
                terminal_result_id = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps([item["file_hash"] for item in expanded_files]),
                "grouped_new",
                now_iso,
                "grouped_new",
                now_iso,
                str(working_group_id or ""),
                upload_id,
            ),
        )
        
        wg_connection.commit()
    except Exception as exc:
        wg_connection.rollback()
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="working_group_publish_failed",
            error_message=f"Failed to create working group: {exc}",
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "working_group_creation_failed",
                "message": str(exc),
                "upload_id": upload_id,
            },
        )
    finally:
        wg_connection.close()

    # Transition to grouped state
    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "uploaded_unverified",
        event_type="working_group_publish_materialized",
        metadata={
            "working_group_id": working_group_id,
            "added_items": added_items,
            "duplicate_items": duplicate_items,
        },
    )
    if not transitioned:
        _remove_browser_upload_staging(state.settings, source_entries)
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": transition_error or "Could not transition upload to uploaded_unverified.",
                "upload_id": upload_id,
                "working_group_id": working_group_id,
            },
        )

    # Final transition to verified
    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "verified",
        event_type="working_group_publish_verified",
        metadata={
            "working_group_id": working_group_id,
            "added_items": added_items,
        },
    )
    if not transitioned:
        _remove_browser_upload_staging(state.settings, source_entries)
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "status_transition_failed",
                "message": transition_error or "Could not finalize working group publish state.",
                "upload_id": upload_id,
                "working_group_id": working_group_id,
            },
        )

    # Browser uploads stage files under a GUID folder; once files are moved
    # into working storage this staging folder can be removed.
    _remove_browser_upload_staging(state.settings, source_entries)

    # Fetch created working groups for response
    detail_connection = connect(state.settings.db_path)
    detail_connection.row_factory = __import__("sqlite3").Row
    try:
        created_groups: list[dict[str, Any]] = []
        for meta in created_groups_meta:
            gid = int(meta.get("working_group_id") or 0)
            wg_row = detail_connection.execute(
                "SELECT * FROM working_groups WHERE id = ?", (gid,)
            ).fetchone()
            serialized_group = _serialize_working_group(detail_connection, wg_row, state.settings) if wg_row else None
            if serialized_group is not None:
                created_groups.append(
                    {
                        "working_group_id": gid,
                        "group": serialized_group,
                        "added_items": int(meta.get("added_items") or 0),
                        "duplicate_items": int(meta.get("duplicate_items") or 0),
                    }
                )
    finally:
        detail_connection.close()

    primary_group = created_groups[0]["group"] if created_groups else None

    return {
        "success": True,
        "contract": "intake-publish-working.v1alpha1",
        "upload_id": upload_id,
        "status": "verified",
        "verification_status": "pass",
        "working_group_id": working_group_id,
        "grouping_strategy": grouping_strategy,
        "preserve_folder_structure": preserve_folder_structure,
        "created_group_count": len(created_groups),
        "created_groups": created_groups,
        "state": "grouped_new",
        "is_terminal": True,
        "allowed_actions": [],
        "added_items": added_items,
        "duplicate_items": duplicate_items,
        "warnings": expansion_warnings,
        "group": primary_group,
        "plan_summary": plan_summary,
        "legacy_adapter": {
            "upload_to_catalog_route": f"/api/intake/uploads/{quote(upload_id, safe='')}/upload-to-catalog",
            "authoritative": False,
            "status": "transition_only",
        },
    }


@router.post("/api/intake/uploads/{upload_id}/upload-to-catalog")
async def intake_upload_to_catalog(
    upload_id: str,
    request: Request,
    collection_id: int | None = None,
    collection_name: str | None = None,
) -> Any:
    """
    Upload files from verified intake upload to catalog.
    
    Streams file from local filesystem directly to catalog server.
    Handles multipart form submission with file hash verification.
    
    Query Parameters:
    - collection_id: Target collection ID (optional)
    - collection_name: Target collection name (optional, overrides ID lookup)
    
    JSON Body (optional):
    - collection_id: Target collection ID
    - collection_name: Target collection name
    
    Response:
    - upload_record: Updated intake upload status
    - catalog_response: catalog response metadata
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
                    "message": f"Upload is in '{upload_row['status']}' state. Only unverified uploads can be uploaded to catalog.",
                },
            )
    finally:
        connection.close()
    
    client = request.app.state.catalog_client

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
            event_type="catalog_upload_failed",
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

    # Upload files to catalog
    uploaded_rows: list[dict[str, Any]] = []
    file_hashes: list[str] = []
    catalog_file_ids: list[str] = []
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
                        key = derive_model_key(
                            model_url=str(p.get("url") or p.get("@id") or "").strip() or None,
                            model_public_id=str(p.get("public_id") or p.get("slug") or "").strip() or None,
                            model_id=str(p.get("id") or "").strip() or None,
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
            
            # Upload file to catalog
            uploaded_file_ref = client.upload_file(
                filename=file_path.name,
                content=file_bytes,
                content_type=content_type,
            )
            
            # Create model in catalog
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
                        payload_key = derive_model_key(
                            model_url=str(payload.get("url") or payload.get("@id") or "").strip() or None,
                            model_public_id=str(payload.get("public_id") or payload.get("slug") or "").strip() or None,
                            model_id=str(payload.get("id") or "").strip() or None,
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
                    model_url = canonicalize_model_url(state.settings.catalog_base_url, model_url, fallback_model_id=model_id)
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
                catalog_file_ids.append(file_ref)
            verification_methods.append(verification_method)
            
            uploaded_rows.append({
                "source_path": str(file_path),
                "filename": file_path.name,
                "sha256": file_hash,
                "size_bytes": file_size,
                "catalog_model_ref": model_ref,
                "catalog_model_id": model_id,
                "model_url": model_url,
                "catalog_file_ref": file_ref,
                "catalog_file_url": file_url,
                "verification_method": verification_method,
            })
    except Exception as exc:
        # Update upload with failure status
        failure_connection = connect(state.settings.db_path)
        try:
            failure_connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?, catalog_file_ids_json = ?, verification_status = ?, updated_at = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps(file_hashes),
                    json.dumps(catalog_file_ids),
                    "failed",
                    _bulk_utc_now_iso(),
                    upload_id,
                )
            )
            failure_connection.commit()
        finally:
            failure_connection.close()
        
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="catalog_upload_failed",
            error_message=str(exc),
            metadata={
                "uploaded_count": len(uploaded_rows),
                "file_hashes": file_hashes,
                "catalog_file_ids": catalog_file_ids,
            },
        )
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": "catalog_upload_failed",
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
            SET file_hashes_json = ?, catalog_file_ids_json = ?, verification_status = ?, updated_at = ?
            WHERE upload_id = ?
            """,
            (
                json.dumps(file_hashes),
                json.dumps(catalog_file_ids),
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
        event_type="catalog_upload_verified",
        metadata={
            "uploaded_count": len(uploaded_rows),
            "file_hashes": file_hashes,
            "catalog_file_ids": catalog_file_ids,
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
        "catalog_response": {
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
