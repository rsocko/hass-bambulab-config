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
        estimate_metadata_json TEXT NOT NULL DEFAULT '{}',
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
    (
        24,
        (
            """
        PRAGMA foreign_keys = OFF
        """,
            """
        ALTER TABLE unified_queue_entries RENAME TO unified_queue_entries_v23
        """,
            """
        CREATE TABLE unified_queue_entries (
        id INTEGER PRIMARY KEY,
        queue_entry_id TEXT NOT NULL UNIQUE,
        source_kind TEXT NOT NULL,
        source_ref TEXT,
        title TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'up_next',
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
        completion_source TEXT,
        last_archive_id TEXT,
        last_attempt_outcome TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (source_kind IN ('catalog_model', 'working_group', 'working_file', 'idea')),
        CHECK (state IN ('backlog', 'up_next', 'preparing', 'ready', 'in_progress', 'blocked', 'done')),
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
        completion_source,
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
        completion_source,
        last_archive_id,
        last_attempt_outcome,
        created_at,
        updated_at
        FROM unified_queue_entries_v23
        """,
            """
        DROP TABLE unified_queue_entries_v23
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
        25,
        (
            """
        ALTER TABLE model_catalog_entries ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'model'
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_entries_entity_type
        ON model_catalog_entries(entity_type)
        """,
        ),
    ),
    (
        26,
        (
            # --- Rename table: manyfold_model_summary_cache → model_summary_cache ---
            """
        ALTER TABLE manyfold_model_summary_cache RENAME TO model_summary_cache
        """,
            """
        ALTER TABLE model_summary_cache RENAME COLUMN manyfold_model_url TO model_url
        """,
            """
        ALTER TABLE model_summary_cache RENAME COLUMN manyfold_model_public_id TO model_public_id
        """,
            """
        ALTER TABLE model_summary_cache RENAME COLUMN manyfold_model_name TO model_name
        """,
            """
        ALTER TABLE model_summary_cache RENAME COLUMN manyfold_model_id TO model_id
        """,
            """
        ALTER TABLE model_summary_cache RENAME COLUMN manyfold_model_key TO model_key
        """,
            # Recreate unique index with new name
            """
        DROP INDEX IF EXISTS idx_manyfold_model_summary_cache_model_key
        """,
            """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_model_summary_cache_model_key
        ON model_summary_cache(model_key)
        """,
            # --- Rename columns in model_catalog_links ---
            """
        ALTER TABLE model_catalog_links RENAME COLUMN manyfold_model_url TO model_url
        """,
            """
        ALTER TABLE model_catalog_links RENAME COLUMN manyfold_model_public_id TO model_public_id
        """,
            """
        ALTER TABLE model_catalog_links RENAME COLUMN manyfold_model_file_id TO model_asset_id
        """,
            # --- Rename columns in model_catalog_model_ranking ---
            """
        ALTER TABLE model_catalog_model_ranking RENAME COLUMN manyfold_model_url TO model_url
        """,
            """
        ALTER TABLE model_catalog_model_ranking RENAME COLUMN manyfold_model_public_id TO model_public_id
        """,
            # --- Rename column in working_groups ---
            """
        ALTER TABLE working_groups RENAME COLUMN related_manyfold_model_id TO related_model_id
        """,
            # --- Rename column in intake_queue_uploads ---
            """
        ALTER TABLE intake_queue_uploads RENAME COLUMN manyfold_file_ids_json TO uploaded_file_ids_json
        """,
        ),
    ),
    (
        27,
        (
            # --- Rename entity_type value 'manyfold_model' → 'catalog_model' ---
            """
        UPDATE model_catalog_custom_fields SET entity_type = 'catalog_model' WHERE entity_type = 'manyfold_model'
        """,
            """
        UPDATE model_catalog_events SET entity_type = 'catalog_model' WHERE entity_type = 'manyfold_model'
        """,
        ),
    ),
    (
        28,
        (
            """
        CREATE TABLE IF NOT EXISTS model_catalog_search_projection (
            model_ref TEXT PRIMARY KEY,
            model_url TEXT NOT NULL,
            model_public_id TEXT,
            model_id TEXT,
            entity_type TEXT NOT NULL DEFAULT 'model',
            model_name TEXT NOT NULL,
            model_name_lc TEXT NOT NULL,
            creator_name TEXT,
            creator_name_lc TEXT NOT NULL DEFAULT '',
            preview_url TEXT,
            collection_names_json TEXT NOT NULL DEFAULT '[]',
            keyword_names_json TEXT NOT NULL DEFAULT '[]',
            collection_blob_lc TEXT NOT NULL DEFAULT '',
            keyword_blob_lc TEXT NOT NULL DEFAULT '',
            catalog_visibility TEXT NOT NULL DEFAULT 'active',
            model_favorite INTEGER NOT NULL DEFAULT 0,
            to_print_status TEXT,
            to_print_priority INTEGER,
            has_other_files INTEGER NOT NULL DEFAULT 0,
            linked_archive_count INTEGER NOT NULL DEFAULT 0,
            last_printed_at TEXT,
            print_count INTEGER NOT NULL DEFAULT 0,
            recent_score REAL,
            frequent_score REAL,
            common_score REAL,
            source_authority TEXT NOT NULL,
            refreshed_at TEXT NOT NULL
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS model_catalog_search_tokens (
            model_ref TEXT NOT NULL,
            token TEXT NOT NULL,
            PRIMARY KEY (model_ref, token)
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS model_catalog_search_projection_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_name
        ON model_catalog_search_projection(model_name_lc)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_creator
        ON model_catalog_search_projection(creator_name_lc)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_entity
        ON model_catalog_search_projection(entity_type)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_visibility
        ON model_catalog_search_projection(catalog_visibility)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_favorite
        ON model_catalog_search_projection(model_favorite)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_priority
        ON model_catalog_search_projection(to_print_priority)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_recent
        ON model_catalog_search_projection(last_printed_at)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_frequent
        ON model_catalog_search_projection(frequent_score)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_tokens_token
        ON model_catalog_search_tokens(token)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_tokens_model_ref
        ON model_catalog_search_tokens(model_ref)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_links_search
        ON model_catalog_links(is_active, review_state, model_url, updated_at)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_custom_fields_lookup
        ON model_catalog_custom_fields(entity_type, field_namespace, entity_id)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_custom_fields_updated
        ON model_catalog_custom_fields(entity_type, field_namespace, updated_at)
        """,
        ),
    ),
    (
        29,
        (
            # --- PR E.1: Drop the legacy working_groups / working_items /
            # working_group_model_links tables. The Working Files store is
            # now folder-first (see docs/features/model_catalog/design/
            # working-files.md); these DB-backed identities are obsolete.
            #
            # Operators MUST have already run the PR B export script
            # (cli/export_working_groups_to_sidecars.py) before this
            # migration is applied. Any rows left in these tables at this
            # point will be permanently discarded.
            #
            # The FK on model_catalog_print_history_jobs.working_group_id
            # becomes a dangling reference, which is benign in SQLite as
            # long as no code inserts a non-NULL value (verified — only
            # legacy working_catalog_service NULLs that column on group
            # deletion, and that path is unreachable after the table is
            # gone). The column itself is removed in a later PR E phase
            # alongside the dead Python code paths.
            """
        PRAGMA foreign_keys = OFF
        """,
            """
        DROP TABLE IF EXISTS working_group_model_links
        """,
            """
        DROP TABLE IF EXISTS working_items
        """,
            """
        DROP TABLE IF EXISTS working_groups
        """,
            """
        PRAGMA foreign_keys = ON
        """,
        ),
    ),
    (
        30,
        (
            # --- PR E.3 batch 1: drop the dangling working_group_id column
            # and its index from model_catalog_print_history_jobs. The
            # column had a FOREIGN KEY clause pointing at the
            # working_groups table dropped in PR E.1, leaving a dangling
            # reference in chartdb / sqlite_schema. SQLite cannot drop a
            # column that participates in a FK constraint via ALTER TABLE
            # DROP COLUMN, so we rebuild the table.
            """
        PRAGMA foreign_keys = OFF
        """,
            """
        CREATE TABLE model_catalog_print_history_jobs__pre_e3 (
            id INTEGER PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            workflow_kind TEXT NOT NULL DEFAULT 'historical_backfill',
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            local_model_id TEXT,
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
            completed_at TEXT
        )
        """,
            """
        INSERT INTO model_catalog_print_history_jobs__pre_e3 (
            id, job_id, workflow_kind, source_kind, source_ref, local_model_id,
            working_file_path, archive_intent, status,
            requested_print_started_at, requested_print_completed_at, requested_print_timezone,
            date_override_strategy, target_archive_id, created_archive_id,
            selected_file_path, selected_plate_key, selected_plate_index,
            source_file_name, source_sha256, sliced_output_path, sliced_output_sha256,
            worker_provider, worker_job_id, attach_source_after_create,
            validation_warnings_json, overrides_json, commit_request_json, result_summary_json,
            last_error, created_at, updated_at, completed_at
        )
        SELECT id, job_id, workflow_kind, source_kind, source_ref, local_model_id,
               working_file_path, archive_intent, status,
               requested_print_started_at, requested_print_completed_at, requested_print_timezone,
               date_override_strategy, target_archive_id, created_archive_id,
               selected_file_path, selected_plate_key, selected_plate_index,
               source_file_name, source_sha256, sliced_output_path, sliced_output_sha256,
               worker_provider, worker_job_id, attach_source_after_create,
               validation_warnings_json, overrides_json, commit_request_json, result_summary_json,
               last_error, created_at, updated_at, completed_at
        FROM model_catalog_print_history_jobs
        """,
            """
        DROP INDEX IF EXISTS idx_model_catalog_print_history_jobs_group_id
        """,
            """
        DROP INDEX IF EXISTS idx_model_catalog_print_history_jobs_status
        """,
            """
        DROP INDEX IF EXISTS idx_model_catalog_print_history_jobs_source
        """,
            """
        DROP INDEX IF EXISTS idx_model_catalog_print_history_jobs_created_archive
        """,
            """
        DROP TABLE model_catalog_print_history_jobs
        """,
            """
        ALTER TABLE model_catalog_print_history_jobs__pre_e3 RENAME TO model_catalog_print_history_jobs
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
        CREATE INDEX IF NOT EXISTS idx_model_catalog_print_history_jobs_created_archive
        ON model_catalog_print_history_jobs(created_archive_id)
        """,
            """
        PRAGMA foreign_keys = ON
        """,
        ),
    ),
    (
        31,
        (
            # --- PR E.3 batch 3: drop 'working_group' from the
            # unified_queue_entries.source_kind CHECK constraint. The
            # working_group source kind is no longer a valid queue source
            # after the working-groups feature was retired. SQLite cannot
            # alter a CHECK constraint in place, so we rebuild the table.
            """
        PRAGMA foreign_keys = OFF
        """,
            """
        CREATE TABLE unified_queue_entries__pre_e3_b3 (
            id INTEGER PRIMARY KEY,
            queue_entry_id TEXT NOT NULL UNIQUE,
            source_kind TEXT NOT NULL,
            source_ref TEXT,
            title TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'up_next',
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
            completion_source TEXT,
            last_archive_id TEXT,
            last_attempt_outcome TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (source_kind IN ('catalog_model', 'working_file', 'idea')),
            CHECK (state IN ('backlog', 'up_next', 'preparing', 'ready', 'in_progress', 'blocked', 'done')),
            CHECK (selection_mode IN ('all_files_all_plates', 'selected_files', 'selected_plates')),
            CHECK (duration_bucket IN ('quick', 'medium', 'overnight', 'marathon', 'unknown')),
            CHECK (last_attempt_outcome IS NULL OR last_attempt_outcome IN ('success', 'failed', 'aborted', 'unknown'))
        )
        """,
            """
        INSERT INTO unified_queue_entries__pre_e3_b3 (
            id, queue_entry_id, source_kind, source_ref, title, state, rank,
            started_at, completed_at, blocked_reason, copies_requested, copies_completed,
            selection_mode, estimated_total_minutes, duration_bucket,
            ams_ready_score, overnight_fit_score, queue_notes, completion_source,
            last_archive_id, last_attempt_outcome, created_at, updated_at
        )
        SELECT id, queue_entry_id, source_kind, source_ref, title, state, rank,
               started_at, completed_at, blocked_reason, copies_requested, copies_completed,
               selection_mode, estimated_total_minutes, duration_bucket,
               ams_ready_score, overnight_fit_score, queue_notes, completion_source,
               last_archive_id, last_attempt_outcome, created_at, updated_at
        FROM unified_queue_entries
        WHERE source_kind <> 'working_group'
        """,
            """
        DROP INDEX IF EXISTS idx_unified_queue_entries_rank
        """,
            """
        DROP INDEX IF EXISTS idx_unified_queue_entries_state
        """,
            """
        DROP INDEX IF EXISTS idx_unified_queue_entries_source
        """,
            """
        DROP TABLE unified_queue_entries
        """,
            """
        ALTER TABLE unified_queue_entries__pre_e3_b3 RENAME TO unified_queue_entries
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
        32,
        (
            """
        ALTER TABLE model_catalog_search_projection ADD COLUMN created_at TEXT
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_search_projection_created_at
        ON model_catalog_search_projection(created_at)
        """,
        ),
    ),
    (
        33,
        (
            """
        CREATE TABLE IF NOT EXISTS model_catalog_collections (
            collection_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            parent_collection_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (parent_collection_id) REFERENCES model_catalog_collections(collection_id)
                ON DELETE RESTRICT
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_collections_parent
        ON model_catalog_collections(parent_collection_id)
        """,
            """
        CREATE TABLE IF NOT EXISTS model_catalog_collection_memberships (
            collection_id TEXT NOT NULL,
            model_ref TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (collection_id, model_ref),
            FOREIGN KEY (collection_id) REFERENCES model_catalog_collections(collection_id)
                ON DELETE CASCADE
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_collection_memberships_model_ref
        ON model_catalog_collection_memberships(model_ref)
        """,
        ),
    ),
    (
        34,
        (
            """
        PRAGMA foreign_keys = OFF
        """,
            """
        CREATE TABLE model_catalog_entries__collections_v34 (
            id INTEGER PRIMARY KEY,
            local_model_id TEXT NOT NULL UNIQUE,
            model_name TEXT NOT NULL,
            model_description TEXT,
            creator_name TEXT,
            created_by TEXT,
            keyword_names_json TEXT NOT NULL DEFAULT '[]',
            tags_json TEXT NOT NULL DEFAULT '[]',
            license_type TEXT,
            preview_image_url TEXT,
            source_origin TEXT,
            source_origin_url TEXT,
            revision_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT,
            entity_type TEXT NOT NULL DEFAULT 'model'
        )
        """,
            """
        INSERT INTO model_catalog_entries__collections_v34 (
            id, local_model_id, model_name, model_description, creator_name,
            created_by, keyword_names_json, tags_json, license_type,
            preview_image_url, source_origin, source_origin_url, revision_hash,
            created_at, updated_at, archived_at, entity_type
        )
        SELECT id, local_model_id, model_name, model_description, creator_name,
               created_by, keyword_names_json, tags_json, license_type,
               preview_image_url, source_origin, source_origin_url, revision_hash,
               created_at, updated_at, archived_at, entity_type
        FROM model_catalog_entries
        """,
            """
        DROP INDEX IF EXISTS idx_model_catalog_entries_local_id
        """,
            """
        DROP INDEX IF EXISTS idx_model_catalog_entries_entity_type
        """,
            """
        DROP TABLE model_catalog_entries
        """,
            """
        ALTER TABLE model_catalog_entries__collections_v34 RENAME TO model_catalog_entries
        """,
            """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_model_catalog_entries_local_id
        ON model_catalog_entries (local_model_id)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_entries_entity_type
        ON model_catalog_entries(entity_type)
        """,
            """
        PRAGMA foreign_keys = ON
        """,
        ),
    ),
    (
        35,
        (
            """
        SELECT 1
        """,
        ),
    ),
    (
        36,
        (
            """
        ALTER TABLE model_catalog_projects ADD COLUMN status TEXT NOT NULL DEFAULT 'evaluating'
        """,
            """
        ALTER TABLE model_catalog_projects ADD COLUMN project_type TEXT
        """,
            """
        ALTER TABLE model_catalog_projects ADD COLUMN origin TEXT
        """,
            """
        ALTER TABLE model_catalog_projects ADD COLUMN origin_url TEXT
        """,
            """
        ALTER TABLE model_catalog_projects ADD COLUMN completed_at TEXT
        """,
            """
        ALTER TABLE model_catalog_projects ADD COLUMN created_by TEXT
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_projects_status
        ON model_catalog_projects(status)
        """,
            """
        CREATE TABLE IF NOT EXISTS model_catalog_project_memberships (
            project_id INTEGER NOT NULL,
            model_ref TEXT NOT NULL,
            member_state TEXT NOT NULL DEFAULT 'candidate',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, model_ref),
            FOREIGN KEY (project_id) REFERENCES model_catalog_projects(id)
                ON DELETE CASCADE
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_project_memberships_model_ref
        ON model_catalog_project_memberships(model_ref)
        """,
            """
        UPDATE model_catalog_projects
        SET status = CASE
            WHEN archived_at IS NOT NULL THEN 'archived'
            ELSE COALESCE(NULLIF(TRIM(status), ''), 'evaluating')
        END
        """,
            """
        INSERT OR IGNORE INTO model_catalog_project_memberships (
            project_id, model_ref, member_state, created_at, updated_at
        )
        SELECT
            CAST(json_extract(cf.field_value_json, '$') AS INTEGER),
            cf.entity_id,
            'candidate',
            COALESCE(cf.updated_at, datetime('now')),
            COALESCE(cf.updated_at, datetime('now'))
        FROM model_catalog_custom_fields cf
        JOIN model_catalog_projects p
            ON p.id = CAST(json_extract(cf.field_value_json, '$') AS INTEGER)
        WHERE cf.entity_type = 'model'
          AND cf.field_key = 'project_id'
          AND json_type(cf.field_value_json, '$') IN ('integer', 'text')
          AND CAST(json_extract(cf.field_value_json, '$') AS INTEGER) > 0
        """,
        ),
    ),
    (
        37,
        (
            """
        CREATE TABLE IF NOT EXISTS source_intake_records (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            capture_channel TEXT NOT NULL,
            capture_mode TEXT NOT NULL,
            source_url_canonical TEXT NOT NULL,
            source_url_original TEXT NOT NULL,
            source_model_id TEXT,
            source_collection_id TEXT,
            title TEXT,
            creator_name TEXT,
            creator_url TEXT,
            description_raw TEXT,
            thumbnail_url TEXT,
            media_manifest_json TEXT NOT NULL DEFAULT '[]',
            file_manifest_json TEXT NOT NULL DEFAULT '[]',
            confidence TEXT NOT NULL DEFAULT 'none',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            review_state TEXT NOT NULL DEFAULT 'pending',
            import_job_id TEXT,
            captured_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_source_intake_records_provider_model
        ON source_intake_records(provider_id, source_model_id)
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_source_intake_records_review_state
        ON source_intake_records(review_state, captured_at DESC)
        """,
            """
        CREATE TABLE IF NOT EXISTS source_collection_snapshots (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            source_collection_id TEXT NOT NULL,
            source_collection_url TEXT,
            collection_title TEXT,
            item_count INTEGER NOT NULL DEFAULT 0,
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            sync_cursor TEXT,
            captured_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_source_collection_snapshots_provider_collection
        ON source_collection_snapshots(provider_id, source_collection_id)
        """,
            """
        CREATE TABLE IF NOT EXISTS source_import_jobs (
            id TEXT PRIMARY KEY,
            intake_record_id TEXT,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            result_json TEXT NOT NULL DEFAULT '{}',
            error_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (intake_record_id) REFERENCES source_intake_records(id)
                ON DELETE SET NULL
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_source_import_jobs_status
        ON source_import_jobs(status, created_at DESC)
        """,
        ),
    ),
    (
        37,
        (
            """
        CREATE TABLE IF NOT EXISTS model_catalog_project_tasks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            due_at TEXT,
            source_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES model_catalog_projects(id)
                ON DELETE CASCADE
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_project_tasks_project_id
        ON model_catalog_project_tasks(project_id, status, updated_at DESC)
        """,
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
        if version == 23:
            _repair_unified_queue_file_units_foreign_key(connection)
        if version == 35:
            ensure_column(connection, "unified_queue_entries", "estimate_metadata_json", "TEXT NOT NULL DEFAULT '{}' ")
        if version == 36:
            ensure_column(connection, "model_catalog_projects", "status", "TEXT NOT NULL DEFAULT 'evaluating'")
            ensure_column(connection, "model_catalog_projects", "project_type", "TEXT")
            ensure_column(connection, "model_catalog_projects", "origin", "TEXT")
            ensure_column(connection, "model_catalog_projects", "origin_url", "TEXT")
            ensure_column(connection, "model_catalog_projects", "completed_at", "TEXT")
            ensure_column(connection, "model_catalog_projects", "created_by", "TEXT")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_catalog_project_memberships (
                    project_id INTEGER NOT NULL,
                    model_ref TEXT NOT NULL,
                    member_state TEXT NOT NULL DEFAULT 'candidate',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, model_ref),
                    FOREIGN KEY (project_id) REFERENCES model_catalog_projects(id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_model_catalog_projects_status
                ON model_catalog_projects(status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_model_catalog_project_memberships_model_ref
                ON model_catalog_project_memberships(model_ref)
                """
            )
            connection.execute(
                """
                UPDATE model_catalog_projects
                SET status = CASE
                    WHEN archived_at IS NOT NULL THEN 'archived'
                    ELSE COALESCE(NULLIF(TRIM(status), ''), 'evaluating')
                END
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO model_catalog_project_memberships (
                    project_id, model_ref, member_state, created_at, updated_at
                )
                SELECT
                    CAST(json_extract(cf.field_value_json, '$') AS INTEGER),
                    cf.entity_id,
                    'candidate',
                    COALESCE(cf.updated_at, datetime('now')),
                    COALESCE(cf.updated_at, datetime('now'))
                FROM model_catalog_custom_fields cf
                JOIN model_catalog_projects p
                    ON p.id = CAST(json_extract(cf.field_value_json, '$') AS INTEGER)
                WHERE cf.entity_type = 'model'
                  AND cf.field_key = 'project_id'
                  AND json_type(cf.field_value_json, '$') IN ('integer', 'text')
                  AND CAST(json_extract(cf.field_value_json, '$') AS INTEGER) > 0
                """
            )
            working_groups_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'working_groups'"
            ).fetchone()
            if working_groups_exists is not None:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO model_catalog_project_memberships (
                        project_id, model_ref, member_state, created_at, updated_at
                    )
                    SELECT
                        project_id,
                        'working-group-' || CAST(id AS TEXT),
                        'candidate',
                        COALESCE(updated_at, datetime('now')),
                        COALESCE(updated_at, datetime('now'))
                    FROM working_groups
                    WHERE project_id IS NOT NULL
                    """
                )
        if version == 37:
            ensure_column(connection, "model_catalog_projects", "task_backend", "TEXT NOT NULL DEFAULT 'none'")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_catalog_project_tasks (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    due_at TEXT,
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES model_catalog_projects(id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_model_catalog_project_tasks_project_id
                ON model_catalog_project_tasks(project_id, status, updated_at DESC)
                """
            )
            connection.execute(
                """
                UPDATE model_catalog_projects
                SET task_backend = COALESCE(NULLIF(TRIM(task_backend), ''), 'none')
                """
            )
        connection.execute(
            "INSERT INTO model_catalog_schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
            (version,),
        )
        applied.add(version)

    # Always run FK drift repair after migration application, even when no
    # migration versions are pending. Some deployed DBs can retain stale
    # references to temporary renamed entry tables from prior schema upgrades.
    _repair_project_task_schema(connection)
    _repair_unified_queue_file_units_foreign_key(connection)


def _repair_project_task_schema(connection: sqlite3.Connection) -> None:
    """Repair stale version-37 bookkeeping when project task schema is missing.

    Some deployed databases recorded migration 37 as applied even though the
    task_backend column and task table were never created. Re-assert the schema
    slice on every startup so those databases self-heal during bootstrap.
    """
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='model_catalog_projects'"
    ).fetchone()
    if row is None:
        return

    ensure_column(connection, "model_catalog_projects", "task_backend", "TEXT NOT NULL DEFAULT 'none'")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS model_catalog_project_tasks (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            due_at TEXT,
            source_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES model_catalog_projects(id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_model_catalog_project_tasks_project_id
        ON model_catalog_project_tasks(project_id, status, updated_at DESC)
        """
    )
    connection.execute(
        """
        UPDATE model_catalog_projects
        SET task_backend = COALESCE(NULLIF(TRIM(task_backend), ''), 'none')
        """
    )


def _repair_unified_queue_file_units_foreign_key(connection: sqlite3.Connection) -> None:
    """Repair unified_queue_file_units FK drift to temporary entry tables.

    In some databases, SQLite rewrote unified_queue_file_units to reference
    temporary renamed tables during prior entry-table migrations, e.g.
    unified_queue_entries_legacy_v20 or unified_queue_entries_v23. Once those
    temp tables are dropped, inserts into unified_queue_file_units can fail with
    "no such table" errors unless we rebuild the FK back to unified_queue_entries.
    """
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='unified_queue_file_units'"
    ).fetchone()
    if row is None:
        return

    fk_rows = connection.execute("PRAGMA foreign_key_list(unified_queue_file_units)").fetchall()
    fk_targets = {str(r["table"]) for r in fk_rows}

    # Already healthy in normal/current schemas.
    if "unified_queue_entries_legacy_v20" not in fk_targets and "unified_queue_entries_v23" not in fk_targets:
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
    from .db import derive_model_key

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
        model_key = derive_model_key(
            model_url=str(row["manyfold_model_url"] or "").strip() or None,
            model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            model_id=str(row["manyfold_model_id"] or "").strip() or None,
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