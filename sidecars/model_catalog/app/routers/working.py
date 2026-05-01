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



import hashlib

import json

import os

import re

import shutil

import sqlite3

from pathlib import Path, PureWindowsPath

from sqlite3 import connect

from typing import Any



from fastapi import APIRouter

from fastapi.responses import JSONResponse



from ..settings import Settings

from ..state import AppState

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

    build_dedup_collision_warning,

    detect_duplicate_files,

    get_all_indexed_file_hashes,

    get_working_items_hashes,

)



router = APIRouter(tags=["working"])



# ==================== CONSTANTS ====================



SUPPORTED_BULK_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj"}



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





# ==================== HELPER FUNCTIONS: FILE OPERATIONS ====================





def _sha256_file(path: Path) -> str:

    """Compute SHA256 hash of a file."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for chunk in iter(lambda: handle.read(1024 * 1024), b""):

            digest.update(chunk)

    return digest.hexdigest()





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





def _slugify_title(value: str) -> str:

    """Convert title to URL-safe slug."""

    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())

    collapsed = re.sub(r"-+", "-", normalized).strip("-")

    return collapsed or "working-group"





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





def _serialize_working_group(connection: Any, group_row: Any, settings: Settings) -> dict[str, Any]:

    """Serialize working group row to JSON response."""

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

    effective_folder_path = folder_hint or (str(Path(primary_file_path).parent) if primary_file_path else "") or discovery_source_folder

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

        "related_manyfold_model_id": group_row["related_manyfold_model_id"],

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





def _serialize_project_row(project_row: Any) -> dict[str, Any]:

    """Serialize project row to JSON response."""

    return {

        "id": int(project_row["id"]),

        "slug": project_row["slug"],

        "title": project_row["title"],

        "description": project_row["description"],

        "notes": project_row["notes"],

        "bambuddy_project_id": int(project_row["bambuddy_project_id"]) if project_row["bambuddy_project_id"] is not None else None,

        "created_at": project_row["created_at"],

        "updated_at": project_row["updated_at"],

        "archived_at": project_row["archived_at"],

    }





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

    state: AppState = request.request.app.state.model_catalog

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

    state: AppState = request.request.app.state.model_catalog

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

    state: AppState = request.request.app.state.model_catalog

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

    state: AppState = request.request.app.state.model_catalog

    group_id = int(payload.get("group_id") or 0)

    if group_id <= 0:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "group_id is required"})



    raw_paths = payload.get("file_paths")

    if not isinstance(raw_paths, list) or not raw_paths:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must be a non-empty array"})



    item_role = str(payload.get("item_role") or "supporting").strip().lower() or "supporting"

    if item_role not in {"primary", "supporting"}:

        item_role = "supporting"

    allow_multi_group = bool(payload.get("allow_multi_group", True))



    allowlisted_roots = _working_group_allowed_source_roots(state.settings)

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})



        now_iso = _bulk_utc_now_iso()

        results: list[dict[str, Any]] = []

        inserted_count = 0

        seen_request_keys: set[str] = set()

        for raw_path in raw_paths:

            source_input = str(raw_path or "").strip()

            if not source_input:

                results.append({"path": source_input, "outcome": "invalid", "message": "empty path"})

                continue

            resolved_path = Path(source_input).expanduser().resolve()

            if not resolved_path.exists():

                results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "missing", "message": "path does not exist"})

                continue



            candidate_files: list[Path] = []

            if resolved_path.is_file():

                candidate_files = [resolved_path]

            elif resolved_path.is_dir():

                candidate_files = [

                    candidate.resolve()

                    for candidate in sorted(resolved_path.rglob("*"))

                    if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_WORKING_FILE_EXTENSIONS

                ]

                if not candidate_files:

                    results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "unsupported", "message": "folder has no supported files"})

                    continue

            else:

                results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "unsupported", "message": "path must be a file or folder"})

                continue



            for candidate_file in candidate_files:

                canonical_path = str(candidate_file)

                compare_key = _normalize_path_compare_key(canonical_path)

                if not compare_key or compare_key in seen_request_keys:

                    continue

                seen_request_keys.add(compare_key)



                if candidate_file.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:

                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "unsupported", "message": "file extension is not supported"})

                    continue

                if allowlisted_roots and not _is_path_within_roots(candidate_file, allowlisted_roots):

                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "blocked", "message": "path is outside the configured intake/working roots"})

                    continue



                existing_in_group = connection.execute(

                    "SELECT id FROM working_items WHERE working_group_id = ? AND LOWER(REPLACE(file_path, '\\\\', '/')) = ?",

                    (group_id, compare_key),

                ).fetchone()

                if existing_in_group is not None:

                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "skipped", "message": "already attached to target group"})

                    continue



                existing_groups = connection.execute(

                    """

                    SELECT wi.working_group_id, wg.title

                    FROM working_items wi

                    JOIN working_groups wg ON wg.id = wi.working_group_id

                    WHERE LOWER(REPLACE(wi.file_path, '\\\\', '/')) = ?

                    ORDER BY wg.updated_at DESC, wg.id DESC

                    """,

                    (compare_key,),

                ).fetchall()

                if existing_groups and not allow_multi_group:

                    labels = [f"{int(row['working_group_id'])}:{row['title']}" for row in existing_groups]

                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "skipped", "message": "already attached to another group", "existing_groups": labels})

                    continue



                try:

                    file_hash = _sha256_file(candidate_file).lower()

                except (OSError, PermissionError):

                    file_hash = ""



                file_hash_to_store: str | None = file_hash or None

                hash_warning: str | None = None

                if file_hash_to_store and allow_multi_group:

                    existing_hash_match = connection.execute(

                        "SELECT id FROM working_items WHERE file_hash = ?",

                        (file_hash_to_store,),

                    ).fetchone()

                    if existing_hash_match is not None:

                        file_hash_to_store = None

                        hash_warning = "hash_conflict_in_existing_group"



                try:

                    stat_result = candidate_file.stat()

                    source_metadata = _bulk_path_source_metadata(candidate_file, stat_result)

                    file_size = int(stat_result.st_size)

                except (OSError, PermissionError):

                    source_metadata = {"source_path": canonical_path}

                    file_size = None



                try:

                    connection.execute(

                        """

                        INSERT INTO working_items (

                            working_group_id, file_path, item_role, created_at, updated_at,

                            file_hash, file_size, source_metadata_json

                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                        """,

                        (

                            group_id,

                            canonical_path,

                            item_role,

                            now_iso,

                            now_iso,

                            file_hash_to_store,

                            file_size,

                            json.dumps(source_metadata),

                        ),

                    )

                except sqlite3.IntegrityError as exc:

                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "failed", "message": str(exc)})

                    continue



                inserted_count += 1

                results.append(

                    {

                        "path": source_input,

                        "canonical_path": canonical_path,

                        "outcome": "added",

                        "item_role": item_role,

                        "warning": hash_warning,

                    }

                )



        if item_role == "primary" and inserted_count:

            primary_row = connection.execute(

                "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",

                (group_id,),

            ).fetchone()

            connection.execute(

                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",

                ((primary_row["file_path"] if primary_row else None), now_iso, group_id),

            )

        elif inserted_count:

            connection.execute("UPDATE working_groups SET updated_at = ? WHERE id = ?", (now_iso, group_id))



        refreshed_group = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        connection.commit()

        return {

            "success": True,

            "group_id": group_id,

            "summary": {

                "requested": len(raw_paths),

                "added": inserted_count,

                "skipped_or_failed": max(0, len(raw_paths) - inserted_count),

            },

            "results": results,

            "group": _serialize_working_group(connection, refreshed_group, state.settings),

        }

    finally:

        connection.close()





@router.post("/api/working-groups/memberships/batch-remove")

def batch_remove_working_group_memberships(request: Request, payload: dict[str, Any]) -> Any:

    """Remove multiple files from a working group."""

    state: AppState = request.request.app.state.model_catalog

    group_id = int(payload.get("group_id") or 0)

    if group_id <= 0:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "group_id is required"})



    raw_paths = payload.get("file_paths")

    if not isinstance(raw_paths, list) or not raw_paths:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must be a non-empty array"})



    normalized_keys = {_normalize_path_compare_key(path) for path in raw_paths if str(path or "").strip()}

    if not normalized_keys:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must include at least one non-empty value"})



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})



        item_rows = connection.execute(

            "SELECT id, file_path FROM working_items WHERE working_group_id = ?",

            (group_id,),

        ).fetchall()

        removable_ids: list[int] = []

        results: list[dict[str, Any]] = []

        for row in item_rows:

            normalized = _normalize_path_compare_key(row["file_path"])

            if normalized in normalized_keys:

                removable_ids.append(int(row["id"]))

                results.append({"path": row["file_path"], "outcome": "removed"})



        if removable_ids:

            placeholders = ",".join("?" for _ in removable_ids)

            connection.execute(

                f"DELETE FROM working_items WHERE working_group_id = ? AND id IN ({placeholders})",

                (group_id, *removable_ids),

            )



        replacement = connection.execute(

            "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",

            (group_id,),

        ).fetchone()

        connection.execute(

            "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",

            ((replacement["file_path"] if replacement else None), _bulk_utc_now_iso(), group_id),

        )



        refreshed_group = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        connection.commit()

        return {

            "success": True,

            "group_id": group_id,

            "summary": {

                "requested": len(normalized_keys),

                "removed": len(removable_ids),

                "not_found": max(0, len(normalized_keys) - len(removable_ids)),

            },

            "results": results,

            "group": _serialize_working_group(connection, refreshed_group, state.settings),

        }

    finally:

        connection.close()





# ==================== ENDPOINTS: WORKING GROUP MANAGEMENT ====================





@router.post("/api/working-groups/{group_id}/reorganize")

def reorganize_working_group(request: Request, group_id: int, payload: dict[str, Any] | None = None) -> Any:

    """Reorganize working group files to target folder."""

    state: AppState = request.request.app.state.model_catalog

    payload = payload or {}

    execute = bool(payload.get("execute", False))

    selected_paths = payload.get("file_paths") if isinstance(payload.get("file_paths"), list) else None



    destination_root = _working_files_destination_root(state.settings)

    if destination_root is None:

        return JSONResponse(status_code=400, content={"success": False, "error": "no_destination_root", "message": "No allowlisted working-files root is configured"})



    allowlisted_roots = _working_group_allowed_source_roots(state.settings)

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})



        item_rows = connection.execute(

            "SELECT id, file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC",

            (group_id,),

        ).fetchall()

        if not item_rows:

            return JSONResponse(status_code=400, content={"success": False, "error": "no_items", "message": "Working group has no files"})



        selected_keys = {

            _normalize_path_compare_key(path)

            for path in (selected_paths or [])

            if str(path or "").strip()

        }

        target_items = []

        for row in item_rows:

            normalized = _normalize_path_compare_key(row["file_path"])

            if selected_keys and normalized not in selected_keys:

                continue

            target_items.append(row)



        if not target_items:

            return JSONResponse(status_code=400, content={"success": False, "error": "no_matching_items", "message": "No matching files found for reorganize"})



        group_slug = str(group_row["slug"] or f"group-{group_id}")

        target_folder = (destination_root / group_slug).resolve()

        plan: list[dict[str, Any]] = []

        conflicts: list[dict[str, Any]] = []

        for row in target_items:

            source_path = Path(str(row["file_path"] or "")).expanduser()

            if not source_path.exists() or not source_path.is_file():

                entry = {

                    "item_id": int(row["id"]),

                    "source_path": str(source_path),

                    "action": "missing",

                    "reason": "source_missing",

                }

                plan.append(entry)

                conflicts.append(entry)

                continue

            resolved_source = source_path.resolve()

            if allowlisted_roots and not _is_path_within_roots(resolved_source, allowlisted_roots):

                entry = {

                    "item_id": int(row["id"]),

                    "source_path": str(resolved_source),

                    "action": "blocked",

                    "reason": "outside_working_or_intake_roots",

                }

                plan.append(entry)

                conflicts.append(entry)

                continue



            destination_path = (target_folder / resolved_source.name).resolve()

            if _normalize_path_compare_key(resolved_source) == _normalize_path_compare_key(destination_path):

                plan.append(

                    {

                        "item_id": int(row["id"]),

                        "source_path": str(resolved_source),

                        "destination_path": str(destination_path),

                        "action": "noop",

                        "reason": "already_in_target_folder",

                    }

                )

                continue

            if destination_path.exists():

                entry = {

                    "item_id": int(row["id"]),

                    "source_path": str(resolved_source),

                    "destination_path": str(destination_path),

                    "action": "conflict",

                    "reason": "destination_exists",

                }

                plan.append(entry)

                conflicts.append(entry)

                continue



            plan.append(

                {

                    "item_id": int(row["id"]),

                    "source_path": str(resolved_source),

                    "destination_path": str(destination_path),

                    "action": "move",

                    "reason": "ok",

                }

            )



        if not execute:

            return {

                "success": True,

                "working_group_id": group_id,

                "dry_run": True,

                "can_execute": len(conflicts) == 0,

                "target_folder": str(target_folder),

                "plan": plan,

                "conflicts": conflicts,

            }



        if conflicts:

            return JSONResponse(

                status_code=409,

                content={

                    "success": False,

                    "error": "reorganize_conflicts",

                    "message": "Reorganize plan has conflicts; run dry-run and resolve conflicts first",

                    "target_folder": str(target_folder),

                    "plan": plan,

                    "conflicts": conflicts,

                },

            )



        target_folder.mkdir(parents=True, exist_ok=True)

        moved_map: dict[int, tuple[str, str]] = {}

        for entry in plan:

            if entry["action"] != "move":

                continue

            item_id = int(entry["item_id"])

            source_path = Path(str(entry["source_path"]))

            destination_path = Path(str(entry["destination_path"]))

            shutil.move(str(source_path), str(destination_path))

            moved_map[item_id] = (str(source_path), str(destination_path))



        now_iso = _bulk_utc_now_iso()

        for item_id, move_pair in moved_map.items():

            old_path, new_path = move_pair

            connection.execute(

                "UPDATE working_items SET file_path = ?, updated_at = ? WHERE id = ?",

                (new_path, now_iso, item_id),

            )

            if str(group_row["primary_file_path"] or "") == old_path:

                connection.execute(

                    "UPDATE working_groups SET primary_file_path = ? WHERE id = ?",

                    (new_path, group_id),

                )



        connection.execute(

            "UPDATE working_groups SET folder_hint = ?, updated_at = ? WHERE id = ?",

            (str(target_folder), now_iso, group_id),

        )

        connection.execute(

            """

            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)

            VALUES (?, ?, ?, ?, ?)

            """,

            (

                "working_group_reorganized",

                "working_group",

                str(group_id),

                json.dumps(

                    {

                        "group_id": group_id,

                        "target_folder": str(target_folder),

                        "moved_count": len(moved_map),

                        "moves": [

                            {"item_id": item_id, "old_path": old_path, "new_path": new_path}

                            for item_id, (old_path, new_path) in moved_map.items()

                        ],

                    }

                ),

                now_iso,

            ),

        )



        connection.commit()

        refreshed = _refresh_working_file_inventory(

            db_path=state.settings.db_path,

            roots=[destination_root],

            compute_hashes=False,

        )

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        return {

            "success": True,

            "working_group_id": group_id,

            "dry_run": False,

            "target_folder": str(target_folder),

            "moved_count": len(moved_map),

            "plan": plan,

            "inventory_refresh": refreshed,

            "group": _serialize_working_group(connection, group_row, state.settings),

        }

    finally:

        connection.close()





@router.post("/api/working-groups")

def create_working_group(request: Request, payload: dict[str, Any]) -> Any:

    """Create a new working group."""

    state: AppState = request.request.app.state.model_catalog

    title = str(payload.get("title") or "").strip()

    if not title:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "title is required"})



    stage = str(payload.get("stage") or "draft").strip() or "draft"

    notes = str(payload.get("notes") or "").strip() or None

    folder_hint = str(payload.get("folder_hint") or "").strip() or None

    primary_file_path = str(payload.get("primary_file_path") or "").strip() or None

    project_id = _resolve_project_id_value(payload.get("project_id"))

    now_iso = _bulk_utc_now_iso()



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        if project_id is not None:

            project_row = connection.execute(

                "SELECT id FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",

                (project_id,),

            ).fetchone()

            if project_row is None:

                return JSONResponse(status_code=404, content={"success": False, "error": "project_not_found", "message": f"Project not found: {project_id}"})

        slug = _unique_slug(connection, title)

        connection.execute(

            """

            INSERT INTO working_groups (

                slug, title, stage, project_id, notes, primary_file_path, folder_hint,

                related_manyfold_model_id, created_at, updated_at,

                discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json

            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """,

            (

                slug,

                title,

                stage,

                project_id,

                notes,

                primary_file_path,

                folder_hint,

                str(payload.get("related_manyfold_model_id") or "").strip() or None,

                now_iso,

                now_iso,

                None,

                None,

                None,

                "{}",

            ),

        )

        group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])

        row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        connection.commit()

        return {"success": True, "group": _serialize_working_group(connection, row, state.settings)}

    finally:

        connection.close()





@router.get("/api/working-groups")

def list_working_groups(request: Request, limit: int | None = None, offset: int | None = None, stage: str | None = None, project_id: int | None = None) -> Any:

    """List working groups with filtering."""

    state: AppState = request.request.app.state.model_catalog

    limit_value = max(1, min(int(limit or 100), 500))

    offset_value = max(0, int(offset or 0))



    where_sql = "1=1"

    params: list[Any] = []

    if stage and stage.strip():

        where_sql += " AND stage = ?"

        params.append(stage.strip())

    if project_id is not None:

        where_sql += " AND project_id = ?"

        params.append(int(project_id))



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        total_row = connection.execute(

            f"SELECT COUNT(*) AS cnt FROM working_groups WHERE {where_sql}",

            params,

        ).fetchone()

        rows = connection.execute(

            f"""

            SELECT * FROM working_groups

            WHERE {where_sql}

            ORDER BY updated_at DESC, id DESC

            LIMIT ? OFFSET ?

            """,

            [*params, limit_value, offset_value],

        ).fetchall()

        groups = [_serialize_working_group(connection, row, state.settings) for row in rows]

    finally:

        connection.close()



    return {

        "success": True,

        "pagination": {

            "limit": limit_value,

            "offset": offset_value,

            "total": int(total_row["cnt"] if total_row else 0),

        },

        "groups": groups,

    }





@router.get("/api/working-groups/{group_id}")

def get_working_group(request: Request, group_id: int) -> Any:

    """Get a single working group."""

    state: AppState = request.request.app.state.model_catalog

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        return {"success": True, "group": _serialize_working_group(connection, row, state.settings)}

    finally:

        connection.close()





@router.patch("/api/working-groups/{group_id}")

def update_working_group(request: Request, group_id: int, payload: dict[str, Any]) -> Any:

    """Update a working group."""

    state: AppState = request.request.app.state.model_catalog

    allowed_fields = {

        "title": "title",

        "stage": "stage",

        "notes": "notes",

        "primary_file_path": "primary_file_path",

        "folder_hint": "folder_hint",

        "related_manyfold_model_id": "related_manyfold_model_id",

    }

    updates: list[str] = []

    params: list[Any] = []

    for field_name, column_name in allowed_fields.items():

        if field_name not in payload:

            continue

        updates.append(f"{column_name} = ?")

        value = payload.get(field_name)

        if value is None:

            params.append(None)

        else:

            text_value = str(value).strip()

            params.append(text_value or None)

    if not updates:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "No mutable fields provided"})



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        if "project_id" in payload:

            requested_project_id = payload.get("project_id")

            project_id_value = _resolve_project_id_value(requested_project_id)

            if requested_project_id not in {None, "", 0, "0"} and project_id_value is None:

                return JSONResponse(status_code=400, content={"success": False, "error": "invalid_project_id", "message": "project_id must be a positive integer or null"})

            if project_id_value is not None:

                project_row = connection.execute(

                    "SELECT id FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",

                    (project_id_value,),

                ).fetchone()

                if project_row is None:

                    return JSONResponse(status_code=404, content={"success": False, "error": "project_not_found", "message": f"Project not found: {project_id_value}"})

            updates.append("project_id = ?")

            params.append(project_id_value)

        updates.append("updated_at = ?")

        params.append(_bulk_utc_now_iso())

        params.append(group_id)

        connection.execute(

            f"UPDATE working_groups SET {', '.join(updates)} WHERE id = ?",

            params,

        )

        row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        connection.commit()

        return {"success": True, "group": _serialize_working_group(connection, row, state.settings)}

    finally:

        connection.close()





@router.delete("/api/working-groups/{group_id}")

def delete_working_group(request: Request, group_id: int) -> Any:

    """Delete a working group and cascade delete items and links."""

    state: AppState = request.request.app.state.model_catalog

    connection = connect(state.settings.db_path)

    try:

        row = connection.execute("SELECT id FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        connection.execute("DELETE FROM working_group_model_links WHERE working_group_id = ?", (group_id,))

        connection.execute("DELETE FROM working_items WHERE working_group_id = ?", (group_id,))

        connection.execute("DELETE FROM working_groups WHERE id = ?", (group_id,))

        connection.commit()

        return {"success": True, "deleted": True, "working_group_id": group_id}

    finally:

        connection.close()





# ==================== ENDPOINTS: WORKING GROUP ITEMS ====================





@router.post("/api/working-groups/{group_id}/items")

def add_working_group_item(request: Request, group_id: int, payload: dict[str, Any]) -> Any:

    """Add a single item to a working group."""

    state: AppState = request.request.app.state.model_catalog

    file_path_raw = str(payload.get("file_path") or "").strip()

    if not file_path_raw:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_path is required"})

    file_path = Path(file_path_raw).expanduser().resolve()

    if not file_path.exists() or not file_path.is_file():

        return JSONResponse(status_code=400, content={"success": False, "error": "missing_source", "message": f"file_path not found: {file_path_raw}"})

    allowed_roots = _working_group_allowed_source_roots(state.settings)

    if allowed_roots and not _is_path_within_roots(file_path, allowed_roots):

        return JSONResponse(status_code=403, content={"success": False, "error": "path_not_allowed", "message": "file_path is outside the configured intake/working roots"})



    item_role = str(payload.get("item_role") or "supporting").strip().lower() or "supporting"

    if item_role not in {"primary", "supporting"}:

        item_role = "supporting"

    file_hash = str(payload.get("file_hash") or "").strip().lower()

    if not file_hash:

        try:

            file_hash = _sha256_file(file_path).lower()

        except (OSError, PermissionError):

            file_hash = ""

    try:

        stat_result = file_path.stat()

        source_metadata = _bulk_path_source_metadata(file_path, stat_result)

        file_size = int(stat_result.st_size)

    except (OSError, PermissionError):

        source_metadata = {"source_path": str(file_path)}

        file_size = None



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})



        now_iso = _bulk_utc_now_iso()

        try:

            connection.execute(

                """

                INSERT INTO working_items (

                    working_group_id, file_path, item_role, created_at, updated_at,

                    file_hash, file_size, source_metadata_json

                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                """,

                (

                    group_id,

                    str(file_path),

                    item_role,

                    now_iso,

                    now_iso,

                    file_hash or None,

                    file_size,

                    json.dumps(source_metadata),

                ),

            )

        except sqlite3.IntegrityError as exc:

            return JSONResponse(status_code=409, content={"success": False, "error": "duplicate_or_conflict", "message": str(exc)})



        if item_role == "primary":

            connection.execute(

                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",

                (str(file_path), now_iso, group_id),

            )

        connection.commit()

        refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}

    finally:

        connection.close()





@router.delete("/api/working-groups/{group_id}/items/{item_id}")

def remove_working_group_item(request: Request, group_id: int, item_id: int) -> Any:

    """Remove an item from a working group."""

    state: AppState = request.request.app.state.model_catalog

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        item_row = connection.execute(

            "SELECT id, file_path FROM working_items WHERE id = ? AND working_group_id = ?",

            (item_id, group_id),

        ).fetchone()

        if item_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working item not found"})

        connection.execute("DELETE FROM working_items WHERE id = ?", (item_id,))

        if str(group_row["primary_file_path"] or "") == str(item_row["file_path"] or ""):

            replacement = connection.execute(

                "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",

                (group_id,),

            ).fetchone()

            connection.execute(

                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",

                ((replacement["file_path"] if replacement else None), _bulk_utc_now_iso(), group_id),

            )

        connection.commit()

        refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}

    finally:

        connection.close()





# ==================== ENDPOINTS: MODEL LINKS ====================





@router.post("/api/working-groups/{group_id}/links")

def create_working_group_link(request: Request, group_id: int, payload: dict[str, Any]) -> Any:

    """Create or update a link from working group to model."""

    state: AppState = request.request.app.state.model_catalog

    model_ref = str(payload.get("model_ref") or "").strip()

    if not model_ref:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "model_ref is required"})

    link_role = str(payload.get("link_role") or "related").strip().lower() or "related"

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    now_iso = _bulk_utc_now_iso()



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        try:

            connection.execute(

                """

                INSERT INTO working_group_model_links (

                    working_group_id, model_ref, link_role, link_metadata_json, created_at, updated_at

                ) VALUES (?, ?, ?, ?, ?, ?)

                """,

                (group_id, model_ref, link_role, json.dumps(metadata), now_iso, now_iso),

            )

        except sqlite3.IntegrityError:

            connection.execute(

                """

                UPDATE working_group_model_links

                SET link_role = ?, link_metadata_json = ?, updated_at = ?

                WHERE working_group_id = ? AND model_ref = ?

                """,

                (link_role, json.dumps(metadata), now_iso, group_id, model_ref),

            )

        connection.commit()

        refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}

    finally:

        connection.close()





@router.get("/api/working-groups/{group_id}/links")

def list_working_group_links(request: Request, group_id: int) -> Any:

    """List model links for a working group."""

    state: AppState = request.request.app.state.model_catalog

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        link_rows = connection.execute(

            "SELECT * FROM working_group_model_links WHERE working_group_id = ? ORDER BY id ASC",

            (group_id,),

        ).fetchall()

        return {

            "success": True,

            "working_group_id": group_id,

            "links": [

                {

                    "id": int(row["id"]),

                    "model_ref": row["model_ref"],

                    "link_role": row["link_role"],

                    "metadata": json.loads(str(row["link_metadata_json"] or "{}")),

                    "created_at": row["created_at"],

                    "updated_at": row["updated_at"],

                }

                for row in link_rows

            ],

        }

    finally:

        connection.close()





@router.delete("/api/working-groups/{group_id}/links/{link_id}")

def delete_working_group_link(request: Request, group_id: int, link_id: int) -> Any:

    """Delete a model link from a working group."""

    state: AppState = request.request.app.state.model_catalog

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        link_row = connection.execute(

            "SELECT id FROM working_group_model_links WHERE id = ? AND working_group_id = ?",

            (link_id, group_id),

        ).fetchone()

        if link_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working-group link not found"})

        connection.execute("DELETE FROM working_group_model_links WHERE id = ?", (link_id,))

        connection.commit()

        refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}

    finally:

        connection.close()





# ==================== ENDPOINTS: MODEL QUERIES ====================





@router.get("/api/models/{model_ref:path}/working-groups")

def list_working_groups_for_model(request: Request, model_ref: str) -> Any:

    """Get all working groups linked to a model."""

    state: AppState = request.request.app.state.model_catalog

    normalized_ref = str(model_ref or "").strip()

    if not normalized_ref:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_model_ref", "message": "model_ref is required"})

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_rows = connection.execute(

            """

            SELECT g.*

            FROM working_groups g

            JOIN working_group_model_links l ON l.working_group_id = g.id

            WHERE l.model_ref = ?

            ORDER BY g.updated_at DESC, g.id DESC

            """,

            (normalized_ref,),

        ).fetchall()

        groups = [_serialize_working_group(connection, row, state.settings) for row in group_rows]

        return {

            "success": True,

            "model_ref": normalized_ref,

            "group_count": len(groups),

            "groups": groups,

        }

    finally:

        connection.close()





# ==================== ENDPOINTS: PUBLISHING ====================





@router.post("/api/working-groups/{group_id}/publish-to-local")

def publish_working_group_to_local(request: Request, group_id: int, payload: dict[str, Any] | None = None) -> Any:

    """Publish a working group to a local model."""

    state: AppState = request.request.app.state.model_catalog

    payload = payload or {}

    publish_outcome = str(payload.get("publish_outcome") or "").strip().lower()

    valid_outcomes = {

        "new_canonical_revision",

        "add_as_additional_file_or_variant",

        "keep_separate_curated_model",

        "cancel_for_cleanup",

    }

    if publish_outcome not in valid_outcomes:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_publish_outcome", "message": "publish_outcome is required and must be a supported value"})

    if publish_outcome == "cancel_for_cleanup":

        return {"success": True, "cancelled": True, "publish_outcome": publish_outcome, "working_group_id": group_id}



    lineage_type = str(payload.get("lineage_type") or "").strip().lower() or None

    if lineage_type and lineage_type not in {"canonical_revision", "supersedes", "superseded_by", "additional_variant", "separate_related"}:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_lineage_type", "message": "Unsupported lineage_type"})



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()

        if group_row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        item_rows = connection.execute(

            "SELECT * FROM working_items WHERE working_group_id = ? ORDER BY id ASC",

            (group_id,),

        ).fetchall()

        if not item_rows:

            return JSONResponse(status_code=400, content={"success": False, "error": "no_items", "message": "Working group has no files to publish"})



        now_iso = _bulk_utc_now_iso()

        try:

            resolved_project_id, created_project = _resolve_publish_project(connection, payload=payload, group_row=group_row, now_iso=now_iso)

        except ValueError as exc:

            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_project", "message": str(exc)})

        except LookupError as exc:

            return JSONResponse(status_code=404, content={"success": False, "error": "project_not_found", "message": str(exc)})



        target_model_ref = str(payload.get("target_model_ref") or payload.get("local_model_id") or "").strip() or None

        model_name = str(payload.get("model_name") or "").strip() or str(group_row["title"] or f"group-{group_id}")

        if not target_model_ref or publish_outcome == "keep_separate_curated_model":

            target_model_ref = _ensure_unique_local_model_id(db_path=state.settings.db_path, preferred=model_name)



        requested_description = str(payload.get("description") or "").strip() or None

        requested_tags = payload.get("tags") if isinstance(payload.get("tags"), list) else None

        requested_collection_names = payload.get("collection_names") if isinstance(payload.get("collection_names"), list) else None



        target_entry = read_local_model(db_path=state.settings.db_path, local_model_id=target_model_ref)

        created_model = False

        if target_entry is None:

            target_entry = create_local_model(

                db_path=state.settings.db_path,

                local_model_id=target_model_ref,

                model_name=model_name,

                model_description=requested_description,

                created_by="working_group_publish",

                collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,

                tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,

                keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,

                source_origin="working_group_publish",

                source_origin_url=f"working-group://{group_id}",

            )

            created_model = True

        else:

            target_entry = update_local_model(

                db_path=state.settings.db_path,

                local_model_id=target_model_ref,

                model_name=(model_name if payload.get("model_name") is not None else None),

                model_description=requested_description,

                collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,

                tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,

                keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,

            )



        if target_entry is None:

            return JSONResponse(status_code=500, content={"success": False, "error": "publish_failed", "message": "Could not create or update local model"})



        if resolved_project_id is not None and group_row["project_id"] != resolved_project_id:

            connection.execute(

                "UPDATE working_groups SET project_id = ?, updated_at = ? WHERE id = ?",

                (resolved_project_id, now_iso, group_id),

            )

        connection.commit()

    finally:

        connection.close()



    existing_assets = list_model_assets(db_path=state.settings.db_path, local_model_id=target_model_ref)

    existing_hashes = {

        str(getattr(asset, "file_hash", "") or "").strip().lower()

        for asset in existing_assets

        if str(getattr(asset, "file_hash", "") or "").strip()

    }

    existing_asset_ids = {

        str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))

        for asset in existing_assets

        if str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))

    }

    has_preview = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "preview" for asset in existing_assets)

    has_primary = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "primary" for asset in existing_assets)



    imported_assets: list[dict[str, Any]] = []

    duplicate_skipped: list[dict[str, Any]] = []

    failed_files: list[dict[str, Any]] = []



    for item_row in item_rows:

        source_path = Path(str(item_row["file_path"])).expanduser().resolve()

        if not source_path.exists() or not source_path.is_file():

            failed_files.append({"source_path": str(source_path), "message": "Source file not found"})

            continue

        file_hash = str(item_row["file_hash"] or "").strip().lower()

        if file_hash and file_hash in existing_hashes:

            duplicate_skipped.append({"source_path": str(source_path), "filename": source_path.name, "sha256": file_hash, "reason": "duplicate_hash"})

            continue

        try:

            storage_path = _copy_local_import_source(settings=state.settings, local_model_id=target_model_ref, source_path=source_path)

            asset_type = _normalize_local_asset_type(source_path)

            normalized_asset_role = _normalize_local_asset_role(

                asset_type=asset_type,

                has_preview=has_preview,

                has_primary=has_primary,

                preview_selected=False,

            )

            if str(item_row["item_role"] or "") == "primary" and not has_primary:

                normalized_asset_role = "primary"

            asset_id = _unique_asset_id(filename=source_path.name, file_hash=file_hash, existing_ids=existing_asset_ids)

            asset = create_model_asset(

                db_path=state.settings.db_path,

                local_model_id=target_model_ref,

                asset_id=asset_id,

                asset_filename=source_path.name,

                asset_type=asset_type,

                storage_path=storage_path,

                asset_role=normalized_asset_role,

                file_size_bytes=int(item_row["file_size"] or 0) or None,

                file_hash=file_hash or None,

                preview_url=None,

                geometry_bounds=None,

            )

            if file_hash:

                existing_hashes.add(file_hash)

            existing_asset_ids.add(asset.asset_id)

            has_preview = has_preview or asset.asset_role == "preview"

            has_primary = has_primary or asset.asset_role == "primary"

            imported_assets.append(

                {

                    "asset_id": asset.asset_id,

                    "filename": asset.asset_filename,

                    "asset_type": asset.asset_type,

                    "asset_role": asset.asset_role,

                    "storage_path": asset.storage_path,

                    "file_hash": asset.file_hash,

                    "source_path": str(source_path),

                }

            )

        except Exception as exc:

            failed_files.append({"source_path": str(source_path), "filename": source_path.name, "message": str(exc)})



    lineage_payload = {

        "lineage_type": lineage_type,

        "target_model_ref": str(payload.get("target_model_ref") or "").strip() or None,

        "reconciliation_notes": str(payload.get("reconciliation_notes") or "").strip() or None,

    }

    set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="project_id", field_value=resolved_project_id)

    set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="published_from_group_id", field_value=group_id)

    set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="publish_outcome", field_value=publish_outcome)

    set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="lineage", field_value=lineage_payload)

    publish_history = _append_intake_publish_history(

        db_path=state.settings.db_path,

        model_ref=target_model_ref,

        entry={

            "published_at": _bulk_utc_now_iso(),

            "source": "working_group_publish",

            "working_group_id": group_id,

            "publish_outcome": publish_outcome,

            "project_id": resolved_project_id,

            "created_model": created_model,

            "imported_asset_count": len(imported_assets),

            "duplicate_skipped_count": len(duplicate_skipped),

            "failed_file_count": len(failed_files),

        },

    )



    return {

        "success": True,

        "working_group_id": group_id,

        "model_ref": target_model_ref,

        "publish_outcome": publish_outcome,

        "project_id": resolved_project_id,

        "created_project": created_project,

        "created_model": created_model,

        "published_from_group_id": group_id,

        "lineage": lineage_payload,

        "imported_assets": imported_assets,

        "duplicate_skipped": duplicate_skipped,

        "failed_files": failed_files,

        "publish_history": publish_history,

    }





@router.get("/api/models/{model_ref:path}/lineage")

def get_model_lineage(request: Request, model_ref: str) -> Any:

    """Get model lineage/publish history."""

    state: AppState = request.request.app.state.model_catalog

    normalized_ref = str(model_ref or "").strip()

    if not normalized_ref:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_model_ref", "message": "model_ref is required"})

    return {"success": True, **_lineage_payload_for_model(db_path=state.settings.db_path, model_ref=normalized_ref)}





# ==================== ENDPOINTS: PROJECTS ====================





@router.post("/api/projects")

def create_model_catalog_project(request: Request, payload: dict[str, Any]) -> Any:

    """Create a new model catalog project."""

    state: AppState = request.request.app.state.model_catalog

    title = str(payload.get("title") or "").strip()

    if not title:

        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "title is required"})



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        project = _create_project_record(

            connection,

            title=title,

            description=str(payload.get("description") or "").strip() or None,

            notes=str(payload.get("notes") or "").strip() or None,

            bambuddy_project_id=_resolve_project_id_value(payload.get("bambuddy_project_id")),

            now_iso=_bulk_utc_now_iso(),

        )

        connection.commit()

        return {"success": True, "project": project}

    finally:

        connection.close()





@router.get("/api/projects")

def list_model_catalog_projects(request: Request, limit: int | None = None, offset: int | None = None) -> Any:

    """List model catalog projects."""

    state: AppState = request.request.app.state.model_catalog

    limit_value = max(1, min(int(limit or 100), 500))

    offset_value = max(0, int(offset or 0))



    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        total_row = connection.execute(

            "SELECT COUNT(*) AS cnt FROM model_catalog_projects WHERE archived_at IS NULL"

        ).fetchone()

        rows = connection.execute(

            """

            SELECT * FROM model_catalog_projects

            WHERE archived_at IS NULL

            ORDER BY updated_at DESC, id DESC

            LIMIT ? OFFSET ?

            """,

            (limit_value, offset_value),

        ).fetchall()

        projects = [_serialize_project_row(row) for row in rows]

    finally:

        connection.close()



    return {

        "success": True,

        "pagination": {

            "limit": limit_value,

            "offset": offset_value,

            "total": int(total_row["cnt"] if total_row else 0),

        },

        "projects": projects,

    }





@router.get("/api/projects/{project_id}")

def get_model_catalog_project(request: Request, project_id: int) -> Any:

    """Get a single project with group and model counts."""

    state: AppState = request.request.app.state.model_catalog

    connection = connect(state.settings.db_path)

    connection.row_factory = sqlite3.Row

    try:

        row = connection.execute(

            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",

            (project_id,),

        ).fetchone()

        if row is None:

            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Project not found"})

        group_count_row = connection.execute(

            "SELECT COUNT(*) AS cnt FROM working_groups WHERE project_id = ?",

            (project_id,),

        ).fetchone()

        model_count_row = connection.execute(

            """

            SELECT COUNT(*) AS cnt

            FROM model_catalog_custom_fields

            WHERE entity_type = 'model'

              AND field_key = 'project_id'

              AND json_extract(field_value_json, '$') = ?

            """,

            (project_id,),

        ).fetchone()

        project = _serialize_project_row(row)

        project["working_group_count"] = int(group_count_row["cnt"] if group_count_row else 0)

        project["curated_model_count"] = int(model_count_row["cnt"] if model_count_row else 0)

        return {"success": True, "project": project}

    finally:

        connection.close()





# ==================== ENDPOINTS: BULK OPERATIONS ====================





@router.post("/working-groups/bulk-discover")

@router.post("/api/working-groups/bulk-discover")

def bulk_discover_working_groups(request: Request, payload: dict[str, Any]) -> Any:

    """Scan folder and propose working groups."""

    state: AppState = request.request.app.state.model_catalog

    root_input = str(payload.get("folder_path") or payload.get("root_path") or "").strip()

    if not root_input:

        return JSONResponse(

            status_code=400,

            content={

                "success": False,

                "error": "invalid_payload",

                "message": "folder_path is required",

            },

        )



    grouping_strategy = _normalize_grouping_strategy(payload.get("grouping_strategy"))

    max_depth = _coerce_int(payload.get("max_depth"))

    if max_depth is not None and max_depth < 0:

        max_depth = 0



    root_path = Path(root_input).expanduser().resolve()

    if not root_path.exists() or not root_path.is_dir():

        return JSONResponse(

            status_code=400,

            content={

                "success": False,

                "error": "invalid_folder_path",

                "message": "folder_path must be an existing directory",

                "folder_path": root_input,

            },

        )



    existing_hashes = get_all_indexed_file_hashes(state.settings.db_path)

    now_iso = _bulk_utc_now_iso()



    proposals_by_key: dict[str, dict[str, Any]] = {}

    warnings: list[dict[str, Any]] = []

    scanned_file_count = 0

    supported_file_count = 0

    duplicate_warning_count = 0



    def _on_walk_error(error: OSError) -> None:

        warning = {

            "type": "walk_error",

            "path": str(getattr(error, "filename", root_path)),

            "message": str(error),

        }

        warnings.append(warning)



    for current_root, dirnames, filenames in os.walk(root_path, topdown=True, onerror=_on_walk_error):

        dirnames.sort()

        filenames.sort()

        current_dir = Path(current_root)



        if max_depth is not None:

            try:

                current_depth = len(current_dir.relative_to(root_path).parts)

            except ValueError:

                current_depth = 0

            if current_depth >= max_depth:

                dirnames[:] = []



        for filename in filenames:

            file_path = current_dir / filename

            scanned_file_count += 1



            if max_depth is not None:

                relative_parts = file_path.relative_to(root_path).parts

                if len(relative_parts) - 1 > max_depth:

                    continue



            suffix = file_path.suffix.lower()

            if suffix not in SUPPORTED_BULK_MODEL_EXTENSIONS:

                continue



            supported_file_count += 1

            group_key = _bulk_group_key(root_path, file_path, grouping_strategy)

            title = _bulk_group_title(root_path, group_key, file_path, grouping_strategy)

            proposal = proposals_by_key.get(group_key)

            if proposal is None:

                proposal = {

                    "proposal_id": _slugify_title(group_key if grouping_strategy == "flat" else title),

                    "group_key": group_key,

                    "title": title,

                    "action": "import",

                    "files": [],

                    "warnings": [],

                }

                proposals_by_key[group_key] = proposal



            try:

                stat_result = file_path.stat()

                source_metadata = _bulk_path_source_metadata(file_path, stat_result)

                file_hash = _sha256_file(file_path)

                file_size = int(stat_result.st_size)

            except (OSError, PermissionError) as error:

                warning = {

                    "type": "read_error",

                    "path": str(file_path),

                    "message": str(error),

                }

                proposal["warnings"].append(warning)

                warnings.append(warning)

                continue



            hash_exists = file_hash.lower() in existing_hashes

            if hash_exists:

                duplicate_warning_count += 1

                warning = {

                    "type": "duplicate_hash",

                    "path": str(file_path),

                    "sha256": file_hash,

                    "message": "Hash already exists in working items",

                }

                proposal["warnings"].append(warning)

                warnings.append(warning)



            proposal["files"].append(

                {

                    "path": str(file_path),

                    "relative_path": str(file_path.relative_to(root_path)),

                    "filename": file_path.name,

                    "size_bytes": file_size,

                    "sha256": file_hash,

                    "duplicate_hash": hash_exists,

                    "source_mtime": source_metadata["source_mtime"],

                    "source_ctime": source_metadata["source_ctime"],

                    "source_birthtime": source_metadata.get("source_birthtime"),

                }

            )



    proposals = sorted(

        proposals_by_key.values(),

        key=lambda item: str(item.get("title") or "").lower(),

    )

    for proposal in proposals:

        proposal["file_count"] = len(proposal["files"])

        proposal["duplicate_count"] = sum(1 for file in proposal["files"] if file.get("duplicate_hash"))

        proposal["discovery"] = {

            "source_folder": str(root_path),

            "strategy": grouping_strategy,

            "timestamp": now_iso,

        }



    return {

        "success": True,

        "contract": "working-group-bulk-discover.v1alpha1",

        "source_folder": str(root_path),

        "grouping_strategy": grouping_strategy,

        "discovered_at": now_iso,

        "summary": {

            "scanned_file_count": scanned_file_count,

            "supported_file_count": supported_file_count,

            "proposal_count": len(proposals),

            "duplicate_warning_count": duplicate_warning_count,

            "warning_count": len(warnings),

        },

        "proposals": proposals,

        "warnings": warnings,

    }





@router.post("/working-groups/bulk-import")

@router.post("/api/working-groups/bulk-import")

def bulk_import_working_groups(request: Request, payload: dict[str, Any]) -> Any:

    """Import bulk discover proposals as working groups."""

    state: AppState = request.request.app.state.model_catalog

    proposals_payload = payload.get("proposals")

    if not isinstance(proposals_payload, list) or not proposals_payload:

        return JSONResponse(

            status_code=400,

            content={

                "success": False,

                "error": "invalid_payload",

                "message": "proposals must be a non-empty list",

            },

        )



    source_folder = str(payload.get("source_folder") or payload.get("folder_path") or payload.get("root_path") or "").strip()

    grouping_strategy = _normalize_grouping_strategy(payload.get("grouping_strategy"))

    discovery_timestamp = str(payload.get("discovered_at") or payload.get("discovery_timestamp") or "").strip() or _bulk_utc_now_iso()

    import_timestamp = _bulk_utc_now_iso()

    default_stage = str(payload.get("stage") or "draft").strip() or "draft"



    grouped_imports: dict[str, dict[str, Any]] = {}

    skipped_groups: list[dict[str, Any]] = []

    for proposal in proposals_payload:

        if not isinstance(proposal, dict):

            continue

        action = str(proposal.get("action") or "import").strip().lower()

        title = str(proposal.get("title") or "").strip()

        proposal_id = str(proposal.get("proposal_id") or "").strip() or _slugify_title(title or "proposal")

        files = proposal.get("files") if isinstance(proposal.get("files"), list) else []

        if action == "skip":

            skipped_groups.append(

                {

                    "proposal_id": proposal_id,

                    "title": title,

                    "reason": "skipped_by_operator",

                }

            )

            continue



        target_group_key = str(proposal.get("merge_target") or proposal_id).strip() if action == "merge" else proposal_id

        if not target_group_key:

            target_group_key = proposal_id

        aggregate = grouped_imports.get(target_group_key)

        if aggregate is None:

            aggregate = {

                "title": title or target_group_key,

                "stage": str(proposal.get("stage") or default_stage).strip() or default_stage,

                "notes": str(proposal.get("notes") or "").strip() or None,

                "proposal_ids": [],

                "files": [],

            }

            grouped_imports[target_group_key] = aggregate

        aggregate["proposal_ids"].append(proposal_id)

        if title and not aggregate.get("title"):

            aggregate["title"] = title

        aggregate["files"].extend(files)



    if not grouped_imports:

        return {

            "success": True,

            "contract": "working-group-bulk-import.v1alpha1",

            "created_group_count": 0,

            "created_item_count": 0,

            "duplicate_skipped_count": 0,

            "skipped_groups": skipped_groups,

            "created_groups": [],

        }



    connection = connect(state.settings.db_path)

    connection.row_factory = None

    existing_hashes = get_all_indexed_file_hashes(state.settings.db_path)

    batch_hashes: set[str] = set()

    created_groups: list[dict[str, Any]] = []

    duplicate_skipped: list[dict[str, Any]] = []

    failed_files: list[dict[str, Any]] = []

    created_item_count = 0



    try:

        for group_key, grouped in grouped_imports.items():

            unique_files: list[dict[str, Any]] = []

            for file_payload in grouped["files"]:

                file_path_raw = str((file_payload or {}).get("path") or "").strip()

                if not file_path_raw:

                    continue

                file_path = Path(file_path_raw).expanduser().resolve()

                if not file_path.exists() or not file_path.is_file():

                    failed_files.append(

                        {

                            "group": grouped.get("title") or group_key,

                            "path": str(file_path),

                            "reason": "missing_source",

                        }

                    )

                    continue



                try:

                    stat_result = file_path.stat()

                    source_metadata = _bulk_path_source_metadata(file_path, stat_result)

                except (OSError, PermissionError) as error:

                    failed_files.append(

                        {

                            "group": grouped.get("title") or group_key,

                            "path": str(file_path),

                            "reason": "stat_error",

                            "message": str(error),

                        }

                    )

                    continue



                file_hash = str((file_payload or {}).get("sha256") or "").strip().lower()

                if not file_hash:

                    try:

                        file_hash = _sha256_file(file_path).lower()

                    except (OSError, PermissionError) as error:

                        failed_files.append(

                            {

                                "group": grouped.get("title") or group_key,

                                "path": str(file_path),

                                "reason": "read_error",

                                "message": str(error),

                            }

                        )

                        continue



                if file_hash in existing_hashes or file_hash in batch_hashes:

                    duplicate_skipped.append(

                        {

                            "group": grouped.get("title") or group_key,

                            "path": str(file_path),

                            "sha256": file_hash,

                            "reason": "duplicate_hash",

                        }

                    )

                    continue



                unique_files.append(

                    {

                        "path": str(file_path),

                        "sha256": file_hash,

                        "size_bytes": int(file_payload.get("size_bytes") or stat_result.st_size),

                        "relative_path": str(file_payload.get("relative_path") or file_path.name),

                        "source_mtime": str(file_payload.get("source_mtime") or source_metadata["source_mtime"]),

                        "source_ctime": str(file_payload.get("source_ctime") or source_metadata["source_ctime"]),

                        "source_birthtime": str(file_payload.get("source_birthtime") or source_metadata.get("source_birthtime") or "") or None,

                    }

                )

                batch_hashes.add(file_hash)



            if not unique_files:

                skipped_groups.append(

                    {

                        "proposal_id": group_key,

                        "title": grouped.get("title") or group_key,

                        "reason": "all_files_skipped_or_duplicate",

                    }

                )

                continue



            group_title = str(grouped.get("title") or group_key).strip() or group_key

            slug = _unique_slug(connection, group_title)

            now_iso = _bulk_utc_now_iso()

            metadata_json = json.dumps(

                {

                    "proposal_ids": grouped.get("proposal_ids") or [],

                    "imported_at": import_timestamp,

                }

            )



            connection.execute(

                """

                INSERT INTO working_groups (

                    slug,

                    title,

                    stage,

                    notes,

                    primary_file_path,

                    folder_hint,

                    related_manyfold_model_id,

                    created_at,

                    updated_at,

                    discovery_source_folder,

                    discovery_strategy,

                    discovery_timestamp,

                    discovery_metadata_json

                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                """,

                (

                    slug,

                    group_title,

                    grouped.get("stage") or default_stage,

                    grouped.get("notes"),

                    unique_files[0]["path"],

                    source_folder or None,

                    None,

                    now_iso,

                    now_iso,

                    source_folder or None,

                    grouping_strategy,

                    discovery_timestamp,

                    metadata_json,

                ),

            )

            group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])



            created_files: list[dict[str, Any]] = []

            for index, file_item in enumerate(unique_files):

                role = "primary" if index == 0 else "supporting"

                connection.execute(

                    """

                    INSERT INTO working_items (

                        working_group_id,

                        file_path,

                        item_role,

                        created_at,

                        updated_at,

                        file_hash,

                        file_size,

                        source_metadata_json

                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                    """,

                    (

                        group_id,

                        file_item["path"],

                        role,

                        now_iso,

                        now_iso,

                        file_item["sha256"],

                        file_item["size_bytes"],

                        json.dumps(

                            {

                                "relative_path": file_item["relative_path"],

                                "source_path": file_item["path"],

                                "source_size_bytes": file_item["size_bytes"],

                                "source_mtime": file_item["source_mtime"],

                                "source_ctime": file_item["source_ctime"],

                                "source_birthtime": file_item.get("source_birthtime"),

                            }

                        ),

                    ),

                )

                existing_hashes.add(file_item["sha256"])

                batch_hashes.add(file_item["sha256"])

                created_item_count += 1

                created_files.append(file_item)



            created_groups.append(

                {

                    "working_group_id": group_id,

                    "slug": slug,

                    "title": group_title,

                    "stage": grouped.get("stage") or default_stage,

                    "file_count": len(created_files),

                    "files": created_files,

                    "discovery": {

                        "source_folder": source_folder or None,

                        "strategy": grouping_strategy,

                        "timestamp": discovery_timestamp,

                    },

                }

            )



        connection.commit()

    finally:

        connection.close()



    return {

        "success": True,

        "contract": "working-group-bulk-import.v1alpha1",

        "created_group_count": len(created_groups),

        "created_item_count": created_item_count,

        "duplicate_skipped_count": len(duplicate_skipped),

        "failed_file_count": len(failed_files),

        "created_groups": created_groups,

        "duplicate_skipped": duplicate_skipped,

        "failed_files": failed_files,

        "skipped_groups": skipped_groups,

        "meta": {

            "source_folder": source_folder or None,

            "grouping_strategy": grouping_strategy,

            "discovery_timestamp": discovery_timestamp,

            "import_timestamp": import_timestamp,

        },

    }
