"""
Phase 3.3 Task 3: Model Statistics And Analytics

Module for aggregating print statistics, success rates, and generating
recommendations based on model history and archive data.

Provides:
- Print statistics aggregation (count, success rate, avg time)
- Filament usage analysis by color/type
- Recommendation engine based on print history
- Difficulty level tracking and matching
- Export and import functionality for model metadata
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from statistics import mean, stdev


class DifficultyLevel(str, Enum):
    """Print difficulty classifications."""
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"


class RecommendationStrategy(str, Enum):
    """Recommendation engine strategies."""
    NEXT_STEPS = "next_steps"
    POPULARITY = "popularity"
    DIFFICULTY_MATCH = "difficulty_match"
    SIMILAR_CREATOR = "similar_creator"
    SAME_COLLECTION = "same_collection"


@dataclass
class PrintStatistics:
    """Aggregated statistics for a model."""
    model_ref: str
    total_prints: int = 0
    successful_prints: int = 0
    failed_prints: int = 0
    avg_print_time: float = 0.0
    median_print_time: float = 0.0
    stdev_print_time: float = 0.0
    min_print_time: float = 0.0
    max_print_time: float = 0.0
    success_rate: float = 0.0
    total_filament_used: float = 0.0  # grams
    avg_filament_per_print: float = 0.0  # grams
    first_print_date: Optional[datetime] = None
    last_print_date: Optional[datetime] = None
    days_since_last_print: int = 0
    popularity_rank: int = 0
    print_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ModelRecommendation:
    """A recommended model for printing."""
    model_ref: str
    model_name: str
    score: float  # 0-100
    reason: str
    strategy: RecommendationStrategy
    match_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FilamentSummary:
    """Filament usage summary for a model."""
    model_ref: str
    total_filament_used: float = 0.0  # grams
    colors_used: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # {color: {total, count, last_used}}
    average_filament_per_print: float = 0.0


class PrintStatisticsAnalyzer:
    """Analyze print statistics for models."""

    def __init__(self, min_prints: int = 1):
        """Initialize analyzer.
        
        Args:
            min_prints: Minimum prints required to compute meaningful statistics
        """
        self.min_prints = min_prints

    def aggregate_print_stats(
        self,
        model_ref: str,
        archives: List[Dict[str, Any]]
    ) -> PrintStatistics:
        """Aggregate statistics across all prints of a model.
        
        Args:
            model_ref: Reference ID of the model
            archives: List of archive records for this model
            
        Returns:
            PrintStatistics object with aggregated data
        """
        stats = PrintStatistics(model_ref=model_ref)
        
        if not archives:
            return stats
        
        stats.total_prints = len(archives)
        
        # Separate successful and failed prints
        print_times = []
        filament_amounts = []
        dates = []
        
        for archive in archives:
            if not isinstance(archive, dict):
                continue
            
            # Count success/failure
            success = archive.get("success", False)
            if success:
                stats.successful_prints += 1
            else:
                stats.failed_prints += 1
            
            # Collect print times
            print_time = archive.get("print_time", 0)
            if print_time and print_time > 0:
                print_times.append(print_time)
            
            # Collect filament amounts
            filament = archive.get("filament_used", 0)
            if filament and filament > 0:
                filament_amounts.append(filament)
            
            # Collect dates
            date_str = archive.get("completed_at") or archive.get("created_at")
            if date_str:
                try:
                    if isinstance(date_str, str):
                        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        date = date_str
                    dates.append(date)
                except (ValueError, AttributeError):
                    pass
        
        # Calculate success rate
        if stats.total_prints > 0:
            stats.success_rate = stats.successful_prints / stats.total_prints
        
        # Calculate print time statistics
        if print_times:
            stats.avg_print_time = mean(print_times)
            stats.median_print_time = sorted(print_times)[len(print_times) // 2]
            stats.min_print_time = min(print_times)
            stats.max_print_time = max(print_times)
            if len(print_times) > 1:
                stats.stdev_print_time = stdev(print_times)
        
        # Calculate filament statistics
        if filament_amounts:
            stats.total_filament_used = sum(filament_amounts)
            stats.avg_filament_per_print = mean(filament_amounts)
        
        # Calculate date statistics
        if dates:
            dates_sorted = sorted(dates)
            stats.first_print_date = dates_sorted[0]
            stats.last_print_date = dates_sorted[-1]
            days_since = (datetime.now(datetime.now().astimezone().tzinfo) - stats.last_print_date).days
            stats.days_since_last_print = max(0, days_since)
        
        stats.print_history = archives
        return stats

    def calculate_success_rate(self, archives: List[Dict[str, Any]]) -> float:
        """Calculate success rate for a list of archives.
        
        Args:
            archives: List of archive records
            
        Returns:
            Success rate as 0-1 decimal
        """
        if not archives:
            return 0.0
        
        successful = sum(1 for a in archives if a.get("success", False))
        return successful / len(archives)

    def get_difficulty_level(self, stats: PrintStatistics) -> DifficultyLevel:
        """Estimate difficulty level based on statistics.
        
        Args:
            stats: PrintStatistics object
            
        Returns:
            DifficultyLevel classification
        """
        if stats.total_prints < self.min_prints:
            return DifficultyLevel.MODERATE  # Default for insufficient data
        
        # Lower success rate = higher difficulty
        if stats.success_rate < 0.7:
            return DifficultyLevel.CHALLENGING
        elif stats.success_rate < 0.9:
            return DifficultyLevel.MODERATE
        else:
            return DifficultyLevel.EASY

    def identify_problematic_models(
        self,
        all_stats: List[PrintStatistics],
        threshold_success_rate: float = 0.7,
        min_prints: int = 3
    ) -> List[PrintStatistics]:
        """Identify models with consistently low success rates.
        
        Args:
            all_stats: List of PrintStatistics
            threshold_success_rate: Success rate below this triggers flag
            min_prints: Minimum prints to consider model
            
        Returns:
            List of problematic model statistics
        """
        problematic = []
        for stats in all_stats:
            if (stats.total_prints >= min_prints and 
                stats.success_rate < threshold_success_rate):
                problematic.append(stats)
        
        # Sort by success rate (worst first)
        return sorted(problematic, key=lambda s: s.success_rate)


class FilamentAnalyzer:
    """Analyze filament usage patterns."""

    def get_filament_summary(
        self,
        model_ref: str,
        archives: List[Dict[str, Any]]
    ) -> FilamentSummary:
        """Summarize filament usage by color for a model.
        
        Args:
            model_ref: Reference ID of the model
            archives: List of archive records
            
        Returns:
            FilamentSummary with breakdown by color
        """
        summary = FilamentSummary(model_ref=model_ref)
        
        if not archives:
            return summary
        
        total_filament = 0
        colors_data = {}
        
        for archive in archives:
            filament = archive.get("filament_used", 0)
            color = archive.get("filament_color", "unknown").lower()
            
            if filament and filament > 0:
                total_filament += filament
                
                if color not in colors_data:
                    colors_data[color] = {
                        "total": 0,
                        "count": 0,
                        "last_used": None,
                        "min": float('inf'),
                        "max": 0
                    }
                
                colors_data[color]["total"] += filament
                colors_data[color]["count"] += 1
                colors_data[color]["min"] = min(colors_data[color]["min"], filament)
                colors_data[color]["max"] = max(colors_data[color]["max"], filament)
                
                # Track last used date
                date_str = archive.get("completed_at") or archive.get("created_at")
                if date_str:
                    try:
                        if isinstance(date_str, str):
                            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        else:
                            date = date_str
                        if (colors_data[color]["last_used"] is None or 
                            date > colors_data[color]["last_used"]):
                            colors_data[color]["last_used"] = date
                    except (ValueError, AttributeError):
                        pass
        
        summary.total_filament_used = total_filament
        summary.colors_used = colors_data
        if len(archives) > 0:
            summary.average_filament_per_print = total_filament / len(archives)
        
        return summary

    def get_top_colors_by_usage(
        self,
        summary: FilamentSummary,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top N colors by total filament usage.
        
        Args:
            summary: FilamentSummary object
            limit: Maximum colors to return
            
        Returns:
            List of color usage dicts, sorted by amount
        """
        colors = []
        for color, data in summary.colors_used.items():
            colors.append({
                "color": color,
                "total_used": data["total"],
                "usage_count": data["count"],
                "average": data["total"] / data["count"] if data["count"] > 0 else 0,
                "last_used": data["last_used"]
            })
        
        # Sort by total usage (descending)
        return sorted(colors, key=lambda c: c["total_used"], reverse=True)[:limit]


