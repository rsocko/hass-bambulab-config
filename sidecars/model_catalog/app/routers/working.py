# sidecars/model_catalog/app/routers/working.py
"""
Working files, working groups, projects, and bulk import/discover operations router.
This router handles:
- File inventory management (reindex, list, explore)
- Working group CRUD and management
- Group-to-model linkage
- Batch membership operations
- Group reorganization
- Project management for working groups
- Publishing working groups to local models
- Bulk discovery and bulk import workflows
"""
from __future__ import annotations
import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import time
from pathlib import Path, PureWindowsPath
from sqlite3 import connect
from typing import Any
from urllib.parse import quote
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..settings import Settings
from ..state import AppState
from ..geometry_3mf import extract_3mf_thumbnail
from .._helpers import (
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _coerce_bool,
    _coerce_int,
    _collect_intake_source_files_in_folder,
    _configured_intake_source_roots,
    _configured_working_files_roots,
    _dedupe_paths,
    _is_path_within_roots,
    _model_photo_storage_root,
    _normalize_path_compare_key,
    _windows_launch_enabled,
)
from ..local_models import (
    create_local_model,
    create_model_asset,
    delete_local_model,
    delete_model_asset,
    list_local_models,
    list_model_assets,
    read_local_model,
    update_local_model,
    update_model_asset,
)
from ..db import (
    read_model_field,
    read_model_fields,
    set_model_field,
)
from ..services import (
    add_working_group_item_service,
    batch_add_working_group_memberships_service,
    batch_remove_working_group_memberships_service,
    bulk_discover_working_groups_service,
    bulk_import_working_groups_service,
    build_dedup_collision_warning,
    create_model_catalog_project_service,
    create_working_group_link_service,
    create_working_group_service,
    delete_working_group_link_service,
    delete_working_group_service,
    detect_duplicate_files,
    get_model_catalog_project_service,
    get_model_lineage_service,
    get_working_group_service,
    get_all_indexed_file_hashes,
    get_working_items_hashes,
    list_model_catalog_projects_service,
    list_working_group_links_service,
    list_working_groups_for_model_service,
    list_working_groups_service,
    publish_working_group_to_local_service,
    remove_working_group_item_service,
    reorganize_working_group_service,
    update_working_group_service,
)
from ..services.shared_helpers import (
    _resolve_local_asset_storage_path,
    _serialize_project_row,
    _serialize_working_group,
    _sha256_file,
    _slugify_title,
    _working_group_effective_folder_path,
)

router = APIRouter(tags=["working"])

# ==================== CONSTANTS ====================

SUPPORTED_BULK_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj"}
LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
LOCAL_IMPORT_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"}
LOCAL_IMPORT_DOCUMENT_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json", ".yaml", ".yml"}

# Valid state transitions for intake queue uploads (shared with intake handler)
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"uploading", "failed"},
    "uploading": {"uploaded_unverified", "failed"},
    "uploaded_unverified": {"verified", "failed"},
    "verified": {"cleanup_pending", "failed"},
    "cleanup_pending": {"cleanup_done", "cleanup_failed"},
    "cleanup_done": set(),
    "cleanup_failed": {"cleanup_pending"},
    "failed": set(),
}

_WORKING_INLINE_IMAGE_MAX_BYTES = 2 * 1024 * 1024
_WORKING_INLINE_3MF_MAX_BYTES = 300 * 1024 * 1024
_WORKING_THUMB_CACHE_MAX = 256
_WORKING_THUMB_CACHE: dict[str, str] = {}
_WORKING_PREVIEW_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_WORKING_PREVIEW_MAX_3MF_BYTES = 300 * 1024 * 1024
_WORKING_INVENTORY_EXTENSIONS = SUPPORTED_WORKING_FILE_EXTENSIONS | LOCAL_IMPORT_IMAGE_EXTENSIONS


def _detect_image_mime(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a"):
        return "image/gif"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    if payload.startswith(b"BM"):
        return "image/bmp"
    return None


def _data_url(mime: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _working_thumbnail_data_url(file_path: str | None) -> str | None:
    path_text = str(file_path or "").strip()
    if not path_text:
        return None
    try:
        resolved = Path(path_text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None

    try:
        stat_result = resolved.stat()
    except OSError:
        return None

    cache_key = f"{_normalize_path_compare_key(str(resolved))}|{int(stat_result.st_mtime)}|{int(stat_result.st_size)}"
    cached = _WORKING_THUMB_CACHE.get(cache_key)
    if cached is not None:
        return cached or None

    suffix = resolved.suffix.lower()
    data_url_value: str | None = None

    try:
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            if int(stat_result.st_size) <= _WORKING_INLINE_IMAGE_MAX_BYTES:
                payload = resolved.read_bytes()
                mime = _detect_image_mime(payload)
                if mime:
                    data_url_value = _data_url(mime, payload)
        elif suffix == ".svg":
            if int(stat_result.st_size) <= _WORKING_INLINE_IMAGE_MAX_BYTES:
                payload = resolved.read_bytes()
                data_url_value = _data_url("image/svg+xml", payload)
        elif suffix == ".3mf":
            if int(stat_result.st_size) <= _WORKING_INLINE_3MF_MAX_BYTES:
                package_bytes = resolved.read_bytes()
                thumbnail_bytes = extract_3mf_thumbnail(package_bytes)
                if thumbnail_bytes:
                    mime = _detect_image_mime(thumbnail_bytes)
                    if mime:
                        data_url_value = _data_url(mime, thumbnail_bytes)
    except OSError:
        data_url_value = None
    except Exception:
        data_url_value = None

    _WORKING_THUMB_CACHE[cache_key] = data_url_value or ""
    if len(_WORKING_THUMB_CACHE) > _WORKING_THUMB_CACHE_MAX:
        oldest_key = next(iter(_WORKING_THUMB_CACHE))
        _WORKING_THUMB_CACHE.pop(oldest_key, None)

    return data_url_value


def _working_preview_url(file_path: str | None) -> str | None:
    path_text = str(file_path or "").strip()
    if not path_text:
        return None
    suffix = Path(path_text).suffix.lower()
    if suffix not in LOCAL_IMPORT_IMAGE_EXTENSIONS and suffix != ".3mf":
        return None
    return f"/api/working-files/preview?path={quote(path_text, safe='')}"


def _resolve_working_file_path(*, settings: Settings, path_value: str | None) -> Path | None:
    candidate = str(path_value or "").strip()
    if not candidate:
        return None
    try:
        resolved = Path(candidate).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    allowlisted_roots = _configured_working_files_roots(settings)
    if not _is_path_within_roots(resolved, allowlisted_roots):
        return None
    return resolved


def _prune_working_file_slicer_tokens(state: AppState) -> None:
    now = time.time()
    last_pruned = float(getattr(state, "working_file_slicer_tokens_last_pruned_at", 0.0) or 0.0)
    if now - last_pruned < 30:
        return
    token_map = getattr(state, "working_file_slicer_tokens", {})
    expired = [
        token
        for token, payload in token_map.items()
        if float(payload.get("expires_at", 0.0) or 0.0) <= now
    ]
    for token in expired:
        token_map.pop(token, None)
    state.working_file_slicer_tokens_last_pruned_at = now


def _prune_local_action_tokens(state: AppState) -> None:
    now = time.time()
    last_pruned = float(getattr(state, "local_action_tokens_last_pruned_at", 0.0) or 0.0)
    if now - last_pruned < 30:
        return
    token_map = getattr(state, "local_action_tokens", {})
    expired = [
        token
        for token, payload in token_map.items()
        if float(payload.get("expires_at", 0.0) or 0.0) <= now
    ]
    for token in expired:
        token_map.pop(token, None)
    state.local_action_tokens_last_pruned_at = now


def _store_local_action_token(*, state: AppState, action: str, file_path: Path) -> str:
    _prune_local_action_tokens(state)
    token = secrets.token_urlsafe(24)
    token_map = getattr(state, "local_action_tokens", {})
    token_map[token] = {
        "action": action,
        "path": str(file_path),
        "expires_at": time.time() + float(getattr(state, "local_action_token_ttl_seconds", 300) or 300),
    }
    return token


def _consume_local_action_token(state: AppState, token: str) -> dict[str, object] | None:
    _prune_local_action_tokens(state)
    token_map = getattr(state, "local_action_tokens", {})
    payload = token_map.pop(token, None)
    if not isinstance(payload, dict):
        return None
    if float(payload.get("expires_at", 0.0) or 0.0) <= time.time():
        return None
    return payload


def _one_drive_consumer_relative_path(windows_path: str | None) -> str | None:
    normalized = str(windows_path or "").strip().replace("/", "\\")
    if not normalized:
        return None
    marker = "\\OneDrive\\"
    marker_index = normalized.lower().find(marker.lower())
    if marker_index < 0:
        return None
    relative = normalized[marker_index + len("\\OneDrive") :].lstrip("\\")
    return relative or None


def _store_working_file_slicer_token(*, state: AppState, file_path: Path) -> str:
    _prune_working_file_slicer_tokens(state)
    token = secrets.token_urlsafe(24)
    token_map = getattr(state, "working_file_slicer_tokens", {})
    token_map[token] = {
        "path": str(file_path),
        "expires_at": time.time() + float(getattr(state, "working_file_slicer_token_ttl_seconds", 300) or 300),
    }
    return token


def _read_working_file_slicer_token(state: AppState, token: str) -> dict[str, object] | None:
    _prune_working_file_slicer_tokens(state)
    token_map = getattr(state, "working_file_slicer_tokens", {})
    payload = token_map.get(token)
    if not isinstance(payload, dict):
        return None
    if float(payload.get("expires_at", 0.0) or 0.0) <= time.time():
        token_map.pop(token, None)
        return None
    return payload


@router.get("/api/working-files/preview")
def working_files_preview(request: Request, path: str | None = None) -> Any:
    """Return a lazy-loaded preview image for working files allowlisted roots."""
    state: AppState = request.app.state.model_catalog

    path_value = str(path or "").strip()
    if not path_value:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_path",
                "message": "Query parameter 'path' is required.",
            },
        )

    try:
        resolved_path = Path(path_value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_path",
                "message": "Could not resolve preview path.",
            },
        )

    allowlisted_roots = _configured_working_files_roots(state.settings)
    if not _is_path_within_roots(resolved_path, allowlisted_roots):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "path_not_allowed",
                "message": "Preview path is outside allowed working roots.",
            },
        )

    if not resolved_path.exists() or not resolved_path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Preview file not found.",
            },
        )

    suffix = str(resolved_path.suffix or "").lower()

    if suffix in LOCAL_IMPORT_IMAGE_EXTENSIONS:
        file_size = resolved_path.stat().st_size
        if file_size > _WORKING_PREVIEW_MAX_IMAGE_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": "preview_too_large",
                    "message": "Image preview exceeds max size (5 MB).",
                },
            )

        try:
            content = resolved_path.read_bytes()
        except (OSError, PermissionError):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "preview_read_failed",
                    "message": "Could not read preview file.",
                },
            )

        if suffix == ".svg":
            media_type = "image/svg+xml"
        elif suffix in {".jpg", ".jpeg"}:
            media_type = "image/jpeg"
        elif suffix == ".png":
            media_type = "image/png"
        elif suffix == ".webp":
            media_type = "image/webp"
        elif suffix == ".gif":
            media_type = "image/gif"
        else:
            media_type = "application/octet-stream"

        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=600"},
        )

    if suffix == ".3mf":
        file_size = resolved_path.stat().st_size
        if file_size > _WORKING_PREVIEW_MAX_3MF_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error": "model_file_too_large",
                    "message": "3MF file exceeds max size for preview extraction.",
                },
            )

        try:
            thumbnail_bytes = extract_3mf_thumbnail(resolved_path.read_bytes())
        except (OSError, PermissionError):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "preview_read_failed",
                    "message": "Could not read model file for preview extraction.",
                },
            )

        if thumbnail_bytes is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "thumbnail_not_found",
                    "message": "No embedded thumbnail found in 3MF file.",
                },
            )

        mime_type = "image/png"
        if thumbnail_bytes[:3] == b"\xff\xd8\xff":
            mime_type = "image/jpeg"

        return Response(
            content=thumbnail_bytes,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=600"},
        )

    return JSONResponse(
        status_code=415,
        content={
            "success": False,
            "error": "preview_unsupported_type",
            "message": "Preview is supported for images and .3mf files only.",
        },
    )


