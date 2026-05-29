"""
Intake workflow routers - combined from focused sub-modules.

This module re-exports all intake endpoints from specialized routers:
- intake_queue: Queue state machine and upload management
- intake_verification: Item validation and working group creation
- intake_cleanup: Source file cleanup operations

Publishing operations (publish-to-local, upload-to-catalog) remain here.
"""

from __future__ import annotations

import html as html_module
import hashlib
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
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
    _compile_force_include_paths,
    _compile_source_entry_exclusions,
    _coerce_bool,
    _is_excluded_source_file,
    _make_intake_warning_id,
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
from ..geometry_3mf import extract_3mf_source_metadata
from ..services.model_detail_service import build_model_detail_response
from ..services.intake_eligibility_service import ActionEligibility
from ..services.shared_helpers import (
    _resolve_local_asset_storage_path,
    _serialize_project_row,
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


def _write_local_generated_asset(
    *,
    settings: Settings,
    local_model_id: str,
    relative_path: str,
    content_bytes: bytes,
) -> str:
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

    safe_parts = _normalized_relative_parts(relative_path)
    relative = Path(*safe_parts) if safe_parts else Path("generated.bin")
    destination_directory = (asset_root / relative.parent).resolve() if str(relative.parent) not in {"", "."} else asset_root
    destination_filename = _sanitize_storage_segment(relative.name or "generated.bin", fallback="generated.bin")
    if not destination_directory.is_relative_to(asset_root.resolve()):
        destination_directory = asset_root
        destination_filename = "generated.bin"

    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination_path(destination_directory, destination_filename)
    destination.write_bytes(content_bytes)
    try:
        stored_relative = destination.relative_to(catalog_root.resolve())
        return str(stored_relative).replace("\\", "/")
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


def _expand_intake_source_entries(
    *,
    source_entries: list[dict[str, Any]],
    force_include_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand source entries into individual files."""
    from ..services.shared_helpers import _sha256_file
    
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    exclusion_exact_keys, exclusion_folder_prefixes = _compile_source_entry_exclusions(source_entries)
    override_paths: set[str] = set(force_include_paths or set())
    override_paths.update(_compile_force_include_paths(source_entries))

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
            # include_unsupported=True so the per-file unsupported_type warning
            # below also fires for files discovered inside folders (issue #1563).
            candidate_paths = _collect_intake_source_files_in_folder(
                source_path, recurse=recurse, include_unsupported=True
            )

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
            suffix = file_path.suffix.lower()
            if suffix not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
                # Approach B (issue #1563): if the operator has explicitly
                # opted-in to this specific file via force_include_paths,
                # surface an info-level audit warning and fall through to
                # include the file. Otherwise keep the prior warn-and-skip
                # behavior (Approach A).
                if normalized_path in override_paths:
                    warnings.append(
                        {
                            "code": "unsupported_type_overridden",
                            "message": f"Unsupported extension included by user override: {suffix or '<none>'}",
                            "path": normalized_path,
                            "warning_id": _make_intake_warning_id(
                                "unsupported_type_overridden", normalized_path
                            ),
                            "severity": "info",
                        }
                    )
                else:
                    warnings.append(
                        {
                            "code": "unsupported_type",
                            "message": f"Unsupported extension: {suffix or '<none>'}",
                            "path": normalized_path,
                            "warning_id": _make_intake_warning_id(
                                "unsupported_type", normalized_path
                            ),
                        }
                    )
                    continue
            if not file_path.exists() or not file_path.is_file():
                warnings.append(
                    {
                        "code": "missing_source",
                        "message": f"Source file not found: {file_path}",
                        "path": normalized_path,
                        "warning_id": _make_intake_warning_id("missing_source", normalized_path),
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
                        "warning_id": _make_intake_warning_id("source_unreadable", normalized_path),
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


import logging as _logging

_intake_logger = _logging.getLogger(__name__)


def _auto_extract_3mf_metadata(
    *,
    state: AppState,
    local_model_id: str,
    imported_assets: list[dict[str, Any]],
    user_provided_creator: str | None,
    user_provided_source_origin: str | None,
    user_provided_source_url: str | None,
) -> dict[str, Any]:
    """Best-effort: extract source metadata from all 3MF assets and merge.

    URLs are unioned (deduplicated) across files.  Creator, platform, and
    primary URL use first-writer-wins from the file that provides them.
    Per-file extractions are stored as an array for traceability.
    """
    per_file: list[dict[str, Any]] = []
    files_scanned = 0

    for asset in imported_assets:
        filename = str(asset.get("filename") or "").lower()
        if not filename.endswith(".3mf"):
            continue
        files_scanned += 1

        storage_path_str = str(asset.get("storage_path") or asset.get("local_storage_path") or "").strip()
        if not storage_path_str:
            continue

        storage_path = _resolve_local_asset_storage_path(
            settings=state.settings,
            asset=SimpleNamespace(storage_path=storage_path_str),
        )
        if storage_path is None or not storage_path.exists() or not storage_path.is_file():
            _intake_logger.debug("3MF auto-extract: storage path missing for %s (%s)", asset.get("filename"), storage_path_str)
            continue

        try:
            file_bytes = storage_path.read_bytes()
        except (OSError, PermissionError):
            _intake_logger.debug("3MF auto-extract: could not read %s", storage_path)
            continue

        extracted = extract_3mf_source_metadata(file_bytes)
        if extracted:
            extracted["_source_file"] = str(asset.get("filename") or "")
            per_file.append(extracted)

    if not per_file:
        return {
            "status": "no_metadata_extracted",
            "files_scanned": files_scanned,
            "files_with_metadata": 0,
            "applied_fields": {
                "creator_name": False,
                "source_origin": False,
                "source_origin_url": False,
                "source_urls": False,
                "source_platform": False,
                "publication_source": False,
                "source_download_url": False,
            },
            "skipped_due_to_user_values": {
                "creator_name": bool(user_provided_creator),
                "source_origin": bool(user_provided_source_origin),
                "source_origin_url": bool(user_provided_source_url),
            },
        }

    # Merge across all files: first-writer-wins for scalar fields, union for URLs
    merged_designer: str | None = None
    merged_platform: str | None = None
    merged_primary_url: str | None = None
    all_urls: list[str] = []
    seen_urls: set[str] = set()

    for ext in per_file:
        if not merged_designer and ext.get("designer"):
            merged_designer = ext["designer"]
        if not merged_platform and ext.get("source_platform"):
            merged_platform = ext["source_platform"]
        if not merged_primary_url and ext.get("source_url"):
            merged_primary_url = ext["source_url"]
        for u in ext.get("source_urls") or []:
            if u not in seen_urls:
                all_urls.append(u)
                seen_urls.add(u)

    # Store per-file extractions as an array for traceability
    set_model_field(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        field_key="extracted_3mf_metadata",
        field_value=per_file if len(per_file) > 1 else per_file[0],
    )

    # Apply extracted fields as defaults (only when user didn't provide them)
    update_kwargs: dict[str, Any] = {}

    if not user_provided_creator and merged_designer:
        update_kwargs["creator_name"] = merged_designer

    if not user_provided_source_origin and merged_platform:
        update_kwargs["source_origin"] = merged_platform

    if not user_provided_source_url and merged_primary_url:
        update_kwargs["source_origin_url"] = merged_primary_url

    if update_kwargs:
        update_local_model(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            **update_kwargs,
        )

    # Persist source URLs and platform into provenance custom fields
    source_urls_applied = False
    source_platform_applied = False
    publication_source_applied = False
    source_download_url_applied = False

    if all_urls:
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="source_urls",
            field_value=all_urls,
        )
        source_urls_applied = True
    if merged_platform:
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="source_platform",
            field_value=merged_platform,
        )
        source_platform_applied = True
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="publication_source",
            field_value=merged_platform,
        )
        publication_source_applied = True
    if merged_primary_url:
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="source_download_url",
            field_value=merged_primary_url,
        )
        source_download_url_applied = True

    return {
        "status": "ok",
        "files_scanned": files_scanned,
        "files_with_metadata": len(per_file),
        "applied_fields": {
            "creator_name": bool(update_kwargs.get("creator_name")),
            "source_origin": bool(update_kwargs.get("source_origin")),
            "source_origin_url": bool(update_kwargs.get("source_origin_url")),
            "source_urls": source_urls_applied,
            "source_platform": source_platform_applied,
            "publication_source": publication_source_applied,
            "source_download_url": source_download_url_applied,
        },
        "skipped_due_to_user_values": {
            "creator_name": bool(user_provided_creator),
            "source_origin": bool(user_provided_source_origin),
            "source_origin_url": bool(user_provided_source_url),
        },
        "merged": {
            "designer": merged_designer,
            "source_platform": merged_platform,
            "source_url": merged_primary_url,
            "source_urls_count": len(all_urls),
        },
    }


def _collect_source_readmes(
    *,
    source_entries: list[dict[str, Any]] | None,
    group_files: list[dict[str, Any]] | None,
) -> list[tuple[Path, Path]]:
    """Return ``(source_folder, readme_path)`` tuples for each unique source folder
    contributing to a planned group that contains a ``README.md``.

    The folder list mirrors what ``_discover_source_metadata()`` walks during
    plan preview: ``folder``-type source entries are checked directly; ``file``
    entries fall back to their parent folder. We re-read the README from disk
    at publish time so the attached asset is the canonical, untruncated copy
    (the plan-preview payload may have been clipped at ``_README_INCLUDE_MAX_CHARS``).
    """
    candidate_folders: list[Path] = []
    for entry in source_entries or []:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            continue
        try:
            entry_path = Path(raw_path).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if entry_type == "folder":
            candidate_folders.append(entry_path)
        elif entry_type == "file":
            candidate_folders.append(entry_path.parent)
    # Fall back to parent folders of resolved files when source_entries is sparse.
    if not candidate_folders:
        for file_item in group_files or []:
            if not isinstance(file_item, dict):
                continue
            raw_path = str(file_item.get("path") or "").strip()
            if not raw_path:
                continue
            try:
                candidate_folders.append(Path(raw_path).expanduser().resolve().parent)
            except (OSError, RuntimeError):
                continue

    seen_keys: set[str] = set()
    results: list[tuple[Path, Path]] = []
    for folder in candidate_folders:
        key = str(folder)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        try:
            if not folder.is_dir():
                continue
        except OSError:
            continue
        readme_path = folder / "README.md"
        try:
            if readme_path.is_file():
                results.append((folder, readme_path))
        except OSError:
            continue
    return results


def _attach_source_snapshot_assets(
    *,
    state: AppState,
    local_model_id: str,
    source_entries: list[dict[str, Any]] | None,
    existing_asset_ids: set[str],
    existing_hashes: set[str],
    imported_assets: list[dict[str, Any]],
    duplicate_skipped: list[dict[str, Any]],
    failed_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    record_ids: list[str] = []
    seen_record_ids: set[str] = set()
    for entry in source_entries or []:
        if not isinstance(entry, dict):
            continue
        record_id = str(entry.get("source_record_id") or "").strip()
        if not record_id or record_id in seen_record_ids:
            continue
        seen_record_ids.add(record_id)
        record_ids.append(record_id)

    if not record_ids:
        return []

    attached: list[dict[str, Any]] = []
    connection = connect(state.settings.db_path)
    try:
        for record_id in record_ids:
            row = connection.execute(
                """
                SELECT provider_id, source_model_id, source_url_canonical, source_url_original,
                       title, creator_name, confidence, warnings_json, media_manifest_json,
                       file_manifest_json, snapshot_json, captured_at
                FROM source_intake_records
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()
            if row is None:
                failed_files.append(
                    {
                        "source_path": f"source_record:{record_id}",
                        "filename": f"source-record-{record_id}.json",
                        "message": "Source intake record was not found for snapshot attachment.",
                        "local_model_id": local_model_id,
                    }
                )
                continue

            provider_id = str(row[0] or "").strip() or "source"
            source_model_id = str(row[1] or "").strip()
            source_url_canonical = str(row[2] or "").strip() or None
            source_url_original = str(row[3] or "").strip() or None
            title = str(row[4] or "").strip() or None
            creator_name = str(row[5] or "").strip() or None
            confidence = str(row[6] or "").strip() or None
            try:
                warnings_json = json.loads(str(row[7] or "[]"))
            except json.JSONDecodeError:
                warnings_json = []
            try:
                media_manifest_json = json.loads(str(row[8] or "[]"))
            except json.JSONDecodeError:
                media_manifest_json = []
            try:
                file_manifest_json = json.loads(str(row[9] or "[]"))
            except json.JSONDecodeError:
                file_manifest_json = []
            try:
                snapshot_json = json.loads(str(row[10] or "{}"))
            except json.JSONDecodeError:
                snapshot_json = {}
            captured_at = str(row[11] or "").strip() or None

            payload = {
                "$schema": "https://hass-bambulab-config/schemas/source-intake-snapshot.v1.json",
                "provider_id": provider_id,
                "source_record_id": record_id,
                "source_model_id": source_model_id or None,
                "source_url_canonical": source_url_canonical,
                "source_url_original": source_url_original,
                "title": title,
                "creator_name": creator_name,
                "confidence": confidence,
                "captured_at": captured_at,
                "warnings": warnings_json if isinstance(warnings_json, list) else [],
                "file_manifest": file_manifest_json if isinstance(file_manifest_json, list) else [],
                "media_manifest": media_manifest_json if isinstance(media_manifest_json, list) else [],
                "snapshot": snapshot_json if isinstance(snapshot_json, dict) else snapshot_json,
            }
            content_bytes = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            file_hash = hashlib.sha256(content_bytes).hexdigest()
            filename_stem = f"{provider_id}-{source_model_id or record_id}-api-snapshot.json"
            if file_hash in existing_hashes:
                duplicate_skipped.append(
                    {
                        "source_path": f"source_record:{record_id}",
                        "filename": filename_stem,
                        "sha256": file_hash,
                        "reason": "duplicate_hash",
                    }
                )
                continue

            try:
                storage_path = _write_local_generated_asset(
                    settings=state.settings,
                    local_model_id=local_model_id,
                    relative_path=f"supporting_files/{filename_stem}",
                    content_bytes=content_bytes,
                )
                asset_id = _unique_asset_id(
                    filename=filename_stem,
                    file_hash=file_hash,
                    existing_ids=existing_asset_ids,
                )
                asset = create_model_asset(
                    db_path=state.settings.db_path,
                    local_model_id=local_model_id,
                    asset_id=asset_id,
                    asset_filename=Path(storage_path).name,
                    asset_type="json",
                    storage_path=storage_path,
                    asset_role="supporting",
                    file_size_bytes=len(content_bytes),
                    file_hash=file_hash,
                    preview_url=None,
                    geometry_bounds=None,
                )
                existing_asset_ids.add(asset.asset_id)
                existing_hashes.add(file_hash)
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
                        "source_path": f"source_record:{record_id}",
                        "source_entry_type": "source_snapshot",
                    }
                )
                attached.append(
                    {
                        "source_record_id": record_id,
                        "provider_id": provider_id,
                        "source_model_id": source_model_id or None,
                        "asset_id": asset.asset_id,
                        "filename": asset.asset_filename,
                    }
                )
            except Exception as exc:
                failed_files.append(
                    {
                        "source_path": f"source_record:{record_id}",
                        "filename": filename_stem,
                        "message": f"Failed to attach source snapshot: {exc}",
                        "local_model_id": local_model_id,
                    }
                )
    finally:
        connection.close()

    return attached


