"""Shared helper functions used across multiple routers.

These functions are canonical implementations shared by intake.py, models.py, and working.py.
All other files should import from this module rather than duplicating implementations.
"""

import json
import os
import re
from pathlib import Path, PureWindowsPath
from sqlite3 import connect
from typing import Any
from urllib.parse import quote

from ..settings import Settings


def _resolve_local_asset_storage_path(*, settings: Settings, asset: Any) -> Path | None:
    """Resolve a local asset's storage path, handling both absolute and relative paths."""
    storage_path_raw = str(getattr(asset, "storage_path", "") or "").strip()
    if not storage_path_raw:
        return None

    from .._helpers import _model_photo_storage_root
    
    curated_root = _model_photo_storage_root(settings).resolve()
    data_root = settings.db_path.parent.resolve()
    storage_path = Path(storage_path_raw).expanduser()

    if storage_path.is_absolute():
        resolved = storage_path.resolve()
        if resolved == curated_root or resolved.is_relative_to(curated_root):
            return resolved
        if resolved == data_root or resolved.is_relative_to(data_root):
            return resolved
        return resolved

    curated_candidate = (curated_root / storage_path).resolve()
    try:
        curated_candidate.relative_to(curated_root)
    except ValueError:
        curated_candidate = None
    if curated_candidate is not None:
        return curated_candidate

    data_candidate = (data_root / storage_path).resolve()
    try:
        data_candidate.relative_to(data_root)
    except ValueError:
        return None
    return data_candidate


def _slugify_title(value: str) -> str:
    """Convert a title to a URL-safe slug."""
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    collapsed = re.sub(r"-+", "-", normalized).strip("-")
    return collapsed or "working-group"


def _local_asset_media_urls(
    *,
    model_ref: str | None,
    asset_id: object,
    asset_type: object = None,
    preview_url: object = None,
) -> dict[str, str | None]:
    """Build canonical media URLs for a local model asset.

    This keeps model detail serialization and intake duplicate previews aligned.
    """
    normalized_model_ref = str(model_ref or "").strip()
    normalized_asset_id = str(asset_id or "").strip()
    normalized_asset_type = str(asset_type or "").strip().lower()
    configured_preview_url = str(preview_url or "").strip() or None

    download_url = (
        f"/api/models/{quote(normalized_model_ref, safe='')}/files/{quote(normalized_asset_id, safe='')}/download"
        if normalized_model_ref and normalized_asset_id
        else None
    )
    resolved_image_url = configured_preview_url or (download_url if normalized_asset_type == "image" else None)

    return {
        "download_url": download_url,
        "preview_url": configured_preview_url,
        "image_url": resolved_image_url,
        "thumbnail_url": resolved_image_url,
    }


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _serialize_project_row(project_row: Any) -> dict[str, Any]:
    """Serialize a model_catalog_projects database row to API response format."""
    return {
        "id": int(project_row["id"]),
        "slug": project_row["slug"],
        "title": project_row["title"],
        "description": project_row["description"],
        "notes": project_row["notes"],
        "status": project_row["status"] if "status" in set(project_row.keys()) else "evaluating",
        "project_type": project_row["project_type"] if "project_type" in set(project_row.keys()) else None,
        "origin": project_row["origin"] if "origin" in set(project_row.keys()) else None,
        "origin_url": project_row["origin_url"] if "origin_url" in set(project_row.keys()) else None,
        "task_backend": project_row["task_backend"] if "task_backend" in set(project_row.keys()) else "none",
        "bambuddy_project_id": int(project_row["bambuddy_project_id"]) if project_row["bambuddy_project_id"] is not None else None,
        "created_by": project_row["created_by"] if "created_by" in set(project_row.keys()) else None,
        "created_at": project_row["created_at"],
        "updated_at": project_row["updated_at"],
        "completed_at": project_row["completed_at"] if "completed_at" in set(project_row.keys()) else None,
        "archived_at": project_row["archived_at"],
    }


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
    from .._helpers import _windows_launch_enabled

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
    from .._helpers import _windows_launch_enabled

    container_path = str(path_value or "").strip()
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip()
    launch_enabled = _windows_launch_enabled(settings)
    windows_path = _container_assets_path_to_windows(container_path, settings)

    reason: str | None = None
    if not launch_enabled:
        reason = "assets_root_host_not_mnt_c"
    elif not windows_path:
        reason = "path_outside_assets_mount"

    explorer_command = f'explorer.exe /select,"{windows_path}"' if windows_path else ""
    folder_command = f'explorer.exe "{windows_path}"' if windows_path else ""

    return {
        "container_path": container_path,
        "assets_root_host": assets_root_host,
        "windows_launch_enabled": launch_enabled,
        "can_launch_file": bool(windows_path),
        "can_open_in_explorer": bool(windows_path),
        "windows_path": windows_path,
        "reason": reason,
        "explorer_command": explorer_command,
        "folder_command": folder_command,
    }


def _working_group_effective_folder_path(
    *,
    item_paths: list[str] | None = None,
    folder_hint: str | None = None,
    primary_file_path: str | None = None,
    discovery_source_folder: str | None = None,
) -> str:
    """Choose the best folder path representing a working group."""
    parent_paths: list[str] = []
    for item_path in item_paths or []:
        normalized = str(item_path or "").strip()
        if not normalized:
            continue
        parent_text = str(Path(normalized).parent).strip()
        if parent_text:
            parent_paths.append(parent_text)

    if parent_paths:
        try:
            common_parent = str(Path(os.path.commonpath(parent_paths))).strip()
        except ValueError:
            common_parent = ""
        if common_parent:
            return common_parent

    normalized_hint = str(folder_hint or "").strip()
    if normalized_hint:
        return normalized_hint

    normalized_primary = str(primary_file_path or "").strip()
    if normalized_primary:
        primary_parent = str(Path(normalized_primary).parent).strip()
        if primary_parent:
            return primary_parent

    return str(discovery_source_folder or "").strip()


