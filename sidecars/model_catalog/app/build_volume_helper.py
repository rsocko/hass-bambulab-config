"""
Build Volume Helper for Phase 3.2 Task 4

Provides utilities for checking model fit, generating placement hints,
and damage prediction for the Bambu P1S printer.

**Bambu P1S Specifications:**
- Build volume: 256×256×256 mm
- Nozzle diameter: 0.4 mm (standard)
- Min feature size: ~2-3 mm
- Typical overhang: 45° before requiring support
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import math


class FitStatus(Enum):
    """Model fit status relative to build volume."""
    FITS = "fits"
    MARGINAL = "marginal"  # Fits but close to limits
    OVERSIZED_X = "oversized_x"
    OVERSIZED_Y = "oversized_y"
    OVERSIZED_Z = "oversized_z"
    OVERSIZED_MULTIPLE = "oversized_multiple"


class PlacementHint(Enum):
    """Recommended placement strategies."""
    CENTER = "center"
    ROTATE_45 = "rotate_45"
    ROTATE_90 = "rotate_90"
    LAY_FLAT = "lay_flat"
    STAND_UPRIGHT = "stand_upright"
    DIAGONAL = "diagonal"


@dataclass
class ModelDimensions:
    """Model dimensions and bounds."""
    width: float  # X-axis (mm)
    height: float  # Y-axis (mm, typically Z on printer)
    depth: float  # Z-axis (mm, typically Y on printer)
    
    @property
    def volume(self) -> float:
        """Calculate model volume in cubic mm."""
        return self.width * self.height * self.depth
    
    @property
    def max_dimension(self) -> float:
        """Get largest dimension."""
        return max(self.width, self.height, self.depth)
    
    @property
    def min_dimension(self) -> float:
        """Get smallest dimension."""
        return min(self.width, self.height, self.depth)


@dataclass
class FitAnalysis:
    """Result of build volume fit analysis."""
    status: FitStatus
    fits: bool
    margin_x: float  # Clearance from X boundary (mm)
    margin_y: float  # Clearance from Y boundary (mm)
    margin_z: float  # Clearance from Z boundary (mm)
    oversized_by_x: float  # How much exceeds X (0 if fits)
    oversized_by_y: float  # How much exceeds Y (0 if fits)
    oversized_by_z: float  # How much exceeds Z (0 if fits)
    warnings: list[str]
    placement_hints: list[PlacementHint]
    estimated_print_time: float | None = None  # hours (optional)


class BuildVolumeHelper:
    """Helper for Bambu P1S build volume analysis."""
    
    # Bambu P1S specifications (mm)
    BUILD_VOLUME_X = 256
    BUILD_VOLUME_Y = 256
    BUILD_VOLUME_Z = 256
    
    # Safety margins (mm) - buffer to prevent crashes
    MARGIN_X = 2.0  # 2mm safety margin
    MARGIN_Y = 2.0
    MARGIN_Z = 1.0  # Less margin on Z (probe is below nozzle)
    
    # Minimum printable feature size
    MIN_FEATURE_SIZE = 2.0  # mm (below this, features may fail)
    
    # Overhang angle threshold (degrees)
    OVERHANG_ANGLE_THRESHOLD = 45.0  # Angles > 45° typically need support
    
    def __init__(self):
        """Initialize build volume helper."""
        self.usable_volume_x = self.BUILD_VOLUME_X - (2 * self.MARGIN_X)
        self.usable_volume_y = self.BUILD_VOLUME_Y - (2 * self.MARGIN_Y)
        self.usable_volume_z = self.BUILD_VOLUME_Z - self.MARGIN_Z  # Only bottom margin
    
    def check_fit(self, model_dims: ModelDimensions) -> FitAnalysis:
        """
        Check if model fits in build volume.
        
        Args:
            model_dims: Model dimensions
            
        Returns:
            FitAnalysis with detailed fit information
        """
        # Calculate margins
        margin_x = self.usable_volume_x - model_dims.width
        margin_y = self.usable_volume_y - model_dims.height
        margin_z = self.usable_volume_z - model_dims.depth
        
        # Calculate oversizing
        oversized_x = max(0, model_dims.width - self.usable_volume_x)
        oversized_y = max(0, model_dims.height - self.usable_volume_y)
        oversized_z = max(0, model_dims.depth - self.usable_volume_z)
        
        # Determine fit status
        oversized_count = sum([
            1 if oversized_x > 0 else 0,
            1 if oversized_y > 0 else 0,
            1 if oversized_z > 0 else 0,
        ])
        
        if oversized_count == 0:
            # Model fits
            min_margin = min(margin_x, margin_y, margin_z)
            if min_margin < 5:
                status = FitStatus.MARGINAL
            else:
                status = FitStatus.FITS
            fits = True
        elif oversized_count == 1:
            # Single dimension oversized
            if oversized_x > 0:
                status = FitStatus.OVERSIZED_X
            elif oversized_y > 0:
                status = FitStatus.OVERSIZED_Y
            else:
                status = FitStatus.OVERSIZED_Z
            fits = False
        else:
            # Multiple dimensions oversized
            status = FitStatus.OVERSIZED_MULTIPLE
            fits = False
        
        # Generate warnings
        warnings = self._generate_warnings(
            model_dims, oversized_x, oversized_y, oversized_z
        )
        
        # Get placement hints
        placement_hints = self._get_placement_hints(model_dims, status)
        
        return FitAnalysis(
            status=status,
            fits=fits,
            margin_x=max(0, margin_x),
            margin_y=max(0, margin_y),
            margin_z=max(0, margin_z),
            oversized_by_x=oversized_x,
            oversized_by_y=oversized_y,
            oversized_by_z=oversized_z,
            warnings=warnings,
            placement_hints=placement_hints,
        )
    
    def generate_placement_hints(self, model_dims: ModelDimensions) -> dict[str, Any]:
        """
        Generate optimal placement strategies.
        
        Args:
            model_dims: Model dimensions
            
        Returns:
            Dictionary with placement strategies and recommendations
        """
        analysis = self.check_fit(model_dims)
        
        hints = {
            "fit_analysis": {
                "status": analysis.status.value,
                "fits": analysis.fits,
                "warnings": analysis.warnings,
            },
            "strategies": [],
        }
        
        if not analysis.fits:
            hints["fit_analysis"]["note"] = "Model does not fit. Consider scaling or splitting."
            return hints
        
        # Generate placement strategies
        strategies = self._generate_strategies(model_dims)
        hints["strategies"] = strategies
        
        # Recommend best strategy
        if strategies:
            best = strategies[0]
            hints["recommended"] = {
                "strategy": best["strategy"],
                "reason": best["reason"],
            }
        
        return hints
    
    def estimate_print_difficulty(self, model_dims: ModelDimensions) -> dict[str, Any]:
        """
        Estimate print difficulty based on dimensions.
        
        Args:
            model_dims: Model dimensions
            
        Returns:
            Dictionary with difficulty assessment
        """
        analysis = self.check_fit(model_dims)
        
        difficulty_factors = {
            "build_volume": 0,
            "feature_size": 0,
            "height": 0,
            "footprint": 0,
        }
        
        # Build volume factor
        if not analysis.fits:
            difficulty_factors["build_volume"] = 3
        elif analysis.status == FitStatus.MARGINAL:
            difficulty_factors["build_volume"] = 2
        
        # Feature size factor (very small models may be difficult)
        if model_dims.min_dimension < self.MIN_FEATURE_SIZE:
            difficulty_factors["feature_size"] = 3
        elif model_dims.min_dimension < 5:
            difficulty_factors["feature_size"] = 2
        
        # Height factor (very tall models may tip or warp)
        if model_dims.height > 200:
            difficulty_factors["height"] = 2
        elif model_dims.height > 240:
            difficulty_factors["height"] = 3
        
        # Footprint factor (large bases need good bed adhesion)
        footprint = model_dims.width * model_dims.depth
        if footprint > 200 * 200:  # Large footprint
            difficulty_factors["footprint"] = 2
        
        # Calculate overall difficulty
        total_score = sum(difficulty_factors.values())
        if total_score == 0:
            difficulty_level = "Easy"
        elif total_score <= 2:
            difficulty_level = "Moderate"
        elif total_score <= 4:
            difficulty_level = "Challenging"
        else:
            difficulty_level = "Expert"
        
        return {
            "level": difficulty_level,
            "score": total_score,
            "max_score": 12,
            "factors": difficulty_factors,
            "recommendations": self._generate_difficulty_recommendations(
                difficulty_factors
            ),
        }
    
    def _generate_warnings(
        self,
        model_dims: ModelDimensions,
        oversized_x: float,
        oversized_y: float,
        oversized_z: float,
    ) -> list[str]:
        """Generate warning messages."""
        warnings = []
        
        if oversized_x > 0:
            warnings.append(
                f"⚠️ Model is {oversized_x:.1f}mm too wide (X-axis). "
                f"Max: {self.usable_volume_x}mm, Model: {model_dims.width:.1f}mm"
            )
        
        if oversized_y > 0:
            warnings.append(
                f"⚠️ Model is {oversized_y:.1f}mm too long (Y-axis). "
                f"Max: {self.usable_volume_y}mm, Model: {model_dims.height:.1f}mm"
            )
        
        if oversized_z > 0:
            warnings.append(
                f"⚠️ Model is {oversized_z:.1f}mm too tall (Z-axis). "
                f"Max: {self.usable_volume_z}mm, Model: {model_dims.depth:.1f}mm"
            )
        
        if model_dims.min_dimension < self.MIN_FEATURE_SIZE:
            warnings.append(
                f"⚠️ Model has very small features ({model_dims.min_dimension:.1f}mm). "
                f"Minimum reliable: {self.MIN_FEATURE_SIZE}mm. May fail or break."
            )
        
        if model_dims.height > 240:
            warnings.append(
                "⚠️ Model is very tall (240mm+). Risk of warp or tip-over. "
                "Consider printing with dense infill or supports."
            )
        
        # Margin warnings
        min_margin = min([
            max(0, self.usable_volume_x - model_dims.width),
            max(0, self.usable_volume_y - model_dims.height),
        ])
        
        if min_margin < 2:
            warnings.append(
                "⚠️ Model is very close to bed edges. "
                "Any offset or nozzle variance could cause crashes."
            )
        
        return warnings
    
    def _get_placement_hints(
        self,
        model_dims: ModelDimensions,
        status: FitStatus,
    ) -> list[PlacementHint]:
        """Determine optimal placement strategies."""
        hints = []
        
        if status == FitStatus.FITS or status == FitStatus.MARGINAL:
            hints.append(PlacementHint.CENTER)
            
            # If wide, suggest laying flat
            if model_dims.width > 200 or model_dims.height > 200:
                hints.append(PlacementHint.LAY_FLAT)
            
            # If tall, suggest upright (to maximize XY area)
            if model_dims.depth > 150:
                hints.append(PlacementHint.STAND_UPRIGHT)
            
            # For mixed dimensions, suggest diagonal
            if 100 < model_dims.width < 220 and 100 < model_dims.height < 220:
                hints.append(PlacementHint.DIAGONAL)
        
        return hints
    
    def _generate_strategies(self, model_dims: ModelDimensions) -> list[dict[str, Any]]:
        """Generate placement strategies with rationales."""
        strategies = []
        
        # Strategy 1: Center
        strategies.append({
            "strategy": "center",
            "placement": "Center model on build plate",
            "pros": ["Even bed contact", "Balanced nozzle wear"],
            "cons": ["Uses maximum footprint"],
            "reason": "Safe baseline approach",
        })
        
        # Strategy 2: Rotate for smaller footprint
        if model_dims.depth > max(model_dims.width, model_dims.height):
            strategies.append({
                "strategy": "rotate_90",
                "placement": "Rotate 90° to reduce footprint",
                "pros": ["Smaller bed area needed", "Better for tall parts"],
                "cons": ["May require supports"],
                "reason": f"Reduces footprint from "
                         f"{model_dims.width:.0f}×{model_dims.height:.0f} "
                         f"to {model_dims.width:.0f}×{model_dims.depth:.0f}",
            })
        
        # Strategy 3: Diagonal placement
        if 150 < model_dims.width < 220 and 150 < model_dims.height < 220:
            diag_dist = math.sqrt(model_dims.width**2 + model_dims.height**2)
            if diag_dist > 256:
                strategies.append({
                    "strategy": "diagonal",
                    "placement": "Place diagonally across build plate",
                    "pros": ["Uses diagonal space (362mm available)"],
                    "cons": ["Uneven bed contact potential"],
                    "reason": f"Diagonal distance {diag_dist:.0f}mm fits in "
                             f"diagonal space (362mm max)",
                })
        
        return strategies
    
    def _generate_difficulty_recommendations(
        self, factors: dict[str, int]
    ) -> list[str]:
        """Generate recommendations based on difficulty factors."""
        recommendations = []
        
        if factors["build_volume"] > 0:
            recommendations.append(
                "📦 Model is large. Ensure bed is level and adhesion is good."
            )
        
        if factors["feature_size"] > 0:
            recommendations.append(
                "🔬 Model has small features. Use fine nozzle or slice at high resolution."
            )
        
        if factors["height"] > 0:
            recommendations.append(
                "📏 Model is tall. Consider dense infill to prevent warping. "
                "Check nozzle height frequently."
            )
        
        if factors["footprint"] > 0:
            recommendations.append(
                "🦶 Model has large footprint. Use brim or raft for better adhesion."
            )
        
        return recommendations


# Convenience function
def analyze_model_fit(model_dims: ModelDimensions) -> FitAnalysis:
    """
    Quick fit analysis without instantiating helper.
    
    Args:
        model_dims: Model dimensions
        
    Returns:
        FitAnalysis result
    """
    helper = BuildVolumeHelper()
    return helper.check_fit(model_dims)


def estimate_difficulty(model_dims: ModelDimensions) -> dict[str, Any]:
    """
    Quick difficulty estimation without instantiating helper.
    
    Args:
        model_dims: Model dimensions
        
    Returns:
        Difficulty assessment
    """
    helper = BuildVolumeHelper()
    return helper.estimate_print_difficulty(model_dims)