def _source_record_ids_from_entries(source_entries: list[dict[str, Any]] | None) -> list[str]:
    record_ids: list[str] = []
    seen_record_ids: set[str] = set()
    for entry in source_entries or []:
        if not isinstance(entry, dict):
            continue
        record_id = str(entry.get("source_record_id") or "").strip()
        if not record_id or record_id in seen_record_ids:
            continue
        seen_record_ids.add(record_id)
        record_ids.append(record_id)
    return record_ids


def _read_source_intake_records(*, db_path: Path, record_ids: list[str]) -> list[dict[str, Any]]:
    if not record_ids:
        return []
    connection = connect(db_path)
    try:
        placeholders = ",".join("?" for _ in record_ids)
        rows = connection.execute(
            f"""
            SELECT id, provider_id, source_model_id, source_url_canonical, source_url_original,
                   title, creator_name, description_raw, thumbnail_url,
                   media_manifest_json, file_manifest_json, snapshot_json
            FROM source_intake_records
            WHERE id IN ({placeholders})
            """,
            tuple(record_ids),
        ).fetchall()
    finally:
        connection.close()

    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        media_manifest_json: list[Any] = []
        file_manifest_json: list[Any] = []
        snapshot_json: dict[str, Any] = {}
        try:
            media_manifest_json = json.loads(str(row[9] or "[]"))
        except json.JSONDecodeError:
            media_manifest_json = []
        try:
            file_manifest_json = json.loads(str(row[10] or "[]"))
        except json.JSONDecodeError:
            file_manifest_json = []
        try:
            snapshot_json = json.loads(str(row[11] or "{}"))
        except json.JSONDecodeError:
            snapshot_json = {}
        by_id[str(row[0])] = {
            "id": str(row[0]),
            "provider_id": str(row[1] or "").strip() or None,
            "source_model_id": str(row[2] or "").strip() or None,
            "source_url_canonical": str(row[3] or "").strip() or None,
            "source_url_original": str(row[4] or "").strip() or None,
            "title": str(row[5] or "").strip() or None,
            "creator_name": str(row[6] or "").strip() or None,
            "description_raw": str(row[7] or "").strip() or None,
            "thumbnail_url": str(row[8] or "").strip() or None,
            "media_manifest_json": media_manifest_json if isinstance(media_manifest_json, list) else [],
            "file_manifest_json": file_manifest_json if isinstance(file_manifest_json, list) else [],
            "snapshot_json": snapshot_json if isinstance(snapshot_json, dict) else {},
        }

    return [by_id[record_id] for record_id in record_ids if record_id in by_id]


