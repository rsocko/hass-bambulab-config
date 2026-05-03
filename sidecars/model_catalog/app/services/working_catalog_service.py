from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi.responses import JSONResponse

from .._helpers import (
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _configured_intake_source_roots,
    _configured_working_files_roots,
    _dedupe_paths,
    _is_path_within_roots,
    _model_photo_storage_root,
)
from ..db import read_model_field, read_model_fields, set_model_field
from ..local_models import (
    create_local_model,
    create_model_asset,
    list_model_assets,
    read_local_model,
    update_local_model,
)
from ..settings import Settings
from .shared_helpers import _serialize_project_row, _serialize_working_group, _sha256_file, _slugify_title

LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
LOCAL_IMPORT_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"}
LOCAL_IMPORT_DOCUMENT_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json", ".yaml", ".yml"}


def _normalize_path_compare_key(path_value: str | Path | None) -> str:
    return str(path_value or "").replace("\\", "/").lower()


def _working_group_allowed_source_roots(settings: Settings) -> list[Path]:
    return _dedupe_paths(_configured_intake_source_roots(settings) + _configured_working_files_roots(settings))


def _resolve_project_id_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


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


def _unique_project_slug(connection: Any, title: str) -> str:
    base = _slugify_title(title) or "project"
    candidate = base
    suffix = 2
    rows = connection.execute("SELECT slug FROM model_catalog_projects").fetchall()
    existing = {str(row["slug"]) for row in rows}
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _unique_destination_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        next_candidate = directory / f"{stem}-{counter}{suffix}"
        if not next_candidate.exists():
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


def _ensure_unique_local_model_id(*, db_path: Path, preferred: str) -> str:
    base_slug = _slugify_title(preferred) or "local-model"
    candidate = base_slug
    suffix = 2
    while read_local_model(db_path=db_path, local_model_id=candidate) is not None:
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


def _create_project_record(
    connection: Any,
    *,
    title: str,
    description: str | None,
    notes: str | None,
    bambuddy_project_id: int | None,
    now_iso: str,
) -> dict[str, Any]:
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


def _append_intake_publish_history(*, db_path: Path, model_ref: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    existing = read_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history")
    history = existing if isinstance(existing, list) else []
    history.append(entry)
    trimmed = history[-20:]
    set_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history", field_value=trimmed)
    return trimmed


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


def create_working_group_service(*, settings: Settings, payload: dict[str, Any]) -> Any:
    title = str(payload.get("title") or "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "title is required"})

    stage = str(payload.get("stage") or "draft").strip() or "draft"
    notes = str(payload.get("notes") or "").strip() or None
    folder_hint = str(payload.get("folder_hint") or "").strip() or None
    primary_file_path = str(payload.get("primary_file_path") or "").strip() or None
    project_id = _resolve_project_id_value(payload.get("project_id"))
    now_iso = _bulk_utc_now_iso()

    connection = connect(settings.db_path)
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
        return {"success": True, "group": _serialize_working_group(connection, row, settings)}
    finally:
        connection.close()


def list_working_groups_service(*, settings: Settings, limit: int | None, offset: int | None, stage: str | None, project_id: int | None) -> dict[str, Any]:
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

    connection = connect(settings.db_path)
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
        groups = [_serialize_working_group(connection, row, settings) for row in rows]
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


def get_working_group_service(*, settings: Settings, group_id: int) -> Any:
    connection = connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
        return {"success": True, "group": _serialize_working_group(connection, row, settings)}
    finally:
        connection.close()


def update_working_group_service(*, settings: Settings, group_id: int, payload: dict[str, Any]) -> Any:
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

    connection = connect(settings.db_path)
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
        return {"success": True, "group": _serialize_working_group(connection, row, settings)}
    finally:
        connection.close()


def delete_working_group_service(*, settings: Settings, group_id: int) -> Any:
    connection = connect(settings.db_path)
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


def add_working_group_item_service(*, settings: Settings, group_id: int, payload: dict[str, Any]) -> Any:
    file_path_raw = str(payload.get("file_path") or "").strip()
    if not file_path_raw:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_path is required"})
    file_path = Path(file_path_raw).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse(status_code=400, content={"success": False, "error": "missing_source", "message": f"file_path not found: {file_path_raw}"})
    allowed_roots = _working_group_allowed_source_roots(settings)
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

    connection = connect(settings.db_path)
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
        return {"success": True, "group": _serialize_working_group(connection, refreshed, settings)}
    finally:
        connection.close()


def remove_working_group_item_service(*, settings: Settings, group_id: int, item_id: int) -> Any:
    connection = connect(settings.db_path)
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
        return {"success": True, "group": _serialize_working_group(connection, refreshed, settings)}
    finally:
        connection.close()


def create_working_group_link_service(*, settings: Settings, group_id: int, payload: dict[str, Any]) -> Any:
    model_ref = str(payload.get("model_ref") or "").strip()
    if not model_ref:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "model_ref is required"})
    link_role = str(payload.get("link_role") or "related").strip().lower() or "related"
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    now_iso = _bulk_utc_now_iso()

    connection = connect(settings.db_path)
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
        return {"success": True, "group": _serialize_working_group(connection, refreshed, settings)}
    finally:
        connection.close()


