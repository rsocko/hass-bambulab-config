from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MIGRATION_TABLE_STATEMENT = """
    CREATE TABLE IF NOT EXISTS model_catalog_schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
"""


MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
    """
    CREATE TABLE IF NOT EXISTS manyfold_model_summary_cache (
        manyfold_model_url TEXT PRIMARY KEY,
        manyfold_model_public_id TEXT,
        manyfold_model_name TEXT NOT NULL,
        manyfold_model_id TEXT,
        preview_url TEXT,
        creator_name TEXT,
        collection_names_json TEXT NOT NULL DEFAULT '[]',
        keyword_names_json TEXT NOT NULL DEFAULT '[]',
        raw_json TEXT NOT NULL,
        refreshed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_catalog_links (
        id INTEGER PRIMARY KEY,
        manyfold_model_url TEXT NOT NULL,
        manyfold_model_public_id TEXT,
        manyfold_model_file_id TEXT,
        bambuddy_archive_id INTEGER,
        relationship_type TEXT NOT NULL,
        link_role TEXT NOT NULL DEFAULT 'primary',
        match_method TEXT NOT NULL DEFAULT 'manual',
        match_confidence TEXT NOT NULL DEFAULT 'high',
        review_state TEXT NOT NULL DEFAULT 'unreviewed',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS working_groups (
        id INTEGER PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        stage TEXT NOT NULL,
        notes TEXT,
        primary_file_path TEXT,
        folder_hint TEXT,
        related_manyfold_model_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS working_items (
        id INTEGER PRIMARY KEY,
        working_group_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        item_role TEXT NOT NULL DEFAULT 'supporting',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (working_group_id) REFERENCES working_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_catalog_events (
        id INTEGER PRIMARY KEY,
        event_type TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
        ),
    ),
    (
        2,
        (
    """
    CREATE TABLE IF NOT EXISTS model_catalog_custom_fields (
        id INTEGER PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        field_namespace TEXT NOT NULL DEFAULT 'model_catalog',
        field_key TEXT NOT NULL,
        field_value_json TEXT NOT NULL,
        value_type TEXT NOT NULL DEFAULT 'json',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(entity_type, entity_id, field_namespace, field_key)
    )
    """,
        ),
    ),
)


@dataclass(frozen=True)
class DatabaseInfo:
    path: str
    tables: tuple[str, ...]
    schema_version: int


@dataclass(frozen=True)
class ArchiveModelLink:
    id: int
    manyfold_model_url: str
    manyfold_model_public_id: str | None
    manyfold_model_file_id: str | None
    bambuddy_archive_id: int
    relationship_type: str
    link_role: str
    match_method: str
    match_confidence: str
    review_state: str
    is_active: bool
    created_at: str
    updated_at: str


def connect(db_path: Path) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def bootstrap_database(db_path: Path) -> DatabaseInfo:
    connection = connect(db_path)
    try:
        connection.execute(MIGRATION_TABLE_STATEMENT)
        _apply_migrations(connection)
        connection.commit()
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema_version = _current_schema_version(connection)
    finally:
        connection.close()
    return DatabaseInfo(path=str(db_path), tables=tuple(str(row["name"]) for row in rows), schema_version=schema_version)


def _current_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM model_catalog_schema_migrations").fetchone()
    return int(row["version"] if row is not None else 0)


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute("SELECT version FROM model_catalog_schema_migrations").fetchall()
    return {int(row["version"]) for row in rows}


def _execute_statements(connection: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        connection.execute(statement)


def _apply_migrations(connection: sqlite3.Connection) -> None:
    applied_versions = _applied_versions(connection)
    for version, statements in MIGRATIONS:
        if version in applied_versions:
            continue
        _execute_statements(connection, statements)
        connection.execute(
            "INSERT INTO model_catalog_schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
            (version,),
        )


def read_archive_links(*, db_path: Path, archive_id: int, active_only: bool = True) -> list[ArchiveModelLink]:
    connection = connect(db_path)
    try:
        query = """
            SELECT
                id,
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_file_id,
                bambuddy_archive_id,
                relationship_type,
                link_role,
                match_method,
                match_confidence,
                review_state,
                is_active,
                created_at,
                updated_at
            FROM model_catalog_links
            WHERE bambuddy_archive_id = ?
        """
        params: tuple[object, ...]
        if active_only:
            query += " AND is_active = 1"
            params = (archive_id,)
        else:
            params = (archive_id,)
        query += " ORDER BY updated_at DESC, id DESC"
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()

    return [
        ArchiveModelLink(
            id=int(row["id"]),
            manyfold_model_url=str(row["manyfold_model_url"]),
            manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            manyfold_model_file_id=str(row["manyfold_model_file_id"] or "").strip() or None,
            bambuddy_archive_id=int(row["bambuddy_archive_id"]),
            relationship_type=str(row["relationship_type"]),
            link_role=str(row["link_role"]),
            match_method=str(row["match_method"]),
            match_confidence=str(row["match_confidence"]),
            review_state=str(row["review_state"]),
            is_active=bool(int(row["is_active"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    ]
