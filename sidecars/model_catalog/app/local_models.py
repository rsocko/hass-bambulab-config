"""Local model catalog CRUD operations (Phase 1+).

This module handles local SQLite-based model storage and asset management,
replacing Manyfold-dependent read paths during Phase 1 transition.

Authority: Sidecar-owned local model authority.
Migration context: See Phase 1 Implementation Plan.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect, utc_now_iso
from .models import LocalModelEntry, ModelAsset


_UNSET = object()


def create_local_model(
    *,
    db_path: Path,
    local_model_id: str,
    model_name: str,
    model_description: str | None = None,
    creator_name: str | None = None,
    created_by: str | None = None,
    collection_names: list[str] | None = None,
    keyword_names: list[str] | None = None,
    tags: list[str] | None = None,
    license_type: str | None = None,
    preview_image_url: str | None = None,
    source_origin: str | None = None,
    source_origin_url: str | None = None,
    revision_hash: str | None = None,
    entity_type: str = "model",
) -> LocalModelEntry:
    """Create a new local model catalog entry."""
    connection = connect(db_path)
    try:
        now = utc_now_iso()
        connection.execute(
            """
            INSERT INTO model_catalog_entries (
                local_model_id, model_name, model_description, creator_name,
                created_by,
                collection_names_json, keyword_names_json, tags_json,
                license_type, preview_image_url,
                source_origin, source_origin_url, revision_hash,
                entity_type,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_model_id,
                model_name,
                model_description,
                creator_name,
                created_by,
                json.dumps(collection_names or []),
                json.dumps(keyword_names or []),
                json.dumps(tags or []),
                license_type,
                preview_image_url,
                source_origin,
                source_origin_url,
                revision_hash,
                entity_type,
                now,
                now,
            ),
        )
        connection.commit()
        entry = read_local_model(db_path=db_path, local_model_id=local_model_id)
        if entry is None:
            raise RuntimeError(f"Failed to create model {local_model_id}")
        return entry
    finally:
        connection.close()


def read_local_model(
    *,
    db_path: Path,
    local_model_id: str,
) -> LocalModelEntry | None:
    """Read a single local model entry (non-archived)."""
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT * FROM model_catalog_entries 
            WHERE local_model_id = ? AND archived_at IS NULL
            """,
            (local_model_id,),
        ).fetchone()
        if not row:
            return None
        return _row_to_local_model_entry(row)
    finally:
        connection.close()


def list_local_models(
    *,
    db_path: Path,
    limit: int = 50,
    offset: int = 0,
    search_query: str | None = None,
) -> tuple[list[LocalModelEntry], int]:
    """List local models with pagination and optional search.
    
    Args:
        db_path: Path to SQLite database
        limit: Max results to return
        offset: Pagination offset
        search_query: Optional search text (searched in name, description, tags)
    
    Returns:
        Tuple of (list of LocalModelEntry, total count)
    """
    connection = connect(db_path)
    try:
        where_clauses = ["archived_at IS NULL"]
        params: list[Any] = []

        if search_query and search_query.strip():
            search_term = f"%{search_query.strip()}%"
            where_clauses.append(
                "(model_name LIKE ? OR model_description LIKE ? OR tags_json LIKE ?)"
            )
            params.extend([search_term, search_term, search_term])

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_row = connection.execute(
            f"SELECT COUNT(*) as cnt FROM model_catalog_entries WHERE {where_sql}",
            params,
        ).fetchone()
        total = int(count_row["cnt"] if count_row else 0)

        # Get paginated results
        rows = connection.execute(
            f"""
            SELECT * FROM model_catalog_entries 
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        entries = [_row_to_local_model_entry(row) for row in rows]
        return entries, total
    finally:
        connection.close()


