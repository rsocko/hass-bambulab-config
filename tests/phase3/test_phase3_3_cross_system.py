"""
Phase 3.3 Tests: Cross-System Integration
Tests for model-archive linking, related models, recommendations, and export
"""

import pytest


class TestModelArchiveLinking:
    """Tests for connecting models to their prints"""

    def test_get_archive_model(self):
        """Retrieve source model for an archive"""
        archive = {
            "archive_id": 12345,
            "model_filename": "test_model.3mf",
            "printer_id": "printer-1",
        }
        
        model = get_archive_model(archive)
        assert model is not None
        assert model["model_ref"] == "test_model"

    def test_archive_model_not_found(self):
        """Handle when archive has no matching model"""
        archive = {
            "archive_id": 99999,
            "model_filename": "nonexistent.3mf",
            "printer_id": "printer-1",
        }
        
        model = get_archive_model(archive)
        assert model is None or model["model_ref"] is None

    def test_find_model_by_filename_exact(self):
        """Find model by exact filename match"""
        model = find_model_by_filename("test_model.3mf", exact=True)
        assert model is not None
        assert model["name"] == "test_model"

    def test_find_model_by_filename_fuzzy(self):
        """Find model by fuzzy name matching"""
        # Archive has "test_model_v2.3mf", model DB has "test_model"
        model = find_model_by_filename("test_model_v2.3mf", exact=False)
        assert model is not None
        assert "test_model" in model["name"]


class TestRelatedModelsAlgorithm:
    """Tests for related models scoring and ranking"""

    def test_collection_match_score(self):
        """Same collection gives +30 points"""
        base = {"name": "Model A", "collections": ["Miniatures"]}
        target = {"name": "Model B", "collections": ["Miniatures"]}
        
        score = calculate_similarity_score(base, target)
        assert score >= 30

    def test_creator_match_score(self):
        """Same creator gives +25 points"""
        base = {"name": "Model A", "creator": "john"}
        target = {"name": "Model B", "creator": "john"}
        
        score = calculate_similarity_score(base, target)
        assert score >= 25

    def test_keyword_match_score(self):
        """Each keyword match gives +5 points"""
        base = {"name": "Model A", "keywords": ["miniature", "dragon", "fantasy"]}
        target = {"name": "Model B", "keywords": ["miniature", "dragon", "sci-fi"]}
        
        score = calculate_similarity_score(base, target)
        # Should have at least 2 matches × 5 = +10
        assert score >= 10

    def test_combined_scores(self):
        """Multiple matches combine scores"""
        base = {
            "name": "Model A",
            "creator": "john",
            "collections": ["Miniatures"],
            "keywords": ["dragon", "fantasy"],
        }
        target = {
            "name": "Model B",
            "creator": "john",  # +25
            "collections": ["Miniatures"],  # +30
            "keywords": ["dragon", "knight"],  # +5 (dragon match)
        }
        
        score = calculate_similarity_score(base, target)
        # Should be around 25 + 30 + 5 = 60
        assert score >= 50

    def test_related_models_max_100(self):
        """Similarity score capped at 100"""
        base = {
            "name": "Model A",
            "creator": "john",
            "collections": ["Miniatures"],
            "keywords": ["dragon", "fantasy", "miniature"],
        }
        target = {
            "name": "Model B",
            "creator": "john",
            "collections": ["Miniatures"],
            "keywords": ["dragon", "fantasy", "miniature"],
        }
        
        score = calculate_similarity_score(base, target)
        assert score <= 100

    def test_related_models_limit(self):
        """Return limited number of related models"""
        models = get_related_models("test-model", limit=5)
        assert len(models) <= 5


class TestRecommendationEngine:
    """Tests for smart recommendations"""

    def test_recommend_by_next_steps(self):
        """Recommend follow-up prints"""
        # User printed large dragon, recommend smaller related models
        recent_prints = [
            {"model_ref": "dragon_large", "filament": "black", "success": True}
        ]
        
        recommendations = get_recommendations(recent_prints, strategy="next_steps")
        assert len(recommendations) > 0
        # Should recommend related models
        assert recommendations[0]["reason"] in ["Similar creator", "Same collection"]

    def test_recommend_by_popularity(self):
        """Recommend trending models"""
        recommendations = get_recommendations([], strategy="popularity")
        assert len(recommendations) > 0
        assert recommendations[0]["popularity_score"] is not None

    def test_recommend_by_difficulty(self):
        """Recommend models at same difficulty level"""
        recent_prints = [
            {"model_ref": "test", "difficulty_level": "intermediate"}
        ]
        
        recommendations = get_recommendations(
            recent_prints,
            strategy="difficulty_match"
        )
        
        for rec in recommendations:
            assert rec["difficulty_level"] == "intermediate"