def list_working_group_links_service(*, settings: Settings, group_id: int) -> Any:
    connection = connect(settings.db_path)
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


def delete_working_group_link_service(*, settings: Settings, group_id: int, link_id: int) -> Any:
    connection = connect(settings.db_path)
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
        return {"success": True, "group": _serialize_working_group(connection, refreshed, settings)}
    finally:
        connection.close()


def list_working_groups_for_model_service(*, settings: Settings, model_ref: str) -> Any:
    normalized_ref = str(model_ref or "").strip()
    if not normalized_ref:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_model_ref", "message": "model_ref is required"})
    connection = connect(settings.db_path)
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
        groups = [_serialize_working_group(connection, row, settings) for row in group_rows]
        return {
            "success": True,
            "model_ref": normalized_ref,
            "group_count": len(groups),
            "groups": groups,
        }
    finally:
        connection.close()


def publish_working_group_to_local_service(*, settings: Settings, group_id: int, payload: dict[str, Any] | None = None) -> Any:
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

    connection = connect(settings.db_path)
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
            target_model_ref = _ensure_unique_local_model_id(db_path=settings.db_path, preferred=model_name)

        requested_description = str(payload.get("description") or "").strip() or None
        requested_tags = payload.get("tags") if isinstance(payload.get("tags"), list) else None
        requested_collection_names = payload.get("collection_names") if isinstance(payload.get("collection_names"), list) else None

        target_entry = read_local_model(db_path=settings.db_path, local_model_id=target_model_ref)
        created_model = False
        if target_entry is None:
            target_entry = create_local_model(
                db_path=settings.db_path,
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
                db_path=settings.db_path,
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

    existing_assets = list_model_assets(db_path=settings.db_path, local_model_id=target_model_ref)
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

    connection = connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        item_rows = connection.execute(
            "SELECT * FROM working_items WHERE working_group_id = ? ORDER BY id ASC",
            (group_id,),
        ).fetchall()
    finally:
        connection.close()

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
            storage_path = _copy_local_import_source(settings=settings, local_model_id=target_model_ref, source_path=source_path)
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
                db_path=settings.db_path,
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
    set_model_field(db_path=settings.db_path, model_ref=target_model_ref, field_key="project_id", field_value=resolved_project_id)
    set_model_field(db_path=settings.db_path, model_ref=target_model_ref, field_key="published_from_group_id", field_value=group_id)
    set_model_field(db_path=settings.db_path, model_ref=target_model_ref, field_key="publish_outcome", field_value=publish_outcome)
    set_model_field(db_path=settings.db_path, model_ref=target_model_ref, field_key="lineage", field_value=lineage_payload)
    publish_history = _append_intake_publish_history(
        db_path=settings.db_path,
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


def get_model_lineage_service(*, settings: Settings, model_ref: str) -> Any:
    normalized_ref = str(model_ref or "").strip()
    if not normalized_ref:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_model_ref", "message": "model_ref is required"})
    return {"success": True, **_lineage_payload_for_model(db_path=settings.db_path, model_ref=normalized_ref)}


def create_model_catalog_project_service(*, settings: Settings, payload: dict[str, Any]) -> Any:
    title = str(payload.get("title") or "").strip()
    if not title:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "title is required"})

    connection = connect(settings.db_path)
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


def list_model_catalog_projects_service(*, settings: Settings, limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    limit_value = max(1, min(int(limit or 100), 500))
    offset_value = max(0, int(offset or 0))

    connection = connect(settings.db_path)
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


def get_model_catalog_project_service(*, settings: Settings, project_id: int) -> Any:
    connection = connect(settings.db_path)
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
