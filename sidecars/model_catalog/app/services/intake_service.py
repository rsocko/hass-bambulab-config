"""
Intake workflow service for model catalog.

Provides business logic for intake queue operations, deduplication,
and working group creation from ingested items.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import connect
from typing import Any

from .intake_eligibility_service import ACTIVE_QUEUE_STATES, TERMINAL_STATES

logger = logging.getLogger(__name__)

# Intake uploads in a terminal inbox_state have already landed their files in
# a destination table (working_items or model_catalog_assets).  Exclude them
# from dedup so that deleting a working group or catalog entry lets you
# re-import the same files without ghost hash collisions.
_TERMINAL_INBOX_STATES = tuple(sorted(TERMINAL_STATES))


def get_all_intake_queue_hashes(
    db_path: Path | str,
    *,
    exclude_upload_id: str | None = None,
) -> set[str]:
    """
    Read file hashes from **in-flight** intake queue uploads only.

    Only uploads whose inbox_state indicates they have NOT yet reached a
    terminal workflow state are included.  Terminal-state uploads
    (grouped_new, published_by_destination, rejected, …) are excluded
    because their files are already represented in the inventory tables
    (working_items / model_catalog_assets).

    Args:
        db_path: Path to SQLite database
        exclude_upload_id: Optional upload ID to exclude from the in-flight
            queue hash set. Used by intake validation to prevent an upload
            from matching its own persisted hash as a duplicate.

    Returns:
        Set of SHA256 hex strings (lowercase) from in-flight queue uploads
    """
    connection = connect(db_path)
    try:
        placeholders = ", ".join("?" for _ in _TERMINAL_INBOX_STATES)
        if exclude_upload_id:
            rows = connection.execute(
                f"""
                SELECT file_hashes_json
                FROM intake_queue_uploads
                WHERE file_hashes_json IS NOT NULL
                  AND upload_id != ?
                  AND COALESCE(inbox_state, 'submitted') NOT IN ({placeholders})
                """,
                (exclude_upload_id, *_TERMINAL_INBOX_STATES),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                SELECT file_hashes_json
                FROM intake_queue_uploads
                WHERE file_hashes_json IS NOT NULL
                  AND COALESCE(inbox_state, 'submitted') NOT IN ({placeholders})
                """,
                _TERMINAL_INBOX_STATES,
            ).fetchall()
        all_hashes: set[str] = set()
        for row in rows:
            file_hashes_json = str(row[0] or "").strip()
            if file_hashes_json:
                try:
                    hashes = json.loads(file_hashes_json)
                    if isinstance(hashes, list):
                        for h in hashes:
                            hash_str = str(h or "").strip().lower()
                            if hash_str:
                                all_hashes.add(hash_str)
                except (json.JSONDecodeError, ValueError):
                    pass
        return all_hashes
    finally:
        connection.close()


