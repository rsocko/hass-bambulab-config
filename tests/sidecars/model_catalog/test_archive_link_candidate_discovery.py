"""Tests for #1114 — broadened archive link candidate discovery.

Covers:
- _extract_asset_hash_map() file-level hash→asset mapping
- _build_candidate_match() scoring, deterministic detection, asset-level resolution
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
)
from app.db_archive_links import refresh_archive_link_candidates
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



NOW = "2026-05-18T00:00:00Z"



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
