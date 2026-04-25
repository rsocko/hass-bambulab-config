"""
Tests for Phase 3.3 Task 2: Related Models Algorithm

Tests the similarity scoring and related models recommendation features.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sidecars.model_catalog.app.archive_linking import (
    ArchiveLinkingEngine,
    ArchiveMetadata,
)


class TestRelatedModelsAlgorithm:
    """Tests for get_related_models method."""

    def test_get_related_models_returns_list(self):
        """get_related_models should return a list."""
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = []
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("123")
        
        assert isinstance(result, list)

    def test_get_related_models_excludes_self(self):
        """Related models should not include the reference model."""
        models = [
            {"id": "123", "name": "Model A", "creator": {"name": "Designer X"}, "collections": [], "keywords": []},
            {"id": "456", "name": "Model B", "creator": {"name": "Designer X"}, "collections": [], "keywords": []},
        ]
        
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = models
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("123")
        
        # Should only have Model B (same creator = 25 points, above min threshold)
        assert len(result) == 1
        assert result[0]["model_id"] == "456"

    def test_get_related_models_respects_limit(self):
        """get_related_models should respect limit parameter."""
        models = [
            {"id": "1", "name": "A", "collections": [], "keywords": [], "creator": "X"},
            {"id": "2", "name": "B", "collections": [], "keywords": [], "creator": "X"},
            {"id": "3", "name": "C", "collections": [], "keywords": [], "creator": "X"},
            {"id": "4", "name": "D", "collections": [], "keywords": [], "creator": "X"},
        ]
        
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = models
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("1", limit=2)
        
        assert len(result) <= 2

    def test_get_related_models_no_model_found(self):
        """get_related_models should return empty list if model not found."""
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = []
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("nonexistent")
        
        assert result == []

    def test_get_related_models_sorted_by_score(self):
        """Related models should be sorted by similarity score (descending)."""
        base_model = {
            "id": "1",
            "name": "Base Model",
            "creator": {"name": "Creator A"},
            "collections": [{"name": "Collection 1"}],
            "keywords": [{"name": "keyword1"}, {"name": "keyword2"}],
        }
        
        # Model B has minimal match
        related_models_b = {
            "id": "2",
            "name": "Model B",
            "creator": {"name": "Creator B"},
            "collections": [],
            "keywords": [],
        }
        
        # Model C has strong match (creator + collection)
        related_models_c = {
            "id": "3",
            "name": "Model C",
            "creator": {"name": "Creator A"},
            "collections": [{"name": "Collection 1"}],
            "keywords": [],
        }
        
        models = [base_model, related_models_b, related_models_c]
        
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = models
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("1", min_similarity=20)
        
        # Model C should be first (higher score)
        assert len(result) >= 1
        assert result[0]["model_id"] == "3"

    def test_get_related_models_with_min_similarity_threshold(self):
        """get_related_models should filter by min_similarity."""
        base_model = {
            "id": "1",
            "name": "Base",
            "creator": {"name": "Creator A"},
            "collections": [],
            "keywords": [],
        }
        
        low_similarity = {
            "id": "2",
            "name": "Unrelated",
            "creator": {"name": "Creator B"},
            "collections": [],
            "keywords": [],
        }
        
        high_similarity = {
            "id": "3",
            "name": "Related",
            "creator": {"name": "Creator A"},
            "collections": [],
            "keywords": [],
        }
        
        models = [base_model, low_similarity, high_similarity]
        
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = models
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("1", min_similarity=20)
        
        # Should only include high_similarity
        assert len(result) == 1
        assert result[0]["model_id"] == "3"


class TestSimilarityScoring:
    """Tests for _calculate_similarity_score method."""

    def test_collection_match_adds_30_points(self):
        """Shared collection should add 30 points."""
        base_model = {
            "id": "1",
            "collections": [{"name": "Gridfinity"}],
            "creator": {"name": "User A"},
            "keywords": [],
        }
        
        target_model = {
            "id": "2",
            "collections": [{"name": "Gridfinity"}],
            "creator": {"name": "User B"},
            "keywords": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        assert score >= 30
        assert any("Shared collection" in r for r in reasons)

    def test_creator_match_adds_25_points(self):
        """Same creator should add 25 points."""
        base_model = {
            "id": "1",
            "creator": {"name": "Designer X"},
            "collections": [],
            "keywords": [],
        }
        
        target_model = {
            "id": "2",
            "creator": {"name": "Designer X"},
            "collections": [],
            "keywords": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        assert score >= 25
        assert any("Same creator" in r for r in reasons)

    def test_keyword_match_adds_5_per_keyword(self):
        """Each shared keyword adds 5 points (max 20)."""
        base_model = {
            "id": "1",
            "keywords": [
                {"name": "storage"},
                {"name": "organizer"},
                {"name": "gridfinity"},
            ],
            "creator": {"name": "User A"},
            "collections": [],
        }
        
        target_model = {
            "id": "2",
            "keywords": [
                {"name": "storage"},
                {"name": "organizer"},
                {"name": "box"},
            ],
            "creator": {"name": "User B"},
            "collections": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        # 2 shared keywords = 10 points
        assert score >= 10
        assert any("shared keyword" in r.lower() for r in reasons)

    def test_keyword_scoring_capped_at_20(self):
        """Keyword scores should be capped at 20 points."""
        base_model = {
            "id": "1",
            "keywords": [
                {"name": "tag1"},
                {"name": "tag2"},
                {"name": "tag3"},
                {"name": "tag4"},
                {"name": "tag5"},
            ],
            "creator": {"name": "User A"},
            "collections": [],
        }
        
        target_model = {
            "id": "2",
            "keywords": [
                {"name": "tag1"},
                {"name": "tag2"},
                {"name": "tag3"},
                {"name": "tag4"},
                {"name": "tag5"},
            ],
            "creator": {"name": "User B"},
            "collections": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        # 5 * 5 = 25, but capped at 20
        assert 20 <= score <= 20

    def test_total_score_capped_at_100(self):
        """Total similarity score should not exceed 100."""
        base_model = {
            "id": "1",
            "creator": {"name": "Designer X"},
            "collections": [
                {"name": "Gridfinity"},
                {"name": "Storage"},
            ],
            "keywords": [
                {"name": "tag1"},
                {"name": "tag2"},
                {"name": "tag3"},
            ],
        }
        
        target_model = {
            "id": "2",
            "creator": {"name": "Designer X"},
            "collections": [
                {"name": "Gridfinity"},
                {"name": "Storage"},
            ],
            "keywords": [
                {"name": "tag1"},
                {"name": "tag2"},
                {"name": "tag3"},
            ],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        assert score <= 100

    def test_no_match_returns_zero_score(self):
        """Completely unrelated models should score 0."""
        base_model = {
            "id": "1",
            "creator": {"name": "Creator A"},
            "collections": [],
            "keywords": [],
        }
        
        target_model = {
            "id": "2",
            "creator": {"name": "Creator B"},
            "collections": [],
            "keywords": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        assert score == 0
        assert reasons == []

    def test_case_insensitive_matching(self):
        """Matching should be case-insensitive."""
        base_model = {
            "id": "1",
            "creator": {"name": "Designer X"},
            "collections": [{"name": "GRIDFINITY"}],
            "keywords": [],
        }
        
        target_model = {
            "id": "2",
            "creator": {"name": "DESIGNER X"},
            "collections": [{"name": "gridfinity"}],
            "keywords": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        # Should match creator and collection despite case differences
        assert score >= 55  # 30 (collection) + 25 (creator)

    def test_empty_collections_handled(self):
        """Missing collections should not cause errors."""
        base_model = {
            "id": "1",
            "creator": {"name": "User A"},
            "keywords": [],
        }
        
        target_model = {
            "id": "2",
            "creator": {"name": "User B"},
            "collections": [],
            "keywords": [],
        }
        
        # Should not raise exception
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        assert isinstance(score, float)
        assert isinstance(reasons, list)

    def test_multiple_shared_collections(self):
        """Multiple shared collections should still cap at 30."""
        base_model = {
            "id": "1",
            "collections": [
                {"name": "Gridfinity"},
                {"name": "Storage"},
                {"name": "Organization"},
            ],
            "creator": {"name": "User A"},
            "keywords": [],
        }
        
        target_model = {
            "id": "2",
            "collections": [
                {"name": "Gridfinity"},
                {"name": "Storage"},
                {"name": "Organization"},
            ],
            "creator": {"name": "User B"},
            "keywords": [],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        # Should be 30 for collections (only one bonus even with multiple matches)
        assert 30 <= score < 100

    def test_reason_strings_descriptive(self):
        """Reason strings should be descriptive."""
        base_model = {
            "id": "1",
            "creator": {"name": "Designer X"},
            "collections": [{"name": "Gridfinity"}],
            "keywords": [{"name": "storage"}],
        }
        
        target_model = {
            "id": "2",
            "creator": {"name": "Designer X"},
            "collections": [{"name": "Gridfinity"}],
            "keywords": [{"name": "storage"}],
        }
        
        score, reasons = ArchiveLinkingEngine._calculate_similarity_score(
            base_model, target_model
        )
        
        assert len(reasons) >= 3
        assert any("Same creator" in r for r in reasons)
        assert any("Shared collection" in r for r in reasons)
        assert any("shared keyword" in r for r in reasons)


class TestRelatedModelsIntegration:
    """Integration tests for related models functionality."""

    def test_real_model_relationships(self):
        """Test with realistic model payloads."""
        models = [
            {
                "id": "1",
                "name": "Gridfinity Bin Small",
                "creator": {"name": "Smithers"},
                "collections": [{"name": "Gridfinity"}, {"name": "Storage"}],
                "keywords": [
                    {"name": "storage"},
                    {"name": "organizer"},
                    {"name": "gridfinity"},
                ],
            },
            {
                "id": "2",
                "name": "Gridfinity Bin Large",
                "creator": {"name": "Smithers"},
                "collections": [{"name": "Gridfinity"}, {"name": "Storage"}],
                "keywords": [
                    {"name": "storage"},
                    {"name": "organizer"},
                    {"name": "gridfinity"},
                ],
            },
            {
                "id": "3",
                "name": "Tool Organizer",
                "creator": {"name": "Other Designer"},
                "collections": [{"name": "Storage"}],
                "keywords": [{"name": "storage"}, {"name": "tools"}],
            },
            {
                "id": "4",
                "name": "Cable Clip",
                "creator": {"name": "Another Designer"},
                "collections": [],
                "keywords": [{"name": "cable"}, {"name": "clips"}],
            },
        ]
        
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = models
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("1", limit=3, min_similarity=5)
        
        # Should have at least 2 results (Models 2 and 3)
        # Model 4 has no shared attributes so may not appear
        assert len(result) >= 2
        # Model 2 should be first (same creator + collections)
        assert result[0]["model_id"] == "2"
        # Model 3 should be second (same collection + keyword)
        assert result[1]["model_id"] == "3"

    def test_similar_models_have_match_reasons(self):
        """Related models should include reasons for similarity."""
        models = [
            {
                "id": "1",
                "name": "Model A",
                "creator": {"name": "Designer X"},
                "collections": [{"name": "Collection 1"}],
                "keywords": [{"name": "keyword1"}],
            },
            {
                "id": "2",
                "name": "Model B",
                "creator": {"name": "Designer X"},
                "collections": [{"name": "Collection 1"}],
                "keywords": [{"name": "keyword1"}],
            },
        ]
        
        mock_client = Mock()
        mock_client.list_model_payloads.return_value = models
        
        engine = ArchiveLinkingEngine(mock_client)
        result = engine.get_related_models("1")
        
        assert len(result) > 0
        assert "match_reasons" in result[0]
        assert len(result[0]["match_reasons"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
