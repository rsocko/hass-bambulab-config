"""Centralized schema management and migrations.

This module handles all CREATE TABLE statements, ALTER TABLE operations,
and schema version tracking. It's the single source of truth for schema evolution.
"""

from __future__ import annotations

import sqlite3
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
    (
        3,
        (),
    ),
    (
        4,
        (
            """
    CREATE TABLE IF NOT EXISTS model_catalog_model_ranking (
        manyfold_model_url TEXT PRIMARY KEY,
        manyfold_model_public_id TEXT,
        last_printed_at TEXT,
        linked_archive_count INTEGER NOT NULL DEFAULT 0,
        print_count INTEGER NOT NULL DEFAULT 0,
        recent_score REAL,
        frequent_score REAL,
        common_score REAL,
        refreshed_at TEXT NOT NULL
    )
    """,
        ),
    ),
    (
        5,
        (),
    ),
    (
        6,
        (),
    ),
    (
        7,
        (
            """
    CREATE TABLE IF NOT EXISTS intake_queue_uploads (
        id INTEGER PRIMARY KEY,
        upload_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'queued',
        source_entries_json TEXT NOT NULL,
        file_hashes_json TEXT NOT NULL DEFAULT '[]',
        manyfold_file_ids_json TEXT NOT NULL DEFAULT '[]',
        verification_status TEXT NOT NULL DEFAULT 'unverified',
        cleanup_policy TEXT NOT NULL DEFAULT 'keep',
        error_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        uploaded_at TEXT,
        verified_at TEXT,
        cleanup_done_at TEXT
    )
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_intake_queue_status
    ON intake_queue_uploads(status)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_intake_queue_created_at
    ON intake_queue_uploads(created_at DESC)
    """,
        ),
    ),
    (
        8,
        (
            """
    CREATE TABLE IF NOT EXISTS model_catalog_entries (
        id INTEGER PRIMARY KEY,
        local_model_id TEXT NOT NULL UNIQUE,
        model_name TEXT NOT NULL,
        model_description TEXT,
        creator_name TEXT,
        created_by TEXT,
        collection_names_json TEXT NOT NULL DEFAULT '[]',
        keyword_names_json TEXT NOT NULL DEFAULT '[]',
        tags_json TEXT NOT NULL DEFAULT '[]',
        license_type TEXT,
        preview_image_url TEXT,
        source_origin TEXT,
        source_origin_url TEXT,
        revision_hash TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT
    )
    """,
            """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_model_catalog_entries_local_id
    ON model_catalog_entries (local_model_id)
    """,
            """
    CREATE TABLE IF NOT EXISTS model_catalog_assets (
        id INTEGER PRIMARY KEY,
        model_catalog_entry_id INTEGER NOT NULL,
        asset_id TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        asset_filename TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        asset_role TEXT NOT NULL DEFAULT 'primary',
        file_size_bytes INTEGER,
        file_hash TEXT,
        storage_path TEXT NOT NULL,
        preview_url TEXT,
        geometry_bounds_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (model_catalog_entry_id) REFERENCES model_catalog_entries(id),
        UNIQUE(model_catalog_entry_id, asset_id)
    )
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_assets_entry_id
    ON model_catalog_assets (model_catalog_entry_id)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_assets_type
    ON model_catalog_assets (asset_type)
    """,
        ),
    ),
    (
        9,
        (),
    ),
    (
        10,
        (
            """
    CREATE TABLE IF NOT EXISTS working_file_inventory (
        id INTEGER PRIMARY KEY,
        source_path_raw TEXT NOT NULL,
        source_path_canonical TEXT NOT NULL,
        source_path_compare_key TEXT NOT NULL,
        file_name_raw TEXT NOT NULL,
        file_name_base_hint TEXT NOT NULL,
        file_extension TEXT NOT NULL,
        file_size_bytes INTEGER NOT NULL,
        sha256_hash TEXT,
        source_mtime TEXT,
        source_ctime TEXT,
        source_birthtime TEXT,
        validation_state TEXT NOT NULL DEFAULT 'ready',
        warnings_json TEXT NOT NULL DEFAULT '[]',
        detected_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        root_path TEXT
    )
    """,
            """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_working_file_inventory_compare_key
    ON working_file_inventory(source_path_compare_key)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_working_file_inventory_name
    ON working_file_inventory(file_name_base_hint)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_working_file_inventory_extension
    ON working_file_inventory(file_extension)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_working_file_inventory_hash
    ON working_file_inventory(sha256_hash)
    WHERE sha256_hash IS NOT NULL
    """,
            """
    CREATE TABLE IF NOT EXISTS working_group_model_links (
        id INTEGER PRIMARY KEY,
        working_group_id INTEGER NOT NULL,
        model_ref TEXT NOT NULL,
        link_role TEXT NOT NULL DEFAULT 'related',
        link_metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (working_group_id) REFERENCES working_groups(id),
        UNIQUE(working_group_id, model_ref)
    )
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_working_group_model_links_model_ref
    ON working_group_model_links(model_ref)
    """,
        ),
    ),
    (
        11,
        (
            """
    CREATE TABLE IF NOT EXISTS model_catalog_projects (
        id INTEGER PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        description TEXT,
        notes TEXT,
        bambuddy_project_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT
    )
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_projects_slug
    ON model_catalog_projects(slug)
    """,
        ),
    ),
    (
        12,
        (
            """
    -- Add terminal state tracking columns to intake_queue_uploads for state machine
    -- terminal_action: what terminal action was performed (grouped_new, grouped_existing, published_to_catalog, rejected)
    -- terminal_at: timestamp when item reached terminal state
    -- terminal_result_id: reference to result entity (e.g., working_group_id or local_model_id)
    """,  # Comment-only SQL
        ),
    ),
    (
        13,
        (
            """
    -- Add terminal actor tracking for intake job history
    -- terminal_actor: user/service path that completed the terminal action
    """,  # Comment-only SQL
        ),
    ),
    (
        14,
        (
            """
    CREATE TABLE IF NOT EXISTS intake_upload_idempotency (
        id INTEGER PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        payload_signature TEXT NOT NULL,
        upload_id TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_intake_upload_idempotency_expires_at
    ON intake_upload_idempotency(expires_at)
    """,
        ),
    ),
    (
        15,
        (
            """
    -- Add intake upload telemetry columns for v1/v2 transport diagnostics
    """,  # Comment-only SQL
        ),
    ),
)


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Get the current schema version."""
    row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM model_catalog_schema_migrations").fetchone()
    return int(row["version"] if row is not None else 0)


def applied_versions(connection: sqlite3.Connection) -> set[int]:
    """Get set of applied migration versions."""
    rows = connection.execute("SELECT version FROM model_catalog_schema_migrations").fetchall()
    return {int(row["version"]) for row in rows}


def execute_statements(connection: sqlite3.Connection, statements: Iterable[str]) -> None:
    """Execute a sequence of SQL statements."""
    for statement in statements:
        connection.execute(statement)


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, sql_type: str) -> None:
    """Add a column to a table if it doesn't exist."""
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {str(row["name"]) for row in rows}
    if column_name in existing:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply all pending migrations."""
    applied = applied_versions(connection)
    for version, statements in MIGRATIONS:
        if version in applied:
            continue
        execute_statements(connection, statements)
        if version == 3:
            ensure_column(connection, "model_catalog_links", "review_note", "TEXT")
        if version == 15:
            ensure_column(connection, "intake_queue_uploads", "transport_mode", "TEXT")
            ensure_column(connection, "intake_queue_uploads", "payload_bytes_raw", "INTEGER")
            ensure_column(connection, "intake_queue_uploads", "payload_bytes_encoded", "INTEGER")
            ensure_column(connection, "intake_queue_uploads", "upload_duration_ms", "INTEGER")
            ensure_column(connection, "intake_queue_uploads", "staging_write_duration_ms", "INTEGER")
            ensure_column(connection, "intake_queue_uploads", "warnings_count", "INTEGER")
        if version == 5:
            _migrate_manyfold_model_cache_keys(connection)
        if version == 6:
            ensure_column(connection, "working_items", "file_hash", "TEXT")
            ensure_column(connection, "working_items", "file_size", "INTEGER")
            ensure_column(connection, "working_items", "source_metadata_json", "TEXT NOT NULL DEFAULT '{}' ")
            ensure_column(connection, "working_groups", "discovery_source_folder", "TEXT")
            ensure_column(connection, "working_groups", "discovery_strategy", "TEXT")
            ensure_column(connection, "working_groups", "discovery_timestamp", "TEXT")
            ensure_column(connection, "working_groups", "discovery_metadata_json", "TEXT NOT NULL DEFAULT '{}' ")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_working_items_file_hash
                ON working_items(file_hash)
                WHERE file_hash IS NOT NULL
                """
            )
        if version == 9:
            ensure_column(connection, "model_catalog_assets", "sort_order", "INTEGER NOT NULL DEFAULT 0")
        if version == 10:
            ensure_column(connection, "intake_queue_uploads", "inbox_state", "TEXT NOT NULL DEFAULT 'submitted'")
            ensure_column(connection, "intake_queue_uploads", "decision_note", "TEXT")
        if version == 11:
            ensure_column(connection, "working_groups", "project_id", "INTEGER")
        if version == 12:
            ensure_column(connection, "intake_queue_uploads", "terminal_action", "TEXT")
            ensure_column(connection, "intake_queue_uploads", "terminal_at", "TEXT")
            ensure_column(connection, "intake_queue_uploads", "terminal_result_id", "TEXT")
        if version == 13:
            ensure_column(connection, "intake_queue_uploads", "terminal_actor", "TEXT")
        connection.execute(
            "INSERT INTO model_catalog_schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
            (version,),
        )


