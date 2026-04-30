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


def get_all_intake_queue_hashes(db_path: Path | str) -> set[str]:
    """
    Read all file hashes from intake queue uploads.
    
    Scans the intake_queue_uploads table for all file_hashes_json entries
    (which is a JSON array of file hashes) and returns a flattened set.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Set of SHA256 hex strings (lowercase) from queue uploads
    """
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hashes_json FROM intake_queue_uploads WHERE file_hashes_json IS NOT NULL"
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


def get_all_indexed_file_hashes(db_path: Path | str) -> set[str]:
    """
    Get all indexed file hashes (working items + intake queue).
    
    Combines hashes from:
    1. working_items (already grouped and imported)
    2. intake_queue_uploads (files in intake pipeline)
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Set of SHA256 hex strings (lowercase) from all indexed files
    """
    working_hashes = get_working_items_hashes(db_path)
    queue_hashes = get_all_intake_queue_hashes(db_path)
    return working_hashes | queue_hashes


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
        "message": f"File hash already exists ({'in working items or intake queue' if collision_type == 'indexed' else 'in current batch'})",
        "collision_type": collision_type,
    }


if __name__ == "__main__":
    # Quick test
    print("intake_service module imported successfully")
