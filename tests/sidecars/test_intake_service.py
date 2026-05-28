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
    get_catalog_asset_hashes,
    detect_duplicate_files,
    build_dedup_collision_warning,
    reject_orphaned_uploads,
)
from sidecars.model_catalog.app.services.intake_service import (
    get_working_file_inventory_hashes,
)
from sidecars.model_catalog.app.routers.intake_verification import (
    _read_indexed_hash_match_contexts,
)
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        catalog_base_url="http://localhost:8314",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
    )


def test_get_all_intake_queue_hashes_reads_inflight_only(tmp_path: Path) -> None:
    """Test that get_all_intake_queue_hashes only reads hashes from in-flight uploads."""
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


def test_get_all_intake_queue_hashes_excludes_terminal_inbox_states(tmp_path: Path) -> None:
    """Terminal inbox_state uploads are excluded — their files live in inventory tables."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        active_hash = "active_hash_aaa"
        published_hash = "published_hash_bbb"
        rejected_hash = "rejected_hash_ccc"
        grouped_hash = "grouped_hash_ddd"

        for upload_id, status, inbox_state, file_hash in [
            ("upload-active", "queued", "submitted", active_hash),
            ("upload-published", "verified", "published_by_destination", published_hash),
            ("upload-rejected", "verified", "rejected", rejected_hash),
            ("upload-grouped", "verified", "grouped_new", grouped_hash),
        ]:
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, inbox_state, source_entries_json, file_hashes_json,
                    verification_status, cleanup_policy, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (upload_id, status, inbox_state, "{}", json.dumps([file_hash]), "unverified", "keep", now, now),
            )
        connection.commit()
    finally:
        connection.close()

    hashes = get_all_intake_queue_hashes(settings.db_path)
    assert active_hash.lower() in hashes
    assert published_hash.lower() not in hashes
    assert rejected_hash.lower() not in hashes
    assert grouped_hash.lower() not in hashes
    assert len(hashes) == 1


def test_get_catalog_asset_hashes_reads_published_assets(tmp_path: Path) -> None:
    """Test that get_catalog_asset_hashes reads hashes from non-archived catalog entries."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        live_hash = "catalog_hash_live"
        archived_hash = "catalog_hash_archived"

        # Create a live catalog entry
        connection.execute(
            """
            INSERT INTO model_catalog_entries (
                local_model_id, model_name, source_origin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("model-live", "Live Model", "local", now, now),
        )
        live_entry_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])

        # Create an archived catalog entry
        connection.execute(
            """
            INSERT INTO model_catalog_entries (
                local_model_id, model_name, source_origin, created_at, updated_at, archived_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("model-archived", "Archived Model", "local", now, now, now),
        )
        archived_entry_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])

        # Add assets to both entries
        for entry_id, asset_id, file_hash in [
            (live_entry_id, "asset-live", live_hash),
            (archived_entry_id, "asset-archived", archived_hash),
        ]:
            connection.execute(
                """
                INSERT INTO model_catalog_assets (
                    model_catalog_entry_id, asset_id, asset_filename, asset_type, asset_role,
                    file_hash, storage_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry_id, asset_id, "model.3mf", "model", "primary", file_hash, "/tmp/model.3mf", now, now),
            )
        connection.commit()
    finally:
        connection.close()

    hashes = get_catalog_asset_hashes(settings.db_path)
    assert live_hash.lower() in hashes
    assert archived_hash.lower() not in hashes
    assert len(hashes) == 1


def test_working_file_inventory_hashes_respects_exclude_source_paths(tmp_path: Path) -> None:
    """Regression: files chosen from under the Working Files root must not
    self-match their own `working_file_inventory` row as a duplicate.

    The intake wizard now allows browsing the Working Files store as an
    intake source. Validation must exclude the inventory rows corresponding
    to the source paths being submitted so the file's own hash isn't
    reported as a `working_group_hash_match` against itself.
    """
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    now = "2026-04-30T00:00:00Z"
    self_path_raw = r"C:\WorkingFiles\Subfolder\widget.3mf"
    self_compare_key = self_path_raw.replace("\\", "/").lower()
    self_hash = "a" * 64
    other_hash = "b" * 64

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO working_file_inventory (
                source_path_raw, source_path_canonical, source_path_compare_key,
                file_name_raw, file_name_base_hint, file_extension, file_size_bytes,
                sha256_hash, detected_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self_path_raw,
                self_path_raw,
                self_compare_key,
                "widget.3mf",
                "widget",
                ".3mf",
                1024,
                self_hash,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO working_file_inventory (
                source_path_raw, source_path_canonical, source_path_compare_key,
                file_name_raw, file_name_base_hint, file_extension, file_size_bytes,
                sha256_hash, detected_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r"C:\WorkingFiles\Other\gadget.3mf",
                r"C:\WorkingFiles\Other\gadget.3mf",
                r"c:/workingfiles/other/gadget.3mf",
                "gadget.3mf",
                "gadget",
                ".3mf",
                2048,
                other_hash,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    # Without exclusion: both hashes are present.
    all_hashes = get_working_file_inventory_hashes(settings.db_path)
    assert self_hash in all_hashes
    assert other_hash in all_hashes

    # With self-exclusion: only the other file's hash remains, so the
    # submitted file will not flag as a duplicate of itself.
    filtered = get_working_file_inventory_hashes(
        settings.db_path,
        exclude_source_paths={self_compare_key},
    )
    assert self_hash not in filtered
    assert other_hash in filtered

    # The combined indexed-hash helper threads the exclusion through.
    combined = get_all_indexed_file_hashes(
        settings.db_path,
        exclude_source_paths={self_compare_key},
    )
    assert self_hash not in combined
    assert other_hash in combined


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


def test_queue_hash_helpers_can_exclude_current_upload(tmp_path: Path) -> None:
    """Regression: validation must not flag the current queue item as its own duplicate."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-30T00:00:00Z"
        self_hash = "self_hash_123"
        other_hash = "other_hash_456"

        for upload_id, file_hash, path in [
            ("upload-self", self_hash, "/data/.source_intake/self/makerworld-1021562.3mf"),
            ("upload-other", other_hash, "/data/.source_intake/other/existing.3mf"),
        ]:
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, source_entries_json, file_hashes_json,
                    verification_status, cleanup_policy, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    "queued",
                    json.dumps([
                        {"path": path, "type": "file", "source_type": "makerworld_download"}
                    ]),
                    json.dumps([file_hash]),
                    "unverified",
                    "keep",
                    now,
                    now,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    all_hashes = get_all_intake_queue_hashes(settings.db_path)
    assert self_hash in all_hashes
    assert other_hash in all_hashes

    filtered_hashes = get_all_intake_queue_hashes(
        settings.db_path,
        exclude_upload_id="upload-self",
    )
    assert self_hash not in filtered_hashes
    assert other_hash in filtered_hashes

    combined_hashes = get_all_indexed_file_hashes(
        settings.db_path,
        exclude_upload_id="upload-self",
    )
    assert self_hash not in combined_hashes
    assert other_hash in combined_hashes

    contexts = _read_indexed_hash_match_contexts(
        settings.db_path,
        exclude_upload_id="upload-self",
    )
    assert self_hash not in contexts
    assert contexts[other_hash][0]["parent_name"] == "Queued intake (upload-o)"


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
    assert "catalog or working inventory" in warning["message"]
    
    # Test batch-local collision
    warning2 = build_dedup_collision_warning(file_item, collision_type="batch_local")
    assert warning2["collision_type"] == "batch_local"
    assert "current batch" in warning2["message"]


def test_reject_orphaned_uploads_cleans_active_states(tmp_path: Path) -> None:
    """Startup cleanup should reject uploads in any active inbox_state."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    now = "2026-05-01T00:00:00Z"
    connection = sqlite3.connect(settings.db_path)
    try:
        for uid, inbox_state in [
            ("orphan-submitted", "submitted"),
            ("orphan-validated", "validated_ready"),
            ("orphan-warning", "validated_warning"),
            ("orphan-deferred", "deferred"),
        ]:
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, source_entries_json, file_hashes_json,
                    verification_status, cleanup_policy, inbox_state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uid, "queued", "{}", "[]", "unverified", "keep", inbox_state, now, now),
            )
        connection.commit()
    finally:
        connection.close()

    count = reject_orphaned_uploads(settings.db_path)
    assert count == 4

    # Verify all rows are now rejected
    connection = sqlite3.connect(settings.db_path)
    try:
        rows = connection.execute(
            "SELECT upload_id, inbox_state, terminal_action, decision_note FROM intake_queue_uploads ORDER BY upload_id"
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        assert row[1] == "rejected"
        assert row[2] == "auto_rejected_startup"
        assert "orphaned" in row[3].lower()


def test_reject_orphaned_uploads_leaves_terminal_states(tmp_path: Path) -> None:
    """Uploads already in terminal states must not be touched."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    now = "2026-05-01T00:00:00Z"
    connection = sqlite3.connect(settings.db_path)
    try:
        for uid, inbox_state in [
            ("terminal-grouped", "grouped_new"),
            ("terminal-published", "published_to_catalog"),
            ("terminal-rejected", "rejected"),
        ]:
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, source_entries_json, file_hashes_json,
                    verification_status, cleanup_policy, inbox_state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uid, "queued", "{}", "[]", "unverified", "keep", inbox_state, now, now),
            )
        connection.commit()
    finally:
        connection.close()

    count = reject_orphaned_uploads(settings.db_path)
    assert count == 0


def test_reject_orphaned_uploads_handles_default_inbox_state(tmp_path: Path) -> None:
    """Uploads with default inbox_state ('submitted') get rejected on startup."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    now = "2026-05-01T00:00:00Z"
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, file_hashes_json,
                verification_status, cleanup_policy,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("default-state", "queued", "{}", "[]", "unverified", "keep", now, now),
        )
        connection.commit()
    finally:
        connection.close()

    count = reject_orphaned_uploads(settings.db_path)
    assert count == 1