class TestPrintStatistics:
    """Tests for per-model print statistics"""

    def test_aggregate_print_stats(self):
        """Aggregate statistics across all prints of a model"""
        archives = [
            {"archive_id": 1, "model_ref": "test", "print_time": 3600, "success": True},
            {"archive_id": 2, "model_ref": "test", "print_time": 3700, "success": True},
            {"archive_id": 3, "model_ref": "test", "print_time": 4000, "success": False},
        ]
        
        stats = aggregate_print_stats("test", archives)
        assert stats["total_prints"] == 3
        assert stats["successful_prints"] == 2
        assert stats["success_rate"] == 2/3
        assert abs(stats["avg_print_time"] - 3700) < 100

    def test_print_success_rate(self):
        """Calculate success rate for a model"""
        archives = [
            {"success": True},
            {"success": True},
            {"success": False},
        ]
        
        rate = calculate_success_rate(archives)
        assert rate == pytest.approx(0.667, rel=0.01)

    def test_filament_usage_summary(self):
        """Summarize filament usage by model"""
        archives = [
            {"model_ref": "test", "filament_used": 10, "filament_color": "black"},
            {"model_ref": "test", "filament_used": 12, "filament_color": "black"},
            {"model_ref": "test", "filament_used": 5, "filament_color": "red"},
        ]
        
        summary = get_filament_summary("test", archives)
        assert summary["black"]["total_used"] == 22
        assert summary["red"]["total_used"] == 5


class TestExportFunctionality:
    """Tests for export/backup of model catalog"""

    def test_export_json(self):
        """Export catalog as JSON"""
        export = export_catalog(format="json")
        assert isinstance(export, str)
        assert export.startswith("[") or export.startswith("{")

    def test_export_includes_enrichment(self):
        """Export includes enrichment metadata"""
        export = export_catalog(format="json", include_enrichment=True)
        data = parse_json(export)
        
        for model in data[:1]:
            assert "enrichment" in model

    def test_export_csv(self):
        """Export catalog as CSV"""
        export = export_catalog(format="csv")
        assert isinstance(export, str)
        lines = export.strip().split("\n")
        assert len(lines) > 1  # Header + data
        assert "model_name" in lines[0]

    def test_export_with_filters(self):
        """Export filtered subset of catalog"""
        export = export_catalog(
            format="json",
            collection="Miniatures",
            creator="john"
        )
        
        data = parse_json(export)
        for model in data:
            assert model["collection"] == "Miniatures"
            assert model["creator"] == "john"


class TestModelMigration:
    """Tests for migrating model metadata between versions"""

    def test_v1_to_v2_migration(self):
        """Migrate model from v1 to v2 format"""
        v1_model = {
            "id": 123,
            "name": "Test Model",
            "tags": "tag1,tag2",  # Comma-separated string
        }
        
        v2_model = migrate_model_format(v1_model, "v1", "v2")
        assert v2_model["model_id"] == 123
        assert isinstance(v2_model["tags"], list)
        assert v2_model["tags"] == ["tag1", "tag2"]

    def test_enrichment_migration(self):
        """Migrate enrichment data to new schema"""
        old_enrichment = {
            "print_time_min": 60,
            "print_time_max": 120,
        }
        
        new_enrichment = migrate_enrichment(old_enrichment)
        assert "print_time_estimate" in new_enrichment
        assert abs(new_enrichment["print_time_estimate"] - 90) < 5


class TestAPIIntegration:
    """Tests for related API endpoints"""

    def test_related_models_endpoint(self):
        """GET /api/models/{ref}/related endpoint"""
        response = call_api_endpoint("GET", "/api/models/test-model/related", {
            "limit": 5
        })
        
        assert response["success"] is True
        assert "related_models" in response
        assert len(response["related_models"]) <= 5

    def test_archive_model_endpoint(self):
        """GET /api/archives/{id}/model endpoint"""
        response = call_api_endpoint("GET", "/api/archives/12345/model", {})
        assert response["success"] is True
        assert "archive_id" in response

    def test_print_stats_endpoint(self):
        """GET /api/models/{ref}/print-stats endpoint"""
        response = call_api_endpoint("GET", "/api/models/test-model/print-stats", {})
        assert response["success"] is True
        assert "total_prints" in response
        assert "success_rate" in response


# Helper functions (would be implemented)

def get_archive_model(archive):
    """Get model for archive"""
    pass

def find_model_by_filename(filename, exact):
    """Find model by filename"""
    pass

def calculate_similarity_score(base, target):
    """Calculate similarity score"""
    pass

def get_related_models(model_ref, limit):
    """Get related models"""
    pass

def get_recommendations(recent_prints, strategy):
    """Get recommendations"""
    pass

def aggregate_print_stats(model_ref, archives):
    """Aggregate print stats"""
    pass

def calculate_success_rate(archives):
    """Calculate success rate"""
    pass

def get_filament_summary(model_ref, archives):
    """Get filament summary"""
    pass

def export_catalog(format, include_enrichment=False, **filters):
    """Export catalog"""
    pass

def parse_json(text):
    """Parse JSON"""
    pass

def migrate_model_format(model, from_version, to_version):
    """Migrate model format"""
    pass

def migrate_enrichment(enrichment):
    """Migrate enrichment"""
    pass

def call_api_endpoint(method, url, params):
    """Call API endpoint"""
    pass