@router.post("/api/working-files/slicer-token")
def create_working_file_slicer_token(request: Request, payload: dict[str, Any] | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    path_value = str((payload or {}).get("path") or "").strip()
    resolved_path = _resolve_working_file_path(settings=state.settings, path_value=path_value)
    if resolved_path is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "path_not_allowed",
                "message": "Working file path is outside allowed roots or could not be resolved.",
            },
        )
    if not resolved_path.exists() or not resolved_path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Working file not found.",
            },
        )
    if resolved_path.suffix.lower() != ".3mf":
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "unsupported_file_type",
                "message": "Open in Slicer is supported for .3mf files only.",
            },
        )

    token = _store_working_file_slicer_token(state=state, file_path=resolved_path)
    relative_download_url = f"/api/working-files/dl/{quote(token, safe='')}/{quote(resolved_path.name, safe='')}"
    base_url = str(getattr(state.settings, "catalog_base_url", "") or "").strip().rstrip("/")
    return {
        "success": True,
        "token": token,
        "filename": resolved_path.name,
        "download_url": f"{base_url}{relative_download_url}" if base_url else relative_download_url,
    }


@router.get("/api/working-files/dl/{token}/{filename}")
def download_working_file_for_slicer(request: Request, token: str, filename: str) -> Any:
    state: AppState = request.app.state.model_catalog
    payload = _read_working_file_slicer_token(state, str(token or "").strip())
    if not payload:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "invalid_or_expired_token",
                "message": "Slicer download token is invalid or expired.",
            },
        )
    resolved_path = _resolve_working_file_path(settings=state.settings, path_value=str(payload.get("path") or ""))
    if resolved_path is None or not resolved_path.exists() or not resolved_path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Working file not found.",
            },
        )
    media_type = mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"
    try:
        return Response(
            content=resolved_path.read_bytes(),
            media_type=media_type,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{resolved_path.name}"',
            },
        )
    except (OSError, PermissionError):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "download_read_failed",
                "message": "Could not read working file for slicer download.",
            },
        )


@router.post("/api/working-files/local-action-token")
def create_working_file_local_action_token(request: Request, payload: dict[str, Any] | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    action = str((payload or {}).get("action") or "").strip().lower()
    if action not in {"open_local", "open_folder", "open_in_slicer"}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_action",
                "message": "action must be one of open_local, open_folder, or open_in_slicer.",
            },
        )
    path_value = str((payload or {}).get("path") or "").strip()
    resolved_path = _resolve_working_file_path(settings=state.settings, path_value=path_value)
    if resolved_path is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "path_not_allowed",
                "message": "Working path is outside allowed roots or could not be resolved.",
            },
        )
    if action in {"open_local", "open_in_slicer"} and (not resolved_path.exists() or not resolved_path.is_file()):
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Working file not found.",
            },
        )
    if action == "open_in_slicer" and resolved_path.suffix.lower() != ".3mf":
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "unsupported_file_type",
                "message": "Open in Slicer is supported for .3mf files only.",
            },
        )
    if action == "open_folder" and not resolved_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Working folder not found.",
            },
        )
    token = _store_local_action_token(state=state, action=action, file_path=resolved_path)
    protocol_action = {
        "open_local": "open-local",
        "open_folder": "open-folder",
        "open_in_slicer": "open-in-slicer",
    }[action]
    return {
        "success": True,
        "token": token,
        "launch_url": f"modelcatalog://{protocol_action}?token={quote(token, safe='')}",
        "action": action,
    }


@router.post("/api/local-actions/resolve")
def resolve_local_action(request: Request, payload: dict[str, Any] | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    token = str((payload or {}).get("token") or "").strip()
    if not token:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "missing_token",
                "message": "token is required.",
            },
        )
    token_payload = _consume_local_action_token(state, token)
    if not token_payload:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "invalid_or_expired_token",
                "message": "Local action token is invalid or expired.",
            },
        )
    resolved_path = _resolve_working_file_path(settings=state.settings, path_value=str(token_payload.get("path") or ""))
    if resolved_path is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "path_not_found",
                "message": "Working path could not be resolved.",
            },
        )
    launch_context = _launch_context_for_path(str(resolved_path), state.settings)
    windows_path = str(launch_context.get("windows_path") or "").strip() or None
    return {
        "success": True,
        "action": str(token_payload.get("action") or ""),
        "path": {
            "container_path": str(resolved_path),
            "windows_path": windows_path,
            "one_drive_consumer_relative_path": _one_drive_consumer_relative_path(windows_path),
            "is_file": resolved_path.is_file(),
            "is_dir": resolved_path.is_dir(),
            "name": resolved_path.name,
        },
    }


# ==================== HELPER FUNCTIONS: FILE OPERATIONS ====================


def _scan_files_under_roots(*, roots: list[Path], recurse: bool = True) -> list[dict[str, Any]]:
    """Scan files under root paths, respecting supported extensions."""
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        walker = root.rglob("*") if recurse else root.glob("*")
        for candidate in sorted(walker):
            if candidate.name.startswith("."):
                continue
            if not candidate.is_file():
                continue
            suffix = candidate.suffix.lower()
            if suffix not in _WORKING_INVENTORY_EXTENSIONS:
                continue
            try:
                stat_result = candidate.stat()
                source_metadata = _bulk_path_source_metadata(candidate, stat_result)
            except (OSError, PermissionError):
                continue
            rows.append(
                {
                    "source_path_raw": str(candidate),
                    "source_path_canonical": str(candidate.resolve()),
                    "source_path_compare_key": _normalize_compare_key(candidate.resolve()),
                    "file_name_raw": candidate.name,
                    "file_name_base_hint": _normalize_file_name_hint(candidate.name),
                    "file_extension": suffix,
                    "file_size_bytes": int(stat_result.st_size),
                    "source_mtime": source_metadata.get("source_mtime"),
                    "source_ctime": source_metadata.get("source_ctime"),
                    "source_birthtime": source_metadata.get("source_birthtime"),
                    "sha256_hash": None,
                    "root_path": str(root),
                }
            )
    return rows


