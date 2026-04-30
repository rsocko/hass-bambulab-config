"""
Tests for intake_service module.

Tests the deduplication service layer used in bulk discover/import and intake workflows.
"""

from __future__ import annotations

import json
import sqlite3
import hashlib
from pathlib import Path

import pytest

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.services import (
    get_all_indexed_file_hashes,
    get_all_intake_queue_hashes,
    get_working_items_hashes,
    detect_duplicate_files,
    build_dedup_collision_warning,
)
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="client-id",
        manyfold_client_secret="client-secret",
        manyfold_oauth_scopes="public read",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
    )


def test_get_working_items_hashes_reads_from_working_items_table(tmp_path: Path) -> None:
    """Test that get_working_items_hashes correctly reads hashes from working_items."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        # Create a working group
        connection.execute(
            """
            INSERT INTO working_groups (
                slug, title, stage, notes, primary_file_path, folder_hint,
                related_manyfold_model_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("test_group", "Test Group", "draft", None, "/tmp/test.3mf", "/tmp", None, now, now),
        )
        group_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        
        # Add working items with hashes
        hash1 = "abc123def456"
        hash2 = "xyz789uvw012"
        connection.execute(
            """
            INSERT INTO working_items (
                working_group_id, file_path, item_role, created_at, updated_at,
                file_hash, file_size, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, "/tmp/test1.3mf", "primary", now, now, hash1, 1000, "{}"),
        )
        connection.execute(
            """
            INSERT INTO working_items (
                working_group_id, file_path, item_role, created_at, updated_at,
                file_hash, file_size, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, "/tmp/test2.3mf", "supporting", now, now, hash2, 2000, "{}"),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Test the function
    hashes = get_working_items_hashes(settings.db_path)
    assert hash1.lower() in hashes
    assert hash2.lower() in hashes
    assert len(hashes) == 2


def test_get_all_intake_queue_hashes_reads_from_intake_table(tmp_path: Path) -> None:
    """Test that get_all_intake_queue_hashes correctly reads hashes from intake_queue_uploads."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        hash1 = "intake_hash_111"
        hash2 = "intake_hash_222"
        
        # Add uploads with hashes
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-1",
                "queued",
                "{}",
                json.dumps([hash1]),
                "unverified",
                "keep",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-2",
                "uploaded_unverified",
                "{}",
                json.dumps([hash2]),
                "unverified",
                "keep",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Test the function
    hashes = get_all_intake_queue_hashes(settings.db_path)
    assert hash1.lower() in hashes
    assert hash2.lower() in hashes
    assert len(hashes) == 2


def test_get_all_indexed_file_hashes_combines_working_and_queue_hashes(tmp_path: Path) -> None:
    """Test that get_all_indexed_file_hashes combines both working items and queue hashes."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        
        # Add a working group with items
        connection.execute(
            """
            INSERT INTO working_groups (
                slug, title, stage, notes, primary_file_path, folder_hint,
                related_manyfold_model_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("test_group", "Test Group", "draft", None, "/tmp/test.3mf", "/tmp", None, now, now),
        )
        group_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        
        working_hash = "working_hash_123"
        connection.execute(
            """
            INSERT INTO working_items (
                working_group_id, file_path, item_role, created_at, updated_at,
                file_hash, file_size, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, "/tmp/test.3mf", "primary", now, now, working_hash, 1000, "{}"),
        )
        
        # Add intake queue upload
        queue_hash = "queue_hash_456"
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-1",
                "queued",
                "{}",
                json.dumps([queue_hash]),
                "unverified",
                "keep",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Test the function
    all_hashes = get_all_indexed_file_hashes(settings.db_path)
    assert working_hash.lower() in all_hashes
    assert queue_hash.lower() in all_hashes
    assert len(all_hashes) == 2


def test_detect_duplicate_files_catches_indexed_collisions(tmp_path: Path) -> None:
    """Test that detect_duplicate_files identifies hashes that exist in indexed files."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        
        # Add a working group with an item
        connection.execute(
            """
            INSERT INTO working_groups (
                slug, title, stage, notes, primary_file_path, folder_hint,
                related_manyfold_model_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("test_group", "Test Group", "draft", None, "/tmp/test.3mf", "/tmp", None, now, now),
        )
        group_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        
        existing_hash = "already_exists_123"
        connection.execute(
            """
            INSERT INTO working_items (
                working_group_id, file_path, item_role, created_at, updated_at,
                file_hash, file_size, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (group_id, "/tmp/test.3mf", "primary", now, now, existing_hash, 1000, "{}"),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Create files to import
    files_to_import = [
        {"path": "/new/file1.3mf", "sha256": "new_hash_111"},
        {"path": "/new/file2.3mf", "sha256": existing_hash},  # This should be flagged as duplicate
        {"path": "/new/file3.3mf", "sha256": "new_hash_222"},
    ]
    
    # Test the function
    unique, duplicates = detect_duplicate_files(files_to_import, settings.db_path)
    
    assert len(unique) == 2
    assert len(duplicates) == 1
    assert duplicates[0]["hash"].lower() == existing_hash.lower()
    assert duplicates[0]["collision_type"] == "indexed"


def test_detect_duplicate_files_catches_queue_collisions(tmp_path: Path) -> None:
    """Test that detect_duplicate_files identifies hashes in the intake queue."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        
        # Add intake queue upload with a hash
        queue_hash = "queue_hash_789"
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-1",
                "queued",
                "{}",
                json.dumps([queue_hash]),
                "unverified",
                "keep",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Create files to import
    files_to_import = [
        {"path": "/new/file1.3mf", "sha256": "new_hash_111"},
        {"path": "/new/file2.3mf", "sha256": queue_hash},  # This should be flagged as duplicate from queue
    ]
    
    # Test the function
    unique, duplicates = detect_duplicate_files(files_to_import, settings.db_path)
    
    assert len(unique) == 1
    assert len(duplicates) == 1
    assert duplicates[0]["hash"].lower() == queue_hash.lower()
    assert duplicates[0]["collision_type"] == "indexed"


def test_detect_duplicate_files_catches_batch_local_collisions(tmp_path: Path) -> None:
    """Test that detect_duplicate_files identifies hashes already seen in the same batch."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    # Create files to import with duplicate in same batch
    files_to_import = [
        {"path": "/new/file1.3mf", "sha256": "batch_hash_aaa"},
        {"path": "/new/file2.3mf", "sha256": "batch_hash_bbb"},
        {"path": "/new/file3.3mf", "sha256": "batch_hash_aaa"},  # Same as first file
    ]
    
    batch_hashes: set[str] = set()
    unique, duplicates = detect_duplicate_files(files_to_import, settings.db_path, batch_hashes)
    
    assert len(unique) == 2
    assert len(duplicates) == 1
    assert duplicates[0]["hash"].lower() == "batch_hash_aaa"
    assert duplicates[0]["collision_type"] == "batch_local"


def test_build_dedup_collision_warning_formats_correctly(tmp_path: Path) -> None:
    """Test that build_dedup_collision_warning creates properly formatted warnings."""
    file_item = {
        "path": "/tmp/model.3mf",
        "sha256": "abc123def456",
        "size_bytes": 1024,
    }
    
    # Test indexed collision
    warning = build_dedup_collision_warning(file_item, collision_type="indexed")
    assert warning["type"] == "duplicate_hash"
    assert warning["path"] == "/tmp/model.3mf"
    assert warning["sha256"] == "abc123def456"
    assert warning["collision_type"] == "indexed"
    assert "working items or intake queue" in warning["message"]
    
    # Test batch-local collision
    warning2 = build_dedup_collision_warning(file_item, collision_type="batch_local")
    assert warning2["collision_type"] == "batch_local"
    assert "current batch" in warning2["message"]


def test_bulk_discover_detects_queue_duplicates(tmp_path: Path) -> None:
    """Integration test: bulk discover should detect duplicates in intake queue."""
    from sidecars.model_catalog.app.main import create_app
    from fastapi.testclient import TestClient
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    # Create a file in intake queue
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        queue_file_content = b"queue file content"
        queue_file_hash = hashlib.sha256(queue_file_content).hexdigest()
        
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-1",
                "queued",
                "{}",
                json.dumps([queue_file_hash]),
                "unverified",
                "keep",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Create a file to discover with same hash
    discover_root = tmp_path / "discover"
    discover_root.mkdir()
    duplicate_file = discover_root / "duplicate.3mf"
    duplicate_file.write_bytes(queue_file_content)
    
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/working-groups/bulk-discover",
            json={
                "folder_path": str(discover_root),
                "grouping_strategy": "flat",
            },
        )
    
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    # The duplicate file should be flagged
    assert payload["summary"]["duplicate_warning_count"] >= 1
    proposal = payload["proposals"][0]
    assert proposal["duplicate_count"] >= 1
    assert proposal["files"][0]["duplicate_hash"] is True


def test_bulk_import_deduplicates_against_queue(tmp_path: Path) -> None:
    """Integration test: bulk import should skip files that are in intake queue."""
    from sidecars.model_catalog.app.main import create_app
    from fastapi.testclient import TestClient
    
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    
    # Create a file in intake queue
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        queue_file_content = b"queue file content"
        queue_file_hash = hashlib.sha256(queue_file_content).hexdigest()
        
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "upload-1",
                "queued",
                "{}",
                json.dumps([queue_file_hash]),
                "unverified",
                "keep",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    
    # Create files to import
    import_root = tmp_path / "import"
    import_root.mkdir()
    duplicate_file = import_root / "duplicate.3mf"
    duplicate_file.write_bytes(queue_file_content)
    unique_file = import_root / "unique.3mf"
    unique_file.write_bytes(b"unique content")
    
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/working-groups/bulk-import",
            json={
                "source_folder": str(import_root),
                "grouping_strategy": "flat",
                "proposals": [
                    {
                        "proposal_id": "import-1",
                        "title": "Import Test",
                        "action": "import",
                        "files": [
                            {"path": str(duplicate_file), "sha256": queue_file_hash},
                            {"path": str(unique_file), "sha256": hashlib.sha256(b"unique content").hexdigest()},
                        ],
                    }
                ],
            },
        )
    
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    # The duplicate file should be skipped
    assert payload["duplicate_skipped_count"] >= 1
    # But the unique file should be imported
    assert payload["created_item_count"] >= 1
