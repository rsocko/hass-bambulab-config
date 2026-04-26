"""
Phase 3.3 Task 3 Tests: Model Statistics And Analytics

Tests for print statistics aggregation, filament analysis, and
recommendation engine functionality.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sidecars.model_catalog.app.model_statistics import (
    PrintStatistics,
    PrintStatisticsAnalyzer,
    FilamentAnalyzer,
    FilamentSummary,
    RecommendationEngine,
    DifficultyLevel,
    RecommendationStrategy,
    ModelRecommendation,
)


class TestPrintStatistics:
    """Test PrintStatistics dataclass."""

    def test_create_print_statistics(self):
        """Create PrintStatistics object."""
        stats = PrintStatistics(model_ref="test_model")
        
        assert stats.model_ref == "test_model"
        assert stats.total_prints == 0
        assert stats.successful_prints == 0
        assert stats.success_rate == 0.0

    def test_print_statistics_with_data(self):
        """Create PrintStatistics with initial data."""
        stats = PrintStatistics(
            model_ref="gridfinity",
            total_prints=5,
            successful_prints=4,
            failed_prints=1,
            success_rate=0.8
        )
        
        assert stats.total_prints == 5
        assert stats.successful_prints == 4
        assert stats.success_rate == 0.8


class TestPrintStatisticsAnalyzer:
    """Test print statistics aggregation."""

    def test_aggregate_print_stats_empty(self):
        """Handle empty archive list."""
        analyzer = PrintStatisticsAnalyzer()
        stats = analyzer.aggregate_print_stats("test", [])
        
        assert stats.model_ref == "test"
        assert stats.total_prints == 0
        assert stats.success_rate == 0.0

    def test_aggregate_print_stats_simple(self):
        """Aggregate simple print statistics."""
        analyzer = PrintStatisticsAnalyzer()
        archives = [
            {"success": True, "print_time": 3600},
            {"success": True, "print_time": 3700},
            {"success": False, "print_time": 3500},
        ]
        
        stats = analyzer.aggregate_print_stats("test", archives)
        
        assert stats.total_prints == 3
        assert stats.successful_prints == 2
        assert stats.failed_prints == 1
        assert stats.success_rate == pytest.approx(0.667, rel=0.01)

    def test_aggregate_print_stats_with_times(self):
        """Aggregate print times accurately."""
        analyzer = PrintStatisticsAnalyzer()
        archives = [
            {"success": True, "print_time": 3600},
            {"success": True, "print_time": 3600},
            {"success": True, "print_time": 3600},
        ]
        
        stats = analyzer.aggregate_print_stats("test", archives)
        
        assert stats.avg_print_time == 3600
        assert stats.min_print_time == 3600
        assert stats.max_print_time == 3600

    def test_aggregate_print_stats_with_dates(self):
        """Track print dates correctly."""
        analyzer = PrintStatisticsAnalyzer()
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        
        archives = [
            {
                "success": True,
                "completed_at": yesterday.isoformat()
            },
            {
                "success": True,
                "completed_at": now.isoformat()
            },
        ]
        
        stats = analyzer.aggregate_print_stats("test", archives)
        
        assert stats.first_print_date is not None
        assert stats.last_print_date is not None
        assert stats.days_since_last_print <= 1

    def test_aggregate_print_stats_with_filament(self):
        """Aggregate filament usage."""
        analyzer = PrintStatisticsAnalyzer()
        archives = [
            {"success": True, "filament_used": 10},
            {"success": True, "filament_used": 12},
            {"success": True, "filament_used": 8},
        ]
        
        stats = analyzer.aggregate_print_stats("test", archives)
        
        assert stats.total_filament_used == 30
        assert stats.avg_filament_per_print == 10.0

    def test_calculate_success_rate_perfect(self):
        """Calculate 100% success rate."""
        analyzer = PrintStatisticsAnalyzer()
        archives = [
            {"success": True},
            {"success": True},
            {"success": True},
        ]
        
        rate = analyzer.calculate_success_rate(archives)
        assert rate == 1.0

    def test_calculate_success_rate_partial(self):
        """Calculate partial success rate."""
        analyzer = PrintStatisticsAnalyzer()
        archives = [
            {"success": True},
            {"success": True},
            {"success": False},
            {"success": False},
        ]
        
        rate = analyzer.calculate_success_rate(archives)
        assert rate == pytest.approx(0.5, rel=0.01)

    def test_calculate_success_rate_empty(self):
        """Handle empty archive list for success rate."""
        analyzer = PrintStatisticsAnalyzer()
        rate = analyzer.calculate_success_rate([])
        assert rate == 0.0

    def test_get_difficulty_level_easy(self):
        """Classify easy difficulty (high success)."""
        analyzer = PrintStatisticsAnalyzer()
        stats = PrintStatistics(model_ref="test", total_prints=5, success_rate=0.95)
        
        difficulty = analyzer.get_difficulty_level(stats)
        assert difficulty == DifficultyLevel.EASY

    def test_get_difficulty_level_moderate(self):
        """Classify moderate difficulty."""
        analyzer = PrintStatisticsAnalyzer()
        stats = PrintStatistics(model_ref="test", total_prints=5, success_rate=0.80)
        
        difficulty = analyzer.get_difficulty_level(stats)
        assert difficulty == DifficultyLevel.MODERATE

    def test_get_difficulty_level_challenging(self):
        """Classify challenging difficulty (low success)."""
        analyzer = PrintStatisticsAnalyzer()
        stats = PrintStatistics(model_ref="test", total_prints=5, success_rate=0.60)
        
        difficulty = analyzer.get_difficulty_level(stats)
        assert difficulty == DifficultyLevel.CHALLENGING

    def test_identify_problematic_models(self):
        """Identify models with low success rates."""
        analyzer = PrintStatisticsAnalyzer()
        stats_list = [
            PrintStatistics(model_ref="good", total_prints=5, success_rate=0.95),
            PrintStatistics(model_ref="bad", total_prints=5, success_rate=0.50),
            PrintStatistics(model_ref="medium", total_prints=5, success_rate=0.75),
        ]
        
        problematic = analyzer.identify_problematic_models(
            stats_list,
            threshold_success_rate=0.70,
            min_prints=3
        )
        
        assert len(problematic) == 2  # "bad" and "medium"
        assert problematic[0].model_ref == "bad"  # Worst first

    def test_identify_problematic_models_min_prints_filter(self):
        """Only flag models with sufficient print history."""
        analyzer = PrintStatisticsAnalyzer()
        stats_list = [
            PrintStatistics(model_ref="insufficient", total_prints=1, success_rate=0.50),
            PrintStatistics(model_ref="sufficient", total_prints=5, success_rate=0.50),
        ]
        
        problematic = analyzer.identify_problematic_models(
            stats_list,
            threshold_success_rate=0.70,
            min_prints=3
        )
        
        assert len(problematic) == 1
        assert problematic[0].model_ref == "sufficient"


class TestFilamentAnalyzer:
    """Test filament analysis."""

    def test_get_filament_summary_empty(self):
        """Handle empty archive list."""
        analyzer = FilamentAnalyzer()
        summary = analyzer.get_filament_summary("test", [])
        
        assert summary.model_ref == "test"
        assert summary.total_filament_used == 0
        assert len(summary.colors_used) == 0

    def test_get_filament_summary_single_color(self):
        """Aggregate filament by single color."""
        analyzer = FilamentAnalyzer()
        archives = [
            {"filament_used": 10, "filament_color": "black"},
            {"filament_used": 12, "filament_color": "black"},
        ]
        
        summary = analyzer.get_filament_summary("test", archives)
        
        assert summary.total_filament_used == 22
        assert summary.colors_used["black"]["total"] == 22
        assert summary.colors_used["black"]["count"] == 2
        assert summary.average_filament_per_print == 11.0

    def test_get_filament_summary_multi_color(self):
        """Aggregate filament by multiple colors."""
        analyzer = FilamentAnalyzer()
        archives = [
            {"filament_used": 10, "filament_color": "black"},
            {"filament_used": 12, "filament_color": "black"},
            {"filament_used": 5, "filament_color": "red"},
            {"filament_used": 8, "filament_color": "blue"},
        ]
        
        summary = analyzer.get_filament_summary("test", archives)
        
        assert summary.total_filament_used == 35
        assert summary.colors_used["black"]["total"] == 22
        assert summary.colors_used["red"]["total"] == 5
        assert summary.colors_used["blue"]["total"] == 8

    def test_get_filament_summary_case_insensitive(self):
        """Handle color names case-insensitively."""
        analyzer = FilamentAnalyzer()
        archives = [
            {"filament_used": 10, "filament_color": "Black"},
            {"filament_used": 12, "filament_color": "BLACK"},
        ]
        
        summary = analyzer.get_filament_summary("test", archives)
        
        assert summary.total_filament_used == 22
        assert summary.colors_used["black"]["total"] == 22

    def test_get_filament_summary_min_max(self):
        """Track min and max filament per print."""
        analyzer = FilamentAnalyzer()
        archives = [
            {"filament_used": 8, "filament_color": "black"},
            {"filament_used": 15, "filament_color": "black"},
            {"filament_used": 12, "filament_color": "black"},
        ]
        
        summary = analyzer.get_filament_summary("test", archives)
        
        assert summary.colors_used["black"]["min"] == 8
        assert summary.colors_used["black"]["max"] == 15

    def test_get_top_colors_by_usage(self):
        """Get top colors by usage amount."""
        analyzer = FilamentAnalyzer()
        archives = [
            {"filament_used": 100, "filament_color": "black"},
            {"filament_used": 50, "filament_color": "red"},
            {"filament_used": 75, "filament_color": "blue"},
            {"filament_used": 25, "filament_color": "green"},
        ]
        
        summary = analyzer.get_filament_summary("test", archives)
        top_colors = analyzer.get_top_colors_by_usage(summary, limit=2)
        
        assert len(top_colors) == 2
        assert top_colors[0]["color"] == "black"  # 100
        assert top_colors[1]["color"] == "blue"   # 75


class TestRecommendationEngine:
    """Test recommendation engine."""

    def test_get_recommendations_next_steps_no_data(self):
        """Handle empty data for next steps."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recs = engine.get_recommendations([], [], strategy=RecommendationStrategy.NEXT_STEPS)
        
        assert len(recs) == 0

    def test_get_recommendations_next_steps_creator_match(self):
        """Recommend models from same creator."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [{"model_ref": "m1", "creator": "john", "collections": []}]
        all_models = [
            {"model_ref": "m2", "creator": "john", "name": "Model 2", "collections": [], "keywords": []},
            {"model_ref": "m3", "creator": "jane", "name": "Model 3", "collections": [], "keywords": []},
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.NEXT_STEPS
        )
        
        assert len(recs) > 0
        assert recs[0].model_ref == "m2"
        assert "Same creator" in recs[0].reason

    def test_get_recommendations_next_steps_collection_match(self):
        """Recommend models from same collection."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [{"model_ref": "m1", "creator": "john", "collections": ["Gridfinity"]}]
        all_models = [
            {
                "model_ref": "m2",
                "creator": "jane",
                "name": "Model 2",
                "collections": ["Gridfinity"],
                "keywords": []
            },
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.NEXT_STEPS
        )
        
        assert len(recs) > 0
        assert "Gridfinity" in recs[0].reason

    def test_get_recommendations_difficulty_match_easy(self):
        """Recommend easy models for high success rate."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [
            {"success": True},
            {"success": True},
            {"success": True},
        ]
        all_models = [
            {"model_ref": "m1", "name": "Model 1", "difficulty_level": DifficultyLevel.EASY},
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.DIFFICULTY_MATCH
        )
        
        assert len(recs) > 0
        assert recs[0].model_ref == "m1"

    def test_get_recommendations_difficulty_match_challenging(self):
        """Recommend challenging models for low success rate."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [
            {"success": False},
            {"success": False},
            {"success": False},
        ]
        all_models = [
            {"model_ref": "m1", "name": "Model 1", "difficulty_level": DifficultyLevel.CHALLENGING},
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.DIFFICULTY_MATCH
        )
        
        assert len(recs) > 0
        assert recs[0].model_ref == "m1"

    def test_get_recommendations_popularity(self):
        """Recommend popular models."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        all_models = [
            {"model_ref": "m1", "name": "Model 1", "print_count": 50},
            {"model_ref": "m2", "name": "Model 2", "print_count": 100},
            {"model_ref": "m3", "name": "Model 3", "print_count": 25},
        ]
        
        recs = engine.get_recommendations(
            [], all_models,
            strategy=RecommendationStrategy.POPULARITY,
            limit=2
        )
        
        assert len(recs) == 2
        assert recs[0].model_ref == "m2"  # Most popular first

    def test_get_recommendations_similar_creator(self):
        """Recommend models from creators of recent prints."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [{"creator": "john"}]
        all_models = [
            {"model_ref": "m1", "name": "Model 1", "creator": "john"},
            {"model_ref": "m2", "name": "Model 2", "creator": "jane"},
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.SIMILAR_CREATOR
        )
        
        assert len(recs) > 0
        assert recs[0].model_ref == "m1"

    def test_get_recommendations_same_collection(self):
        """Recommend models from same collections."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [{"collections": ["Gridfinity", "Storage"]}]
        all_models = [
            {"model_ref": "m1", "name": "Model 1", "collections": ["Gridfinity"]},
            {"model_ref": "m2", "name": "Model 2", "collections": ["Other"]},
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.SAME_COLLECTION
        )
        
        assert len(recs) > 0
        assert recs[0].model_ref == "m1"

    def test_get_recommendations_respects_limit(self):
        """Respect limit on recommendations."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        recent = [{"creator": "john"}]
        all_models = [
            {"model_ref": f"m{i}", "name": f"Model {i}", "creator": "john"}
            for i in range(20)
        ]
        
        recs = engine.get_recommendations(
            recent, all_models,
            strategy=RecommendationStrategy.SIMILAR_CREATOR,
            limit=5
        )
        
        assert len(recs) <= 5

    def test_model_recommendation_dataclass(self):
        """Create ModelRecommendation."""
        rec = ModelRecommendation(
            model_ref="m1",
            model_name="Test Model",
            score=85.5,
            reason="Test reason",
            strategy=RecommendationStrategy.NEXT_STEPS
        )
        
        assert rec.model_ref == "m1"
        assert rec.score == 85.5
        assert rec.strategy == RecommendationStrategy.NEXT_STEPS


