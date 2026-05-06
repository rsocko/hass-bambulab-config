"""Source-filesystem endpoints extracted from main.py (issue #1192).

Covers: /api/source-filesystems, /api/source-filesystems/browse,
/api/source-filesystems/select.

Note: The nested `_intake_source_roots()` helper that closed over `app` in
main.py is replaced here with a direct call to `_configured_intake_source_roots`
using `request.app.state.model_catalog.settings`.
"""
from __future__ import annotations

import json
import uuid as _uuid_module
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..state import AppState
from .._helpers import (
    SUPPORTED_INTAKE_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _coerce_bool,
    _collect_intake_source_files_in_folder,
    _configured_intake_source_roots,
    _is_path_within_roots,
)
from ..services.intake_consolidation import _consolidate_overlapping_selections

router = APIRouter(tags=["source-filesystems"])


def _count_disallowed_files_in_folder(folder: Path, *, recurse: bool) -> int:
    count = 0
    try:
        for item in sorted(folder.iterdir()):
            if item.name.startswith("."):
                continue
            try:
                if item.is_file():
                    if item.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
                        count += 1
                elif item.is_dir() and recurse:
                    count += _count_disallowed_files_in_folder(item, recurse=True)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return count


def _normalize_group_title_source(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower().replace("_", "-")
    if normalized in {"folder", "first-file", "custom"}:
        return normalized
    return None


@router.get("/api/source-filesystems")
def list_source_filesystems(request: Request) -> Any:
    """
    List configured allowlisted source filesystem roots.

    Roots are configured via MODEL_CATALOG_INTAKE_ROOTS.
    Returns metadata for each root including accessibility and item counts.
    """
    state: AppState = request.app.state.model_catalog
    roots = _configured_intake_source_roots(state.settings)
    root_entries = []
    for root in roots:
        accessible = root.exists() and root.is_dir()
        child_count: int | None = None
        if accessible:
            try:
                child_count = sum(
                    1 for item in root.iterdir() if not item.name.startswith(".")
                )
            except (OSError, PermissionError):
                child_count = None
        root_entries.append(
            {
                "path": str(root),
                "name": root.name or str(root),
                "accessible": accessible,
                "child_count": child_count,
            }
        )
    return {
        "success": True,
        "roots": root_entries,
        "root_count": len(root_entries),
    }


@router.get("/api/source-filesystems/browse")
def browse_source_filesystem(request: Request, path: str | None = None) -> Any:
    """
    Browse an allowlisted source filesystem path.

    - Omit path (or pass path=/) to list the configured roots as top-level entries.
    - Provide path to list folder contents.
    - Enforces allowlist; rejects traversal outside configured roots.
    """
    state: AppState = request.app.state.model_catalog
    roots = _configured_intake_source_roots(state.settings)

    if not path or path.strip() in {"", "/"}:
        # Virtual root: show configured roots
        return {
            "success": True,
            "path": "/",
            "is_root": True,
            "type": "virtual_root",
            "entries": [
                {
                    "path": str(root),
                    "name": root.name or str(root),
                    "type": "folder",
                    "accessible": root.exists() and root.is_dir(),
                    "has_children": root.is_dir() if root.exists() else False,
                }
                for root in roots
            ],
        }

    browse_path = Path(path).expanduser().resolve()

    if not _is_path_within_roots(browse_path, roots):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "path_not_allowed",
                "message": (
                    f"Path '{path}' is not within any configured source filesystem root. "
                    f"Allowed: {', '.join(str(r) for r in roots)}"
                ),
            },
        )

    if not browse_path.exists():
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

    entries: list[dict[str, Any]] = []
    try:
        for item in sorted(browse_path.iterdir()):
            if item.name.startswith("."):
                continue
            try:
                is_dir = item.is_dir()
                entry: dict[str, Any] = {
                    "path": str(item),
                    "name": item.name,
                    "type": "folder" if is_dir else "file",
                    "has_children": is_dir,
                }
                if not is_dir:
                    try:
                        entry["size_bytes"] = item.stat().st_size
                    except (OSError, PermissionError):
                        entry["size_bytes"] = None
                    entry["extension"] = item.suffix.lower()
                entries.append(entry)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError) as exc:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "permission_denied",
                "message": f"Cannot access directory: {exc}",
            },
        )

    # Compute parent path if still within allowlist
    parent_path: str | None = None
    parent_candidate = browse_path.parent
    if parent_candidate != browse_path and _is_path_within_roots(parent_candidate, roots):
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