def _migrate_manyfold_model_cache_keys(connection: sqlite3.Connection) -> None:
    """Migrate manyfold model cache keys (migration v5)."""
    from .db import derive_manyfold_model_key

    ensure_column(connection, "manyfold_model_summary_cache", "manyfold_model_key", "TEXT")

    rows = connection.execute(
        """
        SELECT rowid, manyfold_model_url, manyfold_model_public_id, manyfold_model_id, refreshed_at
        FROM manyfold_model_summary_cache
        ORDER BY refreshed_at DESC, rowid DESC
        """
    ).fetchall()

    survivor_by_key: dict[str, int] = {}
    rows_to_delete: list[int] = []
    rows_to_update: list[tuple[str, int]] = []

    for row in rows:
        row_id = int(row["rowid"])
        model_key = derive_manyfold_model_key(
            manyfold_model_url=str(row["manyfold_model_url"] or "").strip() or None,
            manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            manyfold_model_id=str(row["manyfold_model_id"] or "").strip() or None,
        )

        if model_key in survivor_by_key:
            rows_to_delete.append(row_id)
            continue

        survivor_by_key[model_key] = row_id
        rows_to_update.append((model_key, row_id))

    if rows_to_update:
        connection.executemany(
            "UPDATE manyfold_model_summary_cache SET manyfold_model_key = ? WHERE rowid = ?",
            rows_to_update,
        )

    if rows_to_delete:
        connection.executemany(
            "DELETE FROM manyfold_model_summary_cache WHERE rowid = ?",
            [(row_id,) for row_id in rows_to_delete],
        )

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_manyfold_model_summary_cache_model_key
        ON manyfold_model_summary_cache(manyfold_model_key)
        """
    )