def _serialize_working_group(connection: Any, group_row: Any, settings: Settings) -> dict[str, Any]:
    """Serialize a working_groups database row with related items and links to API response format."""
    from .._helpers import _windows_launch_enabled

    group_id = int(group_row["id"])
    group_keys = set(group_row.keys())
    project_id_value = group_row["project_id"] if "project_id" in group_keys else None
    project_row = None
    if project_id_value is not None:
        project_row = connection.execute(
            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
            (project_id_value,),
        ).fetchone()
    item_rows = connection.execute(
        """
        SELECT id, file_path, item_role, file_hash, file_size, source_metadata_json, created_at, updated_at
        FROM working_items
        WHERE working_group_id = ?
        ORDER BY id ASC
        """,
        (group_id,),
    ).fetchall()
    link_rows = connection.execute(
        """
        SELECT id, model_ref, link_role, link_metadata_json, created_at, updated_at
        FROM working_group_model_links
        WHERE working_group_id = ?
        ORDER BY id ASC
        """,
        (group_id,),
    ).fetchall()
    primary_file_path = str(group_row["primary_file_path"] or "").strip()
    folder_hint = str(group_row["folder_hint"] or "").strip()
    discovery_source_folder = str(group_row["discovery_source_folder"] or "").strip()
    effective_folder_path = _working_group_effective_folder_path(
        item_paths=[str(item_row["file_path"] or "") for item_row in item_rows],
        folder_hint=folder_hint,
        primary_file_path=primary_file_path,
        discovery_source_folder=discovery_source_folder,
    )
    return {
        "id": group_id,
        "slug": group_row["slug"],
        "title": group_row["title"],
        "stage": group_row["stage"],
        "project_id": int(project_id_value) if project_id_value is not None else None,
        "project": _serialize_project_row(project_row) if project_row is not None else None,
        "notes": group_row["notes"],
        "primary_file_path": group_row["primary_file_path"],
        "folder_hint": group_row["folder_hint"],
        "launch": {
            "assets_root_host": str(getattr(settings, "assets_root_host", "") or "").strip(),
            "windows_launch_enabled": _windows_launch_enabled(settings),
            "primary": _launch_context_for_path(primary_file_path, settings),
            "folder": _launch_context_for_path(effective_folder_path, settings),
        },
        "related_model_id": group_row["related_model_id"],
        "discovery": {
            "source_folder": group_row["discovery_source_folder"],
            "strategy": group_row["discovery_strategy"],
            "timestamp": group_row["discovery_timestamp"],
            "metadata": json.loads(str(group_row["discovery_metadata_json"] or "{}")),
        },
        "items": [
            {
                "id": int(item_row["id"]),
                "file_path": item_row["file_path"],
                "item_role": item_row["item_role"],
                "file_hash": item_row["file_hash"],
                "file_size": item_row["file_size"],
                "launch": _launch_context_for_path(str(item_row["file_path"] or ""), settings),
                "source_metadata": json.loads(str(item_row["source_metadata_json"] or "{}")),
                "created_at": item_row["created_at"],
                "updated_at": item_row["updated_at"],
            }
            for item_row in item_rows
        ],
        "links": [
            {
                "id": int(link_row["id"]),
                "model_ref": link_row["model_ref"],
                "link_role": link_row["link_role"],
                "metadata": json.loads(str(link_row["link_metadata_json"] or "{}")),
                "created_at": link_row["created_at"],
                "updated_at": link_row["updated_at"],
            }
            for link_row in link_rows
        ],
        "created_at": group_row["created_at"],
        "updated_at": group_row["updated_at"],
    }


def _refresh_working_group_cached_counts(connection: Any, group_id: int) -> dict[str, int]:
    """Recompute and persist cached file/folder counts for a working group."""
    rows = connection.execute(
        "SELECT file_path FROM working_items WHERE working_group_id = ?",
        (int(group_id),),
    ).fetchall()
    model_exts = {".3mf", ".stl", ".step", ".stp", ".obj"}
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"}

    total = 0
    model_count = 0
    image_count = 0
    other_count = 0
    folder_keys: set[str] = set()

    for row in rows:
        path_value = str(row["file_path"] or "").strip().replace("\\", "/")
        if not path_value:
            continue
        total += 1
        suffix = Path(path_value).suffix.lower()
        if suffix in model_exts:
            model_count += 1
        elif suffix in image_exts:
            image_count += 1
        else:
            other_count += 1

        slash_index = path_value.rfind("/")
        if slash_index > 0:
            folder_value = path_value[:slash_index].strip().lower()
            if folder_value:
                folder_keys.add(folder_value)

    folder_count = len(folder_keys)
    connection.execute(
        """
        UPDATE working_groups
        SET
            cached_total_files = ?,
            cached_model_files = ?,
            cached_image_files = ?,
            cached_other_files = ?,
            cached_folder_count = ?
        WHERE id = ?
        """,
        (total, model_count, image_count, other_count, folder_count, int(group_id)),
    )

    return {
        "total": total,
        "models": model_count,
        "images": image_count,
        "other": other_count,
        "folders": folder_count,
    }
