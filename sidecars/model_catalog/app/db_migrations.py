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
    (
        16,
        (
            """
    CREATE TABLE IF NOT EXISTS model_catalog_print_history_jobs (
        id INTEGER PRIMARY KEY,
        job_id TEXT NOT NULL UNIQUE,
        workflow_kind TEXT NOT NULL DEFAULT 'historical_backfill',
        source_kind TEXT NOT NULL,
        source_ref TEXT,
        local_model_id TEXT,
        working_group_id INTEGER,
        working_file_path TEXT,
        archive_intent TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        requested_print_started_at TEXT,
        requested_print_completed_at TEXT,
        requested_print_timezone TEXT,
        date_override_strategy TEXT NOT NULL DEFAULT 'operator_supplied',
        target_archive_id INTEGER,
        created_archive_id INTEGER,
        selected_file_path TEXT,
        selected_plate_key TEXT,
        selected_plate_index INTEGER,
        source_file_name TEXT,
        source_sha256 TEXT,
        sliced_output_path TEXT,
        sliced_output_sha256 TEXT,
        worker_provider TEXT,
        worker_job_id TEXT,
        attach_source_after_create INTEGER NOT NULL DEFAULT 0,
        validation_warnings_json TEXT NOT NULL DEFAULT '[]',
        overrides_json TEXT NOT NULL DEFAULT '{}',
        commit_request_json TEXT NOT NULL DEFAULT '{}',
        result_summary_json TEXT NOT NULL DEFAULT '{}',
        last_error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (working_group_id) REFERENCES working_groups(id)
    )
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_print_history_jobs_status
    ON model_catalog_print_history_jobs(status)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_print_history_jobs_source
    ON model_catalog_print_history_jobs(source_kind, source_ref)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_print_history_jobs_group_id
    ON model_catalog_print_history_jobs(working_group_id)
    """,
            """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_print_history_jobs_created_archive
    ON model_catalog_print_history_jobs(created_archive_id)
    """,
        ),
    ),
        (
        17,
        (
            """
        CREATE TABLE IF NOT EXISTS unified_queue_entries (
        id INTEGER PRIMARY KEY,
        queue_entry_id TEXT NOT NULL UNIQUE,
        source_kind TEXT NOT NULL,
        source_ref TEXT,
        title TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'preparing',
        rank INTEGER NOT NULL DEFAULT 0,
        started_at TEXT,
        completed_at TEXT,
        blocked_reason TEXT,
        copies_requested INTEGER NOT NULL DEFAULT 1,
        copies_completed INTEGER NOT NULL DEFAULT 0,
        selection_mode TEXT NOT NULL DEFAULT 'all_files_all_plates',
        estimated_total_minutes INTEGER,
        duration_bucket TEXT NOT NULL DEFAULT 'unknown',
        ams_ready_score INTEGER NOT NULL DEFAULT 0,
        overnight_fit_score INTEGER NOT NULL DEFAULT 0,
        queue_notes TEXT,
        last_archive_id TEXT,
        last_attempt_outcome TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (source_kind IN ('catalog_model', 'working_group', 'working_file', 'idea')),
        CHECK (state IN ('backlog', 'preparing', 'ready', 'in_progress', 'done', 'blocked')),
        CHECK (selection_mode IN ('all_files_all_plates', 'selected_files', 'selected_plates')),
        CHECK (duration_bucket IN ('quick', 'medium', 'overnight', 'marathon', 'unknown')),
        CHECK (last_attempt_outcome IS NULL OR last_attempt_outcome IN ('success', 'failed', 'aborted', 'unknown'))
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_entries_rank
        ON unified_queue_entries(rank ASC, created_at ASC)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_entries_state
        ON unified_queue_entries(state)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_entries_source
        ON unified_queue_entries(source_kind, source_ref)
        """,
            """
        CREATE TABLE IF NOT EXISTS unified_queue_file_units (
        id INTEGER PRIMARY KEY,
        queue_entry_id TEXT NOT NULL,
        file_unit_id TEXT NOT NULL,
        file_id TEXT,
        file_name TEXT NOT NULL,
        selected INTEGER NOT NULL DEFAULT 1,
        estimated_minutes INTEGER,
        filament_requirements_json TEXT NOT NULL DEFAULT '{}',
        archive_link_summary_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (queue_entry_id) REFERENCES unified_queue_entries(queue_entry_id) ON DELETE CASCADE,
        UNIQUE(queue_entry_id, file_unit_id)
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_file_units_entry
        ON unified_queue_file_units(queue_entry_id)
        """,
            """
        CREATE TABLE IF NOT EXISTS unified_queue_plate_units (
        id INTEGER PRIMARY KEY,
        queue_entry_id TEXT NOT NULL,
        file_unit_id TEXT NOT NULL,
        plate_unit_id TEXT NOT NULL,
        plate_key TEXT NOT NULL,
        plate_name TEXT,
        preview_image_path TEXT,
        selected INTEGER NOT NULL DEFAULT 1,
        state TEXT NOT NULL DEFAULT 'pending',
        completed_by_archive_id TEXT,
        completion_confidence TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_attempt_outcome TEXT,
        estimated_minutes INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (queue_entry_id, file_unit_id)
            REFERENCES unified_queue_file_units(queue_entry_id, file_unit_id)
            ON DELETE CASCADE,
        UNIQUE(queue_entry_id, file_unit_id, plate_unit_id),
        CHECK (state IN ('pending', 'started', 'done', 'blocked')),
        CHECK (completion_confidence IS NULL OR completion_confidence IN ('high', 'medium', 'low')),
        CHECK (last_attempt_outcome IS NULL OR last_attempt_outcome IN ('success', 'failed', 'aborted', 'unknown'))
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_plate_units_entry
        ON unified_queue_plate_units(queue_entry_id)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_plate_units_file
        ON unified_queue_plate_units(queue_entry_id, file_unit_id)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_plate_units_state
        ON unified_queue_plate_units(state)
        """,
        ),
        ),
    (
        18,
        (
            """
        CREATE TABLE IF NOT EXISTS unified_queue_match_suggestions (
        id INTEGER PRIMARY KEY,
        suggestion_id TEXT NOT NULL UNIQUE,
        printer_id TEXT NOT NULL,
        archive_id TEXT NOT NULL,
        queue_entry_id TEXT,
        remapped_queue_entry_id TEXT,
        confidence TEXT NOT NULL,
        confidence_score REAL NOT NULL DEFAULT 0,
        match_method TEXT,
        reasons_json TEXT NOT NULL DEFAULT '[]',
        archive_payload_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'suggested',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        reviewed_at TEXT,
        CHECK (confidence IN ('high', 'medium', 'low', 'unmatched')),
        CHECK (status IN ('suggested', 'auto_completed', 'unmatched', 'rejected', 'remapped'))
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_match_suggestions_status
        ON unified_queue_match_suggestions(status, created_at DESC)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_match_suggestions_archive
        ON unified_queue_match_suggestions(archive_id, created_at DESC)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_match_suggestions_entry
        ON unified_queue_match_suggestions(queue_entry_id, created_at DESC)
        """,
        ),
    ),
    (
        19,
        (
            """
        CREATE TABLE IF NOT EXISTS unified_queue_planner_preferences (
        id INTEGER PRIMARY KEY,
        printer_id TEXT NOT NULL UNIQUE,
        strategy TEXT NOT NULL DEFAULT 'balanced',
        weights_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (strategy IN ('aggressive', 'balanced', 'lazy'))
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_planner_preferences_strategy
        ON unified_queue_planner_preferences(strategy)
        """,
        ),
    ),
    (
        20,
        (
            """
        CREATE TABLE IF NOT EXISTS planner_operations_audit (
        id INTEGER PRIMARY KEY,
        printer_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        strategy TEXT,
        delta_json TEXT NOT NULL DEFAULT '{}',
        moved_entry_ids_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        created_by TEXT,
        CHECK (operation IN ('apply', 'undo'))
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS planner_operation_snapshots (
        id INTEGER PRIMARY KEY,
        audit_id INTEGER NOT NULL,
        queue_entry_id TEXT NOT NULL,
        rank_before INTEGER NOT NULL,
        rank_after INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (audit_id) REFERENCES planner_operations_audit(id)
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_planner_operations_audit_printer
        ON planner_operations_audit(printer_id, created_at DESC)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_planner_operations_audit_operation
        ON planner_operations_audit(operation, created_at DESC)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_planner_operation_snapshots_audit
        ON planner_operation_snapshots(audit_id)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_planner_operation_snapshots_entry
        ON planner_operation_snapshots(queue_entry_id, created_at DESC)
        """,
        ),
    ),
    (
        21,
        (
            """
        PRAGMA foreign_keys = OFF
        """,
            """
        ALTER TABLE unified_queue_entries RENAME TO unified_queue_entries_legacy_v20
        """,
            """
        CREATE TABLE unified_queue_entries (
        id INTEGER PRIMARY KEY,
        queue_entry_id TEXT NOT NULL UNIQUE,
        source_kind TEXT NOT NULL,
        source_ref TEXT,
        title TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'preparing',
        rank INTEGER NOT NULL DEFAULT 0,
        started_at TEXT,
        completed_at TEXT,
        blocked_reason TEXT,
        copies_requested INTEGER NOT NULL DEFAULT 1,
        copies_completed INTEGER NOT NULL DEFAULT 0,
        selection_mode TEXT NOT NULL DEFAULT 'all_files_all_plates',
        estimated_total_minutes INTEGER,
        duration_bucket TEXT NOT NULL DEFAULT 'unknown',
        ams_ready_score INTEGER NOT NULL DEFAULT 0,
        overnight_fit_score INTEGER NOT NULL DEFAULT 0,
        queue_notes TEXT,
        last_archive_id TEXT,
        last_attempt_outcome TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (source_kind IN ('catalog_model', 'working_group', 'working_file', 'idea')),
        CHECK (state IN ('backlog', 'preparing', 'ready', 'in_progress', 'done', 'blocked')),
        CHECK (selection_mode IN ('all_files_all_plates', 'selected_files', 'selected_plates')),
        CHECK (duration_bucket IN ('quick', 'medium', 'overnight', 'marathon', 'unknown')),
        CHECK (last_attempt_outcome IS NULL OR last_attempt_outcome IN ('success', 'failed', 'aborted', 'unknown'))
        )
        """,
            """
        INSERT INTO unified_queue_entries (
        id,
        queue_entry_id,
        source_kind,
        source_ref,
        title,
        state,
        rank,
        started_at,
        completed_at,
        blocked_reason,
        copies_requested,
        copies_completed,
        selection_mode,
        estimated_total_minutes,
        duration_bucket,
        ams_ready_score,
        overnight_fit_score,
        queue_notes,
        last_archive_id,
        last_attempt_outcome,
        created_at,
        updated_at
        )
        SELECT
        id,
        queue_entry_id,
        source_kind,
        source_ref,
        title,
        CASE state
            WHEN 'idea' THEN 'backlog'
            WHEN 'todo' THEN 'preparing'
            WHEN 'started' THEN 'in_progress'
            ELSE state
        END,
        rank,
        started_at,
        completed_at,
        blocked_reason,
        copies_requested,
        copies_completed,
        selection_mode,
        estimated_total_minutes,
        duration_bucket,
        ams_ready_score,
        overnight_fit_score,
        queue_notes,
        last_archive_id,
        last_attempt_outcome,
        created_at,
        updated_at
        FROM unified_queue_entries_legacy_v20
        """,
            """
        DROP TABLE unified_queue_entries_legacy_v20
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_entries_rank
        ON unified_queue_entries(rank ASC, created_at ASC)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_entries_state
        ON unified_queue_entries(state)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_unified_queue_entries_source
        ON unified_queue_entries(source_kind, source_ref)
        """,
            """
        PRAGMA foreign_keys = ON
        """,
        ),
    ),
    (
        22,
        (
            """
        ALTER TABLE unified_queue_entries ADD COLUMN completion_source TEXT
        """,
            """
        ALTER TABLE unified_queue_plate_units ADD COLUMN completion_source TEXT
        """,
            """
        UPDATE unified_queue_entries
        SET completion_source = 'auto_match'
        WHERE completion_source IS NULL
          AND state = 'done'
          AND COALESCE(last_archive_id, '') != ''
        """,
            """
        UPDATE unified_queue_plate_units
        SET completion_source = 'auto_match'
        WHERE completion_source IS NULL
          AND state = 'done'
          AND COALESCE(completed_by_archive_id, '') != ''
        """,
            """
        UPDATE unified_queue_plate_units
        SET completion_source = 'manual'
        WHERE completion_source IS NULL
          AND state = 'done'
          AND COALESCE(completed_by_archive_id, '') = ''
          AND COALESCE(last_attempt_outcome, '') = 'success'
        """,
        ),
    ),
    (
        23,
        (),
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
        if version == 23:
            _repair_unified_queue_file_units_foreign_key(connection)
        connection.execute(
            "INSERT INTO model_catalog_schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
            (version,),
        )


def _repair_unified_queue_file_units_foreign_key(connection: sqlite3.Connection) -> None:
    """Repair v21 FK drift from unified_queue_entries to legacy temp table.

    Migration v21 temporarily renamed unified_queue_entries while foreign keys
    were disabled. In some databases, SQLite rewrote unified_queue_file_units
    to reference unified_queue_entries_legacy_v20, then the legacy table was
    dropped, leaving dangling FK metadata that breaks schema introspection.
    """
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='unified_queue_file_units'"
    ).fetchone()
    if row is None:
        return

    fk_rows = connection.execute("PRAGMA foreign_key_list(unified_queue_file_units)").fetchall()
    fk_targets = {str(r["table"]) for r in fk_rows}

    # Already healthy in normal/current schemas.
    if "unified_queue_entries_legacy_v20" not in fk_targets:
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute(
            """
            CREATE TABLE unified_queue_file_units_v23_repair (
                id INTEGER PRIMARY KEY,
                queue_entry_id TEXT NOT NULL,
                file_unit_id TEXT NOT NULL,
                file_id TEXT,
                file_name TEXT NOT NULL,
                selected INTEGER NOT NULL DEFAULT 1,
                estimated_minutes INTEGER,
                filament_requirements_json TEXT NOT NULL DEFAULT '{}',
                archive_link_summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (queue_entry_id) REFERENCES unified_queue_entries(queue_entry_id) ON DELETE CASCADE,
                UNIQUE(queue_entry_id, file_unit_id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO unified_queue_file_units_v23_repair (
                id,
                queue_entry_id,
                file_unit_id,
                file_id,
                file_name,
                selected,
                estimated_minutes,
                filament_requirements_json,
                archive_link_summary_json,
                created_at,
                updated_at
            )
            SELECT
                id,
                queue_entry_id,
                file_unit_id,
                file_id,
                file_name,
                selected,
                estimated_minutes,
                filament_requirements_json,
                archive_link_summary_json,
                created_at,
                updated_at
            FROM unified_queue_file_units
            """
        )
        connection.execute("DROP TABLE unified_queue_file_units")
        connection.execute(
            "ALTER TABLE unified_queue_file_units_v23_repair RENAME TO unified_queue_file_units"
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_unified_queue_file_units_entry
            ON unified_queue_file_units(queue_entry_id)
            """
        )
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


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