def update_local_model(
    *,
    db_path: Path,
    local_model_id: str,
    model_name: str | None = None,
    model_description: str | None = None,
    creator_name: str | None = None,
    created_by: str | None = None,
    tags: list[str] | None = None,
    keyword_names: list[str] | None = None,
    collection_names: list[str] | None = None,
    license_type: str | None = None,
    preview_image_url: str | None = None,
    source_origin: str | None = None,
    source_origin_url: str | None = None,
    revision_hash: str | None = None,
    entity_type: str | None = None,
) -> LocalModelEntry | None:
    """Update a local model entry (partial update).
    
    Only provided fields are updated; None values are skipped.
    Returns updated entry or None if not found.
    """
    connection = connect(db_path)
    try:
        # Check if model exists
        existing = connection.execute(
            "SELECT id FROM model_catalog_entries WHERE local_model_id = ? AND archived_at IS NULL",
            (local_model_id,),
        ).fetchone()

        if not existing:
            return None

        # Build update statement dynamically
        updates = []
        params = []

        if model_name is not None:
            updates.append("model_name = ?")
            params.append(model_name)
        if model_description is not None:
            updates.append("model_description = ?")
            params.append(model_description)
        if creator_name is not None:
            updates.append("creator_name = ?")
            params.append(creator_name)
        if created_by is not None:
            updates.append("created_by = ?")
            params.append(created_by)
        if tags is not None:
            updates.append("tags_json = ?")
            params.append(json.dumps(tags))
        if keyword_names is not None:
            updates.append("keyword_names_json = ?")
            params.append(json.dumps(keyword_names))
        if collection_names is not None:
            updates.append("collection_names_json = ?")
            params.append(json.dumps(collection_names))
        if license_type is not None:
            updates.append("license_type = ?")
            params.append(license_type)
        if preview_image_url is not None:
            updates.append("preview_image_url = ?")
            params.append(preview_image_url)
        if source_origin is not None:
            updates.append("source_origin = ?")
            params.append(source_origin)
        if source_origin_url is not None:
            updates.append("source_origin_url = ?")
            params.append(source_origin_url)
        if revision_hash is not None:
            updates.append("revision_hash = ?")
            params.append(revision_hash)
        if entity_type is not None:
            updates.append("entity_type = ?")
            params.append(entity_type)

        if not updates:
            # No updates requested, return current state
            return read_local_model(db_path=db_path, local_model_id=local_model_id)

        updates.append("updated_at = ?")
        params.append(utc_now_iso())
        params.append(local_model_id)

        update_sql = ", ".join(updates)
        connection.execute(
            f"UPDATE model_catalog_entries SET {update_sql} WHERE local_model_id = ?",
            params,
        )
        connection.commit()

        return read_local_model(db_path=db_path, local_model_id=local_model_id)
    finally:
        connection.close()


def delete_local_model(
    *,
    db_path: Path,
    local_model_id: str,
    hard_delete: bool = False,
) -> bool:
    """Soft-delete (archive) or hard-delete a model.
    
    Args:
        db_path: Path to SQLite database
        local_model_id: Model to delete
        hard_delete: If True, permanently remove; if False, set archived_at timestamp
    
    Returns:
        True if deleted, False if not found
    """
    connection = connect(db_path)
    try:
        if hard_delete:
            # Hard delete: remove all assets first, then model
            model_id_row = connection.execute(
                "SELECT id FROM model_catalog_entries WHERE local_model_id = ?",
                (local_model_id,),
            ).fetchone()

            if not model_id_row:
                return False

            model_id = model_id_row["id"]
            connection.execute(
                "DELETE FROM model_catalog_assets WHERE model_catalog_entry_id = ?",
                (model_id,),
            )
            connection.execute(
                "DELETE FROM model_catalog_entries WHERE local_model_id = ?",
                (local_model_id,),
            )
        else:
            # Soft delete: set archived_at
            cursor = connection.execute(
                "UPDATE model_catalog_entries SET archived_at = ? WHERE local_model_id = ? AND archived_at IS NULL",
                (utc_now_iso(), local_model_id),
            )
            if cursor.rowcount == 0:
                return False

        connection.commit()
        return True
    finally:
        connection.close()


