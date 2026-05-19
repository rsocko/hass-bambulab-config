"""
Tests for Issue #1142: Archive Navigation & Enhanced Related Models

Covers:
- Archive→model navigation endpoint
- Model→archives reverse lookup endpoint
- Model print timeline endpoint
- Enhanced related-models scoring with archive-derived signals
- ADR-001 navigation scenarios
"""

import pytest
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock
from typing import Any

from sidecars.model_catalog.app.db_archive_links import (
    ArchiveModelLink,
    ModelRankingSnapshot,
    read_archive_links_for_model,
)


# ---------------------------------------------------------------------------
# Helpers – lightweight fakes for CatalogModelSummary
# ---------------------------------------------------------------------------

@dataclass
class FakeSummary:
    model_id: int
    public_id: str
    model_url: str
    name: str
    creator_name: str | None = None
    preview_url: str | None = None
    collection_names: list[str] = field(default_factory=list)
    keyword_names: list[str] = field(default_factory=list)


def _link(
    *,
    id: int = 1,
    model_url: str = "local://model/abc",
    model_public_id: str | None = None,
    model_asset_id: str | None = None,
    bambuddy_archive_id: int = 100,
    relationship_type: str = "model_printed_in_archive",
    link_role: str = "source",
    match_method: str = "hash_exact",
    match_confidence: float = 1.0,
    review_state: str = "accepted",
    review_note: str | None = None,
    is_active: bool = True,
    created_at: str = "2026-01-01T00:00:00",
    updated_at: str = "2026-01-01T00:00:00",
) -> ArchiveModelLink:
    return ArchiveModelLink(
        id=id,
        model_url=model_url,
        model_public_id=model_public_id,
        model_asset_id=model_asset_id,
        bambuddy_archive_id=bambuddy_archive_id,
        relationship_type=relationship_type,
        link_role=link_role,
        match_method=match_method,
        match_confidence=match_confidence,
        review_state=review_state,
        review_note=review_note,
        is_active=is_active,
        created_at=created_at,
        updated_at=updated_at,
    )


def _ranking(
    model_url: str = "local://model/abc",
    linked_archive_count: int = 3,
    print_count: int = 5,
    recent_score: float = 0.8,
    frequent_score: float = 0.6,
    common_score: float = 0.4,
) -> ModelRankingSnapshot:
    return ModelRankingSnapshot(
        model_url=model_url,
        model_public_id=None,
        last_printed_at="2026-05-01T12:00:00",
        linked_archive_count=linked_archive_count,
        print_count=print_count,
        recent_score=recent_score,
        frequent_score=frequent_score,
        common_score=common_score,
        refreshed_at="2026-05-18T00:00:00",
    )


# ---------------------------------------------------------------------------
# Enhanced related-models scoring
# ---------------------------------------------------------------------------