class RecommendationEngine:
    """Generate recommendations based on print history."""

    def __init__(self, analyzer: PrintStatisticsAnalyzer, catalog_client=None):
        """Initialize engine.
        
        Args:
            analyzer: PrintStatisticsAnalyzer instance
            catalog_client: Optional catalog client for model lookups
        """
        self.analyzer = analyzer
        self.catalog_client = catalog_client

    def get_recommendations(
        self,
        recent_prints: List[Dict[str, Any]],
        all_models: Optional[List[Dict[str, Any]]] = None,
        strategy: RecommendationStrategy = RecommendationStrategy.NEXT_STEPS,
        limit: int = 5
    ) -> List[ModelRecommendation]:
        """Generate recommendations based on print history.
        
        Args:
            recent_prints: List of recent archive/model records
            all_models: Optional list of all available models for matching
            strategy: Recommendation strategy to use
            limit: Maximum recommendations to return
            
        Returns:
            List of ModelRecommendation objects
        """
        recommendations = []
        
        if not all_models:
            all_models = []
        
        if strategy == RecommendationStrategy.NEXT_STEPS:
            recommendations = self._recommend_next_steps(recent_prints, all_models, limit)
        elif strategy == RecommendationStrategy.DIFFICULTY_MATCH:
            recommendations = self._recommend_by_difficulty(recent_prints, all_models, limit)
        elif strategy == RecommendationStrategy.POPULARITY:
            recommendations = self._recommend_by_popularity(all_models, limit)
        elif strategy == RecommendationStrategy.SIMILAR_CREATOR:
            recommendations = self._recommend_by_creator(recent_prints, all_models, limit)
        elif strategy == RecommendationStrategy.SAME_COLLECTION:
            recommendations = self._recommend_by_collection(recent_prints, all_models, limit)
        
        return sorted(recommendations, key=lambda r: r.score, reverse=True)[:limit]

    def _recommend_next_steps(
        self,
        recent_prints: List[Dict[str, Any]],
        all_models: List[Dict[str, Any]],
        limit: int
    ) -> List[ModelRecommendation]:
        """Recommend related models from recent prints."""
        recommendations = []
        
        if not recent_prints or not all_models:
            return recommendations
        
        # Get last printed model
        last_model = recent_prints[0]
        last_model_ref = last_model.get("model_ref")
        
        # Find related models
        for model in all_models:
            if model.get("model_ref") == last_model_ref:
                continue  # Skip same model
            
            score = 0
            reasons = []
            
            # Same creator
            if (model.get("creator") == last_model.get("creator") and 
                model.get("creator")):
                score += 30
                reasons.append("Same creator")
            
            # Same collection
            last_collections = last_model.get("collections", [])
            model_collections = model.get("collections", [])
            shared_collections = set(last_collections) & set(model_collections)
            if shared_collections:
                score += 20
                reasons.append(f"Shared collection: {list(shared_collections)[0]}")
            
            # Keyword overlap
            last_keywords = set(k.lower() for k in last_model.get("keywords", []))
            model_keywords = set(k.lower() for k in model.get("keywords", []))
            keyword_overlap = len(last_keywords & model_keywords)
            score += min(keyword_overlap * 5, 20)
            if keyword_overlap > 0:
                reasons.append(f"{keyword_overlap} shared keywords")
            
            if score > 0:
                recommendation = ModelRecommendation(
                    model_ref=model.get("model_ref", "unknown"),
                    model_name=model.get("name", "Unknown"),
                    score=min(score, 100),
                    reason=" + ".join(reasons) if reasons else "Related model",
                    strategy=RecommendationStrategy.NEXT_STEPS,
                    match_details={
                        "creator_match": model.get("creator") == last_model.get("creator"),
                        "collection_matches": list(shared_collections),
                        "keyword_overlap": keyword_overlap
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations

    def _recommend_by_difficulty(
        self,
        recent_prints: List[Dict[str, Any]],
        all_models: List[Dict[str, Any]],
        limit: int
    ) -> List[ModelRecommendation]:
        """Recommend models at same difficulty level."""
        recommendations = []
        
        if not recent_prints or not all_models:
            return recommendations
        
        # Estimate current difficulty level from recent print success
        recent_success = sum(1 for p in recent_prints if p.get("success", False))
        recent_success_rate = recent_success / len(recent_prints) if recent_prints else 0
        
        if recent_success_rate < 0.7:
            target_difficulty = DifficultyLevel.CHALLENGING
        elif recent_success_rate < 0.9:
            target_difficulty = DifficultyLevel.MODERATE
        else:
            target_difficulty = DifficultyLevel.EASY
        
        for model in all_models:
            model_difficulty = model.get("difficulty_level", DifficultyLevel.MODERATE)
            if model_difficulty == target_difficulty:
                recommendation = ModelRecommendation(
                    model_ref=model.get("model_ref", "unknown"),
                    model_name=model.get("name", "Unknown"),
                    score=75,
                    reason=f"Matched to your {target_difficulty.value} skill level",
                    strategy=RecommendationStrategy.DIFFICULTY_MATCH,
                    match_details={
                        "target_difficulty": target_difficulty,
                        "recent_success_rate": recent_success_rate
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations

    def _recommend_by_popularity(
        self,
        all_models: List[Dict[str, Any]],
        limit: int
    ) -> List[ModelRecommendation]:
        """Recommend trending/popular models."""
        recommendations = []
        
        for i, model in enumerate(sorted(
            all_models,
            key=lambda m: m.get("print_count", 0),
            reverse=True
        )[:limit * 2]):  # Get more than needed
            # Popularity score based on position
            score = 100 - (i * 5)
            score = max(score, 50)
            
            recommendation = ModelRecommendation(
                model_ref=model.get("model_ref", "unknown"),
                model_name=model.get("name", "Unknown"),
                score=score,
                reason=f"Trending model ({model.get('print_count', 0)} prints)",
                strategy=RecommendationStrategy.POPULARITY,
                match_details={
                    "popularity_score": score,
                    "print_count": model.get("print_count", 0)
                }
            )
            recommendations.append(recommendation)
        
        return recommendations

    def _recommend_by_creator(
        self,
        recent_prints: List[Dict[str, Any]],
        all_models: List[Dict[str, Any]],
        limit: int
    ) -> List[ModelRecommendation]:
        """Recommend models from creators of recent prints."""
        recommendations = []
        
        if not recent_prints or not all_models:
            return recommendations
        
        # Get creators from recent prints
        creators = set()
        for print_record in recent_prints:
            creator = print_record.get("creator")
            if creator:
                creators.add(creator.lower())
        
        for model in all_models:
            model_creator = (model.get("creator") or "").lower()
            if model_creator in creators:
                recommendation = ModelRecommendation(
                    model_ref=model.get("model_ref", "unknown"),
                    model_name=model.get("name", "Unknown"),
                    score=70,
                    reason=f"From creator you've printed before",
                    strategy=RecommendationStrategy.SIMILAR_CREATOR,
                    match_details={"creator": model.get("creator")}
                )
                recommendations.append(recommendation)
        
        return recommendations

    def _recommend_by_collection(
        self,
        recent_prints: List[Dict[str, Any]],
        all_models: List[Dict[str, Any]],
        limit: int
    ) -> List[ModelRecommendation]:
        """Recommend models from same collections."""
        recommendations = []
        
        if not recent_prints or not all_models:
            return recommendations
        
        # Get collections from recent prints
        collections = set()
        for print_record in recent_prints:
            for col in print_record.get("collections", []):
                collections.add(col.lower())
        
        for model in all_models:
            for model_col in model.get("collections", []):
                if model_col.lower() in collections:
                    recommendation = ModelRecommendation(
                        model_ref=model.get("model_ref", "unknown"),
                        model_name=model.get("name", "Unknown"),
                        score=65,
                        reason=f"From collection: {model_col}",
                        strategy=RecommendationStrategy.SAME_COLLECTION,
                        match_details={"collection": model_col}
                    )
                    recommendations.append(recommendation)
                    break  # Only add once per model
        
        return recommendations
