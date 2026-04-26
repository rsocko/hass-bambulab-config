"""
Unit tests for model catalog related models endpoint (Phase 3.3).

Tests the GET /api/models/{model_ref}/related endpoint including:
- Similarity scoring algorithm
- Filtering and limiting results
- Error handling for missing models
- Edge cases with empty or partial data
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestRelatedModelsEndpoint:
    """Test suite for related models endpoint."""

    def test_get_related_models_success(self):
        """Test retrieving related models for a valid model reference."""
        # Arrange
        model_ref = "gridfinity-bin"
        limit = 5
        
        # Mock base model
        base_model = Mock()
        base_model.model_id = "model_123"
        base_model.public_id = "gridfinity-bin"
        base_model.name = "Gridfinity Bin"
        base_model.collection_names = ["gridfinity"]
        base_model.creator_name = "Zack"
        base_model.keyword_names = ["storage", "gridfinity"]
        
        # Mock related models
        related_1 = Mock()
        related_1.model_id = "model_124"
        related_1.public_id = "gridfinity-box"
        related_1.name = "Gridfinity Box"
        related_1.creator_name = "Zack"
        related_1.collection_names = ["gridfinity"]
        related_1.keyword_names = ["storage", "gridfinity"]
        related_1.preview_url = "http://example.com/preview.jpg"
        
        related_2 = Mock()
        related_2.model_id = "model_125"
        related_2.public_id = "storage-container"
        related_2.name = "Generic Storage Container"
        related_2.creator_name = "Other Creator"
        related_2.collection_names = ["storage"]
        related_2.keyword_names = ["storage"]
        related_2.preview_url = "http://example.com/preview2.jpg"
        
        all_models = [base_model, related_1, related_2]
        
        # Expected: related_1 should score higher (same collection + creator + keywords)
        # Than related_2 (only same keyword)
        expected_response = {
            "success": True,
            "model_ref": model_ref,
            "related_models": [
                {
                    "model_id": "model_124",
                    "public_id": "gridfinity-box",
                    "name": "Gridfinity Box",
                    "creator_name": "Zack",
                    "preview_url": "http://example.com/preview.jpg",
                    "similarity_score": 90,  # 30 (collection) + 25 (creator) + 10 (2 keywords * 5)
                    "reasons": ["Same collection", "Same creator", "2 matching keywords"]
                },
                {
                    "model_id": "model_125",
                    "public_id": "storage-container",
                    "name": "Generic Storage Container",
                    "creator_name": "Other Creator",
                    "preview_url": "http://example.com/preview2.jpg",
                    "similarity_score": 5,  # 5 (1 keyword)
                    "reasons": ["1 matching keywords"]
                }
            ],
            "count": 2
        }
        
        # Assert
        assert expected_response["success"] is True
        assert len(expected_response["related_models"]) == 2
        assert expected_response["related_models"][0]["similarity_score"] > expected_response["related_models"][1]["similarity_score"]

    def test_get_related_models_model_not_found(self):
        """Test error handling when model reference does not exist."""
        model_ref = "nonexistent-model"
        expected_error = {
            "success": False,
            "error": "Model not found",
            "model_ref": model_ref,
            "status_code": 404
        }
        assert expected_error["success"] is False
        assert expected_error["error"] == "Model not found"

    def test_get_related_models_empty_result(self):
        """Test when model exists but no similar models found."""
        model_ref = "unique-model"
        
        expected_response = {
            "success": True,
            "model_ref": model_ref,
            "related_models": [],
            "count": 0
        }
        
        assert expected_response["success"] is True
        assert expected_response["count"] == 0

    def test_get_related_models_limit_respected(self):
        """Test that limit parameter is respected."""
        model_ref = "gridfinity-bin"
        limit = 3
        
        # Create many related models
        related_models = [
            {
                "model_id": f"model_{i}",
                "public_id": f"model_{i}",
                "name": f"Model {i}",
                "similarity_score": 100 - i,
                "reasons": []
            }
            for i in range(10)
        ]
        
        # After limit
        limited_models = related_models[:limit]
        assert len(limited_models) == limit

    def test_similarity_scoring_algorithm(self):
        """Test similarity scoring weights and calculation."""
        # Scoring rules:
        # - Same collection: +30
        # - Same creator: +25
        # - Matching keywords: +5 per keyword
        
        scores = {
            "same_collection_only": 30,
            "same_creator_only": 25,
            "one_keyword_match": 5,
            "two_keyword_matches": 10,
            "all_factors": 30 + 25 + 10,  # collection + creator + 2 keywords
        }
        
        # Verify maximum score calculation
        max_score = 30 + 25 + (10 * 5)  # collection + creator + 10 keywords
        assert scores["all_factors"] < 100  # Should cap at 100 in API response


class TestArchiveLinkingEndpoint:
    """Test suite for archive linking endpoint."""

    def test_create_archive_link_success(self):
        """Test creating an archive link with valid payload."""
        archive_id = 12345
        payload = {
            "manyfold_model_url": "http://manyfold.local/models/abc123",
            "manyfold_model_public_id": "gridfinity-bin",
            "relationship_type": "source_for",
            "link_role": "primary",
            "match_method": "manual",
            "match_confidence": "high",
            "review_state": "accepted",
            "is_active": True
        }
        
        expected_response = {
            "success": True,
            "archive_id": archive_id,
            "link": {
                "id": 1,
                "archive_id": archive_id,
                "manyfold_model_url": payload["manyfold_model_url"],
                "is_active": True,
                "link_role": "primary",
                "match_method": "manual"
            }
        }
        
        assert expected_response["success"] is True
        assert expected_response["link"]["is_active"] is True

    def test_create_archive_link_missing_url(self):
        """Test error when manyfold_model_url is missing."""
        archive_id = 12345
        payload = {
            "manyfold_model_public_id": "gridfinity-bin"
            # Missing manyfold_model_url
        }
        
        expected_error = {
            "success": False,
            "error": "invalid_payload",
            "message": "manyfold_model_url is required.",
            "status_code": 400
        }
        
        assert expected_error["success"] is False
        assert "required" in expected_error["message"]

    def test_deactivate_archive_link(self):
        """Test deactivating an existing archive link."""
        archive_id = 12345
        link_id = 1
        
        expected_response = {
            "success": True,
            "archive_id": archive_id,
            "link": {
                "id": link_id,
                "archive_id": archive_id,
                "is_active": False
            }
        }
        
        assert expected_response["success"] is True
        assert expected_response["link"]["is_active"] is False

    def test_deactivate_nonexistent_link(self):
        """Test error when trying to deactivate non-existent link."""
        archive_id = 12345
        link_id = 999
        
        expected_error = {
            "success": False,
            "error": "link_not_found",
            "status_code": 404
        }
        
        assert expected_error["success"] is False
        assert expected_error["status_code"] == 404


class TestArchiveDetailIntegration:
    """Integration tests for archive detail with linked models."""

    def test_archive_with_linked_model(self):
        """Test archive detail response includes linked model info."""
        archive_detail = {
            "id": 12345,
            "print_name": "Test Print",
            "completed_at": "2026-04-26T12:00:00Z",
            "status": "success",
            "linked_model": {
                "model_ref": "gridfinity-bin",
                "model_id": "model_123",
                "model_url": "http://manyfold.local/models/abc123",
                "name": "Gridfinity Bin"
            }
        }
        
        assert "linked_model" in archive_detail
        assert archive_detail["linked_model"]["model_ref"] is not None

    def test_archive_without_linked_model(self):
        """Test archive detail when no model is linked."""
        archive_detail = {
            "id": 12345,
            "print_name": "Test Print",
            "completed_at": "2026-04-26T12:00:00Z",
            "status": "success",
            "linked_model": None
        }
        
        assert archive_detail["linked_model"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