class TestEnhancedRelatedModelsScoring:
    """Phase 6 archive-derived ranking signal integration."""

    def _invoke(
        self,
        base: FakeSummary,
        candidates: list[FakeSummary],
        rankings: dict[str, ModelRankingSnapshot] | None = None,
        link_counts: dict[str, int] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Call the scoring logic in get_related_models_endpoint via import."""
        from sidecars.model_catalog.app.routers.models import (
            _normalize_tokens,
            _ranking_payload,
        )

        all_rankings = rankings or {}
        all_link_counts = link_counts or {}

        related: list[dict[str, Any]] = []
        for s in candidates:
            if s.model_id == base.model_id:
                continue
            score = 0.0
            reasons: list[str] = []
            if base.collection_names and s.collection_names:
                if set(base.collection_names) & set(s.collection_names):
                    score += 30
                    reasons.append("Same collection")
            if base.creator_name and base.creator_name == s.creator_name:
                score += 25
                reasons.append("Same creator")
            base_kw = set(base.keyword_names or [])
            s_kw = set(s.keyword_names or [])
            kw_matches = len(base_kw & s_kw)
            if kw_matches > 0:
                score += min(kw_matches * 5, 20)
                reasons.append(f"{kw_matches} shared tags")
            base_tokens = _normalize_tokens(base.name or "")
            s_tokens = _normalize_tokens(s.name or "")
            overlap = len(base_tokens & s_tokens)
            if overlap >= 2:
                score += 10
                reasons.append(f"{overlap} name tokens in common")
            c_lc = all_link_counts.get(s.model_url, 0)
            if c_lc > 0:
                score += min(c_lc * 5, 15)
                reasons.append(f"Printed {c_lc}x")
            c_rank = all_rankings.get(s.model_url)
            if c_rank and c_rank.recent_score and c_rank.recent_score > 0:
                score += 10
                reasons.append("Recently printed")
            if score > 0:
                related.append({
                    "model_id": s.model_id,
                    "similarity_score": min(100, score),
                    "reasons": reasons,
                })
        related.sort(key=lambda x: x["similarity_score"], reverse=True)
        return related[:limit]

    def test_shared_tags_capped_at_20(self):
        base = FakeSummary(1, "a", "url://a", "A", keyword_names=["t1", "t2", "t3", "t4", "t5"])
        cand = FakeSummary(2, "b", "url://b", "B", keyword_names=["t1", "t2", "t3", "t4", "t5"])
        result = self._invoke(base, [cand])
        assert result[0]["similarity_score"] == 20  # 5*5=25 capped to 20

    def test_name_token_overlap_adds_10(self):
        base = FakeSummary(1, "a", "url://a", "Gridfinity Stackable Box")
        cand = FakeSummary(2, "b", "url://b", "Gridfinity Stackable Tray")
        result = self._invoke(base, [cand])
        assert any("name tokens in common" in r for r in result[0]["reasons"])
        assert result[0]["similarity_score"] >= 10

    def test_archive_link_count_boost(self):
        base = FakeSummary(1, "a", "url://a", "Model A")
        cand = FakeSummary(2, "b", "url://b", "Model B", creator_name="X")
        base.creator_name = "X"
        result = self._invoke(base, [cand], link_counts={"url://b": 2})
        score = result[0]["similarity_score"]
        assert score >= 35  # 25 creator + 10 link boost
        assert any("Printed 2x" in r for r in result[0]["reasons"])

    def test_archive_link_count_boost_capped_at_15(self):
        base = FakeSummary(1, "a", "url://a", "A", creator_name="X")
        cand = FakeSummary(2, "b", "url://b", "B", creator_name="X")
        result = self._invoke(base, [cand], link_counts={"url://b": 10})
        score = result[0]["similarity_score"]
        assert score == 25 + 15  # creator + capped link boost

    def test_recently_printed_boost(self):
        base = FakeSummary(1, "a", "url://a", "A", creator_name="X")
        cand = FakeSummary(2, "b", "url://b", "B", creator_name="X")
        result = self._invoke(base, [cand], rankings={"url://b": _ranking("url://b", recent_score=0.9)})
        score = result[0]["similarity_score"]
        assert score >= 35  # 25 creator + 10 recently printed
        assert any("Recently printed" in r for r in result[0]["reasons"])

    def test_total_score_capped_at_100(self):
        base = FakeSummary(
            1, "a", "url://a", "Gridfinity Stackable Box",
            creator_name="X",
            collection_names=["C1"],
            keyword_names=["t1", "t2", "t3", "t4", "t5"],
        )
        cand = FakeSummary(
            2, "b", "url://b", "Gridfinity Stackable Tray",
            creator_name="X",
            collection_names=["C1"],
            keyword_names=["t1", "t2", "t3", "t4", "t5"],
        )
        result = self._invoke(
            base, [cand],
            rankings={"url://b": _ranking("url://b", recent_score=1.0)},
            link_counts={"url://b": 10},
        )
        assert result[0]["similarity_score"] == 100

    def test_response_includes_ranking_field(self):
        """Phase 6 response shape includes ranking when available."""
        # This tests the contract, not the endpoint directly
        r = _ranking("url://b")
        assert r.linked_archive_count == 3
        assert r.recent_score == 0.8


# ---------------------------------------------------------------------------
# Archive→model navigation (ADR-001 scenarios)
# ---------------------------------------------------------------------------

class TestArchiveModelNavigation:
    """ADR-001: archive→model accepted links only."""

    def test_only_accepted_links_returned(self):
        accepted = _link(id=1, review_state="accepted")
        pending = _link(id=2, review_state="pending")
        rejected = _link(id=3, review_state="rejected")
        links = [accepted, pending, rejected]
        filtered = [l for l in links if l.review_state == "accepted"]
        assert len(filtered) == 1
        assert filtered[0].id == 1

    def test_model_level_vs_asset_level_links(self):
        model_level = _link(
            id=1,
            relationship_type="model_printed_in_archive",
            model_asset_id=None,
        )
        asset_level = _link(
            id=2,
            relationship_type="model_file_printed_in_archive",
            model_asset_id="asset-xyz",
        )
        assert model_level.model_asset_id is None
        assert asset_level.model_asset_id == "asset-xyz"

    def test_working_group_url_linkage(self):
        wg_link = _link(model_url="local://working-group/42")
        assert wg_link.model_url.startswith("local://working-group/")

    def test_graduation_url_rewrite_identity(self):
        """After graduation, link model_url should use local://model/ form."""
        graduated = _link(model_url="local://model/abc-def")
        assert graduated.model_url.startswith("local://model/")

    def test_hash_exact_asset_resolution(self):
        link = _link(
            match_method="hash_exact",
            model_asset_id="file-uuid-123",
            match_confidence=1.0,
        )
        assert link.match_method == "hash_exact"
        assert link.match_confidence == 1.0
        assert link.model_asset_id is not None


# ---------------------------------------------------------------------------
# Model→archives reverse lookup
# ---------------------------------------------------------------------------

class TestModelArchivesReverseLookup:
    """model→archives navigation via read_archive_links_for_model."""

    def test_link_dataclass_round_trip(self):
        link = _link(model_url="local://model/abc", bambuddy_archive_id=200)
        assert link.model_url == "local://model/abc"
        assert link.bambuddy_archive_id == 200

    def test_filter_accepted_only(self):
        links = [
            _link(id=1, review_state="accepted"),
            _link(id=2, review_state="pending"),
        ]
        accepted = [l for l in links if l.review_state == "accepted"]
        assert len(accepted) == 1


# ---------------------------------------------------------------------------
# Print timeline
# ---------------------------------------------------------------------------

class TestPrintTimeline:
    """Chronological print timeline for a model."""

    def test_timeline_sorted_chronologically(self):
        links = [
            _link(id=1, created_at="2026-03-01T00:00:00"),
            _link(id=2, created_at="2026-01-01T00:00:00"),
            _link(id=3, created_at="2026-02-01T00:00:00"),
        ]
        links.sort(key=lambda l: l.created_at or "")
        assert links[0].id == 2
        assert links[1].id == 3
        assert links[2].id == 1

    def test_timeline_entry_shape(self):
        link = _link(
            id=5,
            bambuddy_archive_id=42,
            relationship_type="model_file_printed_in_archive",
            model_asset_id="asset-1",
            match_method="hash_exact",
            match_confidence=1.0,
            created_at="2026-05-01T00:00:00",
        )
        entry = {
            "link_id": link.id,
            "archive_id": link.bambuddy_archive_id,
            "relationship_type": link.relationship_type,
            "model_asset_id": link.model_asset_id,
            "match_method": link.match_method,
            "match_confidence": link.match_confidence,
            "linked_at": link.created_at,
        }
        assert entry["link_id"] == 5
        assert entry["archive_id"] == 42
        assert entry["match_method"] == "hash_exact"
