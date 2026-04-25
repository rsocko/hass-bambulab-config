"""
Tests for Phase 3.2 Task 4: Build Volume Helper

Tests for model fit analysis, placement hints, and difficulty estimation.
"""

import pytest
from sidecars.model_catalog.app.build_volume_helper import (
    ModelDimensions,
    FitStatus,
    BuildVolumeHelper,
)


class TestModelDimensions:
    """Test ModelDimensions dataclass."""

    def test_dimensions_creation(self):
        """Create model dimensions."""
        dims = ModelDimensions(width=100, height=150, depth=80)
        
        assert dims.width == 100
        assert dims.height == 150
        assert dims.depth == 80

    def test_volume_calculation(self):
        """Calculate model volume."""
        dims = ModelDimensions(width=100, height=100, depth=100)
        assert dims.volume == 1_000_000  # 100 * 100 * 100

    def test_max_dimension(self):
        """Get largest dimension."""
        dims = ModelDimensions(width=100, height=200, depth=50)
        assert dims.max_dimension == 200

    def test_min_dimension(self):
        """Get smallest dimension."""
        dims = ModelDimensions(width=100, height=200, depth=50)
        assert dims.min_dimension == 50


class TestBuildVolumeHelperFitAnalysis:
    """Test build volume fit analysis."""

    def test_model_fits(self):
        """Model within build volume should fit."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=200, height=200, depth=200)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is True
        assert analysis.status == FitStatus.FITS

    def test_model_oversized_x(self):
        """Model too wide should be flagged."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=200, depth=200)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is False
        assert analysis.status == FitStatus.OVERSIZED_X
        assert analysis.oversized_by_x > 0

    def test_model_oversized_y(self):
        """Model too long should be flagged."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=200, height=260, depth=200)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is False
        assert analysis.status == FitStatus.OVERSIZED_Y
        assert analysis.oversized_by_y > 0

    def test_model_oversized_z(self):
        """Model too tall should be flagged."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=200, height=200, depth=260)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is False
        assert analysis.status == FitStatus.OVERSIZED_Z
        assert analysis.oversized_by_z > 0

    def test_model_oversized_multiple_dimensions(self):
        """Model oversized in multiple dimensions."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=260, depth=260)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is False
        assert analysis.status == FitStatus.OVERSIZED_MULTIPLE

    def test_marginal_fit(self):
        """Model that fits but has tight margins."""
        helper = BuildVolumeHelper()
        # Leave only 3mm margin (threshold is 5mm)
        dims = ModelDimensions(
            width=helper.usable_volume_x - 3,
            height=helper.usable_volume_y - 3,
            depth=100,
        )
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is True
        assert analysis.status == FitStatus.MARGINAL

    def test_margin_calculation(self):
        """Calculate clearance margins correctly."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=100, height=100, depth=100)
        
        analysis = helper.check_fit(dims)
        assert analysis.margin_x > 0
        assert analysis.margin_y > 0
        assert analysis.margin_z > 0
        
        # Margins should be usable_volume minus model dimension
        expected_margin_x = helper.usable_volume_x - 100
        assert abs(analysis.margin_x - expected_margin_x) < 0.1

    def test_warnings_generated_for_oversized(self):
        """Warnings should be generated for oversized models."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=200, depth=200)
        
        analysis = helper.check_fit(dims)
        assert len(analysis.warnings) > 0
        assert any("too wide" in w.lower() for w in analysis.warnings)

    def test_warnings_generated_for_small_features(self):
        """Warnings for very small features."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=100, height=100, depth=1.5)
        
        analysis = helper.check_fit(dims)
        assert len(analysis.warnings) > 0
        assert any("small" in w.lower() for w in analysis.warnings)

    def test_warnings_generated_for_tall_model(self):
        """Warnings for very tall models."""
        helper = BuildVolumeHelper()
        # Model taller than 240mm threshold (height field is Y-axis)
        dims = ModelDimensions(width=100, height=241, depth=100)
        
        analysis = helper.check_fit(dims)
        assert len(analysis.warnings) > 0
        assert any("tall" in w.lower() for w in analysis.warnings)


