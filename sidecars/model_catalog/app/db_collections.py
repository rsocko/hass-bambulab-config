from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .db_common import connect, utc_now_iso


COLLECTION_PATH_SEPARATOR = " / "
COLLECTION_PATH_SPLIT_RE = re.compile(r"\s*(?:/|>|::)\s*")
MAX_COLLECTION_DEPTH = 4


def _normalize_collection_name(value: object | None) -> str:
    name = " ".join(str(value or "").strip().split())
    if not name:
        raise ValueError("collection name is required")
    return name


def _split_collection_path(value: object | None) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return tuple()
    return tuple(
        segment.strip()
        for segment in COLLECTION_PATH_SPLIT_RE.split(raw)
        if str(segment or "").strip()
    )


def _join_collection_id(parts: tuple[str, ...]) -> str:
    return COLLECTION_PATH_SEPARATOR.join(part.strip().lower() for part in parts if str(part or "").strip())


def _collection_depth(collection_id: str | None) -> int:
    normalized = str(collection_id or "").strip()
    if not normalized:
        return 0
    return len([segment for segment in normalized.split(COLLECTION_PATH_SEPARATOR) if segment])


def collection_display_path(collection_id: str | None, collection_rows_by_id: dict[str, dict[str, Any]]) -> str:
    normalized_id = str(collection_id or "").strip().lower()
    if not normalized_id:
        return ""
    current = collection_rows_by_id.get(normalized_id)
    if current is None:
        return normalized_id

    segments: list[str] = []
    visited: set[str] = set()
    while current is not None:
        current_id = str(current.get("collection_id") or "").strip().lower()
        if not current_id or current_id in visited:
            break
        visited.add(current_id)
        current_name = str(current.get("name") or "").strip()
        if current_name:
            segments.append(current_name)
        parent_id = str(current.get("parent_collection_id") or "").strip().lower()
        current = collection_rows_by_id.get(parent_id) if parent_id else None
    return COLLECTION_PATH_SEPARATOR.join(reversed(segments)) or normalized_id


def collection_paths_from_memberships(
    memberships: list[dict[str, Any]] | None,
    collection_rows_by_id: dict[str, dict[str, Any]],
) -> tuple[str, ...]:
    if not memberships:
        return tuple()
    ordered_names: list[str] = []
    seen: set[str] = set()
    for membership in memberships:
        collection_id = str(membership.get("collection_id") or "").strip().lower()
        if not collection_id or collection_id in seen:
            continue
        seen.add(collection_id)
        display_path = collection_display_path(collection_id, collection_rows_by_id)
        if display_path:
            ordered_names.append(display_path)
    return tuple(ordered_names)