def create_model_asset(
    *,
    db_path: Path,
    local_model_id: str,
    asset_id: str,
    asset_filename: str,
    asset_type: str,
    storage_path: str,
    asset_role: str = "primary",
    file_size_bytes: int | None = None,
    file_hash: str | None = None,
    preview_url: str | None = None,
    geometry_bounds: dict[str, Any] | None = None,
) -> ModelAsset:
    """Add a file/image asset to a model.
    
    Args:
        db_path: Path to SQLite database
        local_model_id: Parent model ID
        asset_id: Unique identifier for this asset within the model
        asset_filename: Filename (e.g., 'model.3mf', 'preview.jpg')
        asset_type: Asset type ('image', '3mf', 'stl', 'obj', 'pdf', etc.)
        storage_path: Absolute or relative path where file is stored
        asset_role: Role in model ('primary', 'supporting', 'preview', 'documentation')
        file_size_bytes: File size in bytes (optional)
        file_hash: SHA256 or similar hash (optional)
        preview_url: URL to thumbnail (optional)
        geometry_bounds: Bounding box for 3D models (optional)
    
    Returns:
        Created ModelAsset
    """
    connection = connect(db_path)
    try:
        # Get model ID
        model_id_row = connection.execute(
            "SELECT id FROM model_catalog_entries WHERE local_model_id = ? AND archived_at IS NULL",
            (local_model_id,),
        ).fetchone()

        if not model_id_row:
            raise ValueError(f"Model {local_model_id} not found")

        model_id = model_id_row["id"]
        now = utc_now_iso()
        sort_order_row = connection.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort_order FROM model_catalog_assets WHERE model_catalog_entry_id = ?",
            (model_id,),
        ).fetchone()
        sort_order = int(sort_order_row["next_sort_order"] if sort_order_row is not None else 0)

        connection.execute(
            """
            INSERT INTO model_catalog_assets (
                model_catalog_entry_id, asset_id, sort_order, asset_filename, asset_type, asset_role,
                file_size_bytes, file_hash, storage_path, preview_url, geometry_bounds_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_id,
                asset_id,
                sort_order,
                asset_filename,
                asset_type,
                asset_role,
                file_size_bytes,
                file_hash,
                storage_path,
                preview_url,
                json.dumps(geometry_bounds) if geometry_bounds else None,
                now,
                now,
            ),
        )
        connection.commit()

        asset = read_model_asset(db_path=db_path, local_model_id=local_model_id, asset_id=asset_id)
        if asset is None:
            raise RuntimeError(f"Failed to create asset {asset_id}")
        return asset
    finally:
        connection.close()


def read_model_asset(
    *,
    db_path: Path,
    local_model_id: str,
    asset_id: str,
) -> ModelAsset | None:
    """Read a single model asset."""
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT a.* FROM model_catalog_assets a
            JOIN model_catalog_entries e ON a.model_catalog_entry_id = e.id
            WHERE e.local_model_id = ? AND a.asset_id = ? AND e.archived_at IS NULL
            """,
            (local_model_id, asset_id),
        ).fetchone()

        if not row:
            return None
        return _row_to_model_asset(row)
    finally:
        connection.close()


def list_model_assets(
    *,
    db_path: Path,
    local_model_id: str,
    asset_type: str | None = None,
) -> list[ModelAsset]:
    """List all assets for a model (optionally filtered by type)."""
    connection = connect(db_path)
    try:
        where_clauses = ["e.local_model_id = ?", "e.archived_at IS NULL"]
        params: list[Any] = [local_model_id]

        if asset_type:
            where_clauses.append("a.asset_type = ?")
            params.append(asset_type)

        where_sql = " AND ".join(where_clauses)

        rows = connection.execute(
            f"""
            SELECT a.* FROM model_catalog_assets a
            JOIN model_catalog_entries e ON a.model_catalog_entry_id = e.id
            WHERE {where_sql}
            ORDER BY a.sort_order ASC, a.asset_role ASC, a.created_at ASC, a.asset_id ASC
            """,
            params,
        ).fetchall()

        return [_row_to_model_asset(row) for row in rows]
    finally:
        connection.close()


