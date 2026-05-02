"""Model catalog schema and custom field operations.

This module handles local model storage (model_catalog_entries, model_catalog_assets),
and generic custom fields for models and other entities.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db_common import connect, utc_now_iso


def _normalize_model_ref(model_ref: str) -> str:
    return str(model_ref).strip()


def _field_entity(model_ref: str) -> tuple[str, str]:
    return ("manyfold_model", _normalize_model_ref(model_ref))


def _coerce_json_value(raw_value: str) -> object:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def set_model_field(
    *,
    db_path: Path,
    model_ref: str,
    field_key: str,
    field_value: object,
    field_namespace: str = "model_catalog",
) -> object:
    now = utc_now_iso()
    entity_type, entity_id = _field_entity(model_ref)
    encoded_value = json.dumps(field_value)
    value_type = type(field_value).__name__
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_custom_fields (
                entity_type,
                entity_id,
                field_namespace,
                field_key,
                field_value_json,
                value_type,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, entity_id, field_namespace, field_key)
            DO UPDATE SET
                field_value_json = excluded.field_value_json,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (
                entity_type,
                entity_id,
                field_namespace,
                field_key,
                encoded_value,
                value_type,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return field_value


def read_model_fields(
    *,
    db_path: Path,
    model_ref: str,
    field_namespace: str = "model_catalog",
) -> dict[str, object]:
    entity_type, entity_id = _field_entity(model_ref)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT field_key, field_value_json
            FROM model_catalog_custom_fields
            WHERE entity_type = ? AND entity_id = ? AND field_namespace = ?
            ORDER BY field_key ASC
            """,
            (entity_type, entity_id, field_namespace),
        ).fetchall()
    finally:
        connection.close()
    return {str(row["field_key"]): _coerce_json_value(str(row["field_value_json"])) for row in rows}


def read_model_field(
    *,
    db_path: Path,
    model_ref: str,
    field_key: str,
    field_namespace: str = "model_catalog",
) -> object | None:
    entity_type, entity_id = _field_entity(model_ref)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT field_value_json
            FROM model_catalog_custom_fields
            WHERE entity_type = ? AND entity_id = ? AND field_namespace = ? AND field_key = ?
            """,
            (entity_type, entity_id, field_namespace, field_key),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return _coerce_json_value(str(row["field_value_json"]))


def delete_model_field(
    *,
    db_path: Path,
    model_ref: str,
    field_key: str,
    field_namespace: str = "model_catalog",
) -> bool:
    entity_type, entity_id = _field_entity(model_ref)
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            DELETE FROM model_catalog_custom_fields
            WHERE entity_type = ? AND entity_id = ? AND field_namespace = ? AND field_key = ?
            """,
            (entity_type, entity_id, field_namespace, field_key),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()
