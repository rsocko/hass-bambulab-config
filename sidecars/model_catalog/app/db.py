"""Database connection factory and shared utilities.

This module provides:
- Connection pooling and factory (connect function)
- Shared dataclasses and utilities
- Centralized schema management through db_migrations
- Re-exports of all database operations for backward compatibility

Structure:
  db.py (this file) - Connection factory, shared utilities
  db_common.py - Low-level utilities (connect, utc_now_iso)
  db_migrations.py - Schema statements and migrations
  db_archive_links.py - Archive linking operations
  db_models.py - Model catalog and custom fields
  db_working.py - Working groups (schema only)
  db_intake.py - Intake queue (schema only)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .db_common import connect, utc_now_iso
from .db_migrations import (
    MIGRATION_TABLE_STATEMENT,
    MIGRATIONS,
    applied_versions,
    apply_migrations,
    current_schema_version,
    execute_statements,
    ensure_column,
)

# Re-export dataclasses for backward compatibility
from .db_archive_links import (
    ArchiveModelLink,
    CanonicalModelUrlRepairResult,
    ModelRankingInput,
    ModelRankingSnapshot,
    create_archive_link,
    deactivate_archive_link,
    delete_archive_links,
    read_all_model_ranking,
    read_archive_links,
    read_model_link_counts,
    read_model_ranking,
    read_model_ranking_inputs,
    repair_canonical_model_urls,
    refresh_archive_link_candidates,
    set_archive_link_review_state,
    update_archive_link,
    upsert_model_ranking,
)

# Re-export model functions for backward compatibility
from .db_models import (
    delete_model_field,
    read_model_field,
    read_model_fields,
    set_model_field,
)
from .db_unified_queue import (
    ReorderMove,
    UnifiedQueueEntry,
    UnifiedQueueFileUnit,
    UnifiedQueueMatchSuggestion,
    UnifiedQueuePlateUnit,
    create_unified_queue_match_suggestion,
    create_unified_queue_transition_audit,
    list_unified_queue_match_suggestions,
    read_unified_queue_match_suggestion,
    reorder_unified_queue_entries,
    create_unified_queue_entry,
    create_unified_queue_file_unit,
    create_unified_queue_plate_unit,
    delete_unified_queue_entry,
    delete_unified_queue_file_unit,
    delete_unified_queue_plate_unit,
    list_unified_queue_entries,
    list_unified_queue_file_units,
    list_unified_queue_plate_units,
    read_unified_queue_entry,
    read_unified_queue_file_unit,
    read_unified_queue_plate_unit,
    update_unified_queue_entry,
    update_unified_queue_file_unit,
    update_unified_queue_match_suggestion,
    update_unified_queue_plate_unit,
)


@dataclass(frozen=True)
class DatabaseInfo:
    path: str
    tables: tuple[str, ...]
    schema_version: int


def bootstrap_database(db_path: Path) -> DatabaseInfo:
    """Initialize database schema and return database info."""
    connection = connect(db_path)
    try:
        connection.execute(MIGRATION_TABLE_STATEMENT)
        apply_migrations(connection)
        connection.commit()
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema_version = current_schema_version(connection)
    finally:
        connection.close()
    return DatabaseInfo(path=str(db_path), tables=tuple(str(row["name"]) for row in rows), schema_version=schema_version)


def derive_manyfold_model_key(
    *,
    manyfold_model_url: str | None,
    manyfold_model_public_id: str | None,
    manyfold_model_id: str | None,
) -> str:
    """Derive a canonical model key from various identifiers."""
    public_id = str(manyfold_model_public_id or "").strip()
    if public_id:
        return f"public:{public_id}"

    model_id = str(manyfold_model_id or "").strip()
    if model_id:
        return f"id:{model_id}"

    model_url = str(manyfold_model_url or "").strip()
    if model_url:
        parsed = urlsplit(model_url)
        path = parsed.path or ""
        parts = [segment for segment in path.split("/") if segment]
        if len(parts) >= 2 and parts[-2] == "models":
            return f"url:{parts[-1]}"
        if path:
            return f"url-path:{path}"
        return f"url:{model_url}"

    return "unknown:missing-model-reference"


__all__ = [
    # Connection factory (from db_common)
    "connect",
    "utc_now_iso",
    # Database utilities
    "bootstrap_database",
    "DatabaseInfo",
    # Shared utilities
    "derive_manyfold_model_key",
    # Archive linking (re-exported for backward compatibility)
    "ArchiveModelLink",
    "CanonicalModelUrlRepairResult",
    "ModelRankingSnapshot",
    "ModelRankingInput",
    "create_archive_link",
    "update_archive_link",
    "deactivate_archive_link",
    "delete_archive_links",
    "set_archive_link_review_state",
    "refresh_archive_link_candidates",
    "read_archive_links",
    "repair_canonical_model_urls",
    "upsert_model_ranking",
    "read_model_ranking",
    "read_all_model_ranking",
    "read_model_link_counts",
    "read_model_ranking_inputs",
    # Model fields (re-exported for backward compatibility)
    "set_model_field",
    "read_model_fields",
    "read_model_field",
    "delete_model_field",
    # Unified queue operations
    "ReorderMove",
    "UnifiedQueueEntry",
    "UnifiedQueueFileUnit",
    "UnifiedQueueMatchSuggestion",
    "UnifiedQueuePlateUnit",
    "create_unified_queue_match_suggestion",
    "create_unified_queue_transition_audit",
    "read_unified_queue_match_suggestion",
    "list_unified_queue_match_suggestions",
    "update_unified_queue_match_suggestion",
    "reorder_unified_queue_entries",
    "create_unified_queue_entry",
    "read_unified_queue_entry",
    "list_unified_queue_entries",
    "update_unified_queue_entry",
    "delete_unified_queue_entry",
    "create_unified_queue_file_unit",
    "read_unified_queue_file_unit",
    "list_unified_queue_file_units",
    "update_unified_queue_file_unit",
    "delete_unified_queue_file_unit",
    "create_unified_queue_plate_unit",
    "read_unified_queue_plate_unit",
    "list_unified_queue_plate_units",
    "update_unified_queue_plate_unit",
    "delete_unified_queue_plate_unit",
    # Migrations (re-exported for backward compatibility)
    "MIGRATION_TABLE_STATEMENT",
    "MIGRATIONS",
    "applied_versions",
    "apply_migrations",
    "current_schema_version",
    "execute_statements",
    "ensure_column",
]
