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
import os
import re
import shutil
import sqlite3
from pathlib import Path, PureWindowsPath
from sqlite3 import connect
from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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
            if suffix not in SUPPORTED_WORKING_FILE_EXTENSIONS:
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

        connection.commit()
    finally:
        connection.close()

    return {
        "discovered": len(discovered_rows),
        "inserted": inserted,
        "updated": updated,
        "removed": removed,
        "hashed": hashed,
        "roots": [str(root) for root in roots],
        "refreshed_at": now_iso,
    }


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

    return {
        "container_path": container_path,
        "assets_root_host": assets_root_host,
        "windows_launch_enabled": launch_enabled,
        "can_launch_file": bool(windows_path),
        "can_open_in_explorer": bool(windows_path),
        "windows_path": windows_path,
        "reason": reason,
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
            if suffix not in SUPPORTED_WORKING_FILE_EXTENSIONS:
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


@router.get("/api/working-files/explorer")
def explore_working_files(request: Request,
    view: str | None = None,
    q: str | None = None,
    extension: str | None = None,
    path_contains: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Any:
    """Explore working files grouped or ungrouped."""
    state: AppState = request.app.state.model_catalog
    view_mode = str(view or "groups").strip().lower() or "groups"
    if view_mode not in {"groups", "all", "ungrouped"}:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_view", "message": "view must be one of groups, all, ungrouped"})

    limit_value = max(1, min(int(limit or 200), 1000))
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
    preferred_roots = _configured_working_files_roots(state.settings)
    connection = connect(state.settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        inventory_rows = connection.execute(
            f"""
            SELECT *
            FROM working_file_inventory
            WHERE {where_sql}
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
            params,
        ).fetchall()

        if preferred_roots:
            inventory_rows = [
                row
                for row in inventory_rows
                if _working_file_path_within_roots(
                    str(row["source_path_canonical"] or row["source_path_raw"] or ""),
                    preferred_roots,
                )
            ]

        path_keys = {
            _normalize_path_compare_key(row["source_path_canonical"] or row["source_path_raw"])
            for row in inventory_rows
            if _normalize_path_compare_key(row["source_path_canonical"] or row["source_path_raw"])
        }
        memberships_by_key = _file_membership_map(connection, path_keys=path_keys)

        all_files = []
        for row in inventory_rows:
            canonical_path = str(row["source_path_canonical"] or row["source_path_raw"] or "")
            compare_key = _normalize_path_compare_key(canonical_path)
            memberships = memberships_by_key.get(compare_key, [])
            all_files.append(
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
                    "launch": _launch_context_for_path(canonical_path, state.settings),
                    "group_memberships": memberships,
                }
            )

        ungrouped_files = [entry for entry in all_files if not entry["group_memberships"]]

        if view_mode in {"all", "ungrouped"}:
            scoped_files = all_files if view_mode == "all" else ungrouped_files
            paged = scoped_files[offset_value: offset_value + limit_value]
            return {
                "success": True,
                "view": view_mode,
                "summary": {
                    "all_count": len(all_files),
                    "ungrouped_count": len(ungrouped_files),
                },
                "pagination": {
                    "limit": limit_value,
                    "offset": offset_value,
                    "total": len(scoped_files),
                },
                "files": paged,
            }

        group_rows = connection.execute(
            """
            SELECT *
            FROM working_groups
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit_value, offset_value),
        ).fetchall()
        groups = []
        for group_row in group_rows:
            serialized_group = _serialize_working_group(connection, group_row, state.settings)
            sorted_items = sorted(
                serialized_group.get("items") or [],
                key=lambda item: _working_file_sort_key(
                    file_extension=Path(str(item.get("file_path") or "")).suffix.lower(),
                    file_name=Path(str(item.get("file_path") or "")).name,
                    file_path=str(item.get("file_path") or ""),
                ),
            )
            for item in sorted_items:
                file_path = str(item.get("file_path") or "")
                membership_key = _normalize_path_compare_key(file_path)
                item["group_memberships"] = memberships_by_key.get(membership_key, [])
                source_metadata = item.get("source_metadata")
                if not isinstance(source_metadata, dict):
                    source_metadata = {}
                has_thumbnail = any(
                    str(source_metadata.get(field) or "").strip()
                    for field in ("thumbnail_url", "preview_url", "image_url", "embedded_thumbnail_url", "thumb_url")
                )
                if not has_thumbnail:
                    data_url_value = _working_thumbnail_data_url(file_path)
                    if data_url_value:
                        source_metadata["thumbnail_url"] = data_url_value
                        source_metadata["image_url"] = data_url_value
                        if Path(file_path).suffix.lower() == ".3mf":
                            source_metadata["embedded_thumbnail_url"] = data_url_value
                        item["source_metadata"] = source_metadata

            if q and q.strip():
                query_text = q.strip().lower()
                haystack = " ".join(
                    [
                        str(serialized_group.get("title") or ""),
                        str(serialized_group.get("notes") or ""),
                        str(serialized_group.get("folder_hint") or ""),
                    ]
                    + [str(item.get("file_path") or "") for item in sorted_items]
                ).lower()
                if query_text not in haystack:
                    continue

            count_3mf = sum(1 for item in sorted_items if Path(str(item.get("file_path") or "")).suffix.lower() == ".3mf")
            groups.append(
                {
                    "id": serialized_group["id"],
                    "slug": serialized_group["slug"],
                    "title": serialized_group["title"],
                    "stage": serialized_group["stage"],
                    "notes": serialized_group.get("notes"),
                    "folder_hint": serialized_group.get("folder_hint"),
                    "launch": serialized_group.get("launch"),
                    "primary_file_path": serialized_group.get("primary_file_path"),
                    "updated_at": serialized_group.get("updated_at"),
                    "counts": {
                        "total": len(sorted_items),
                        "count_3mf": count_3mf,
                        "count_other": max(0, len(sorted_items) - count_3mf),
                    },
                    "files": sorted_items,
                }
            )

        total_groups = int(
            connection.execute("SELECT COUNT(*) AS cnt FROM working_groups").fetchone()["cnt"]
        )
        return {
            "success": True,
            "view": "groups",
            "summary": {
                "all_count": len(all_files),
                "ungrouped_count": len(ungrouped_files),
                "group_count": total_groups,
            },
            "pagination": {
                "limit": limit_value,
                "offset": offset_value,
                "total": total_groups,
            },
            "groups": groups,
        }
    finally:
        connection.close()


# ==================== ENDPOINTS: WORKING GROUP MEMBERSHIPS ====================


@router.post("/api/working-groups/memberships/batch-add")
def batch_add_working_group_memberships(request: Request, payload: dict[str, Any]) -> Any:
    """Add multiple files to a working group."""
    state: AppState = request.app.state.model_catalog
    return batch_add_working_group_memberships_service(settings=state.settings, payload=payload)


@router.post("/api/working-groups/memberships/batch-remove")
def batch_remove_working_group_memberships(request: Request, payload: dict[str, Any]) -> Any:
    """Remove multiple files from a working group."""
    state: AppState = request.app.state.model_catalog
    return batch_remove_working_group_memberships_service(settings=state.settings, payload=payload)


# ==================== ENDPOINTS: WORKING GROUP MANAGEMENT ====================


@router.post("/api/working-groups/{group_id}/reorganize")
def reorganize_working_group(request: Request, group_id: int, payload: dict[str, Any] | None = None) -> Any:
    """Reorganize working group files to target folder."""
    state: AppState = request.app.state.model_catalog
    return reorganize_working_group_service(
        settings=state.settings,
        group_id=group_id,
        payload=payload,
        refresh_inventory=lambda: _refresh_working_file_inventory(
            db_path=state.settings.db_path,
            roots=_configured_working_files_roots(state.settings),
            compute_hashes=False,
        ),
    )


@router.post("/api/working-groups")
def create_working_group(request: Request, payload: dict[str, Any]) -> Any:
    """Create a new working group."""
    state: AppState = request.app.state.model_catalog
    return create_working_group_service(settings=state.settings, payload=payload)


@router.get("/api/working-groups")
def list_working_groups(request: Request, limit: int | None = None, offset: int | None = None, stage: str | None = None, project_id: int | None = None, q: str | None = None) -> Any:
    """List working groups with filtering."""
    state: AppState = request.app.state.model_catalog
    return list_working_groups_service(
        settings=state.settings,
        limit=limit,
        offset=offset,
        stage=stage,
        project_id=project_id,
        q=q,
    )


@router.get("/api/working-groups/{group_id}")
def get_working_group(request: Request, group_id: int) -> Any:
    """Get a single working group."""
    state: AppState = request.app.state.model_catalog
    return get_working_group_service(settings=state.settings, group_id=group_id)


@router.patch("/api/working-groups/{group_id}")
def update_working_group(request: Request, group_id: int, payload: dict[str, Any]) -> Any:
    """Update a working group."""
    state: AppState = request.app.state.model_catalog
    return update_working_group_service(settings=state.settings, group_id=group_id, payload=payload)


@router.delete("/api/working-groups/{group_id}")
def delete_working_group(request: Request, group_id: int) -> Any:
    """Delete a working group and cascade delete items and links."""
    state: AppState = request.app.state.model_catalog
    return delete_working_group_service(settings=state.settings, group_id=group_id)


# ==================== ENDPOINTS: WORKING GROUP ITEMS ====================


@router.post("/api/working-groups/{group_id}/items")
def add_working_group_item(request: Request, group_id: int, payload: dict[str, Any]) -> Any:
    """Add a single item to a working group."""
    state: AppState = request.app.state.model_catalog
    return add_working_group_item_service(settings=state.settings, group_id=group_id, payload=payload)


@router.delete("/api/working-groups/{group_id}/items/{item_id}")
def remove_working_group_item(request: Request, group_id: int, item_id: int) -> Any:
    """Remove an item from a working group."""
    state: AppState = request.app.state.model_catalog
    return remove_working_group_item_service(settings=state.settings, group_id=group_id, item_id=item_id)


# ==================== ENDPOINTS: MODEL LINKS ====================


@router.post("/api/working-groups/{group_id}/links")
def create_working_group_link(request: Request, group_id: int, payload: dict[str, Any]) -> Any:
    """Create or update a link from working group to model."""
    state: AppState = request.app.state.model_catalog
    return create_working_group_link_service(settings=state.settings, group_id=group_id, payload=payload)


@router.get("/api/working-groups/{group_id}/links")
def list_working_group_links(request: Request, group_id: int) -> Any:
    """List model links for a working group."""
    state: AppState = request.app.state.model_catalog
    return list_working_group_links_service(settings=state.settings, group_id=group_id)


@router.delete("/api/working-groups/{group_id}/links/{link_id}")
def delete_working_group_link(request: Request, group_id: int, link_id: int) -> Any:
    """Delete a model link from a working group."""
    state: AppState = request.app.state.model_catalog
    return delete_working_group_link_service(settings=state.settings, group_id=group_id, link_id=link_id)


# ==================== ENDPOINTS: MODEL QUERIES ====================


@router.get("/api/models/{model_ref:path}/working-groups")
def list_working_groups_for_model(request: Request, model_ref: str) -> Any:
    """Get all working groups linked to a model."""
    state: AppState = request.app.state.model_catalog
    return list_working_groups_for_model_service(settings=state.settings, model_ref=model_ref)


# ==================== ENDPOINTS: PUBLISHING ====================


@router.post("/api/working-groups/{group_id}/publish-to-local")
def publish_working_group_to_local(request: Request, group_id: int, payload: dict[str, Any] | None = None) -> Any:
    """Publish a working group to a local model."""
    state: AppState = request.app.state.model_catalog
    return publish_working_group_to_local_service(settings=state.settings, group_id=group_id, payload=payload)


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
    """Scan folder and propose working groups."""
    state: AppState = request.app.state.model_catalog
    return bulk_discover_working_groups_service(db_path=state.settings.db_path, payload=payload)


@router.post("/working-groups/bulk-import")
@router.post("/api/working-groups/bulk-import")
def bulk_import_working_groups(request: Request, payload: dict[str, Any]) -> Any:
    """Import bulk discover proposals as working groups."""
    state: AppState = request.app.state.model_catalog
    return bulk_import_working_groups_service(db_path=state.settings.db_path, payload=payload)