@router.post("/api/source-filesystems/select")
def select_source_filesystem_entries(request: Request, payload: dict[str, Any]) -> Any:
    """
    Select files/folders from allowlisted source filesystem roots and create an intake queue item.

    Payload:
      selections: list of
        { type: "file", path: "/abs/path/to/file.3mf" }
                { type: "folder", path: "/abs/path/to/folder", recurse: bool }
      cleanup_policy: "keep" | "delete_on_verified" | "replace_with_stub"  (default "keep")

    - Enforces allowlist on every path.
    - Folder selections expand to file lists for source_metadata but are stored as-is.
    - Creates one intake_queue_uploads record.
    - Returns upload_id for tracking.
    """
    state: AppState = request.app.state.model_catalog
    roots = _configured_intake_source_roots(state.settings)
    if not roots:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_roots_configured",
                "message": "No intake source roots are configured. Set MODEL_CATALOG_INTAKE_ROOTS.",
            },
        )

    selections = payload.get("selections")
    if not isinstance(selections, list) or len(selections) == 0:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "selections must be a non-empty list of {type, path, recurse?}",
            },
        )

    cleanup_policy = str(payload.get("cleanup_policy") or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        cleanup_policy = "keep"

    validated_entries: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    expanded_file_count = 0

    for idx, selection in enumerate(selections):
        if not isinstance(selection, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_selection",
                    "message": f"selections[{idx}] must be an object",
                },
            )

        entry_type = str(selection.get("type") or "").strip().lower()
        entry_path_raw = str(selection.get("path") or "").strip()

        if entry_type not in {"file", "folder"}:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_selection_type",
                    "message": f"selections[{idx}].type must be 'file' or 'folder', got '{entry_type}'",
                },
            )

        if not entry_path_raw:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_selection_path",
                    "message": f"selections[{idx}].path is required",
                },
            )

        resolved = Path(entry_path_raw).expanduser().resolve()

        # Traversal guard: must be within an allowlisted root
        if not _is_path_within_roots(resolved, roots):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "path_not_allowed",
                    "message": (
                        f"selections[{idx}].path '{entry_path_raw}' is not within any "
                        f"configured source filesystem root."
                    ),
                },
            )

        if not resolved.exists():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "source_not_found",
                    "message": f"selections[{idx}].path does not exist: {entry_path_raw}",
                },
            )

        if entry_type == "file":
            if not resolved.is_file():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_is_not_file",
                        "message": f"selections[{idx}] type is 'file' but path is not a file: {entry_path_raw}",
                    },
                )
            try:
                stat_result = resolved.stat()
            except (OSError, PermissionError) as exc:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_stat_error",
                        "message": f"selections[{idx}].path could not be read: {exc}",
                    },
                )
            if resolved.suffix.lower() not in SUPPORTED_INTAKE_FILE_EXTENSIONS:
                warnings.append(
                    {
                        "code": "unsupported_file_type",
                        "message": f"Skipped unsupported selection: {resolved.name}",
                        "path": str(resolved),
                    }
                )
                continue
            entry_meta = _bulk_path_source_metadata(resolved, stat_result)
            validated_entries.append(
                {
                    "type": "file",
                    "path": str(resolved),
                    "source_mtime": entry_meta["source_mtime"],
                    "source_ctime": entry_meta["source_ctime"],
                    "source_birthtime": entry_meta.get("source_birthtime"),
                    "source_size_bytes": int(stat_result.st_size),
                }
            )
            normalized_title_source = _normalize_group_title_source(selection.get("group_title_source"))
            group_title = str(selection.get("group_title") or "").strip()
            grouping_strategy = str(selection.get("grouping_strategy") or "").strip().lower()
            if normalized_title_source:
                validated_entries[-1]["group_title_source"] = normalized_title_source
            if group_title:
                validated_entries[-1]["group_title"] = group_title
            if grouping_strategy:
                validated_entries[-1]["grouping_strategy"] = grouping_strategy
            if "preserve_folder_structure" in selection:
                validated_entries[-1]["preserve_folder_structure"] = _coerce_bool(selection.get("preserve_folder_structure"))
            # Issue #1347: persist excluded_items so validation/grouping can honour user removals.
            raw_excluded = selection.get("excluded_items")
            if isinstance(raw_excluded, list):
                normalized_excluded = [str(p).strip() for p in raw_excluded if str(p or "").strip()]
                if normalized_excluded:
                    validated_entries[-1]["excluded_items"] = normalized_excluded
            expanded_file_count += 1

        else:  # folder
            if not resolved.is_dir():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_is_not_folder",
                        "message": f"selections[{idx}] type is 'folder' but path is not a directory: {entry_path_raw}",
                    },
                )
            recurse = _coerce_bool(selection.get("recurse", True))
            try:
                folder_stat = resolved.stat()
            except (OSError, PermissionError) as exc:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_stat_error",
                        "message": f"selections[{idx}].path could not be read: {exc}",
                    },
                )
            folder_meta = _bulk_path_source_metadata(resolved, folder_stat)
            # Expand to count contained files (for metadata); the queue entry stores the folder
            contained_files = _collect_intake_source_files_in_folder(
                resolved, recurse=recurse
            )
            disallowed_count = _count_disallowed_files_in_folder(resolved, recurse=recurse)
            if disallowed_count > 0:
                warnings.append(
                    {
                        "code": "unsupported_file_type",
                        "message": f"Skipped {disallowed_count} unsupported file(s) under folder selection.",
                        "path": str(resolved),
                        "excluded_count": disallowed_count,
                    }
                )
            validated_entries.append(
                {
                    "type": "folder",
                    "path": str(resolved),
                    "recurse": recurse,
                    "source_mtime": folder_meta["source_mtime"],
                    "source_ctime": folder_meta["source_ctime"],
                    "source_birthtime": folder_meta.get("source_birthtime"),
                    "contained_file_count": len(contained_files),
                }
            )
            normalized_title_source = _normalize_group_title_source(selection.get("group_title_source"))
            group_title = str(selection.get("group_title") or "").strip()
            grouping_strategy = str(selection.get("grouping_strategy") or "").strip().lower()
            if normalized_title_source:
                validated_entries[-1]["group_title_source"] = normalized_title_source
            if group_title:
                validated_entries[-1]["group_title"] = group_title
            if grouping_strategy:
                validated_entries[-1]["grouping_strategy"] = grouping_strategy
            if "preserve_folder_structure" in selection:
                validated_entries[-1]["preserve_folder_structure"] = _coerce_bool(selection.get("preserve_folder_structure"))
            # Issue #1347: persist excluded_items so validation/grouping can honour user removals.
            raw_excluded = selection.get("excluded_items")
            if isinstance(raw_excluded, list):
                normalized_excluded = [str(p).strip() for p in raw_excluded if str(p or "").strip()]
                if normalized_excluded:
                    validated_entries[-1]["excluded_items"] = normalized_excluded
            expanded_file_count += len(contained_files)

    if not validated_entries:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_supported_sources",
                "message": "No supported intake sources remained after filtering selections.",
                "warnings": warnings,
            },
        )

    consolidated_entries = _consolidate_overlapping_selections(validated_entries)
    expanded_file_count = 0
    for entry in consolidated_entries:
        if str(entry.get("type") or "").strip().lower() == "file":
            expanded_file_count += 1
            continue
        folder_path = Path(str(entry.get("path") or "")).expanduser().resolve()
        recurse = _coerce_bool(entry.get("recurse", True))
        expanded_file_count += len(
            _collect_intake_source_files_in_folder(folder_path, recurse=recurse)
        )

    # Create intake queue record
    upload_id = str(_uuid_module.uuid4())
    now_iso = _bulk_utc_now_iso()
    source_entries_json = json.dumps(consolidated_entries)

    connection = connect(state.settings.db_path)
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
                source_entries_json,
                "unverified",
                cleanup_policy,
                now_iso,
                now_iso,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "success": True,
        "upload_id": upload_id,
        "status": "queued",
        "verification_status": "unverified",
        "cleanup_policy": cleanup_policy,
        "selection_count": len(consolidated_entries),
        "expanded_file_count": expanded_file_count,
        "warnings": warnings,
        "created_at": now_iso,
    }