def _sanitize_source_description(value: Any) -> str | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    text_value = re.sub(r"<br\s*/?>", "\n", raw_value, flags=re.IGNORECASE)
    text_value = re.sub(r"</p\s*>", "\n\n", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"<[^>]+>", " ", text_value)
    text_value = html_module.unescape(text_value)
    text_value = text_value.replace("\r\n", "\n").replace("\r", "\n")
    text_value = re.sub(r"[ \t]+", " ", text_value)
    text_value = re.sub(r"\n{3,}", "\n\n", text_value)
    text_value = "\n".join(line.strip() for line in text_value.split("\n"))
    text_value = text_value.strip()
    return text_value or None


def _makerworld_prediction_summary(source_record: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = source_record.get("snapshot_json") if isinstance(source_record, dict) else {}
    if not isinstance(snapshot, dict):
        return []
    instances = snapshot.get("instances") if isinstance(snapshot.get("instances"), list) else []
    summaries: list[dict[str, Any]] = []
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        prediction_value = instance.get("prediction")
        extention = instance.get("extention") if isinstance(instance.get("extention"), dict) else {}
        model_info = extention.get("modelInfo") if isinstance(extention.get("modelInfo"), dict) else {}
        prediction = prediction_value if isinstance(prediction_value, (dict, int, float, str)) else {}
        plates = instance.get("plates") if isinstance(instance.get("plates"), list) else []
        if not plates and isinstance(model_info.get("plates"), list):
            plates = model_info.get("plates")
        plate_summaries: list[dict[str, Any]] = []
        for plate in plates:
            if not isinstance(plate, dict):
                continue
            plate_prediction = plate.get("prediction")
            if plate_prediction in ({}, [], None, ""):
                continue
            plate_summaries.append(
                {
                    "plate_id": plate.get("plateId") or plate.get("id"),
                    "prediction": plate_prediction,
                }
            )
        summaries.append(
            {
                "instance_id": instance.get("id"),
                "profile_id": instance.get("profileId"),
                "title": instance.get("title"),
                "prediction": prediction,
                "plate_predictions": plate_summaries,
            }
        )
    return summaries


def _makerworld_normalize_color_values(*sources: Any) -> list[str]:
    colors: list[str] = []
    seen_colors: set[str] = set()
    candidate_keys = (
        "filamentColor",
        "filamentColors",
        "filament_color",
        "filament_colors",
        "colors",
    )
    for source in sources:
        if isinstance(source, dict):
            values: list[Any] = []
            for key in candidate_keys:
                raw_value = source.get(key)
                if isinstance(raw_value, list):
                    values.extend(raw_value)
                elif raw_value not in (None, ""):
                    values.append(raw_value)
        elif isinstance(source, list):
            values = list(source)
        elif source not in (None, ""):
            values = [source]
        else:
            values = []
        for raw_value in values:
            color_value = str(raw_value or "").strip()
            color_key = color_value.lower()
            if not color_value or color_key in seen_colors:
                continue
            seen_colors.add(color_key)
            colors.append(color_value)
    return colors


def _makerworld_profile_summary(source_record: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = source_record.get("snapshot_json") if isinstance(source_record, dict) else {}
    if not isinstance(snapshot, dict):
        return []
    design_creator = snapshot.get("designCreator") if isinstance(snapshot.get("designCreator"), dict) else {}

    def _normalize_identity(value: Any) -> str:
        return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())

    creator_name = str(source_record.get("creator_name") or design_creator.get("name") or "").strip()
    creator_uid = int(
        design_creator.get("uid")
        or design_creator.get("userId")
        or design_creator.get("user_id")
        or design_creator.get("id")
        or 0
    )
    creator_key = _normalize_identity(creator_name)
    instances = snapshot.get("instances") if isinstance(snapshot.get("instances"), list) else []
    summaries: list[dict[str, Any]] = []
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        extention = instance.get("extention") if isinstance(instance.get("extention"), dict) else {}
        model_info = extention.get("modelInfo") if isinstance(extention.get("modelInfo"), dict) else {}
        plates = instance.get("plates") if isinstance(instance.get("plates"), list) else []
        if not plates and isinstance(model_info.get("plates"), list):
            plates = model_info.get("plates")
        plate_details: list[dict[str, Any]] = []
        for plate in plates:
            if not isinstance(plate, dict):
                continue
            plate_summary = {
                "plate_id": plate.get("plateId") or plate.get("id"),
                "prediction": plate.get("prediction") if plate.get("prediction") not in ({}, [], None, "") else None,
                "filament_colors": _makerworld_normalize_color_values(plate),
            }
            if not plate_summary["plate_id"] and not plate_summary["prediction"] and not plate_summary["filament_colors"]:
                continue
            plate_details.append(plate_summary)
        instance_colors = _makerworld_normalize_color_values(instance, model_info)
        if not instance_colors and plate_details:
            instance_colors = _makerworld_normalize_color_values(plate_details[0].get("filament_colors"))
        profile_owner_name = str(
            instance.get("profileUserName")
            or instance.get("profile_user_name")
            or instance.get("userName")
            or instance.get("username")
            or ""
        ).strip() or None
        profile_owner_id = int(
            instance.get("profileUserId")
            or instance.get("profile_user_id")
            or instance.get("profileUid")
            or instance.get("profile_uid")
            or instance.get("userId")
            or instance.get("user_id")
            or instance.get("uid")
            or 0
        )
        profile_owner_key = _normalize_identity(profile_owner_name)
        is_designer_profile = bool(
            (creator_key and profile_owner_key and creator_key == profile_owner_key)
            or (creator_uid > 0 and profile_owner_id > 0 and creator_uid == profile_owner_id)
        )
        summaries.append(
            {
                "instance_id": instance.get("id"),
                "profile_id": instance.get("profileId"),
                "title": instance.get("title"),
                "profile_owner_name": profile_owner_name,
                "profile_owner_id": profile_owner_id or None,
                "is_designer_profile": is_designer_profile,
                "is_default": bool(instance.get("isDefault")),
                "need_ams": instance.get("needAms") if instance.get("needAms") in (True, False) else None,
                "material_count": instance.get("materialCnt"),
                "print_count": instance.get("printCount"),
                "prediction": instance.get("prediction") if instance.get("prediction") not in ({}, [], None, "") else None,
                "filament_colors": instance_colors,
                "plate_details": plate_details,
            }
        )
    return summaries


def _source_intake_publish_context(
    *,
    db_path: Path,
    source_entries: list[dict[str, Any]] | None,
    destination_plan: dict[str, Any],
    selected_instance_ids: list[int] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    source_records = _read_source_intake_records(
        db_path=db_path,
        record_ids=_source_record_ids_from_entries(source_entries),
    )
    makerworld_record = next(
        (
            record for record in source_records
            if str(record.get("provider_id") or "").strip().lower() == "makerworld"
        ),
        None,
    )
    if makerworld_record is None:
        return dict(destination_plan), None

    enriched_plan = dict(destination_plan)
    if not str(enriched_plan.get("model_name") or "").strip():
        enriched_plan["model_name"] = makerworld_record.get("title") or enriched_plan.get("model_name")
    if not str(enriched_plan.get("description") or "").strip():
        enriched_plan["description"] = _sanitize_source_description(makerworld_record.get("description_raw"))
    if not str(enriched_plan.get("creator_name") or "").strip():
        enriched_plan["creator_name"] = makerworld_record.get("creator_name")
    source_origin = str(enriched_plan.get("source_origin") or "").strip().lower()
    if not source_origin or source_origin == "intake_queue":
        enriched_plan["source_origin"] = "makerworld"
    source_origin_url = str(enriched_plan.get("source_origin_url") or "").strip()
    if not source_origin_url or source_origin_url.startswith("intake://uploads/"):
        enriched_plan["source_origin_url"] = (
            makerworld_record.get("source_url_canonical")
            or makerworld_record.get("source_url_original")
            or source_origin_url
        )
    if not isinstance(enriched_plan.get("tags"), list) or not enriched_plan.get("tags"):
        snapshot = makerworld_record.get("snapshot_json") if isinstance(makerworld_record.get("snapshot_json"), dict) else {}
        has_reviewed_tags = "selected_tags" in snapshot and isinstance(snapshot.get("selected_tags"), list)
        raw_tags = snapshot.get("selected_tags") if has_reviewed_tags else (snapshot.get("tags") if isinstance(snapshot.get("tags"), list) else [])
        next_tags: list[str] = []
        seen_tags: set[str] = set()
        for raw_tag in raw_tags:
            if isinstance(raw_tag, dict):
                tag_name = str(raw_tag.get("name") or "").strip()
            else:
                tag_name = str(raw_tag or "").strip()
            key = tag_name.lower()
            if not tag_name or key in seen_tags:
                continue
            seen_tags.add(key)
            next_tags.append(tag_name)
        if next_tags:
            enriched_plan["tags"] = next_tags

    selected_ids = [int(value) for value in (selected_instance_ids or []) if int(value) > 0]
    selected_id_set = {int(value) for value in selected_ids}

    prediction_summary = _makerworld_prediction_summary(makerworld_record)
    profiles = _makerworld_profile_summary(makerworld_record)
    if selected_id_set:
        prediction_summary = [
            item for item in prediction_summary
            if int(item.get("instance_id") or 0) in selected_id_set
        ]
        profiles = [
            item for item in profiles
            if int(item.get("instance_id") or 0) in selected_id_set
        ]

    source_context = {
        "provider_id": "makerworld",
        "source_record_id": makerworld_record.get("id"),
        "source_model_id": makerworld_record.get("source_model_id"),
        "canonical_url": makerworld_record.get("source_url_canonical") or makerworld_record.get("source_url_original"),
        "original_url": makerworld_record.get("source_url_original") or makerworld_record.get("source_url_canonical"),
        "creator_name": makerworld_record.get("creator_name"),
        "thumbnail_url": makerworld_record.get("thumbnail_url"),
        "image_urls": [
            str(item.get("url") or "").strip()
            for item in (makerworld_record.get("media_manifest_json") or [])
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        ],
        "description_raw": makerworld_record.get("description_raw"),
        "description_text": _sanitize_source_description(makerworld_record.get("description_raw")),
        "prediction_summary": prediction_summary,
        "profiles": profiles,
        "selected_instance_ids": selected_ids if selected_ids else None,
    }
    return enriched_plan, source_context


def _normalize_print_estimates(prediction_summary: Any) -> list[dict[str, Any]]:
    summaries = prediction_summary if isinstance(prediction_summary, list) else []
    normalized: list[dict[str, Any]] = []
    for item in summaries:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "source": "makerworld",
                "instance_id": item.get("instance_id"),
                "profile_id": item.get("profile_id"),
                "title": item.get("title"),
                "estimated_print_time_seconds": item.get("prediction"),
                "plate_estimates": [
                    {
                        "plate_id": plate.get("plate_id"),
                        "estimated_print_time_seconds": plate.get("prediction"),
                    }
                    for plate in (item.get("plate_predictions") if isinstance(item.get("plate_predictions"), list) else [])
                    if isinstance(plate, dict)
                ],
            }
        )
    return normalized