def list_collections(*, db_path: Path) -> list[dict[str, Any]]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT collection_id, name, parent_collection_id, created_at, updated_at
            FROM model_catalog_collections
            ORDER BY collection_id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def read_collection(*, db_path: Path, collection_id: str) -> dict[str, Any] | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT collection_id, name, parent_collection_id, created_at, updated_at
            FROM model_catalog_collections
            WHERE collection_id = ?
            """,
            (str(collection_id or "").strip().lower(),),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def create_collection(*, db_path: Path, name: str, parent_collection_id: str | None = None) -> dict[str, Any]:
    normalized_name = _normalize_collection_name(name)
    parent_id = str(parent_collection_id or "").strip().lower() or None
    connection = connect(db_path)
    try:
        if parent_id:
            parent_row = connection.execute(
                "SELECT collection_id FROM model_catalog_collections WHERE collection_id = ?",
                (parent_id,),
            ).fetchone()
            if parent_row is None:
                raise ValueError(f"parent collection not found: {parent_id}")
        collection_id = _join_collection_id(
            tuple([segment for segment in (parent_id or "").split(COLLECTION_PATH_SEPARATOR) if segment] + [normalized_name])
        )
        if _collection_depth(collection_id) > MAX_COLLECTION_DEPTH:
            raise ValueError(f"collection depth exceeds max depth {MAX_COLLECTION_DEPTH}")
        now_iso = utc_now_iso()
        try:
            connection.execute(
                """
                INSERT INTO model_catalog_collections (
                    collection_id, name, parent_collection_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (collection_id, normalized_name, parent_id, now_iso, now_iso),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"collection path already exists: {collection_id}") from exc
        connection.commit()
        row = connection.execute(
            "SELECT collection_id, name, parent_collection_id, created_at, updated_at FROM model_catalog_collections WHERE collection_id = ?",
            (collection_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to read created collection")
        return dict(row)
    finally:
        connection.close()


def update_collection(
    *,
    db_path: Path,
    collection_id: str,
    name: str | None = None,
    parent_collection_id: str | None = None,
) -> dict[str, Any]:
    target_id = str(collection_id or "").strip().lower()
    if not target_id:
        raise ValueError("collection_id is required")
    connection = connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        rows = connection.execute(
            "SELECT collection_id, name, parent_collection_id, created_at, updated_at FROM model_catalog_collections ORDER BY collection_id ASC"
        ).fetchall()
        collection_map = {str(row["collection_id"]): dict(row) for row in rows}
        current = collection_map.get(target_id)
        if current is None:
            raise ValueError(f"collection not found: {target_id}")

        next_parent_id = str(parent_collection_id).strip().lower() if parent_collection_id is not None else str(current.get("parent_collection_id") or "").strip().lower()
        next_parent_id = next_parent_id or None
        if next_parent_id == target_id:
            raise ValueError("collection cannot parent itself")
        if next_parent_id and next_parent_id not in collection_map:
            raise ValueError(f"parent collection not found: {next_parent_id}")
        if next_parent_id and next_parent_id.startswith(target_id + COLLECTION_PATH_SEPARATOR):
            raise ValueError("collection move would create a cycle")

        next_name = _normalize_collection_name(name if name is not None else current.get("name"))
        next_id = _join_collection_id(
            tuple([segment for segment in (next_parent_id or "").split(COLLECTION_PATH_SEPARATOR) if segment] + [next_name])
        )
        if _collection_depth(next_id) > MAX_COLLECTION_DEPTH:
            raise ValueError(f"collection depth exceeds max depth {MAX_COLLECTION_DEPTH}")

        descendant_ids = [row_id for row_id in collection_map if row_id == target_id or row_id.startswith(target_id + COLLECTION_PATH_SEPARATOR)]
        replacement_pairs: list[tuple[str, str, str]] = []
        for row_id in sorted(descendant_ids, key=len, reverse=True):
            suffix = row_id[len(target_id):]
            replacement_id = next_id + suffix
            replacement_pairs.append((row_id, replacement_id, row_id))

        replacement_ids = {new_id for _old_id, new_id, _row_id in replacement_pairs}
        for existing_id in collection_map:
            if existing_id in descendant_ids:
                continue
            if existing_id in replacement_ids:
                raise ValueError(f"collection path already exists: {existing_id}")

        now_iso = utc_now_iso()
        for old_id, new_id, row_id in replacement_pairs:
            row = collection_map[row_id]
            parent_id = str(row.get("parent_collection_id") or "").strip().lower() or None
            if old_id == target_id:
                parent_id = next_parent_id
                row_name = next_name
            else:
                row_name = str(row.get("name") or "")
            connection.execute(
                """
                UPDATE model_catalog_collections
                SET collection_id = ?, name = ?, parent_collection_id = ?, updated_at = ?
                WHERE collection_id = ?
                """,
                (new_id, row_name, parent_id, now_iso, old_id),
            )
            connection.execute(
                """
                UPDATE model_catalog_collection_memberships
                SET collection_id = ?, updated_at = ?
                WHERE collection_id = ?
                """,
                (new_id, now_iso, old_id),
            )
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute(
            "SELECT collection_id, name, parent_collection_id, created_at, updated_at FROM model_catalog_collections WHERE collection_id = ?",
            (next_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to read updated collection")
        return dict(row)
    finally:
        try:
            connection.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        connection.close()


def read_model_collection_memberships_bulk(*, db_path: Path, model_refs: list[str]) -> dict[str, list[dict[str, Any]]]:
    normalized_refs = [str(model_ref or "").strip() for model_ref in model_refs if str(model_ref or "").strip()]
    if not normalized_refs:
        return {}
    placeholders = ", ".join(["?"] * len(normalized_refs))
    connection = connect(db_path)
    try:
        rows = connection.execute(
            f"""
            SELECT m.model_ref, c.collection_id, c.name, c.parent_collection_id, c.created_at, c.updated_at
            FROM model_catalog_collection_memberships m
            JOIN model_catalog_collections c ON c.collection_id = m.collection_id
            WHERE m.model_ref IN ({placeholders})
            ORDER BY c.collection_id ASC
            """,
            normalized_refs,
        ).fetchall()
    finally:
        connection.close()
    memberships: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        model_ref = str(row["model_ref"])
        memberships.setdefault(model_ref, []).append(dict(row))
    return memberships


def replace_model_collection_memberships(*, db_path: Path, model_ref: str, collection_ids: list[str]) -> list[dict[str, Any]]:
    normalized_model_ref = str(model_ref or "").strip()
    if not normalized_model_ref:
        raise ValueError("model_ref is required")
    normalized_collection_ids: list[str] = []
    seen: set[str] = set()
    for raw_value in collection_ids:
        normalized = str(raw_value or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_collection_ids.append(normalized)

    connection = connect(db_path)
    try:
        if normalized_collection_ids:
            placeholders = ", ".join(["?"] * len(normalized_collection_ids))
            existing_rows = connection.execute(
                f"SELECT collection_id FROM model_catalog_collections WHERE collection_id IN ({placeholders})",
                normalized_collection_ids,
            ).fetchall()
            existing_ids = {str(row["collection_id"]) for row in existing_rows}
            missing_ids = [collection_id for collection_id in normalized_collection_ids if collection_id not in existing_ids]
            if missing_ids:
                raise ValueError(f"collection not found: {missing_ids[0]}")

        now_iso = utc_now_iso()
        connection.execute(
            "DELETE FROM model_catalog_collection_memberships WHERE model_ref = ?",
            (normalized_model_ref,),
        )
        for collection_id in normalized_collection_ids:
            connection.execute(
                """
                INSERT INTO model_catalog_collection_memberships (
                    collection_id, model_ref, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (collection_id, normalized_model_ref, now_iso, now_iso),
            )
        connection.commit()
    finally:
        connection.close()
    return read_model_collection_memberships_bulk(db_path=db_path, model_refs=[normalized_model_ref]).get(normalized_model_ref, [])


def ensure_collection_paths(*, db_path: Path, collection_names: list[str] | tuple[str, ...] | None) -> list[dict[str, Any]]:
    normalized_names = [str(value or "").strip() for value in collection_names or [] if str(value or "").strip()]
    if not normalized_names:
        return []

    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT collection_id, name, parent_collection_id, created_at, updated_at FROM model_catalog_collections ORDER BY collection_id ASC"
        ).fetchall()
        collection_rows_by_id: dict[str, dict[str, Any]] = {
            str(row["collection_id"]): dict(row) for row in rows
        }
        ensured_leaf_ids: list[str] = []
        seen_leaf_ids: set[str] = set()
        now_iso = utc_now_iso()

        for raw_name in normalized_names:
            path_parts = _split_collection_path(raw_name)
            if not path_parts:
                continue
            if len(path_parts) > MAX_COLLECTION_DEPTH:
                raise ValueError(f"collection depth exceeds max depth {MAX_COLLECTION_DEPTH}")

            built_parts: list[str] = []
            parent_id: str | None = None
            for part in path_parts:
                normalized_part = _normalize_collection_name(part)
                built_parts.append(normalized_part)
                collection_id = _join_collection_id(tuple(built_parts))
                existing = collection_rows_by_id.get(collection_id)
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO model_catalog_collections (
                            collection_id, name, parent_collection_id, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (collection_id, normalized_part, parent_id, now_iso, now_iso),
                    )
                    existing = {
                        "collection_id": collection_id,
                        "name": normalized_part,
                        "parent_collection_id": parent_id,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                    collection_rows_by_id[collection_id] = existing
                parent_id = collection_id
            if parent_id and parent_id not in seen_leaf_ids:
                seen_leaf_ids.add(parent_id)
                ensured_leaf_ids.append(parent_id)

        connection.commit()
        return [collection_rows_by_id[collection_id] for collection_id in ensured_leaf_ids]
    finally:
        connection.close()