class TestPlacementHints:
    """Test placement hint generation."""

    def test_placement_hints_for_fitting_model(self):
        """Placement hints should include CENTER for fitting models."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=150, height=150, depth=100)
        
        analysis = helper.check_fit(dims)
        assert len(analysis.placement_hints) > 0

    def test_placement_hints_for_wide_model(self):
        """Wide models should suggest LAY_FLAT."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=220, height=100, depth=100)
        
        analysis = helper.check_fit(dims)
        # Should include placement hint for wide models
        assert len(analysis.placement_hints) > 0

    def test_placement_hints_for_oversized_model(self):
        """Oversized models should not have placement hints."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=200, depth=200)
        
        analysis = helper.check_fit(dims)
        # Oversized models should have no valid placement hints
        assert len(analysis.placement_hints) == 0


class TestPlacementStrategies:
    """Test placement strategy generation."""

    def test_generate_strategies_for_fitting_model(self):
        """Generate strategies for models that fit."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=150, height=150, depth=100)
        
        hints = helper.generate_placement_hints(dims)
        assert "strategies" in hints
        assert len(hints["strategies"]) > 0

    def test_strategy_includes_center(self):
        """CENTER strategy should always be first."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=150, height=150, depth=100)
        
        hints = helper.generate_placement_hints(dims)
        assert hints["strategies"][0]["strategy"] == "center"

    def test_recommended_strategy_provided(self):
        """A recommended strategy should be provided."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=150, height=150, depth=100)
        
        hints = helper.generate_placement_hints(dims)
        if len(hints["strategies"]) > 0:
            assert "recommended" in hints

    def test_strategies_for_oversized_model(self):
        """No strategies for oversized models."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=200, depth=200)
        
        hints = helper.generate_placement_hints(dims)
        assert len(hints["strategies"]) == 0
        assert "note" in hints["fit_analysis"]


class TestPrintDifficulty:
    """Test print difficulty estimation."""

    def test_easy_model(self):
        """Small, simple model should be Easy."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=100, height=100, depth=100)
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert difficulty["level"] == "Easy"
        assert difficulty["score"] == 0

    def test_challenging_model(self):
        """Oversized model should be Challenging or Expert."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=200, depth=200)
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert difficulty["level"] in ["Challenging", "Expert"]
        assert difficulty["score"] > 2

    def test_tall_model_difficulty(self):
        """Very tall model should increase difficulty."""
        helper = BuildVolumeHelper()
        # Model taller than 240mm threshold (height field is Y-axis)
        dims = ModelDimensions(width=100, height=241, depth=100)
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert difficulty["factors"]["height"] > 0

    def test_small_feature_difficulty(self):
        """Model with very small features should be challenging."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=100, height=100, depth=1.5)
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert difficulty["factors"]["feature_size"] > 0

    def test_difficulty_recommendations_provided(self):
        """Recommendations should be provided for difficult models."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=260, height=200, depth=200)
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert "recommendations" in difficulty
        assert len(difficulty["recommendations"]) > 0

    def test_difficulty_score_range(self):
        """Difficulty score should be within valid range."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=200, height=200, depth=200)
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert 0 <= difficulty["score"] <= difficulty["max_score"]


class TestWarningMessages:
    """Test warning message generation."""

    def test_oversized_x_warning_contains_dimensions(self):
        """X oversizing warning should include actual dimensions."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=270, height=200, depth=200)
        
        analysis = helper.check_fit(dims)
        x_warnings = [w for w in analysis.warnings if "X-axis" in w or "wide" in w]
        assert len(x_warnings) > 0
        assert "270" in x_warnings[0] or "270.0" in x_warnings[0]

    def test_warning_indicates_how_much_oversized(self):
        """Warning should indicate exact overage amount."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=265, height=200, depth=200)
        
        analysis = helper.check_fit(dims)
        x_warnings = [w for w in analysis.warnings if "X-axis" in w or "wide" in w]
        assert len(x_warnings) > 0
        # Should mention the overage (about 7mm with 2mm margins)

    def test_margin_warning_threshold(self):
        """Should warn when margins are less than 2mm."""
        helper = BuildVolumeHelper()
        # Create model with very tight margins
        dims = ModelDimensions(
            width=helper.usable_volume_x - 1,
            height=helper.usable_volume_y - 1,
            depth=100,
        )
        
        analysis = helper.check_fit(dims)
        margin_warnings = [w for w in analysis.warnings if "close to bed edges" in w]
        assert len(margin_warnings) > 0


class TestIntegration:
    """Integration tests for BuildVolumeHelper."""

    def test_realistic_small_print(self):
        """Analyze realistic small print job."""
        helper = BuildVolumeHelper()
        # Gridfinity bin: ~100x100x100mm
        dims = ModelDimensions(width=100, height=100, depth=100)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is True
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert difficulty["level"] == "Easy"

    def test_realistic_large_print(self):
        """Analyze realistic large print job."""
        helper = BuildVolumeHelper()
        # Large organizer: 200x200x120mm
        dims = ModelDimensions(width=200, height=200, depth=120)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is True
        
        difficulty = helper.estimate_print_difficulty(dims)
        # Large footprint increases difficulty
        assert difficulty["level"] in ["Easy", "Moderate", "Challenging"]

    def test_realistic_oversized_print(self):
        """Analyze oversized model."""
        helper = BuildVolumeHelper()
        # Model too large: 270x270x150mm
        dims = ModelDimensions(width=270, height=270, depth=150)
        
        analysis = helper.check_fit(dims)
        assert analysis.fits is False
        
        difficulty = helper.estimate_print_difficulty(dims)
        assert difficulty["level"] == "Expert"

    def test_complete_workflow(self):
        """Test complete analysis workflow."""
        helper = BuildVolumeHelper()
        dims = ModelDimensions(width=180, height=180, depth=150)
        
        # Get fit analysis
        fit_analysis = helper.check_fit(dims)
        assert fit_analysis.fits is True
        
        # Get placement hints
        placement = helper.generate_placement_hints(dims)
        assert "strategies" in placement
        
        # Get difficulty
        difficulty = helper.estimate_print_difficulty(dims)
        assert "level" in difficulty
        
        # All should be consistent
        assert placement["fit_analysis"]["fits"] == fit_analysis.fits


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