def _refresh_working_file_inventory(*, db_path: Path, roots: list[Path], compute_hashes: bool = False) -> dict[str, Any]:
    """Refresh working file inventory, updating hashes and detecting missing files."""
    discovered_rows = _scan_files_under_roots(roots=roots)
    now_iso = _bulk_utc_now_iso()

    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    inserted = 0
    updated = 0
    removed = 0
    hashed = 0
    try:
        existing_rows = connection.execute(
            "SELECT id, source_path_compare_key, file_size_bytes, source_mtime, sha256_hash FROM working_file_inventory"
        ).fetchall()
        existing_by_key = {str(row["source_path_compare_key"]): row for row in existing_rows}
        seen_keys: set[str] = set()

        for row in discovered_rows:
            compare_key = str(row["source_path_compare_key"])
            seen_keys.add(compare_key)
            existing = existing_by_key.get(compare_key)
            next_hash = None
            if compute_hashes:
                try:
                    next_hash = _sha256_file(Path(str(row["source_path_canonical"]))).lower()
                    hashed += 1
                except (OSError, PermissionError):
                    next_hash = None
            elif existing is not None:
                existing_size = int(existing["file_size_bytes"] or 0)
                existing_mtime = str(existing["source_mtime"] or "")
                if existing_size == int(row["file_size_bytes"]) and existing_mtime == str(row["source_mtime"] or ""):
                    next_hash = str(existing["sha256_hash"] or "").strip() or None

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO working_file_inventory (
                        source_path_raw, source_path_canonical, source_path_compare_key,
                        file_name_raw, file_name_base_hint, file_extension,
                        file_size_bytes, sha256_hash,
                        source_mtime, source_ctime, source_birthtime,
                        validation_state, warnings_json,
                        detected_at, last_seen_at, root_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["source_path_raw"],
                        row["source_path_canonical"],
                        row["source_path_compare_key"],
                        row["file_name_raw"],
                        row["file_name_base_hint"],
                        row["file_extension"],
                        row["file_size_bytes"],
                        next_hash,
                        row["source_mtime"],
                        row["source_ctime"],
                        row["source_birthtime"],
                        "ready",
                        "[]",
                        now_iso,
                        now_iso,
                        row["root_path"],
                    ),
                )
                inserted += 1
                continue

            connection.execute(
                """
                UPDATE working_file_inventory
                SET source_path_raw = ?,
                    source_path_canonical = ?,
                    file_name_raw = ?,
                    file_name_base_hint = ?,
                    file_extension = ?,
                    file_size_bytes = ?,
                    sha256_hash = COALESCE(?, sha256_hash),
                    source_mtime = ?,
                    source_ctime = ?,
                    source_birthtime = ?,
                    validation_state = ?,
                    warnings_json = ?,
                    last_seen_at = ?,
                    root_path = ?
                WHERE source_path_compare_key = ?
                """,
                (
                    row["source_path_raw"],
                    row["source_path_canonical"],
                    row["file_name_raw"],
                    row["file_name_base_hint"],
                    row["file_extension"],
                    row["file_size_bytes"],
                    next_hash,
                    row["source_mtime"],
                    row["source_ctime"],
                    row["source_birthtime"],
                    "ready",
                    "[]",
                    now_iso,
                    row["root_path"],
                    compare_key,
                ),
            )
            updated += 1

        stale_keys = [
            str(row["source_path_compare_key"])
            for row in existing_rows
            if str(row["source_path_compare_key"]) not in seen_keys
        ]
        if stale_keys:
            placeholders = ",".join("?" for _ in stale_keys)
            connection.execute(
                f"DELETE FROM working_file_inventory WHERE source_path_compare_key IN ({placeholders})",
                stale_keys,
            )
            removed = len(stale_keys)

        repaired_group_paths = _repair_stale_working_group_paths(connection, now_iso=now_iso)

        connection.commit()
    finally:
        connection.close()

    return {
        "discovered": len(discovered_rows),
        "inserted": inserted,
        "updated": updated,
        "removed": removed,
        "hashed": hashed,
        "repaired_group_paths": repaired_group_paths,
        "roots": [str(root) for root in roots],
        "refreshed_at": now_iso,
    }


def _repair_stale_working_group_paths(connection: sqlite3.Connection, *, now_iso: str) -> int:
    inventory_rows = [dict(row) for row in connection.execute(
        """
        SELECT id, source_path_raw, source_path_canonical, source_path_compare_key,
               file_name_raw, file_size_bytes, sha256_hash,
               source_mtime, source_ctime, source_birthtime
        FROM working_file_inventory
        """
    ).fetchall()]
    inventory_by_key = {
        str(row.get("source_path_compare_key") or ""): row
        for row in inventory_rows
        if str(row.get("source_path_compare_key") or "")
    }
    inventory_by_hash = {
        str(row.get("sha256_hash") or "").strip().lower(): row
        for row in inventory_rows
        if str(row.get("sha256_hash") or "").strip()
    }
    candidate_rows_by_name_size: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
    for row in inventory_rows:
        candidate_key = (
            str(row.get("file_name_raw") or "").strip().lower(),
            int(row["file_size_bytes"]) if row.get("file_size_bytes") is not None else None,
        )
        candidate_rows_by_name_size.setdefault(candidate_key, []).append(row)

    stale_item_rows = connection.execute(
        """
        SELECT wi.id, wi.working_group_id, wi.file_path, wi.item_role, wi.file_hash, wi.file_size,
               wi.source_metadata_json, wg.primary_file_path
        FROM working_items wi
        JOIN working_groups wg ON wg.id = wi.working_group_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM working_file_inventory wfi
            WHERE wfi.source_path_compare_key = LOWER(REPLACE(wi.file_path, '\\', '/'))
        )
        ORDER BY wi.id ASC
        """
    ).fetchall()

    repaired = 0
    for item_row in stale_item_rows:
        current_path = str(item_row["file_path"] or "").strip()
        if not current_path:
            continue

        raw_source_metadata = str(item_row["source_metadata_json"] or "{}").strip() or "{}"
        try:
            source_metadata = json.loads(raw_source_metadata)
        except json.JSONDecodeError:
            source_metadata = {}
        if not isinstance(source_metadata, dict):
            source_metadata = {}

        item_hash = str(item_row["file_hash"] or "").strip().lower()
        replacement_row = inventory_by_hash.get(item_hash) if item_hash else None
        if replacement_row is None and item_hash:
            candidate_key = (
                Path(current_path).name.strip().lower(),
                int(item_row["file_size"]) if item_row["file_size"] is not None else None,
            )
            for candidate in candidate_rows_by_name_size.get(candidate_key, []):
                candidate_hash = str(candidate.get("sha256_hash") or "").strip().lower()
                if not candidate_hash:
                    candidate_path = str(candidate.get("source_path_canonical") or candidate.get("source_path_raw") or "").strip()
                    if not candidate_path:
                        continue
                    try:
                        candidate_hash = _sha256_file(Path(candidate_path)).lower()
                    except (OSError, PermissionError):
                        continue
                    candidate["sha256_hash"] = candidate_hash
                    inventory_by_hash[candidate_hash] = candidate
                    connection.execute(
                        "UPDATE working_file_inventory SET sha256_hash = ? WHERE id = ?",
                        (candidate_hash, int(candidate["id"])),
                    )
                if candidate_hash == item_hash:
                    replacement_row = candidate
                    break

        if replacement_row is None:
            candidate_key = (
                Path(current_path).name.strip().lower(),
                int(item_row["file_size"]) if item_row["file_size"] is not None else None,
            )
            metadata_candidates = list(candidate_rows_by_name_size.get(candidate_key, []))
            for field_name in ("source_mtime", "source_birthtime", "source_ctime"):
                expected_value = str(source_metadata.get(field_name) or "").strip()
                if not expected_value or len(metadata_candidates) <= 1:
                    continue
                narrowed = [
                    candidate
                    for candidate in metadata_candidates
                    if str(candidate.get(field_name) or "").strip() == expected_value
                ]
                if narrowed:
                    metadata_candidates = narrowed
            if len(metadata_candidates) == 1:
                replacement_row = metadata_candidates[0]

        if replacement_row is None:
            continue

        next_path = str(replacement_row.get("source_path_canonical") or replacement_row.get("source_path_raw") or "").strip()
        next_key = _normalize_path_compare_key(next_path)
        current_key = _normalize_path_compare_key(current_path)
        if not next_path or not next_key or next_key == current_key:
            continue

        source_metadata["source_path"] = next_path
        for field_name in ("source_mtime", "source_ctime", "source_birthtime"):
            field_value = str(replacement_row.get(field_name) or "").strip()
            if field_value:
                source_metadata[field_name] = field_value
            else:
                source_metadata.pop(field_name, None)

        connection.execute(
            "UPDATE working_items SET file_path = ?, updated_at = ?, source_metadata_json = ? WHERE id = ?",
            (next_path, now_iso, json.dumps(source_metadata), int(item_row["id"])),
        )
        if _normalize_path_compare_key(item_row["primary_file_path"]) == current_key:
            connection.execute(
                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                (next_path, now_iso, int(item_row["working_group_id"])),
            )
        repaired += 1

    return repaired