def get_working_file_inventory_hashes(
    db_path: Path | str,
    *,
    exclude_source_paths: set[str] | None = None,
) -> set[str]:
    """
    Read all file hashes from the folder-first working file inventory.

    Used so duplicate-validation also covers files published to the
    folder-first Working Files store (not just legacy working_items rows).

    Args:
        db_path: Path to SQLite database.
        exclude_source_paths: Optional set of normalized
            ``source_path_compare_key`` values to ignore. Used by the intake
            validation flow to prevent files selected from under the Working
            Files root from self-matching their own inventory entry (which
            would otherwise surface as a false-positive duplicate).
    """
    connection = connect(db_path)
    try:
        if exclude_source_paths:
            keys = [str(key) for key in exclude_source_paths if str(key or "").strip()]
        else:
            keys = []
        if keys:
            placeholders = ", ".join("?" for _ in keys)
            rows = connection.execute(
                f"""
                SELECT sha256_hash
                FROM working_file_inventory
                WHERE sha256_hash IS NOT NULL
                  AND TRIM(sha256_hash) != ''
                  AND source_path_compare_key NOT IN ({placeholders})
                """,
                keys,
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT sha256_hash FROM working_file_inventory WHERE sha256_hash IS NOT NULL AND TRIM(sha256_hash) != ''"
            ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    except sqlite3.OperationalError:
        return set()
    finally:
        connection.close()


def get_catalog_asset_hashes(db_path: Path | str) -> set[str]:
    """
    Read all file hashes from published catalog assets.

    Scans the model_catalog_assets table for non-archived entries and returns
    a set of their SHA256 hashes.  This represents files that have been
    committed to the local catalog.

    Args:
        db_path: Path to SQLite database

    Returns:
        Set of SHA256 hex strings (lowercase) from catalog assets
    """
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT a.file_hash
            FROM model_catalog_assets a
            JOIN model_catalog_entries e ON e.id = a.model_catalog_entry_id
            WHERE a.file_hash IS NOT NULL
              AND TRIM(a.file_hash) != ''
              AND e.archived_at IS NULL
            """
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    except sqlite3.OperationalError:
        # Table may not exist in older databases
        return set()
    finally:
        connection.close()


def get_all_indexed_file_hashes(
    db_path: Path | str,
    *,
    exclude_source_paths: set[str] | None = None,
    exclude_upload_id: str | None = None,
) -> set[str]:
    """
    Get all indexed file hashes from actual inventory + in-flight imports.

    Combines hashes from three sources:
    1. working_file_inventory — files currently in the working files store (inventory)
    2. model_catalog_assets — files published to the catalog (inventory)
    3. intake_queue_uploads — files in the intake pipeline that have NOT
       yet been committed to a destination (in-flight only)

    Terminal-status intake records (committed, published, cleanup_done) are
    excluded because their files are already represented in sources 1 or 2.
    This prevents ghost hashes from blocking re-import after a working group
    or catalog entry is deleted.

    Args:
        db_path: Path to SQLite database
        exclude_source_paths: Optional set of normalized
            ``source_path_compare_key`` values whose
            ``working_file_inventory`` rows should be excluded. Used by the
            intake validation path so files chosen from inside the Working
            Files root do not self-match their own inventory entry as a
            duplicate.
        exclude_upload_id: Optional upload ID to exclude from the in-flight
            queue hash set. Used by intake validation to prevent an upload
            from matching its own queue record as a duplicate.

    Returns:
        Set of SHA256 hex strings (lowercase) from inventory + in-flight
    """
    inventory_hashes = get_working_file_inventory_hashes(
        db_path, exclude_source_paths=exclude_source_paths
    )
    catalog_hashes = get_catalog_asset_hashes(db_path)
    inflight_hashes = get_all_intake_queue_hashes(
        db_path,
        exclude_upload_id=exclude_upload_id,
    )
    return inventory_hashes | catalog_hashes | inflight_hashes


def detect_duplicate_files(
    files_to_import: list[dict[str, Any]],
    db_path: Path | str,
    existing_batch_hashes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Detect duplicate files in a proposed import batch.
    
    Compares file hashes against:
    1. Already-indexed working items
    2. Intake queue uploads
    3. Already-processed batch items (if provided)
    
    Args:
        files_to_import: List of file dicts with 'path', 'sha256' keys
        db_path: Path to SQLite database
        existing_batch_hashes: Optional set of hashes already seen in this batch
        
    Returns:
        Tuple of (unique_files, duplicates) where:
        - unique_files: Files that don't conflict with indexed hashes
        - duplicates: Files that have hash collisions
    """
    if existing_batch_hashes is None:
        existing_batch_hashes = set()
    
    indexed_hashes = get_all_indexed_file_hashes(db_path)
    unique_files: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    
    for file_item in files_to_import:
        file_hash = str(file_item.get("sha256") or "").strip().lower()
        if not file_hash:
            # No hash available; assume unique for now
            unique_files.append(file_item)
            continue
        
        # Check against indexed hashes and batch-local hashes
        if file_hash in indexed_hashes or file_hash in existing_batch_hashes:
            duplicates.append({
                "file": file_item,
                "reason": "duplicate_hash",
                "hash": file_hash,
                "collision_type": "indexed" if file_hash in indexed_hashes else "batch_local",
            })
        else:
            unique_files.append(file_item)
            existing_batch_hashes.add(file_hash)
    
    return unique_files, duplicates


def build_dedup_collision_warning(
    file_item: dict[str, Any],
    collision_type: str = "indexed",
) -> dict[str, Any]:
    """
    Build a collision warning object for the operator.
    
    Args:
        file_item: File dict with path and metadata
        collision_type: "indexed" (working items) or "batch_local" (already seen in batch)
        
    Returns:
        Formatted warning dict
    """
    return {
        "type": "duplicate_hash",
        "path": str(file_item.get("path") or "").strip(),
        "sha256": str(file_item.get("sha256") or "").strip().lower(),
        "message": f"File hash already exists ({'in catalog or working inventory' if collision_type == 'indexed' else 'in current batch'})",
        "collision_type": collision_type,
    }


def reject_orphaned_uploads(db_path: Path | str) -> int:
    """Reject intake uploads left in active states from a previous process.

    On startup, any upload still in an ``ACTIVE_QUEUE_STATES`` inbox_state
    is definitionally orphaned — the wizard session that created it no longer
    exists.  This function transitions those rows to ``rejected`` so they
    don't block future imports via hash/filename dedup collisions.

    Returns the number of uploads rejected.
    """
    active_states = tuple(sorted(ACTIVE_QUEUE_STATES))
    placeholders = ", ".join("?" for _ in active_states)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = connect(db_path)
    try:
        cursor = conn.execute(
            f"""
            UPDATE intake_queue_uploads
            SET inbox_state = 'rejected',
                terminal_action = 'auto_rejected_startup',
                terminal_at = ?,
                decision_note = 'Auto-rejected: orphaned upload from service restart',
                updated_at = ?
            WHERE inbox_state IN ({placeholders})
            """,
            (now_iso, now_iso, *active_states),
        )
        count = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if count:
        logger.warning("Startup cleanup: rejected %d orphaned intake upload(s)", count)
    else:
        logger.info("Startup cleanup: no orphaned intake uploads found")

    return count


if __name__ == "__main__":
    # Quick test
    print("intake_service module imported successfully")