def update_model_asset(
    *,
    db_path: Path,
    local_model_id: str,
    asset_id: str,
    asset_filename: str | object = _UNSET,
    asset_type: str | object = _UNSET,
    storage_path: str | object = _UNSET,
    sort_order: int | object = _UNSET,
    asset_role: str | object = _UNSET,
    file_size_bytes: int | None | object = _UNSET,
    file_hash: str | None | object = _UNSET,
    preview_url: str | None | object = _UNSET,
    geometry_bounds: dict[str, Any] | None | object = _UNSET,
) -> ModelAsset | None:
    """Update mutable fields for a single model asset.

    Returns the updated asset, or None if the asset/model does not exist.
    """
    connection = connect(db_path)
    try:
        existing = connection.execute(
            """
            SELECT a.id FROM model_catalog_assets a
            JOIN model_catalog_entries e ON a.model_catalog_entry_id = e.id
            WHERE e.local_model_id = ? AND a.asset_id = ? AND e.archived_at IS NULL
            """,
            (local_model_id, asset_id),
        ).fetchone()

        if not existing:
            return None

        update_fields: list[str] = []
        params: list[Any] = []

        if asset_filename is not _UNSET:
            update_fields.append("asset_filename = ?")
            params.append(asset_filename)
        if asset_type is not _UNSET:
            update_fields.append("asset_type = ?")
            params.append(asset_type)
        if storage_path is not _UNSET:
            update_fields.append("storage_path = ?")
            params.append(storage_path)
        if sort_order is not _UNSET:
            update_fields.append("sort_order = ?")
            params.append(sort_order)
        if asset_role is not _UNSET:
            update_fields.append("asset_role = ?")
            params.append(asset_role)
        if file_size_bytes is not _UNSET:
            update_fields.append("file_size_bytes = ?")
            params.append(file_size_bytes)
        if file_hash is not _UNSET:
            update_fields.append("file_hash = ?")
            params.append(file_hash)
        if preview_url is not _UNSET:
            update_fields.append("preview_url = ?")
            params.append(preview_url)
        if geometry_bounds is not _UNSET:
            update_fields.append("geometry_bounds_json = ?")
            params.append(json.dumps(geometry_bounds) if geometry_bounds is not None else None)

        if not update_fields:
            return read_model_asset(db_path=db_path, local_model_id=local_model_id, asset_id=asset_id)

        update_fields.append("updated_at = ?")
        params.append(utc_now_iso())
        params.extend([local_model_id, asset_id])

        connection.execute(
            f"""
            UPDATE model_catalog_assets
            SET {', '.join(update_fields)}
            WHERE model_catalog_entry_id IN (
                SELECT id FROM model_catalog_entries
                WHERE local_model_id = ? AND archived_at IS NULL
            ) AND asset_id = ?
            """,
            params,
        )
        connection.commit()
    finally:
        connection.close()

    return read_model_asset(db_path=db_path, local_model_id=local_model_id, asset_id=asset_id)


def delete_model_asset(
    *,
    db_path: Path,
    local_model_id: str,
    asset_id: str,
) -> bool:
    """Delete a model asset."""
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            DELETE FROM model_catalog_assets
            WHERE asset_id = ? AND model_catalog_entry_id IN (
                SELECT id FROM model_catalog_entries 
                WHERE local_model_id = ? AND archived_at IS NULL
            )
            """,
            (asset_id, local_model_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def _row_to_local_model_entry(row: Any) -> LocalModelEntry:
    """Convert DB row to LocalModelEntry dataclass."""
    entity_type = "model"
    try:
        entity_type_raw = row["entity_type"]
    except Exception:
        entity_type_raw = "model"
    entity_type = str(entity_type_raw or "model")

    def _safe_json_list(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        raw = str(value).strip()
        if not raw:
            return ()
        try:
            parsed = json.loads(raw)
        except Exception:
            return ()
        if not isinstance(parsed, list):
            return ()
        normalized: list[str] = []
        for item in parsed:
            text = str(item or "").strip()
            if text:
                normalized.append(text)
        return tuple(normalized)

    return LocalModelEntry(
        id=int(row["id"]),
        local_model_id=str(row["local_model_id"]),
        model_name=str(row["model_name"]),
        model_description=row["model_description"],
        creator_name=row["creator_name"],
        created_by=row["created_by"],
        collection_names=_safe_json_list(row["collection_names_json"]),
        keyword_names=_safe_json_list(row["keyword_names_json"]),
        tags=_safe_json_list(row["tags_json"]),
        license_type=row["license_type"],
        preview_image_url=row["preview_image_url"],
        source_origin=row["source_origin"],
        source_origin_url=row["source_origin_url"],
        revision_hash=row["revision_hash"],
        entity_type=entity_type,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_model_asset(row: Any) -> ModelAsset:
    """Convert DB row to ModelAsset dataclass."""
    bounds_json = row["geometry_bounds_json"]
    try:
        bounds = json.loads(bounds_json) if bounds_json else None
    except Exception:
        bounds = None

    return ModelAsset(
        id=int(row["id"]),
        asset_id=str(row["asset_id"]),
        sort_order=int(row["sort_order"] or 0),
        asset_filename=str(row["asset_filename"]),
        asset_type=str(row["asset_type"]),
        asset_role=str(row["asset_role"]),
        file_size_bytes=row["file_size_bytes"],
        file_hash=row["file_hash"],
        storage_path=str(row["storage_path"]),
        preview_url=row["preview_url"],
        geometry_bounds=bounds,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