def _read_existing_working_hashes(db_path: Path) -> set[str]:
    """Read all existing file hashes from working_items."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hash FROM working_items WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''"
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    finally:
        connection.close()


# ==================== HELPER FUNCTIONS: PATH OPERATIONS ====================


def _normalize_compare_key(path_value: Path) -> str:
    """Normalize path for comparison (lowercase, forward slashes)."""
    return str(path_value).replace("\\", "/").lower()


def _working_file_path_within_roots(path_value: str | None, roots: list[Path]) -> bool:
    """Check if a path is within allowed roots."""
    path_text = str(path_value or "").strip()
    if not path_text:
        return False
    try:
        resolved = Path(path_text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return _is_path_within_roots(resolved, roots)


def _windows_root_from_assets_host(settings: Settings) -> str | None:
    """Extract Windows root from assets_root_host config."""
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
    """Convert container /assets path to Windows path if possible."""
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


def _generate_commands_for_path(windows_path: str | None) -> dict[str, str]:
    """Generate Windows shell commands for a file or folder path."""
    if not windows_path:
        return {"explorer_command": "", "folder_command": ""}
    
    # Normalize the path
    normalized = str(windows_path).strip()
    if not normalized:
        return {"explorer_command": "", "folder_command": ""}
    
    # For a file: explorer.exe /select,"C:\path\to\file.ext"
    # For a folder: explorer.exe "C:\path\to\folder"
    explorer_select = f'explorer.exe /select,"{normalized}"'
    explorer_open = f'explorer.exe "{normalized}"'
    
    return {
        "explorer_command": explorer_select,  # Use /select for files, open for folders
        "folder_command": explorer_open,      # Always available for opening folder
    }


def _launch_context_for_path(path_value: str | None, settings: Settings) -> dict[str, Any]:
    """Generate launch context for a file path (Windows file opening)."""
    container_path = str(path_value or "").strip()
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip()
    launch_enabled = _windows_launch_enabled(settings)
    windows_path = _container_assets_path_to_windows(container_path, settings)

    reason: str | None = None
    if not launch_enabled:
        reason = "assets_root_host_not_mnt_c"
    elif not windows_path:
        reason = "path_outside_assets_mount"

    commands = _generate_commands_for_path(windows_path)

    return {
        "container_path": container_path,
        "assets_root_host": assets_root_host,
        "windows_launch_enabled": launch_enabled,
        "can_launch_file": bool(windows_path),
        "can_open_in_explorer": bool(windows_path),
        "windows_path": windows_path,
        "reason": reason,
        "explorer_command": commands.get("explorer_command", ""),
        "folder_command": commands.get("folder_command", ""),
    }


def _working_files_destination_root(settings: Settings) -> Path | None:
    """Get the primary working files destination root."""
    preferred_roots = _configured_working_files_roots(settings)
    if not preferred_roots:
        return None
    return preferred_roots[0]


def _working_group_allowed_source_roots(settings: Settings) -> list[Path]:
    """Get all allowed source roots for working groups (intake + working)."""
    return _dedupe_paths(_configured_intake_source_roots(settings) + _configured_working_files_roots(settings))


def _preferred_working_files_roots(allowlisted_roots: list[Path]) -> list[Path]:
    """Get preferred working files roots, preferring 'Model Working Files' folder."""
    if not allowlisted_roots:
        return []
    preferred_root = Path("/assets/Model Working Files").resolve()
    if _is_path_within_roots(preferred_root, allowlisted_roots):
        return [preferred_root]
    named_roots = [root for root in allowlisted_roots if root.name.strip().lower() == "model working files"]
    if named_roots:
        return named_roots
    return allowlisted_roots


# ==================== HELPER FUNCTIONS: GROUP AND PROJECT MANAGEMENT ====================


def _existing_working_slugs(connection: Any) -> set[str]:
    """Read all existing working group slugs from database."""
    rows = connection.execute("SELECT slug FROM working_groups").fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _normalize_grouping_strategy(value: object | None) -> str:
    """Normalize bulk grouping strategy."""
    normalized = str(value or "").strip().lower()
    if normalized in {"by-folder", "by-root", "flat"}:
        return normalized
    return "by-folder"


def _unique_slug(connection: Any, title: str) -> str:
    """Generate unique slug for working group."""
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


def _unique_project_slug(connection: Any, title: str) -> str:
    """Generate unique slug for project."""
    base = _slugify_title(title) or "project"
    candidate = base
    suffix = 2
    rows = connection.execute("SELECT slug FROM model_catalog_projects").fetchall()
    existing = {str(row["slug"]) for row in rows}
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _resolve_project_id_value(value: Any) -> int | None:
    """Resolve and validate project ID."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _normalize_file_name_hint(file_name: str) -> str:
    """Normalize file name for searching (remove (copies), suffixes, etc.)."""
    stem = Path(file_name).stem.strip().lower()
    if not stem:
        return ""
    stem = re.sub(r"\s+", " ", stem)
    stem = re.sub(r"\s*\((\d+)\)$", "", stem)
    stem = re.sub(r"(?:[_-](copy|\d+))$", "", stem)
    return stem.strip()


def _working_file_extension_rank(file_extension: str | None) -> int:
    """Rank file extensions for sorting (3mf first, then models, then others)."""
    normalized = str(file_extension or "").strip().lower()
    if normalized == ".3mf":
        return 0
    if normalized in {".stl", ".step", ".stp", ".obj"}:
        return 1
    if normalized == ".zip":
        return 2
    return 3


def _working_file_sort_key(*, file_extension: str | None, file_name: str | None, file_path: str | None) -> tuple[int, str, str]:
    """Generate sort key for working files."""
    return (
        _working_file_extension_rank(file_extension),
        str(file_name or "").strip().lower(),
        str(file_path or "").strip().lower(),
    )


def _unique_destination_path(
    directory: Path,
    filename: str,
    *,
    reserved_paths: set[str] | None = None,
) -> Path:
    """Return a collision-safe destination path using -2/-3 suffix semantics."""
    reserved = reserved_paths if reserved_paths is not None else set()
    candidate = directory / filename
    candidate_key = _normalize_path_compare_key(str(candidate.resolve()))
    if not candidate.exists() and candidate_key not in reserved:
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        next_candidate = directory / f"{stem}-{counter}{suffix}"
        next_key = _normalize_path_compare_key(str(next_candidate.resolve()))
        if not next_candidate.exists() and next_key not in reserved:
            return next_candidate
        counter += 1


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


def _copy_local_import_source(*, settings: Settings, local_model_id: str, source_path: Path) -> str:
    catalog_root = _model_photo_storage_root(settings)
    asset_root = catalog_root / local_model_id
    asset_root.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination_path(asset_root, source_path.name)
    shutil.move(str(source_path), str(destination))  # MOVE instead of copy
    try:
        relative_path = destination.relative_to(catalog_root.resolve())
        return str(relative_path).replace("\\", "/")
    except ValueError:
        return str(destination).replace("\\", "/")


