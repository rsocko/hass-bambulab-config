"""Tests for #1114 — broadened archive link candidate discovery.

Covers:
- _working_group_url() identity construction
- _extract_asset_hash_map() file-level hash→asset mapping
- _build_candidate_match() scoring, deterministic detection, asset-level resolution
- _read_working_groups_for_matching() DB query with stage filtering
- _read_working_group_summaries() DB query for link display
- migrate_links_for_graduation() URL rewrite from WG to local model
- refresh_archive_link_candidates() relationship_type + model_asset_id passthrough
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# ── Module imports (path is already set by conftest.py) ──────────────────
from app.catalog_cache import CachedCatalogModel
from app.models import CatalogModelSummary
from app.routers.archive_links import (
    CandidateMatch,
    _build_candidate_match,
    _extract_asset_hash_map,
    _signal_strength,
    _working_group_url,
)
from app.db_archive_links import migrate_links_for_graduation, refresh_archive_link_candidates
from app.db_common import connect


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_summary(
    *,
    model_url: str = "local://model/test-uuid",
    name: str = "Test Model",
    entity_type: str = "model",
    public_id: str | None = None,
) -> CatalogModelSummary:
    return CatalogModelSummary(
        model_url=model_url,
        public_id=public_id or model_url.rsplit("/", 1)[-1],
        model_id=public_id or model_url.rsplit("/", 1)[-1],
        name=name,
        preview_url=None,
        creator_name=None,
        collection_names=(),
        keyword_names=(),
        entity_type=entity_type,
    )


def _make_cached_model(
    *,
    summary: CatalogModelSummary | None = None,
    files: list[dict[str, str]] | None = None,
    name: str = "Test Model",
    entity_type: str = "model",
    model_url: str = "local://model/test-uuid",
) -> CachedCatalogModel:
    if summary is None:
        summary = _make_summary(model_url=model_url, name=name, entity_type=entity_type)
    payload: dict[str, Any] = {
        "name": summary.name,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-01T00:00:00Z",
        "files": files or [],
    }
    return CachedCatalogModel(summary=summary, raw_payload=payload)


def _init_links_schema(db_path: Path) -> None:
    """Create the model_catalog_links table matching current schema (post-rename)."""
    conn = connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_catalog_links (
                id INTEGER PRIMARY KEY,
                model_url TEXT NOT NULL,
                model_public_id TEXT,
                model_asset_id TEXT,
                bambuddy_archive_id INTEGER,
                relationship_type TEXT NOT NULL,
                link_role TEXT NOT NULL DEFAULT 'primary',
                match_method TEXT NOT NULL DEFAULT 'manual',
                match_confidence TEXT NOT NULL DEFAULT 'high',
                review_state TEXT NOT NULL DEFAULT 'unreviewed',
                review_note TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _init_working_groups_schema(db_path: Path) -> None:
    """Create working_groups + working_items tables."""
    conn = connect(db_path)
    try:
        conn.execute("""
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
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS working_items (
                id INTEGER PRIMARY KEY,
                working_group_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                item_role TEXT NOT NULL DEFAULT 'supporting',
                file_hash TEXT,
                file_size INTEGER,
                source_metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (working_group_id) REFERENCES working_groups(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


NOW = "2026-05-18T00:00:00Z"


# ═════════════════════════════════════════════════════════════════════════
# 1. _working_group_url
# ═════════════════════════════════════════════════════════════════════════

class TestWorkingGroupUrl:
    def test_returns_local_scheme_with_group_id(self):
        assert _working_group_url(42) == "local://working-group/42"

    def test_zero_id(self):
        assert _working_group_url(0) == "local://working-group/0"


# ═════════════════════════════════════════════════════════════════════════
# 2. _extract_asset_hash_map
# ═════════════════════════════════════════════════════════════════════════

class TestExtractAssetHashMap:
    def test_empty_payload(self):
        assert _extract_asset_hash_map({}) == {}

    def test_no_files_key(self):
        assert _extract_asset_hash_map({"name": "model"}) == {}

    def test_files_not_a_list(self):
        assert _extract_asset_hash_map({"files": "not-a-list"}) == {}

    def test_single_file_with_content_hash_and_filename(self):
        payload = {
            "files": [
                {"content_hash": "ABC123", "filename": "part_a.3mf"},
            ]
        }
        result = _extract_asset_hash_map(payload)
        assert result == {"abc123": "part_a.3mf"}

    def test_file_hash_field_fallback(self):
        payload = {
            "files": [
                {"file_hash": "DEF456", "filename": "bracket.stl"},
            ]
        }
        result = _extract_asset_hash_map(payload)
        assert result == {"def456": "bracket.stl"}

    def test_asset_id_takes_priority_over_filename(self):
        payload = {
            "files": [
                {"content_hash": "aaa", "asset_id": "asset-uuid-1", "filename": "foo.3mf"},
            ]
        }
        result = _extract_asset_hash_map(payload)
        assert result == {"aaa": "asset-uuid-1"}

    def test_multiple_files(self):
        payload = {
            "files": [
                {"content_hash": "h1", "filename": "file_a.3mf"},
                {"content_hash": "h2", "filename": "file_b.stl"},
            ]
        }
        result = _extract_asset_hash_map(payload)
        assert result == {"h1": "file_a.3mf", "h2": "file_b.stl"}

    def test_skips_empty_hash(self):
        payload = {
            "files": [
                {"content_hash": "", "filename": "no_hash.3mf"},
                {"content_hash": "valid", "filename": "has_hash.stl"},
            ]
        }
        result = _extract_asset_hash_map(payload)
        assert result == {"valid": "has_hash.stl"}

    def test_skips_non_dict_items(self):
        payload = {"files": ["not-a-dict", {"content_hash": "ok", "filename": "f.3mf"}]}
        result = _extract_asset_hash_map(payload)
        assert result == {"ok": "f.3mf"}

    def test_hash_lowercased(self):
        payload = {"files": [{"content_hash": "UPPER", "filename": "f.3mf"}]}
        result = _extract_asset_hash_map(payload)
        assert "upper" in result


# ═════════════════════════════════════════════════════════════════════════
# 3. _build_candidate_match
# ═════════════════════════════════════════════════════════════════════════

class TestBuildCandidateMatch:
    """Tests for the candidate scoring/matching function."""

    def test_no_match_returns_none(self):
        model = _make_cached_model(name="Totally Different Name")
        result = _build_candidate_match(
            cached_model=model,
            archive_name="benchy boat",
            source_file_name=None,
            source_hash=None,
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is None

    def test_name_overlap_produces_match(self):
        model = _make_cached_model(name="Benchy Boat Tugboat")
        result = _build_candidate_match(
            cached_model=model,
            archive_name="benchy boat test",
            source_file_name=None,
            source_hash=None,
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert not result.deterministic
        assert result.score > 0
        assert result.match_method == "name_similarity"
        assert result.matched_asset_id is None

    def test_hash_match_is_deterministic(self):
        model = _make_cached_model(
            name="Some Model",
            files=[{"content_hash": "abc123", "filename": "file.3mf"}],
        )
        result = _build_candidate_match(
            cached_model=model,
            archive_name="unrelated name",
            source_file_name=None,
            source_hash="ABC123",
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert result.deterministic is True
        assert result.score >= 10.0
        assert result.match_method == "source_hash"
        assert result.match_confidence == "high"

    def test_hash_match_resolves_asset_id(self):
        """ADR-001: when hash matches a specific file, matched_asset_id is populated."""
        model = _make_cached_model(
            name="Multi Part Model",
            files=[
                {"content_hash": "hash_a", "filename": "part_left.3mf"},
                {"content_hash": "hash_b", "filename": "part_right.3mf"},
            ],
        )
        result = _build_candidate_match(
            cached_model=model,
            archive_name="something",
            source_file_name=None,
            source_hash="HASH_A",
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert result.matched_asset_id == "part_left.3mf"

    def test_hash_match_no_asset_resolution_when_hash_not_in_files(self):
        """Hash matched via source_hash/sha256 field but no files list entry."""
        summary = _make_summary(name="Model")
        payload: dict[str, Any] = {
            "name": "Model",
            "source_hash": "matchhash",
            "created_at": NOW,
            "updated_at": NOW,
            "files": [],
        }
        model = CachedCatalogModel(summary=summary, raw_payload=payload)
        result = _build_candidate_match(
            cached_model=model,
            archive_name="something",
            source_file_name=None,
            source_hash="matchhash",
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert result.deterministic is True
        assert result.matched_asset_id is None

    def test_filename_overlap_scoring(self):
        model = _make_cached_model(
            name="Benchy",
            files=[{"filename": "benchy_v2_final.3mf", "content_hash": ""}],
        )
        result = _build_candidate_match(
            cached_model=model,
            archive_name="something",
            source_file_name="benchy_v2_final.gcode.3mf",
            source_hash=None,
            archive_times=[],
            allow_filename_fallback=True,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert result.score > 0
        assert "filename" in result.match_method

    def test_filename_not_used_when_disabled(self):
        model = _make_cached_model(
            name="Completely Different",
            files=[{"filename": "unique_part.3mf", "content_hash": ""}],
        )
        result = _build_candidate_match(
            cached_model=model,
            archive_name="no overlap here",
            source_file_name="unique_part.gcode.3mf",
            source_hash=None,
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        # With filename disabled and no name overlap, should be None
        assert result is None

    def test_time_proximity_adds_boost(self):
        archive_time = datetime(2026, 5, 10, tzinfo=timezone.utc)
        summary = _make_summary(name="Recent Upload Model")
        payload: dict[str, Any] = {
            "name": "Recent Upload Model",
            "created_at": "2026-05-09T00:00:00Z",
            "updated_at": "2026-05-09T00:00:00Z",
            "files": [],
        }
        model = CachedCatalogModel(summary=summary, raw_payload=payload)
        # First get score WITHOUT time proximity
        result_no_time = _build_candidate_match(
            cached_model=model,
            archive_name="recent upload model test",
            source_file_name=None,
            source_hash=None,
            archive_times=[archive_time],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        # Then WITH time proximity
        result_with_time = _build_candidate_match(
            cached_model=model,
            archive_name="recent upload model test",
            source_file_name=None,
            source_hash=None,
            archive_times=[archive_time],
            allow_filename_fallback=False,
            allow_time_proximity=True,
            recent_upload_window_days=14,
        )
        assert result_no_time is not None
        assert result_with_time is not None
        assert result_with_time.score > result_no_time.score

    def test_working_group_entity_type_preserved(self):
        """Ensure entity_type from working group summaries flows through."""
        model = _make_cached_model(
            name="My Print Project",
            model_url="local://working-group/7",
            entity_type="working_group",
        )
        result = _build_candidate_match(
            cached_model=model,
            archive_name="my print project",
            source_file_name=None,
            source_hash=None,
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert result.summary.entity_type == "working_group"
        assert result.summary.model_url == "local://working-group/7"

    def test_confidence_levels(self):
        """Verify match_confidence assignment for non-deterministic matches."""
        # Low score (< 0.5)
        model = _make_cached_model(name="Alpha Beta Gamma Delta Epsilon Zeta")
        result = _build_candidate_match(
            cached_model=model,
            archive_name="alpha something",
            source_file_name=None,
            source_hash=None,
            archive_times=[],
            allow_filename_fallback=False,
            allow_time_proximity=False,
            recent_upload_window_days=14,
        )
        assert result is not None
        assert result.match_confidence == "low"


# ═════════════════════════════════════════════════════════════════════════
# 4. _read_working_groups_for_matching (DB integration)
# ═════════════════════════════════════════════════════════════════════════

class TestReadWorkingGroupsForMatching:
    """Integration tests for WG candidate discovery from the database."""

    @pytest.fixture
    def wg_db(self, tmp_path) -> Path:
        db_path = tmp_path / "test_wg.db"
        _init_working_groups_schema(db_path)
        return db_path

    def _seed_group(self, db_path: Path, *, group_id: int, title: str, stage: str, items: list[dict[str, str]] | None = None) -> None:
        conn = connect(db_path)
        try:
            conn.execute(
                "INSERT INTO working_groups (id, slug, title, stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, f"slug-{group_id}", title, stage, NOW, NOW),
            )
            for item in (items or []):
                conn.execute(
                    "INSERT INTO working_items (working_group_id, file_path, file_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (group_id, item["file_path"], item.get("file_hash"), NOW, NOW),
                )
            conn.commit()
        finally:
            conn.close()

    def test_active_groups_returned(self, wg_db):
        from app.routers.archive_links import _read_working_groups_for_matching

        self._seed_group(wg_db, group_id=1, title="Active Project", stage="drafting")
        results = _read_working_groups_for_matching(wg_db)
        assert len(results) == 1
        assert results[0].summary.model_url == "local://working-group/1"
        assert results[0].summary.entity_type == "working_group"
        assert results[0].summary.name == "Active Project"

    def test_archived_groups_excluded(self, wg_db):
        from app.routers.archive_links import _read_working_groups_for_matching

        self._seed_group(wg_db, group_id=1, title="Old Group", stage="archived")
        results = _read_working_groups_for_matching(wg_db)
        assert len(results) == 0

    def test_published_groups_excluded(self, wg_db):
        from app.routers.archive_links import _read_working_groups_for_matching

        self._seed_group(wg_db, group_id=1, title="Published Group", stage="published")
        results = _read_working_groups_for_matching(wg_db)
        assert len(results) == 0

    def test_items_included_in_payload(self, wg_db):
        from app.routers.archive_links import _read_working_groups_for_matching

        self._seed_group(
            wg_db,
            group_id=1,
            title="Group With Files",
            stage="drafting",
            items=[
                {"file_path": "/models/part.3mf", "file_hash": "abc"},
                {"file_path": "/models/support.stl", "file_hash": "def"},
            ],
        )
        results = _read_working_groups_for_matching(wg_db)
        assert len(results) == 1
        files = results[0].raw_payload["files"]
        assert len(files) == 2
        # filename should be basename only
        assert files[0]["filename"] == "part.3mf"
        assert files[0]["content_hash"] == "abc"
        assert files[1]["filename"] == "support.stl"

    def test_multiple_active_groups(self, wg_db):
        from app.routers.archive_links import _read_working_groups_for_matching

        self._seed_group(wg_db, group_id=1, title="Project A", stage="drafting")
        self._seed_group(wg_db, group_id=2, title="Project B", stage="reviewing")
        self._seed_group(wg_db, group_id=3, title="Old Project", stage="archived")
        results = _read_working_groups_for_matching(wg_db)
        assert len(results) == 2
        names = {r.summary.name for r in results}
        assert names == {"Project A", "Project B"}


# ═════════════════════════════════════════════════════════════════════════
# 5. _read_working_group_summaries (DB integration)
# ═════════════════════════════════════════════════════════════════════════

class TestReadWorkingGroupSummaries:
    @pytest.fixture
    def wg_db(self, tmp_path) -> Path:
        db_path = tmp_path / "test_wg_summary.db"
        _init_working_groups_schema(db_path)
        return db_path

    def test_returns_all_groups_including_archived(self, wg_db):
        """Summaries are used for link display — include all groups so
        historical links to archived/published WGs still resolve."""
        from app.routers.archive_links import _read_working_group_summaries

        conn = connect(wg_db)
        try:
            conn.execute(
                "INSERT INTO working_groups (id, slug, title, stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (1, "active", "Active", "drafting", NOW, NOW),
            )
            conn.execute(
                "INSERT INTO working_groups (id, slug, title, stage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (2, "old", "Old", "archived", NOW, NOW),
            )
            conn.commit()
        finally:
            conn.close()

        summaries = _read_working_group_summaries(wg_db)
        assert len(summaries) == 2
        assert all(s.entity_type == "working_group" for s in summaries)
        urls = {s.model_url for s in summaries}
        assert "local://working-group/1" in urls
        assert "local://working-group/2" in urls


# ═════════════════════════════════════════════════════════════════════════
# 6. migrate_links_for_graduation (DB integration)
# ═════════════════════════════════════════════════════════════════════════

class TestMigrateLinksForGraduation:
    @pytest.fixture
    def link_db(self, tmp_path) -> Path:
        db_path = tmp_path / "test_migrate.db"
        _init_links_schema(db_path)
        return db_path

    def _insert_link(self, db_path: Path, *, archive_id: int, model_url: str, model_public_id: str | None = None) -> int:
        conn = connect(db_path)
        try:
            cursor = conn.execute(
                """INSERT INTO model_catalog_links
                   (model_url, model_public_id, bambuddy_archive_id, relationship_type, link_role, match_method, match_confidence, review_state, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, 'model_printed_in_archive', 'candidate', 'auto', 'high', 'accepted', 1, ?, ?)""",
                (model_url, model_public_id, archive_id, NOW, NOW),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def test_rewrites_wg_url_to_local_model(self, link_db):
        self._insert_link(link_db, archive_id=100, model_url="local://working-group/5")
        new_uuid = str(uuid.uuid4())
        count = migrate_links_for_graduation(db_path=link_db, group_id=5, new_local_model_id=new_uuid)
        assert count == 1

        conn = connect(link_db)
        try:
            row = conn.execute("SELECT model_url, model_public_id FROM model_catalog_links WHERE bambuddy_archive_id = 100").fetchone()
        finally:
            conn.close()
        assert row["model_url"] == f"local://model/{new_uuid}"
        assert row["model_public_id"] == new_uuid

    def test_does_not_touch_other_urls(self, link_db):
        self._insert_link(link_db, archive_id=100, model_url="local://working-group/5")
        self._insert_link(link_db, archive_id=200, model_url="local://model/existing-uuid")
        self._insert_link(link_db, archive_id=300, model_url="local://working-group/99")

        count = migrate_links_for_graduation(db_path=link_db, group_id=5, new_local_model_id="new-id")
        assert count == 1

        conn = connect(link_db)
        try:
            rows = conn.execute("SELECT bambuddy_archive_id, model_url FROM model_catalog_links ORDER BY bambuddy_archive_id").fetchall()
        finally:
            conn.close()
        assert rows[0]["model_url"] == "local://model/new-id"
        assert rows[1]["model_url"] == "local://model/existing-uuid"
        assert rows[2]["model_url"] == "local://working-group/99"

    def test_multiple_links_same_wg(self, link_db):
        self._insert_link(link_db, archive_id=100, model_url="local://working-group/5")
        self._insert_link(link_db, archive_id=200, model_url="local://working-group/5")
        count = migrate_links_for_graduation(db_path=link_db, group_id=5, new_local_model_id="grad-uuid")
        assert count == 2

    def test_zero_when_no_matching_links(self, link_db):
        self._insert_link(link_db, archive_id=100, model_url="local://model/something")
        count = migrate_links_for_graduation(db_path=link_db, group_id=999, new_local_model_id="unused")
        assert count == 0

    def test_preserves_existing_public_id(self, link_db):
        """COALESCE should keep existing model_public_id if already set."""
        self._insert_link(link_db, archive_id=100, model_url="local://working-group/5", model_public_id="keep-me")
        migrate_links_for_graduation(db_path=link_db, group_id=5, new_local_model_id="new-uuid")

        conn = connect(link_db)
        try:
            row = conn.execute("SELECT model_public_id FROM model_catalog_links WHERE bambuddy_archive_id = 100").fetchone()
        finally:
            conn.close()
        assert row["model_public_id"] == "keep-me"


# ═════════════════════════════════════════════════════════════════════════
# 7. refresh_archive_link_candidates — relationship_type + model_asset_id
# ═════════════════════════════════════════════════════════════════════════

class TestRefreshCandidatesRelationshipType:
    """Verify the DB layer respects relationship_type and model_asset_id from the candidate dict."""

    @pytest.fixture
    def link_db(self, tmp_path) -> Path:
        db_path = tmp_path / "test_refresh.db"
        _init_links_schema(db_path)
        return db_path

    def test_inserts_model_printed_in_archive(self, link_db):
        candidates = [
            {
                "model_url": "local://model/uuid-1",
                "model_public_id": "uuid-1",
                "model_asset_id": None,
                "relationship_type": "model_printed_in_archive",
                "match_method": "name_similarity",
                "match_confidence": "medium",
                "review_state": "new",
                "is_active": False,
            }
        ]
        links, changed = refresh_archive_link_candidates(db_path=link_db, archive_id=1, candidates=candidates)
        assert changed == 1
        assert len(links) >= 1
        inserted = links[0]
        assert inserted.relationship_type == "model_printed_in_archive"
        assert inserted.model_asset_id is None

    def test_inserts_model_file_printed_with_asset_id(self, link_db):
        candidates = [
            {
                "model_url": "local://model/uuid-2",
                "model_public_id": "uuid-2",
                "model_asset_id": "part_a.3mf",
                "relationship_type": "model_file_printed_in_archive",
                "match_method": "source_hash",
                "match_confidence": "high",
                "review_state": "accepted",
                "is_active": True,
            }
        ]
        links, changed = refresh_archive_link_candidates(db_path=link_db, archive_id=2, candidates=candidates)
        assert changed == 1
        conn = connect(link_db)
        try:
            row = conn.execute("SELECT relationship_type, model_asset_id FROM model_catalog_links WHERE bambuddy_archive_id = 2").fetchone()
        finally:
            conn.close()
        assert row["relationship_type"] == "model_file_printed_in_archive"
        assert row["model_asset_id"] == "part_a.3mf"

    def test_defaults_to_model_printed_when_missing(self, link_db):
        """When relationship_type is omitted, the DB layer defaults to model_printed_in_archive."""
        candidates = [
            {
                "model_url": "local://model/uuid-3",
                "model_public_id": "uuid-3",
                "match_method": "name_similarity",
                "match_confidence": "low",
                "review_state": "new",
                "is_active": False,
            }
        ]
        links, changed = refresh_archive_link_candidates(db_path=link_db, archive_id=3, candidates=candidates)
        assert changed == 1
        conn = connect(link_db)
        try:
            row = conn.execute("SELECT relationship_type, model_asset_id FROM model_catalog_links WHERE bambuddy_archive_id = 3").fetchone()
        finally:
            conn.close()
        assert row["relationship_type"] == "model_printed_in_archive"
        assert row["model_asset_id"] is None


# ── #1118 — structured signals, linked-archive boost, signal_strength ────

class TestSignalStrength:
    """Tests for the _signal_strength helper."""

    def test_strong(self):
        assert _signal_strength(0.8) == "strong"
        assert _signal_strength(1.0) == "strong"

    def test_moderate(self):
        assert _signal_strength(0.5) == "moderate"
        assert _signal_strength(0.79) == "moderate"

    def test_weak(self):
        assert _signal_strength(0.1) == "weak"
        assert _signal_strength(0.49) == "weak"


class TestBuildCandidateMatchSignals:
    """Tests for structured signals in _build_candidate_match (#1118)."""

    _DEFAULTS = dict(archive_times=[], allow_filename_fallback=True, allow_time_proximity=False, recent_upload_window_days=14)

    def test_hash_match_has_deterministic_signal(self):
        cached = _make_cached_model(
            name="Widget",
            files=[{"filename": "widget.3mf", "source_hash": "abc123"}],
        )
        match = _build_candidate_match(
            cached_model=cached,
            archive_name="widget v1",
            source_file_name="widget.3mf",
            source_hash="abc123",
            **self._DEFAULTS,
        )
        assert match is not None
        assert match.deterministic
        signal_types = [s["type"] for s in match.signals]
        assert "source_hash_exact" in signal_types
        assert any(s["strength"] == "deterministic" for s in match.signals if s["type"] == "source_hash_exact")

    def test_name_overlap_has_signal(self):
        cached = _make_cached_model(name="Widget Holder")
        match = _build_candidate_match(
            cached_model=cached,
            archive_name="Widget Holder v2",
            source_file_name=None,
            source_hash=None,
            **self._DEFAULTS,
        )
        assert match is not None
        signal_types = [s["type"] for s in match.signals]
        assert "name_overlap" in signal_types

    def test_filename_overlap_has_signal(self):
        cached = _make_cached_model(
            name="Unrelated Name",
            files=[{"filename": "phone_stand.3mf"}],
        )
        match = _build_candidate_match(
            cached_model=cached,
            archive_name="phone stand print",
            source_file_name="phone_stand.3mf",
            source_hash=None,
            **self._DEFAULTS,
        )
        assert match is not None
        signal_types = [s["type"] for s in match.signals]
        assert "filename_overlap" in signal_types

    def test_linked_archive_boost_applied_when_score_positive(self):
        cached = _make_cached_model(name="Widget Holder")
        match_without = _build_candidate_match(
            cached_model=cached,
            archive_name="Widget Holder v2",
            source_file_name=None,
            source_hash=None,
            existing_link_count=0,
            **self._DEFAULTS,
        )
        match_with = _build_candidate_match(
            cached_model=cached,
            archive_name="Widget Holder v2",
            source_file_name=None,
            source_hash=None,
            existing_link_count=3,
            **self._DEFAULTS,
        )
        assert match_without is not None
        assert match_with is not None
        assert match_with.score > match_without.score
        signal_types = [s["type"] for s in match_with.signals]
        assert "linked_archive_count" in signal_types

    def test_linked_archive_boost_not_applied_when_score_zero(self):
        cached = _make_cached_model(name="Completely Different")
        match = _build_candidate_match(
            cached_model=cached,
            archive_name="No overlap whatsoever xyz",
            source_file_name=None,
            source_hash=None,
            existing_link_count=5,
            **self._DEFAULTS,
        )
        assert match is None

    def test_signals_tuple_is_immutable(self):
        cached = _make_cached_model(name="Widget Holder")
        match = _build_candidate_match(
            cached_model=cached,
            archive_name="Widget Holder",
            source_file_name=None,
            source_hash=None,
            **self._DEFAULTS,
        )
        assert match is not None
        assert isinstance(match.signals, tuple)