class TestIntegration:
    """Integration tests for statistics and recommendations."""

    def test_full_workflow_aggregation_and_recommendation(self):
        """Full workflow: aggregate stats, recommend models."""
        analyzer = PrintStatisticsAnalyzer()
        engine = RecommendationEngine(analyzer)
        
        # Model with print history
        archives = [
            {
                "model_ref": "gridfinity_bin",
                "success": True,
                "print_time": 3600,
                "filament_used": 10,
                "filament_color": "black",
                "completed_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
                "creator": "gridfinity_design",
                "collections": ["Storage", "Organization"]
            },
            {
                "model_ref": "gridfinity_bin",
                "success": True,
                "print_time": 3700,
                "filament_used": 11,
                "filament_color": "black",
                "completed_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "creator": "gridfinity_design",
                "collections": ["Storage", "Organization"]
            },
        ]
        
        # Aggregate statistics
        stats = analyzer.aggregate_print_stats("gridfinity_bin", archives)
        assert stats.success_rate == 1.0
        assert stats.avg_filament_per_print == 10.5
        
        # Get filament analysis
        filament_analyzer = FilamentAnalyzer()
        filament_summary = filament_analyzer.get_filament_summary("gridfinity_bin", archives)
        assert filament_summary.total_filament_used == 21
        
        # Generate recommendations
        all_models = [
            {
                "model_ref": "gridfinity_drawer",
                "name": "Gridfinity Drawer",
                "creator": "gridfinity_design",
                "collections": ["Storage", "Organization"],
                "keywords": ["storage", "organizer"],
                "difficulty_level": DifficultyLevel.EASY
            },
            {
                "model_ref": "other_model",
                "name": "Other Model",
                "creator": "someone_else",
                "collections": ["Toys"],
                "keywords": ["fun"],
                "difficulty_level": DifficultyLevel.MODERATE
            },
        ]
        
        recs = engine.get_recommendations(
            archives,
            all_models,
            strategy=RecommendationStrategy.NEXT_STEPS
        )
        
        # Should recommend gridfinity_drawer (same creator and collection)
        assert len(recs) > 0
        assert recs[0].model_ref == "gridfinity_drawer"