def _file_membership_map(connection: Any, *, path_keys: set[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Build map of files to their group memberships."""
    query = """
        SELECT
            wi.file_path,
            wi.item_role,
            wi.working_group_id,
            wg.slug,
            wg.title,
            wg.stage
        FROM working_items wi
        JOIN working_groups wg ON wg.id = wi.working_group_id
        ORDER BY wg.updated_at DESC, wg.id DESC, wi.id ASC
    """
    rows = connection.execute(query).fetchall()
    memberships: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _normalize_path_compare_key(row["file_path"])
        if not key:
            continue
        if path_keys is not None and key not in path_keys:
            continue
        memberships.setdefault(key, []).append(
            {
                "group_id": int(row["working_group_id"]),
                "group_slug": row["slug"],
                "group_title": row["title"],
                "group_stage": row["stage"],
                "item_role": row["item_role"],
            }
        )
    return memberships


# ==================== HELPER FUNCTIONS: SERIALIZATION ====================


def _create_project_record(
    connection: Any,
    *,
    title: str,
    description: str | None,
    notes: str | None,
    bambuddy_project_id: int | None,
    now_iso: str,
) -> dict[str, Any]:
    """Create a new project record."""
    slug = _unique_project_slug(connection, title)
    connection.execute(
        """
        INSERT INTO model_catalog_projects (
            slug, title, description, notes, bambuddy_project_id, created_at, updated_at, archived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, title, description, notes, bambuddy_project_id, now_iso, now_iso, None),
    )
    project_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
    project_row = connection.execute("SELECT * FROM model_catalog_projects WHERE id = ?", (project_id,)).fetchone()
    return _serialize_project_row(project_row)


def _resolve_publish_project(connection: Any, *, payload: dict[str, Any], group_row: Any, now_iso: str) -> tuple[int | None, dict[str, Any] | None]:
    """Resolve project for publishing, creating if needed."""
    create_project_payload = payload.get("create_project") if isinstance(payload.get("create_project"), dict) else None
    if create_project_payload:
        project_title = str(create_project_payload.get("title") or "").strip()
        if not project_title:
            raise ValueError("create_project.title is required")
        created_project = _create_project_record(
            connection,
            title=project_title,
            description=str(create_project_payload.get("description") or "").strip() or None,
            notes=str(create_project_payload.get("notes") or "").strip() or None,
            bambuddy_project_id=_resolve_project_id_value(create_project_payload.get("bambuddy_project_id")),
            now_iso=now_iso,
        )
        return int(created_project["id"]), created_project

    explicit_project_id = _resolve_project_id_value(payload.get("project_id"))
    if explicit_project_id is not None:
        project_row = connection.execute(
            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
            (explicit_project_id,),
        ).fetchone()
        if project_row is None:
            raise LookupError(f"Project not found: {explicit_project_id}")
        return explicit_project_id, _serialize_project_row(project_row)

    group_project_id = group_row["project_id"] if "project_id" in set(group_row.keys()) else None
    if group_project_id is not None:
        project_row = connection.execute(
            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
            (group_project_id,),
        ).fetchone()
        if project_row is not None:
            return int(group_project_id), _serialize_project_row(project_row)

    return None, None


def _lineage_payload_for_model(*, db_path: Path, model_ref: str) -> dict[str, Any]:
    """Get lineage info for a published model."""
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


def _bulk_group_key(root_path: Path, file_path: Path, strategy: str) -> str:
    """Generate group key for bulk discover based on strategy."""
    if strategy == "by-root":
        return "__root__"
    if strategy == "flat":
        return str(file_path)
    relative_parent = file_path.parent.relative_to(root_path)
    return str(relative_parent) if str(relative_parent) != "." else "__root_folder__"


def _bulk_group_title(root_path: Path, group_key: str, file_path: Path, strategy: str) -> str:
    """Generate group title for bulk discover based on strategy."""
    if strategy == "by-root":
        return root_path.name or str(root_path)
    if strategy == "flat":
        return file_path.stem or file_path.name
    if group_key == "__root_folder__":
        return f"{root_path.name} Root"
    parent = Path(group_key)
    return parent.name or group_key


def _append_intake_publish_history(*, db_path: Path, model_ref: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Append publish history entry to model."""
    existing = read_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history")
    history = existing if isinstance(existing, list) else []
    history.append(entry)
    trimmed = history[-20:]
    set_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history", field_value=trimmed)
    return trimmed


# ==================== ENDPOINTS: WORKING FILES ====================


@router.post("/api/working-files/reindex")
def reindex_working_files(request: Request, payload: dict[str, Any] | None = None) -> Any:
    """Reindex working files from configured roots."""
    state: AppState = request.app.state.model_catalog
    payload = payload or {}
    compute_hashes = _coerce_bool(payload.get("compute_hashes", False))
    recurse = _coerce_bool(payload.get("recurse", True))

    requested_roots: list[Path] = []
    root_paths = payload.get("roots")
    if isinstance(root_paths, list):
        for root_item in root_paths:
            root_text = str(root_item or "").strip()
            if not root_text:
                continue
            requested_roots.append(Path(root_text).expanduser().resolve())

    allowlisted_roots = _configured_working_files_roots(state.settings)
    if requested_roots:
        if not allowlisted_roots:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "roots_not_configured",
                    "message": "MODEL_CATALOG_WORKING_FILES_ROOT is empty; cannot validate requested roots.",
                },
            )
        invalid_roots = [root for root in requested_roots if not _is_path_within_roots(root, allowlisted_roots)]
        if invalid_roots:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "root_not_allowed",
                    "message": "One or more requested roots are outside the configured working-files root.",
                    "invalid_roots": [str(root) for root in invalid_roots],
                },
            )
        roots = requested_roots
    else:
        roots = allowlisted_roots

    if not roots:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_roots",
                "message": "No working-files root is configured.",
            },
        )

    if recurse:
        result = _refresh_working_file_inventory(db_path=state.settings.db_path, roots=roots, compute_hashes=compute_hashes)
        result["recurse"] = True
        return {"success": True, **result}

    # Non-recursive scan mode
    now_iso = _bulk_utc_now_iso()
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for file_item in sorted(root.glob("*")):
            if not file_item.is_file() or file_item.name.startswith("."):
                continue
            suffix = file_item.suffix.lower()
            if suffix not in _WORKING_INVENTORY_EXTENSIONS:
                continue
            try:
                stat_result = file_item.stat()
                source_metadata = _bulk_path_source_metadata(file_item, stat_result)
            except (OSError, PermissionError):
                continue
            rows.append(
                {
                    "source_path_raw": str(file_item),
                    "source_path_canonical": str(file_item.resolve()),
                    "source_path_compare_key": _normalize_compare_key(file_item.resolve()),
                    "file_name_raw": file_item.name,
                    "file_name_base_hint": _normalize_file_name_hint(file_item.name),
                    "file_extension": suffix,
                    "file_size_bytes": int(stat_result.st_size),
                    "sha256_hash": _sha256_file(file_item).lower() if compute_hashes else None,
                    "source_mtime": source_metadata.get("source_mtime"),
                    "source_ctime": source_metadata.get("source_ctime"),
                    "source_birthtime": source_metadata.get("source_birthtime"),
                    "root_path": str(root),
                }
            )

    connection = connect(state.settings.db_path)
    try:
        connection.execute("DELETE FROM working_file_inventory")
        for row in rows:
            connection.execute(
                """
                INSERT INTO working_file_inventory (
                    source_path_raw, source_path_canonical, source_path_compare_key,
                    file_name_raw, file_name_base_hint, file_extension,
                    file_size_bytes, sha256_hash,
                    source_mtime, source_ctime, source_birthtime,
                    validation_state, warnings_json,
                    detected_at, last_seen_at, root_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["source_path_raw"],
                    row["source_path_canonical"],
                    row["source_path_compare_key"],
                    row["file_name_raw"],
                    row["file_name_base_hint"],
                    row["file_extension"],
                    row["file_size_bytes"],
                    row["sha256_hash"],
                    row["source_mtime"],
                    row["source_ctime"],
                    row["source_birthtime"],
                    "ready",
                    "[]",
                    now_iso,
                    now_iso,
                    row["root_path"],
                ),
            )
        connection.commit()
    finally:
        connection.close()

    return {
        "success": True,
        "discovered": len(rows),
        "inserted": len(rows),
        "updated": 0,
        "removed": 0,
        "hashed": len(rows) if compute_hashes else 0,
        "roots": [str(root) for root in roots],
        "recurse": False,
        "refreshed_at": now_iso,
    }


@router.get("/api/working-files")
def list_working_files(request: Request,
    q: str | None = None,
    extension: str | None = None,
    path_contains: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """List working files with filtering and pagination."""
    state: AppState = request.app.state.model_catalog
    limit_value = max(1, min(int(limit or 100), 1000))
    offset_value = max(0, int(offset or 0))

    where_clauses = ["1=1"]
    params: list[Any] = []
    if q and q.strip():
        q_like = f"%{q.strip().lower()}%"
        where_clauses.append("(LOWER(file_name_raw) LIKE ? OR LOWER(file_name_base_hint) LIKE ?)")
        params.extend([q_like, q_like])
    if extension and extension.strip():
        normalized_ext = extension.strip().lower()
        if not normalized_ext.startswith("."):
            normalized_ext = f".{normalized_ext}"
        where_clauses.append("file_extension = ?")
        params.append(normalized_ext)
    if path_contains and path_contains.strip():
        where_clauses.append("LOWER(source_path_canonical) LIKE ?")
        params.append(f"%{path_contains.strip().lower()}%")

    where_sql = " AND ".join(where_clauses)
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS cnt FROM working_file_inventory WHERE {where_sql}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT *
            FROM working_file_inventory
            WHERE {where_sql}
            ORDER BY file_name_base_hint ASC, source_path_canonical ASC
            LIMIT ? OFFSET ?
            """,
            [*params, limit_value, offset_value],
        ).fetchall()
    finally:
        connection.close()

    return {
        "success": True,
        "pagination": {
            "limit": limit_value,
            "offset": offset_value,
            "total": int(total_row["cnt"] if total_row else 0),
        },
        "files": [
            {
                "id": int(row["id"]),
                "source_path_raw": row["source_path_raw"],
                "source_path_canonical": row["source_path_canonical"],
                "source_path_compare_key": row["source_path_compare_key"],
                "file_name_raw": row["file_name_raw"],
                "file_name_base_hint": row["file_name_base_hint"],
                "file_extension": row["file_extension"],
                "file_size_bytes": int(row["file_size_bytes"] or 0),
                "sha256_hash": row["sha256_hash"],
                "source_mtime": row["source_mtime"],
                "source_ctime": row["source_ctime"],
                "source_birthtime": row["source_birthtime"],
                "validation_state": row["validation_state"],
                "warnings": json.loads(str(row["warnings_json"] or "[]")),
                "detected_at": row["detected_at"],
                "last_seen_at": row["last_seen_at"],
                "root_path": row["root_path"],
                "launch": _launch_context_for_path(str(row["source_path_canonical"] or row["source_path_raw"] or ""), state.settings),
            }
            for row in rows
        ],
    }


# ==================== ENDPOINTS: FOLDER-FIRST WORKING FILES (design §6.4) ====================
#
# These endpoints implement the folder-first model from
# docs/features/model_catalog/design/working-files.md §6.4.
# They derive "groups" from filesystem folders under the configured working-files
# root rather than from the now-removed working_groups/working_items tables.
# See docs/features/model_catalog/planning/working-groups-deprecation.md for the
# legacy surface they replace.

_WORKING_FILES_DEPRECATION_BODY: dict[str, Any] = {
    "success": False,
    "error": "endpoint_gone",
    "message": (
        "Working Groups have been removed in favor of folder-first Working Files. "
        "Use the new /api/working-files/* endpoints listed in 'new_endpoints'. "
        "See the deprecation plan for migration guidance."
    ),
    "deprecation_plan": "docs/features/model_catalog/planning/working-groups-deprecation.md",
    "design": "docs/features/model_catalog/design/working-files.md",
    "new_endpoints": [
        "GET /api/working-files/tree",
        "GET /api/working-files/groups/{folder_slug}",
        "GET /api/working-files/groups/{folder_slug}/files?mode=files|folders",
        "GET /api/working-files/loose",
        "POST /api/working-files/reindex",
    ],
}

_WORKING_FILES_GONE_HEADERS: dict[str, str] = {
    "Deprecation": "true",
    "Link": '</api/working-files/tree>; rel="successor-version"',
}


def _working_files_gone_response() -> JSONResponse:
    """Return HTTP 410 Gone response for legacy working-groups endpoints."""
    return JSONResponse(
        status_code=410,
        content=_WORKING_FILES_DEPRECATION_BODY,
        headers=_WORKING_FILES_GONE_HEADERS,
    )


def _primary_working_root(settings: Settings) -> Path | None:
    """Return the first configured working-files root, if any."""
    roots = _configured_working_files_roots(settings)
    return roots[0] if roots else None


def _relative_under_root(source_path: str | None, root: Path) -> str | None:
    """Return POSIX-style relative path of source_path under root, or None."""
    if not source_path:
        return None
    try:
        rel = Path(source_path).resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    rel_str = str(rel).replace("\\", "/").strip("/")
    return rel_str or None


def _top_level_folder_of(rel_path: str) -> str | None:
    """Return the first path segment of rel_path, or None if file is at root."""
    parts = [segment for segment in rel_path.split("/") if segment and segment != "."]
    if len(parts) <= 1:
        return None
    return parts[0]


def _read_folder_sidecar(folder_path: Path) -> dict[str, Any]:
    """Read .modelmeta.json + README.md from folder, if present."""
    out: dict[str, Any] = {"modelmeta": None, "readme": None}
    meta_path = folder_path / ".modelmeta.json"
    if meta_path.is_file():
        try:
            out["modelmeta"] = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out["modelmeta_error"] = str(exc)
    readme_path = folder_path / "README.md"
    if readme_path.is_file():
        try:
            out["readme"] = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            out["readme_error"] = str(exc)
    return out


def _inventory_file_payload(row: sqlite3.Row, settings: Settings) -> dict[str, Any]:
    """Shared serializer for a single working_file_inventory row."""
    canonical_path = str(row["source_path_canonical"] or row["source_path_raw"] or "")
    return {
        "id": int(row["id"]),
        "source_path_raw": row["source_path_raw"],
        "source_path_canonical": row["source_path_canonical"],
        "source_path_compare_key": row["source_path_compare_key"],
        "file_name_raw": row["file_name_raw"],
        "file_name_base_hint": row["file_name_base_hint"],
        "file_extension": row["file_extension"],
        "file_size_bytes": int(row["file_size_bytes"] or 0),
        "sha256_hash": row["sha256_hash"],
        "source_mtime": row["source_mtime"],
        "source_ctime": row["source_ctime"],
        "source_birthtime": row["source_birthtime"],
        "validation_state": row["validation_state"],
        "warnings": json.loads(str(row["warnings_json"] or "[]")),
        "detected_at": row["detected_at"],
        "last_seen_at": row["last_seen_at"],
        "root_path": row["root_path"],
        "launch": _launch_context_for_path(canonical_path, settings),
    }


@router.get("/api/working-files/tree")
def working_files_tree(request: Request) -> Any:
    """Top-level groups (folders under working root) + (loose files) summary.

    Implements design §6.4. Groups are derived from the first-level subfolders
    of the configured working-files root. Loose files are files indexed at the
    root (no subfolder).
    """
    state: AppState = request.app.state.model_catalog
    root = _primary_working_root(state.settings)
    if root is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_root",
                "message": "MODEL_CATALOG_WORKING_FILES_ROOT is not configured.",
            },
        )

    root_str = str(root)
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT source_path_canonical, source_path_raw, file_extension,
                   file_size_bytes, last_seen_at
            FROM working_file_inventory
            WHERE root_path = ?
            """,
            (root_str,),
        ).fetchall()
    finally:
        connection.close()

    folder_buckets: dict[str, dict[str, Any]] = {}
    loose_count = 0
    loose_size = 0
    loose_last_seen: str | None = None

    for row in rows:
        rel = _relative_under_root(row["source_path_canonical"] or row["source_path_raw"], root)
        if rel is None:
            continue
        top = _top_level_folder_of(rel)
        size = int(row["file_size_bytes"] or 0)
        last_seen = row["last_seen_at"]
        ext = str(row["file_extension"] or "").lower()
        if top is None:
            loose_count += 1
            loose_size += size
            if last_seen and (loose_last_seen is None or last_seen > loose_last_seen):
                loose_last_seen = last_seen
            continue
        bucket = folder_buckets.setdefault(
            top,
            {
                "slug": top,
                "name": top,
                "file_count": 0,
                "size_bytes": 0,
                "count_3mf": 0,
                "last_seen_at": None,
                "has_modelmeta": (root / top / ".modelmeta.json").is_file(),
                "has_readme": (root / top / "README.md").is_file(),
            },
        )
        bucket["file_count"] += 1
        bucket["size_bytes"] += size
        if ext == ".3mf":
            bucket["count_3mf"] += 1
        if last_seen and (bucket["last_seen_at"] is None or last_seen > bucket["last_seen_at"]):
            bucket["last_seen_at"] = last_seen

    groups = sorted(folder_buckets.values(), key=lambda g: g["name"].lower())

    return {
        "success": True,
        "root_path": root_str,
        "root_launch": _launch_context_for_path(root_str, state.settings),
        "groups": groups,
        "loose": {
            "file_count": loose_count,
            "size_bytes": loose_size,
            "last_seen_at": loose_last_seen,
        },
    }


@router.get("/api/working-files/loose")
def working_files_loose(
    request: Request,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """Files at the working-files root (no subfolder)."""
    state: AppState = request.app.state.model_catalog
    root = _primary_working_root(state.settings)
    if root is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_root",
                "message": "MODEL_CATALOG_WORKING_FILES_ROOT is not configured.",
            },
        )

    limit_value = max(1, min(int(limit or 200), 1000))
    offset_value = max(0, int(offset or 0))
    root_str = str(root)

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM working_file_inventory
            WHERE root_path = ?
            ORDER BY file_name_base_hint ASC, source_path_canonical ASC
            """,
            (root_str,),
        ).fetchall()
    finally:
        connection.close()

    loose_rows = [
        row
        for row in rows
        if _top_level_folder_of(
            _relative_under_root(row["source_path_canonical"] or row["source_path_raw"], root) or ""
        )
        is None
        and _relative_under_root(row["source_path_canonical"] or row["source_path_raw"], root)
        is not None
    ]

    total = len(loose_rows)
    paged = loose_rows[offset_value : offset_value + limit_value]

    return {
        "success": True,
        "root_path": root_str,
        "pagination": {
            "limit": limit_value,
            "offset": offset_value,
            "total": total,
        },
        "files": [_inventory_file_payload(row, state.settings) for row in paged],
    }


@router.get("/api/working-files/folders")
def working_files_folders_list(
    request: Request,
    q: str = "",
    limit: int = 25,
    offset: int = 0,
) -> Any:
    """Lightweight folder picker for the intake wizard's "append to existing" branch.

    Enumerates top-level folders under the configured working-files root, optionally
    filtered by a case-insensitive substring matching either the folder slug or the
    sidecar ``display_title``. Each entry includes minimal metadata sufficient for
    the wizard to render a result row and POST a ``target_folder_slug``.
    """
    state: AppState = request.app.state.model_catalog
    root = _primary_working_root(state.settings)
    if root is None:
        return {
            "success": True,
            "folders": [],
            "total": 0,
            "limit": int(limit or 25),
            "offset": int(offset or 0),
        }

    needle = (q or "").strip().lower()
    try:
        safe_limit = max(1, min(int(limit or 25), 200))
    except (TypeError, ValueError):
        safe_limit = 25
    try:
        safe_offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        safe_offset = 0

    matches: list[dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        entries = []

    for entry in entries:
        if not entry.is_dir():
            continue
        slug = entry.name
        if slug.startswith(".") or slug in {"..", "."}:
            continue
        sidecar = _read_folder_sidecar(entry)
        modelmeta = sidecar.get("modelmeta") if isinstance(sidecar.get("modelmeta"), dict) else None
        display_title = (modelmeta or {}).get("display_title") if modelmeta else None
        primary_file = (modelmeta or {}).get("primary_file") if modelmeta else None
        tags_raw = (modelmeta or {}).get("tags") if modelmeta else None
        tags = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []
        files_raw = (modelmeta or {}).get("files") if modelmeta else None
        file_count = len(files_raw) if isinstance(files_raw, list) else None

        haystack = f"{slug}\n{display_title or ''}".lower()
        if needle and needle not in haystack:
            continue

        matches.append(
            {
                "slug": slug,
                "name": slug,
                "display_title": str(display_title) if display_title else None,
                "folder_path": str(entry),
                "primary_file": str(primary_file) if primary_file else None,
                "file_count": file_count,
                "tags": tags,
                "has_modelmeta": modelmeta is not None,
                "has_readme": sidecar.get("readme") is not None,
            }
        )

    total = len(matches)
    page = matches[safe_offset : safe_offset + safe_limit]
    return {
        "success": True,
        "folders": page,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
    }


_INVALID_SLUG_CHARS = re.compile(r"[^a-zA-Z0-9._-]+")


def _sanitize_folder_slug_candidate(value: str) -> str:
    """Reduce a free-form slug candidate to a safe folder name segment."""
    cleaned = _INVALID_SLUG_CHARS.sub("-", str(value or "").strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-._")
    return cleaned


def _disambiguate_folder_slug(root: Path, base_slug: str) -> str:
    """Append numeric suffix until the folder name is unused under root."""
    candidate = base_slug
    counter = 1
    while (root / candidate).exists():
        counter += 1
        candidate = f"{base_slug}-{counter}"
        if counter > 1000:  # pragma: no cover - defensive
            raise RuntimeError("Unable to allocate unique working-files folder name")
    return candidate


@router.post("/api/local/models/{local_model_id}/move-to-working-files")
def move_idea_to_working_files(
    request: Request,
    local_model_id: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Move an Idea catalog entry to a new Working Files folder.

    Folder-first replacement for the legacy ``idea → working_group`` promotion.
    Materializes the idea as a top-level folder under
    ``MODEL_CATALOG_WORKING_FILES_ROOT`` with a ``.modelmeta.json`` sidecar,
    optional ``README.md`` (from notes), and a copy of the sketch image asset
    (when present). The idea row is hard-deleted from the local catalog on
    success — the idea has moved out of the catalog and now lives on disk.
    """
    state: AppState = request.app.state.model_catalog
    settings = state.settings
    payload = payload or {}

    entry = read_local_model(db_path=settings.db_path, local_model_id=local_model_id)
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "not_found", "message": f"Local model '{local_model_id}' not found."},
        )
    if entry.entity_type != "idea":
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "not_an_idea",
                "message": f"Only idea entries can be moved to Working Files (entity_type={entry.entity_type}).",
            },
        )

    root = _primary_working_root(settings)
    if root is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_root",
                "message": "MODEL_CATALOG_WORKING_FILES_ROOT is not configured.",
            },
        )

    # Derive folder slug
    requested_slug = _sanitize_folder_slug_candidate(str(payload.get("slug") or ""))
    base_slug = requested_slug or _slugify_title(entry.model_name)
    if not base_slug:
        base_slug = "idea"
    try:
        folder_slug = _disambiguate_folder_slug(root, base_slug)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "slug_exhausted", "message": str(exc)},
        )

    # Gather idea metadata
    raw_fields = read_model_fields(db_path=settings.db_path, model_ref=local_model_id) or {}
    notes_value = str(raw_fields.get("notes") or "").strip()

    external_links_raw = raw_fields.get("external_links")
    origin_url = entry.source_origin_url or None
    if not origin_url and isinstance(external_links_raw, list):
        for link in external_links_raw:
            if isinstance(link, dict):
                candidate = str(link.get("url") or "").strip()
            else:
                candidate = str(link or "").strip()
            if candidate:
                origin_url = candidate
                break

    # Locate sketch image asset (if any)
    sketch_asset_path: Path | None = None
    sketch_target_name: str | None = None
    sketch_raw = raw_fields.get("sketch_image")
    sketch_asset_id = ""
    if isinstance(sketch_raw, dict):
        sketch_asset_id = str(sketch_raw.get("asset_id") or "").strip()
    if sketch_asset_id:
        for asset in list_model_assets(db_path=settings.db_path, local_model_id=local_model_id):
            if str(getattr(asset, "asset_id", "") or "") == sketch_asset_id:
                resolved = _resolve_local_asset_storage_path(settings=settings, asset=asset)
                if resolved is not None and resolved.is_file():
                    sketch_asset_path = resolved
                    original_name = str(getattr(asset, "asset_filename", "") or resolved.name)
                    sketch_target_name = f"sketch{Path(original_name).suffix or resolved.suffix or '.png'}"
                break

    # Build sidecar payload
    modelmeta: dict[str, Any] = {
        "$schema": "https://hass-bambulab-config/schemas/modelmeta.v1.json",
        "display_title": entry.model_name,
    }
    tag_list = [str(t).strip() for t in (entry.tags or ()) if str(t).strip()]
    if tag_list:
        modelmeta["tags"] = tag_list
    if origin_url:
        modelmeta["origin_url"] = origin_url
    if sketch_target_name:
        modelmeta["thumbnail"] = sketch_target_name

    folder_path = root / folder_slug
    created_paths: list[Path] = []
    try:
        folder_path.mkdir(parents=True, exist_ok=False)
        created_paths.append(folder_path)

        meta_path = folder_path / ".modelmeta.json"
        meta_path.write_text(
            json.dumps(modelmeta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        created_paths.append(meta_path)

        if notes_value:
            readme_path = folder_path / "README.md"
            readme_body = notes_value if notes_value.endswith("\n") else notes_value + "\n"
            readme_path.write_text(readme_body, encoding="utf-8")
            created_paths.append(readme_path)

        if sketch_asset_path and sketch_target_name:
            sketch_dest = folder_path / sketch_target_name
            shutil.copy2(sketch_asset_path, sketch_dest)
            created_paths.append(sketch_dest)
    except OSError as exc:
        # Best-effort cleanup
        try:
            if folder_path.exists():
                shutil.rmtree(folder_path, ignore_errors=True)
        except OSError:
            pass
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "fs_error", "message": str(exc)},
        )

    # Hard-delete the idea row (and its assets) now that the folder is on disk.
    try:
        delete_local_model(db_path=settings.db_path, local_model_id=local_model_id, hard_delete=True)
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "idea_delete_failed",
                "message": f"Folder created at {folder_path} but failed to remove idea row: {exc}",
                "folder_slug": folder_slug,
                "folder_path": str(folder_path),
            },
        )

    return {
        "success": True,
        "folder_slug": folder_slug,
        "folder_path": str(folder_path),
        "modelmeta": modelmeta,
        "has_readme": bool(notes_value),
        "has_thumbnail": bool(sketch_target_name),
    }