def _persist_source_publish_context(*, db_path: Path, model_ref: str, source_publish_context: dict[str, Any] | None) -> None:
    if not isinstance(source_publish_context, dict):
        return
    provider_id = str(source_publish_context.get("provider_id") or "").strip() or None
    canonical_url = str(source_publish_context.get("canonical_url") or "").strip() or None
    original_url = str(source_publish_context.get("original_url") or "").strip() or None
    primary_source_url = canonical_url or original_url
    source_urls: list[str] = []
    seen_source_urls: set[str] = set()
    for candidate in (canonical_url, original_url):
        normalized = str(candidate or "").strip()
        if not normalized or normalized in seen_source_urls:
            continue
        seen_source_urls.add(normalized)
        source_urls.append(normalized)
    preview_image_url = str(source_publish_context.get("thumbnail_url") or "").strip() or None
    if not preview_image_url:
        for image_url in (source_publish_context.get("image_urls") or []):
            normalized = str(image_url or "").strip()
            if normalized:
                preview_image_url = normalized
                break
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_capture_provider",
        field_value=provider_id,
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_capture_record_id",
        field_value=source_publish_context.get("source_record_id"),
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_capture_model_id",
        field_value=source_publish_context.get("source_model_id"),
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_capture_image_urls",
        field_value=source_publish_context.get("image_urls") or [],
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_description_raw",
        field_value=source_publish_context.get("description_raw"),
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_prediction_summary",
        field_value=source_publish_context.get("prediction_summary") or [],
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="source_capture_profiles",
        field_value=source_publish_context.get("profiles") or [],
    )
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key="print_estimates",
        field_value=_normalize_print_estimates(source_publish_context.get("prediction_summary") or []),
    )
    if provider_id:
        set_model_field(
            db_path=db_path,
            model_ref=model_ref,
            field_key="publication_source",
            field_value=provider_id,
        )
        set_model_field(
            db_path=db_path,
            model_ref=model_ref,
            field_key="source_platform",
            field_value=provider_id,
        )
    if primary_source_url:
        set_model_field(
            db_path=db_path,
            model_ref=model_ref,
            field_key="source_download_url",
            field_value=primary_source_url,
        )
    if source_urls:
        set_model_field(
            db_path=db_path,
            model_ref=model_ref,
            field_key="source_urls",
            field_value=source_urls,
        )
    if preview_image_url:
        set_model_field(
            db_path=db_path,
            model_ref=model_ref,
            field_key="source_image_preview_url",
            field_value=preview_image_url,
        )


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

    destination_plan, source_publish_context = _source_intake_publish_context(
        db_path=state.settings.db_path,
        source_entries=source_entries,
        destination_plan=destination_plan,
    )

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
    requested_preview_image_url = str(destination_plan.get("preview_image_url") or "").strip() or None
    if requested_preview_image_url is None and isinstance(source_publish_context, dict):
        requested_preview_image_url = str(source_publish_context.get("thumbnail_url") or "").strip() or None
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
            preview_image_url=requested_preview_image_url,
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
            preview_image_url=requested_preview_image_url,
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

    # Optional: attach source folder README.md files as documentation assets.
    # Driven by the wizard's Organize-step "Attach README" opt-in (Phase 2 of
    # the intake sidecar-enrichment design). README contents are re-read from
    # disk here so the asset is the canonical, untruncated copy.
    attached_readmes: list[dict[str, Any]] = []
    if _coerce_bool(destination_plan.get("attach_source_readme")):
        for source_folder, readme_path in _collect_source_readmes(
            source_entries=source_entries, group_files=group_files
        ):
            try:
                readme_bytes = readme_path.read_bytes()
                readme_hash = hashlib.sha256(readme_bytes).hexdigest()
            except OSError as exc:
                failed_files.append({
                    "source_path": str(readme_path),
                    "filename": readme_path.name,
                    "message": f"Failed to read source README: {exc}",
                    "local_model_id": local_model_id,
                })
                continue
            if readme_hash in existing_hashes:
                matched_asset_id = ""
                matched_filename = readme_path.name
                for imported in imported_assets:
                    if str(imported.get("file_hash") or "").strip().lower() != readme_hash:
                        continue
                    matched_asset_id = str(imported.get("asset_id") or "").strip()
                    imported_name = str(imported.get("filename") or "").strip()
                    if imported_name:
                        matched_filename = imported_name
                    break
                if not matched_asset_id:
                    for existing_asset in existing_assets:
                        existing_hash = str(getattr(existing_asset, "file_hash", "") or "").strip().lower()
                        if existing_hash != readme_hash:
                            continue
                        matched_asset_id = str(getattr(existing_asset, "asset_id", "") or "").strip()
                        existing_name = str(getattr(existing_asset, "asset_filename", "") or "").strip()
                        if existing_name:
                            matched_filename = existing_name
                        break
                attached_readmes.append({
                    "source_folder": str(source_folder),
                    "source_path": str(readme_path),
                    "asset_id": matched_asset_id or None,
                    "filename": matched_filename,
                    "already_present": True,
                })
                duplicate_skipped.append({
                    "source_path": str(readme_path),
                    "filename": readme_path.name,
                    "sha256": readme_hash,
                    "reason": "duplicate_hash",
                })
                continue
            try:
                storage_path = _copy_local_import_source(
                    settings=state.settings,
                    local_model_id=local_model_id,
                    source_path=readme_path,
                    relative_path=readme_path.name,
                    preserve_folder_structure=False,
                )
                asset_type = _normalize_local_asset_type(readme_path)
                asset_role = _normalize_local_asset_role(
                    asset_type=asset_type,
                    has_preview=has_preview,
                    has_primary=has_primary,
                    preview_selected=False,
                )
                asset_id = _unique_asset_id(
                    filename=readme_path.name,
                    file_hash=readme_hash,
                    existing_ids=existing_asset_ids,
                )
                asset = create_model_asset(
                    db_path=state.settings.db_path,
                    local_model_id=local_model_id,
                    asset_id=asset_id,
                    asset_filename=readme_path.name,
                    asset_type=asset_type,
                    storage_path=storage_path,
                    asset_role=asset_role,
                    file_size_bytes=len(readme_bytes),
                    file_hash=readme_hash,
                    preview_url=None,
                    geometry_bounds=None,
                )
                existing_hashes.add(readme_hash)
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
                    "source_path": str(readme_path),
                    "source_entry_type": "source_readme",
                })
                attached_readmes.append({
                    "source_folder": str(source_folder),
                    "source_path": str(readme_path),
                    "asset_id": asset.asset_id,
                    "filename": asset.asset_filename,
                })
            except Exception as exc:
                failed_files.append({
                    "source_path": str(readme_path),
                    "filename": readme_path.name,
                    "message": f"Failed to attach README: {exc}",
                    "local_model_id": local_model_id,
                })

    attached_source_snapshots = _attach_source_snapshot_assets(
        state=state,
        local_model_id=local_model_id,
        source_entries=source_entries,
        existing_asset_ids=existing_asset_ids,
        existing_hashes=existing_hashes,
        imported_assets=imported_assets,
        duplicate_skipped=duplicate_skipped,
        failed_files=failed_files,
    )

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
    _persist_source_publish_context(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        source_publish_context=source_publish_context,
    )

    # --- Auto-extract 3MF source metadata (best-effort) ---
    extraction_log = _auto_extract_3mf_metadata(
        state=state,
        local_model_id=local_model_id,
        imported_assets=imported_assets,
        user_provided_creator=requested_creator_name,
        user_provided_source_origin=destination_plan.get("source_origin"),
        user_provided_source_url=destination_plan.get("source_origin_url"),
    )

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
        "attached_readmes": attached_readmes,
        "attached_source_snapshots": attached_source_snapshots,
        "source_metadata_extraction": extraction_log,
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
    """Publish a planned intake group into the folder-first Working Files store.

    Per docs/features/model_catalog/design/working-files.md the Working Files store
    is folder-first: a folder under MODEL_CATALOG_WORKING_FILES_ROOT *is* the group.
    There is no working_groups / working_items DB table identity.

    Two modes are supported:

    * **New folder** (default): create a fresh, uniquely-named folder under the
      root and write a `.modelmeta.json` sidecar carrying display_title / tags /
      origin / primary_file. Notes from the destination plan are written to
      `README.md`.

    * **Append to existing folder**: when ``destination_plan["target_folder_slug"]``
      is set, copy files into the existing folder, merge new entries into the
      sidecar's ``files[]`` list (preserving the original ``display_title``,
      ``imported_at``, ``primary_file``, ``tags``, and ``origin_url``), record
      a ``last_import_at`` timestamp, and append an ``import_history[]`` entry.
      The existing ``README.md`` is never overwritten in append mode.
    """
    group_files = list(group.get("files") or [])
    if not group_files:
        return None, [], []

    from ..services.working_groups_service import _working_files_destination_root

    working_root = _working_files_destination_root(state.settings)
    if not working_root:
        raise ValueError("No working files root configured")

    group_title = str(destination_plan.get("title") or group.get("title") or "Working Folder").strip() or "Working Folder"
    requested_notes = str(destination_plan.get("notes") or "").strip()
    requested_tags_raw = destination_plan.get("tags") or []
    requested_origin = str(destination_plan.get("origin_url") or "").strip()
    group_strategy = str(group.get("strategy") or "none").strip() or "none"
    preserve_folder_structure = _coerce_bool(group.get("preserve_folder_structure", True))

    if isinstance(requested_tags_raw, str):
        requested_tags = [tag.strip() for tag in requested_tags_raw.split(",") if tag.strip()]
    elif isinstance(requested_tags_raw, list):
        requested_tags = [str(tag).strip() for tag in requested_tags_raw if str(tag).strip()]
    else:
        requested_tags = []

    # Append-mode: caller has selected an existing folder under the working root.
    target_folder_slug = str(destination_plan.get("target_folder_slug") or "").strip()
    append_mode = bool(target_folder_slug)
    existing_sidecar: dict[str, Any] = {}
    existing_hashes: set[str] = set()
    existing_files_entries: list[dict[str, Any]] = []

    if append_mode:
        # Validate slug safety (single top-level folder name, no traversal).
        if (
            "/" in target_folder_slug
            or "\\" in target_folder_slug
            or target_folder_slug.startswith(".")
            or target_folder_slug in {"..", "."}
        ):
            raise ValueError(f"Invalid target_folder_slug: {target_folder_slug!r}")
        candidate_slug = target_folder_slug
        group_dir = working_root / candidate_slug
        if not group_dir.is_dir():
            raise LookupError(f"Working folder '{target_folder_slug}' does not exist under the working-files root.")

        existing_modelmeta = group_dir / ".modelmeta.json"
        if existing_modelmeta.is_file():
            try:
                loaded = json.loads(existing_modelmeta.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing_sidecar = loaded
                    raw_files = loaded.get("files")
                    if isinstance(raw_files, list):
                        for entry in raw_files:
                            if not isinstance(entry, dict):
                                continue
                            existing_files_entries.append(entry)
                            h = str(entry.get("sha256") or "").strip().lower()
                            if h:
                                existing_hashes.add(h)
            except (OSError, json.JSONDecodeError):
                existing_sidecar = {}
                existing_files_entries = []
                existing_hashes = set()
    else:
        # Resolve a unique folder slug on disk (no DB lookup; folder existence is authoritative).
        slug_base = _slugify_title(group_title) or f"import-{upload_id[:8]}"
        candidate_slug = slug_base
        counter = 0
        while (working_root / candidate_slug).exists():
            counter += 1
            candidate_slug = f"{slug_base}-{counter}"

        group_dir = working_root / candidate_slug
        group_dir.mkdir(parents=True, exist_ok=True)

    added_items = 0
    duplicate_items = 0
    seen_hashes: set[str] = set(existing_hashes)
    primary_file_relative: str | None = None
    primary_file_abs: str | None = None
    file_metadata_entries: list[dict[str, Any]] = []

    for file_item in group_files:
        source_file_path = Path(str(file_item["path"])).resolve()
        file_hash = str(file_item.get("file_hash") or "").strip().lower() or None
        if file_hash and file_hash in seen_hashes:
            # Same hash already published in this run — skip duplicate within group.
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
        moved_abs = Path(moved_path).resolve()
        try:
            relative_in_group = moved_abs.relative_to(group_dir.resolve()).as_posix()
        except ValueError:
            relative_in_group = moved_abs.name
        if primary_file_relative is None:
            primary_file_relative = relative_in_group
            primary_file_abs = str(moved_abs)
        if file_hash:
            seen_hashes.add(file_hash)
        added_items += 1

        # Capture per-file source timestamps for the sidecar.
        source_meta = file_item.get("source_metadata") or {}
        file_entry: dict[str, Any] = {"path": relative_in_group}
        for key in ("source_mtime", "source_ctime", "source_birthtime"):
            value = str(source_meta.get(key) or "").strip()
            if value:
                file_entry[key] = value
        if file_hash:
            file_entry["sha256"] = file_hash
        file_metadata_entries.append(file_entry)

    # Aggregate source timestamp summary across the published files.
    timestamp_summary = _source_timestamp_summary(group_files)
    imported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if append_mode:
        # Merge into existing sidecar without clobbering original metadata.
        modelmeta_payload: dict[str, Any] = dict(existing_sidecar) if existing_sidecar else {}
        modelmeta_payload.setdefault("$schema", "https://hass-bambulab-config/schemas/modelmeta.v1.json")
        # Preserve existing display_title; fall back to the (existing or new) title only if missing.
        modelmeta_payload.setdefault("display_title", existing_sidecar.get("display_title") or group_title)
        # Preserve original imported_at; record this batch's timestamp separately.
        if not modelmeta_payload.get("imported_at"):
            modelmeta_payload["imported_at"] = imported_at
        modelmeta_payload["last_import_at"] = imported_at

        merged_files = list(existing_files_entries)
        merged_files.extend(file_metadata_entries)
        if merged_files:
            modelmeta_payload["files"] = merged_files

        # Append to import history (cap to last 20 entries).
        history_raw = modelmeta_payload.get("import_history")
        history_list = [entry for entry in history_raw if isinstance(entry, dict)] if isinstance(history_raw, list) else []
        history_list.append(
            {
                "imported_at": imported_at,
                "added_file_count": added_items,
                "duplicate_file_count": duplicate_items,
                "source_timestamp_summary": timestamp_summary,
            }
        )
        modelmeta_payload["import_history"] = history_list[-20:]

        # primary_file: only set if it was missing from the existing sidecar.
        if not modelmeta_payload.get("primary_file") and primary_file_relative:
            modelmeta_payload["primary_file"] = primary_file_relative
        # tags: union with existing.
        if requested_tags:
            existing_tags = modelmeta_payload.get("tags")
            existing_tag_list = [str(t).strip() for t in existing_tags if str(t).strip()] if isinstance(existing_tags, list) else []
            for tag in requested_tags:
                if tag and tag not in existing_tag_list:
                    existing_tag_list.append(tag)
            if existing_tag_list:
                modelmeta_payload["tags"] = existing_tag_list
        # origin_url: only set if missing.
        if requested_origin and not modelmeta_payload.get("origin_url"):
            modelmeta_payload["origin_url"] = requested_origin
    else:
        # Write fresh .modelmeta.json sidecar for the new folder.
        modelmeta_payload = {
            "$schema": "https://hass-bambulab-config/schemas/modelmeta.v1.json",
            "display_title": group_title,
            "imported_at": imported_at,
            "source_timestamp_summary": timestamp_summary,
        }
        if file_metadata_entries:
            modelmeta_payload["files"] = file_metadata_entries
        if primary_file_relative:
            modelmeta_payload["primary_file"] = primary_file_relative
        if requested_tags:
            modelmeta_payload["tags"] = requested_tags
        if requested_origin:
            modelmeta_payload["origin_url"] = requested_origin

    modelmeta_path: Path | None = group_dir / ".modelmeta.json"
    try:
        modelmeta_path.write_text(  # type: ignore[union-attr]
            json.dumps(modelmeta_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        modelmeta_path = None

    # README.md handling: in append mode preserve existing; otherwise write notes if provided.
    readme_path: Path | None = None
    candidate_readme = group_dir / "README.md"
    if append_mode:
        if candidate_readme.is_file():
            readme_path = candidate_readme
        elif requested_notes:
            try:
                candidate_readme.write_text(requested_notes.rstrip() + "\n", encoding="utf-8")
                readme_path = candidate_readme
            except OSError:
                readme_path = None
    elif requested_notes:
        try:
            candidate_readme.write_text(requested_notes.rstrip() + "\n", encoding="utf-8")
            readme_path = candidate_readme
        except OSError:
            readme_path = None

    # Refresh inventory so the new folder shows up in /api/working-files/tree immediately.
    try:
        from .working import _refresh_working_file_inventory
        _refresh_working_file_inventory(
            db_path=Path(state.settings.db_path),
            roots=[working_root],
            compute_hashes=True,
        )
    except Exception:
        # Inventory refresh is best-effort; a later reindex will pick up the folder.
        pass

    return (
        {
            "destination": "working",
            "match_mode": "appended" if append_mode else "new",
            "group_title": group_title,
            "grouping_strategy": group_strategy,
            "preserve_folder_structure": preserve_folder_structure,
            "folder_slug": candidate_slug,
            "folder_path": str(group_dir),
            "primary_file": primary_file_relative,
            "primary_file_path": primary_file_abs,
            "added_items": added_items,
            "duplicate_items": duplicate_items,
            "modelmeta_path": str(modelmeta_path) if modelmeta_path else None,
            "readme_path": str(readme_path) if readme_path else None,
            "tags": requested_tags,
            "origin_url": requested_origin or None,
        },
        [
            {
                "file_hash": str(file_item.get("file_hash") or "").strip().lower(),
                "source_path": str(file_item.get("path") or ""),
            }
            for file_item in group_files
            if str(file_item.get("file_hash") or "").strip()
        ],
        [],
    )


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
    override_warning = bool(payload.get("override_warning"))

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
    if not is_eligible and current_state == "validated_warning":
        is_eligible, reason_code = ActionEligibility.validate_override_for_warning_state(
            current_state,
            ActionEligibility.PUBLISH_CATALOG,
            override_warning,
        )
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
    working_folder_slugs: list[str] = []

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
                if group_result is not None and group_result.get("folder_slug"):
                    working_folder_slugs.append(str(group_result["folder_slug"]))
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
                        "working_folder_slugs": working_folder_slugs,
                        "group_results": [
                            {
                                "destination": str(result.get("destination") or "").strip().lower(),
                                "match_mode": str(result.get("match_mode") or "").strip().lower(),
                                "result_id": str(result.get("local_model_id") or result.get("folder_slug") or "").strip(),
                                "local_model_id": result.get("local_model_id"),
                                "folder_slug": result.get("folder_slug"),
                                "folder_path": result.get("folder_path"),
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
        metadata={"curated_model_ids": curated_model_ids, "working_folder_slugs": working_folder_slugs, "group_count": len(results)},
    )
    if transitioned:
        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "verified",
            event_type="destination_publish_verified",
            metadata={"curated_model_ids": curated_model_ids, "working_folder_slugs": working_folder_slugs},
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
        "working_folder_slugs": working_folder_slugs,
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
    user_provided_creator = str(payload.get("creator_name") or "").strip() or None
    requested_created_by = str(payload.get("created_by") or "intake_queue").strip() or "intake_queue"
    requested_source_origin = str(payload.get("source_origin") or "intake_queue").strip() or "intake_queue"
    requested_source_origin_url = str(payload.get("source_origin_url") or f"intake://uploads/{upload_id}").strip()
    user_provided_source_origin = str(payload.get("source_origin") or "").strip() or None
    user_provided_source_url = str(payload.get("source_origin_url") or "").strip() or None
    requested_preview_source_path = str(payload.get("preview_source_path") or "").strip()
    destination_defaults, source_publish_context = _source_intake_publish_context(
        db_path=state.settings.db_path,
        source_entries=source_entries,
        destination_plan={
            "model_ref": requested_model_ref,
            "model_name": requested_model_name,
            "description": requested_description,
            "tags": requested_tags,
            "collection_names": requested_collection_names,
            "creator_name": requested_creator_name,
            "created_by": requested_created_by,
            "source_origin": requested_source_origin,
            "source_origin_url": requested_source_origin_url,
            "preview_source_path": requested_preview_source_path,
        },
    )
    requested_model_ref = str(destination_defaults.get("model_ref") or destination_defaults.get("local_model_id") or requested_model_ref).strip()
    requested_model_name = str(destination_defaults.get("model_name") or requested_model_name).strip()
    requested_description = str(destination_defaults.get("description") or requested_description).strip()
    requested_tags = destination_defaults.get("tags") if isinstance(destination_defaults.get("tags"), list) else requested_tags
    requested_collection_names = destination_defaults.get("collection_names") if isinstance(destination_defaults.get("collection_names"), list) else requested_collection_names
    requested_creator_name = str(destination_defaults.get("creator_name") or requested_creator_name or "").strip() or None
    requested_created_by = str(destination_defaults.get("created_by") or requested_created_by).strip() or requested_created_by
    requested_source_origin = str(destination_defaults.get("source_origin") or requested_source_origin).strip() or requested_source_origin
    requested_source_origin_url = str(destination_defaults.get("source_origin_url") or requested_source_origin_url).strip()
    requested_preview_source_path = str(destination_defaults.get("preview_source_path") or requested_preview_source_path).strip()
    requested_preview_image_url = str(destination_defaults.get("preview_image_url") or "").strip() or None
    if requested_preview_image_url is None and isinstance(source_publish_context, dict):
        requested_preview_image_url = str(source_publish_context.get("thumbnail_url") or "").strip() or None
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
        extraction_logs: list[dict[str, Any]] = []
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
                preview_image_url=requested_preview_image_url,
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
            group_imported_assets: list[dict[str, Any]] = []
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
                    group_imported_assets.append(
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
            _attach_source_snapshot_assets(
                state=state,
                local_model_id=local_model_id,
                source_entries=source_entries,
                existing_asset_ids=existing_asset_ids,
                existing_hashes=existing_hashes,
                imported_assets=group_imported_assets,
                duplicate_skipped=duplicate_skipped,
                failed_files=failed_files,
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
            _persist_source_publish_context(
                db_path=state.settings.db_path,
                model_ref=local_model_id,
                source_publish_context=source_publish_context,
            )

            extraction_log = _auto_extract_3mf_metadata(
                state=state,
                local_model_id=local_model_id,
                imported_assets=group_imported_assets,
                user_provided_creator=user_provided_creator,
                user_provided_source_origin=user_provided_source_origin,
                user_provided_source_url=user_provided_source_url,
            )
            extraction_logs.append(
                {
                    "local_model_id": local_model_id,
                    "group_title": group_title,
                    "extraction": extraction_log,
                }
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
            "source_metadata_extraction": extraction_logs,
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
            preview_image_url=requested_preview_image_url,
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
            preview_image_url=requested_preview_image_url,
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
    attached_source_snapshots = _attach_source_snapshot_assets(
        state=state,
        local_model_id=local_model_id,
        source_entries=source_entries,
        existing_asset_ids=existing_asset_ids,
        existing_hashes=existing_hashes,
        imported_assets=imported_assets,
        duplicate_skipped=duplicate_skipped,
        failed_files=failed_files,
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
    _persist_source_publish_context(
        db_path=state.settings.db_path,
        model_ref=local_model_id,
        source_publish_context=source_publish_context,
    )

    extraction_log = _auto_extract_3mf_metadata(
        state=state,
        local_model_id=local_model_id,
        imported_assets=imported_assets,
        user_provided_creator=user_provided_creator,
        user_provided_source_origin=user_provided_source_origin,
        user_provided_source_url=user_provided_source_url,
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
        "attached_source_snapshots": attached_source_snapshots,
        "source_metadata_extraction": extraction_log,
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
    # Optional: append into an existing working folder rather than creating a new one.
    requested_target_folder_slug = str(payload.get("target_folder_slug") or "").strip()

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

    # Publish each planned group into the folder-first Working Files store.
    # No more working_groups / working_items DB writes — each group becomes a
    # uniquely-named folder under MODEL_CATALOG_WORKING_FILES_ROOT with an
    # optional .modelmeta.json / README.md sidecar.
    added_items = 0
    duplicate_items = 0
    created_groups_meta: list[dict[str, Any]] = []
    working_folder_slugs: list[str] = []
    imported_rows: list[dict[str, Any]] = []
    cleanup_policy = str(upload_row["cleanup_policy"] or "keep").strip().lower()

    try:
        for group in planned_groups:
            group_title = str(group.get("title") or "").strip() or default_title
            destination_plan = {
                "destination": "working",
                "title": group_title,
                "notes": requested_notes,
            }
            if requested_target_folder_slug:
                destination_plan["target_folder_slug"] = requested_target_folder_slug
            group_result, group_rows, _group_failures = _publish_group_to_working_destination(
                state=state,
                upload_id=upload_id,
                source_entries=source_entries,
                group=group,
                destination_plan=destination_plan,
                cleanup_policy=cleanup_policy,
            )
            if group_result is None:
                continue
            slug_value = str(group_result.get("folder_slug") or "").strip()
            if slug_value:
                working_folder_slugs.append(slug_value)
            group_added = int(group_result.get("added_items") or 0)
            group_dup = int(group_result.get("duplicate_items") or 0)
            added_items += group_added
            duplicate_items += group_dup
            imported_rows.extend(group_rows)
            created_groups_meta.append(
                {
                    "folder_slug": slug_value,
                    "folder_path": group_result.get("folder_path"),
                    "title": group_title,
                    "added_items": group_added,
                    "duplicate_items": group_dup,
                    "primary_file": group_result.get("primary_file"),
                    "modelmeta_path": group_result.get("modelmeta_path"),
                    "readme_path": group_result.get("readme_path"),
                }
            )
    except Exception as exc:
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "failed",
            event_type="working_group_publish_failed",
            error_message=f"Failed to publish to Working Files: {exc}",
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

    # Update upload status row (terminal_result_id now carries the primary folder slug).
    now_iso = _bulk_utc_now_iso()
    primary_slug = working_folder_slugs[0] if working_folder_slugs else ""
    status_connection = connect(state.settings.db_path)
    try:
        status_connection.execute(
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
                primary_slug,
                upload_id,
            ),
        )
        status_connection.commit()
    finally:
        status_connection.close()

    # Transition to grouped state
    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "uploaded_unverified",
        event_type="working_group_publish_materialized",
        metadata={
            "working_folder_slugs": working_folder_slugs,
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
                "working_folder_slugs": working_folder_slugs,
            },
        )

    # Final transition to verified
    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "verified",
        event_type="working_group_publish_verified",
        metadata={
            "working_folder_slugs": working_folder_slugs,
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
                "working_folder_slugs": working_folder_slugs,
            },
        )

    # Browser uploads stage files under a GUID folder; once files are moved
    # into working storage this staging folder can be removed.
    _remove_browser_upload_staging(state.settings, source_entries)

    created_groups: list[dict[str, Any]] = list(created_groups_meta)
    primary_group_slug = working_folder_slugs[0] if working_folder_slugs else None

    return {
        "success": True,
        "contract": "intake-publish-working.v1alpha1",
        "upload_id": upload_id,
        "status": "verified",
        "verification_status": "pass",
        "working_folder_slug": primary_group_slug,
        "working_folder_slugs": working_folder_slugs,
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
