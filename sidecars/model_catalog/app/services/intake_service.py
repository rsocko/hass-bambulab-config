"""
Intake workflow service for model catalog.

Provides business logic for intake queue operations, deduplication,
and working group creation from ingested items.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from sqlite3 import connect
from typing import Any


# Intake queue statuses considered "in-flight" — the upload has been submitted
# but its files have NOT yet landed in a destination table (working_items or
# model_catalog_assets).  Terminal statuses like 'committed', 'cleanup_done',
# etc. are excluded because their files are already represented in inventory.
_INFLIGHT_INTAKE_STATUSES = (
    "queued",
    "verified",
    "uploaded_unverified",
    "uploaded_verified",
)


def get_all_intake_queue_hashes(db_path: Path | str) -> set[str]:
    """
    Read file hashes from **in-flight** intake queue uploads only.

    Only uploads whose status indicates they have NOT yet been committed to a
    destination (working group or catalog) are included.  Terminal-status
    uploads (committed, published, cleanup_done, …) are excluded because their
    files are already represented in the inventory tables (working_items /
    model_catalog_assets).

    Args:
        db_path: Path to SQLite database

    Returns:
        Set of SHA256 hex strings (lowercase) from in-flight queue uploads
    """
    connection = connect(db_path)
    try:
        placeholders = ", ".join("?" for _ in _INFLIGHT_INTAKE_STATUSES)
        rows = connection.execute(
            f"""
            SELECT file_hashes_json
            FROM intake_queue_uploads
            WHERE file_hashes_json IS NOT NULL
              AND status IN ({placeholders})
            """,
            _INFLIGHT_INTAKE_STATUSES,
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


def get_working_items_hashes(db_path: Path | str) -> set[str]:
    """
    Read all file hashes from working items.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Set of SHA256 hex strings (lowercase) from working items
    """
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hash FROM working_items WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''"
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
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


def get_all_indexed_file_hashes(db_path: Path | str) -> set[str]:
    """
    Get all indexed file hashes from actual inventory + in-flight imports.

    Combines hashes from three sources:
    1. working_items — files currently in working groups (inventory)
    2. model_catalog_assets — files published to the catalog (inventory)
    3. intake_queue_uploads — files in the intake pipeline that have NOT
       yet been committed to a destination (in-flight only)

    Terminal-status intake records (committed, published, cleanup_done) are
    excluded because their files are already represented in sources 1 or 2.
    This prevents ghost hashes from blocking re-import after a working group
    or catalog entry is deleted.

    Args:
        db_path: Path to SQLite database

    Returns:
        Set of SHA256 hex strings (lowercase) from inventory + in-flight
    """
    working_hashes = get_working_items_hashes(db_path)
    catalog_hashes = get_catalog_asset_hashes(db_path)
    inflight_hashes = get_all_intake_queue_hashes(db_path)
    return working_hashes | catalog_hashes | inflight_hashes


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


if __name__ == "__main__":
    # Quick test
    print("intake_service module imported successfully")