@router.get("/api/working-files/groups/{folder_slug}")
def working_files_group_detail(request: Request, folder_slug: str) -> Any:
    """Group detail: file count, folder tree, sidecar contents.

    folder_slug is the top-level folder name under the configured working-files
    root. Returns 404 if the folder does not exist on disk.
    """
    state: AppState = request.app.state.model_catalog
    root = _primary_working_root(state.settings)
    if root is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_root",
                "message": "MODEL_CATALOG_WORKING_FILES_ROOT is not configured.",
            },
        )

    slug = (folder_slug or "").strip()
    if not slug or "/" in slug or "\\" in slug or slug.startswith(".") or slug in {"..", "."}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_folder_slug",
                "message": "folder_slug must be a single top-level folder name.",
            },
        )

    folder_path = root / slug
    if not folder_path.is_dir():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "folder_not_found",
                "message": f"Folder '{slug}' does not exist under the working-files root.",
                "folder_slug": slug,
            },
        )

    root_str = str(root)
    folder_str = str(folder_path)
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT file_extension, file_size_bytes, last_seen_at,
                   source_path_canonical, source_path_raw
            FROM working_file_inventory
            WHERE root_path = ?
            """,
            (root_str,),
        ).fetchall()
    finally:
        connection.close()

    subfolders: dict[str, dict[str, Any]] = {}
    file_count = 0
    size_bytes = 0
    count_3mf = 0
    last_seen: str | None = None

    for row in rows:
        rel = _relative_under_root(row["source_path_canonical"] or row["source_path_raw"], root)
        if not rel:
            continue
        if _top_level_folder_of(rel) != slug:
            continue
        size = int(row["file_size_bytes"] or 0)
        ext = str(row["file_extension"] or "").lower()
        row_last_seen = row["last_seen_at"]
        file_count += 1
        size_bytes += size
        if ext == ".3mf":
            count_3mf += 1
        if row_last_seen and (last_seen is None or row_last_seen > last_seen):
            last_seen = row_last_seen
        parts = [segment for segment in rel.split("/") if segment]
        if len(parts) > 2:
            subfolder_rel = "/".join(parts[1:-1])
            sub = subfolders.setdefault(
                subfolder_rel,
                {"path": subfolder_rel, "file_count": 0, "size_bytes": 0},
            )
            sub["file_count"] += 1
            sub["size_bytes"] += size

    sidecar = _read_folder_sidecar(folder_path)

    return {
        "success": True,
        "folder_slug": slug,
        "folder_path": folder_str,
        "folder_launch": _launch_context_for_path(folder_str, state.settings),
        "counts": {
            "file_count": file_count,
            "size_bytes": size_bytes,
            "count_3mf": count_3mf,
            "count_other": max(0, file_count - count_3mf),
        },
        "last_seen_at": last_seen,
        "subfolders": sorted(subfolders.values(), key=lambda s: s["path"].lower()),
        "sidecar": sidecar,
    }


@router.get("/api/working-files/groups/{folder_slug}/files")
def working_files_group_files(
    request: Request,
    folder_slug: str,
    mode: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """Paginated file listing for a group, optionally folder-organized."""
    state: AppState = request.app.state.model_catalog
    root = _primary_working_root(state.settings)
    if root is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_root",
                "message": "MODEL_CATALOG_WORKING_FILES_ROOT is not configured.",
            },
        )

    slug = (folder_slug or "").strip()
    if not slug or "/" in slug or "\\" in slug or slug.startswith(".") or slug in {"..", "."}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_folder_slug",
                "message": "folder_slug must be a single top-level folder name.",
            },
        )

    folder_path = root / slug
    if not folder_path.is_dir():
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "folder_not_found",
                "message": f"Folder '{slug}' does not exist under the working-files root.",
                "folder_slug": slug,
            },
        )

    mode_value = (mode or "files").strip().lower() or "files"
    if mode_value not in {"files", "folders"}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_mode",
                "message": "mode must be one of: files, folders",
            },
        )

    limit_value = max(1, min(int(limit or 200), 1000))
    offset_value = max(0, int(offset or 0))
    root_str = str(root)

    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM working_file_inventory
            WHERE root_path = ?
            ORDER BY
                CASE
                    WHEN file_extension = '.3mf' THEN 0
                    WHEN file_extension IN ('.stl', '.step', '.stp', '.obj') THEN 1
                    WHEN file_extension = '.zip' THEN 2
                    ELSE 3
                END ASC,
                file_name_base_hint ASC,
                source_path_canonical ASC
            """,
            (root_str,),
        ).fetchall()
    finally:
        connection.close()

    scoped_rows = [
        row
        for row in rows
        if _top_level_folder_of(
            _relative_under_root(row["source_path_canonical"] or row["source_path_raw"], root) or ""
        )
        == slug
    ]

    total = len(scoped_rows)

    if mode_value == "files":
        paged = scoped_rows[offset_value : offset_value + limit_value]
        return {
            "success": True,
            "folder_slug": slug,
            "mode": "files",
            "pagination": {
                "limit": limit_value,
                "offset": offset_value,
                "total": total,
            },
            "files": [_inventory_file_payload(row, state.settings) for row in paged],
        }

    # mode == "folders": group files by their subfolder under the group root
    bucketed: dict[str, list[sqlite3.Row]] = {}
    for row in scoped_rows:
        rel = _relative_under_root(row["source_path_canonical"] or row["source_path_raw"], root) or ""
        parts = [segment for segment in rel.split("/") if segment]
        # parts[0] == slug; remaining segments are subfolders + filename
        sub_rel = "/".join(parts[1:-1]) if len(parts) > 2 else ""
        bucketed.setdefault(sub_rel, []).append(row)

    folders_payload = [
        {
            "path": sub_rel,
            "file_count": len(bucket),
            "files": [_inventory_file_payload(row, state.settings) for row in bucket],
        }
        for sub_rel, bucket in sorted(bucketed.items(), key=lambda kv: kv[0].lower())
    ]

    paged_folders = folders_payload[offset_value : offset_value + limit_value]

    return {
        "success": True,
        "folder_slug": slug,
        "mode": "folders",
        "pagination": {
            "limit": limit_value,
            "offset": offset_value,
            "total": len(folders_payload),
            "total_files": total,
        },
        "folders": paged_folders,
    }


# ==================== DEPRECATED ENDPOINTS: WORKING GROUPS (HTTP 410) ====================
#
# Per docs/features/model_catalog/planning/working-groups-deprecation.md PR C,
# all /api/working-groups/* endpoints and the legacy
# /api/working-files/explorer endpoint return HTTP 410 Gone. The route
# declarations are kept so OpenAPI and ops dashboards can still see them; the
# bodies just return the deprecation envelope pointing at the new endpoints.


@router.get("/api/working-files/explorer")
def explore_working_files(request: Request,
    view: str | None = None,
    q: str | None = None,
    extension: str | None = None,
    path_contains: str | None = None,
    lightweight: bool | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """DEPRECATED: returns HTTP 410. Use /api/working-files/tree, /loose, /groups/{slug}."""
    return _working_files_gone_response()


# ==================== ENDPOINTS: WORKING GROUP MEMBERSHIPS ====================


@router.post("/api/working-groups/memberships/batch-add")
def batch_add_working_group_memberships(request: Request, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folder membership is intrinsic in the new model."""
    return _working_files_gone_response()


@router.post("/api/working-groups/memberships/batch-remove")
def batch_remove_working_group_memberships(request: Request, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folder membership is intrinsic in the new model."""
    return _working_files_gone_response()


# ==================== ENDPOINTS: WORKING GROUP MANAGEMENT ====================


@router.post("/api/working-groups/{group_id}/reorganize")
def reorganize_working_group(request: Request, group_id: int, payload: dict[str, Any] | None = None) -> Any:
    """DEPRECATED: returns HTTP 410. Reorganize files on disk via OS file manager."""
    return _working_files_gone_response()


@router.post("/api/working-groups")
def create_working_group(request: Request, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folders are the group identity now."""
    return _working_files_gone_response()


@router.get("/api/working-groups")
def list_working_groups(request: Request, limit: int | None = None, offset: int | None = None, stage: str | None = None, project_id: int | None = None, q: str | None = None) -> Any:
    """DEPRECATED: returns HTTP 410. Use /api/working-files/tree."""
    return _working_files_gone_response()


@router.get("/api/working-groups/{group_id}")
def get_working_group(request: Request, group_id: int) -> Any:
    """DEPRECATED: returns HTTP 410. Use /api/working-files/groups/{folder_slug}."""
    return _working_files_gone_response()


@router.patch("/api/working-groups/{group_id}")
def update_working_group(request: Request, group_id: int, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folder metadata lives in sidecars on disk."""
    return _working_files_gone_response()


@router.delete("/api/working-groups/{group_id}")
def delete_working_group(request: Request, group_id: int) -> Any:
    """DEPRECATED: returns HTTP 410. Delete the folder via OS file manager."""
    return _working_files_gone_response()


# ==================== ENDPOINTS: WORKING GROUP ITEMS ====================


@router.post("/api/working-groups/{group_id}/items")
def add_working_group_item(request: Request, group_id: int, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folder membership is intrinsic in the new model."""
    return _working_files_gone_response()


@router.delete("/api/working-groups/{group_id}/items/{item_id}")
def remove_working_group_item(request: Request, group_id: int, item_id: int) -> Any:
    """DEPRECATED: returns HTTP 410. Folder membership is intrinsic in the new model."""
    return _working_files_gone_response()


# ==================== ENDPOINTS: MODEL LINKS ====================


@router.post("/api/working-groups/{group_id}/links")
def create_working_group_link(request: Request, group_id: int, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Model links move to the new working-files layer."""
    return _working_files_gone_response()


@router.get("/api/working-groups/{group_id}/links")
def list_working_group_links(request: Request, group_id: int) -> Any:
    """DEPRECATED: returns HTTP 410. Model links move to the new working-files layer."""
    return _working_files_gone_response()


@router.delete("/api/working-groups/{group_id}/links/{link_id}")
def delete_working_group_link(request: Request, group_id: int, link_id: int) -> Any:
    """DEPRECATED: returns HTTP 410. Model links move to the new working-files layer."""
    return _working_files_gone_response()


# ==================== ENDPOINTS: MODEL QUERIES ====================


@router.get("/api/models/{model_ref:path}/working-groups")
def list_working_groups_for_model(request: Request, model_ref: str) -> Any:
    """DEPRECATED: returns HTTP 410. Working groups are gone; model links move to the new layer."""
    return _working_files_gone_response()


# ==================== ENDPOINTS: PUBLISHING ====================


@router.post("/api/working-groups/{group_id}/publish-to-local")
def publish_working_group_to_local(request: Request, group_id: int, payload: dict[str, Any] | None = None) -> Any:
    """DEPRECATED: returns HTTP 410. Publishing flow will be reintroduced on the new layer."""
    return _working_files_gone_response()


@router.get("/api/models/{model_ref:path}/lineage")
def get_model_lineage(request: Request, model_ref: str) -> Any:
    """Get model lineage/publish history."""
    state: AppState = request.app.state.model_catalog
    return get_model_lineage_service(settings=state.settings, model_ref=model_ref)


# ==================== ENDPOINTS: PROJECTS ====================


@router.post("/api/projects")
def create_model_catalog_project(request: Request, payload: dict[str, Any]) -> Any:
    """Create a new model catalog project."""
    state: AppState = request.app.state.model_catalog
    return create_model_catalog_project_service(settings=state.settings, payload=payload)


@router.get("/api/projects")
def list_model_catalog_projects(request: Request, limit: int | None = None, offset: int | None = None) -> Any:
    """List model catalog projects."""
    state: AppState = request.app.state.model_catalog
    return list_model_catalog_projects_service(settings=state.settings, limit=limit, offset=offset)


@router.get("/api/projects/{project_id}")
def get_model_catalog_project(request: Request, project_id: int) -> Any:
    """Get a single project with group and model counts."""
    state: AppState = request.app.state.model_catalog
    return get_model_catalog_project_service(settings=state.settings, project_id=project_id)


# ==================== ENDPOINTS: BULK OPERATIONS ====================


@router.post("/working-groups/bulk-discover")
@router.post("/api/working-groups/bulk-discover")
def bulk_discover_working_groups(request: Request, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folder discovery is intrinsic in /api/working-files/tree."""
    return _working_files_gone_response()


@router.post("/working-groups/bulk-import")
@router.post("/api/working-groups/bulk-import")
def bulk_import_working_groups(request: Request, payload: dict[str, Any]) -> Any:
    """DEPRECATED: returns HTTP 410. Folder discovery is intrinsic in /api/working-files/tree."""
    return _working_files_gone_response()
