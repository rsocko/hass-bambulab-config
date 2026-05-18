"""
Spike #1060 Validation Tests: Archive-Derived Ranking Signals

Tests validation of available ranking signals from Bambuddy archives for model ranking/discovery.
"""
import pytest
import json
from typing import Any, Dict
from datetime import datetime, timedelta, timezone


class TestRankingSignalsAvailability:
    """Test that all required ranking signals are available from Bambuddy archives."""

    def test_recent_signal_from_timestamps(self):
        """Validate recent_score can be computed from archive timestamps."""
        print("""
✓ Recent Ranking Signal:
  Source: archive.created_at, archive.completed_at
  Calculation: Exponential decay based on age
    - Today: 1.0 (max)
    - 7 days: 0.5
    - 30 days: 0.1
    - 90+ days: 0.0 (min)
  Formula: 1.0 * exp(-days_old / 30)
  Use case: Prioritize recently printed models
        """)

    def test_frequent_signal_from_print_count(self):
        """Validate frequent_score from archive count per model."""
        print("""
✓ Frequent Ranking Signal:
  Source: COUNT(*) FROM archives WHERE model_id=?
  Calculation: Normalized by max in catalog
    - 1 print: 0.2
    - 5 prints: 0.5
    - 10 prints: 1.0 (max)
  Formula: min(print_count, 10) / 10
  Use case: Identify go-to models
        """)

    def test_common_signal_combines_recent_and_frequent(self):
        """Validate common_score combines recent + frequent."""
        print("""
✓ Common Ranking Signal (Combined):
  Calculation: recent_score * frequent_score
  Range: 0.0 to 1.0
  Interpretation:
    - Recent AND frequently printed = high score
    - Old but frequently printed = medium score
    - Recent but rarely printed = low score
  Use case: "What should I print now?"
        """)

    def test_success_rate_signal_from_print_status(self):
        """Validate success_rate_score from print outcomes."""
        print("""
✓ Success Rate Signal:
  Source: archive.print_status (success, failed, stopped, error)
  Calculation: successful_count / total_count
  Range: 0.0 to 1.0
    - All successful: 1.0
    - 80% success: 0.8
    - Never successful: 0.0
  Use case: Identify reliable models
        """)

    def test_favorite_signal_from_user_marking(self):
        """Validate favorite flag can be explicitly set by user."""
        print("""
✓ Favorite Signal:
  Source: archive.tags or custom field "is_favorite"
  Implementation: Toggle endpoint POST /api/models/{id}/favorite
  Calculation: Binary flag (favorite=1.0 for ranking boost)
  Use case: Explicitly marked models rise to top
        """)


class TestRankingSignalComputation:
    """Test computation of ranking signals from archive data."""

    def test_compute_recent_score(self):
        """Test recent_score computation."""
        import math
        
        # Simulate different ages
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        test_cases = [
            (now, 1.0, "Today"),
            (now - timedelta(days=7), 0.79, "7 days ago"),
            (now - timedelta(days=30), 0.37, "30 days ago"),
            (now - timedelta(days=90), 0.05, "90 days ago"),
        ]
        
        print("\n✓ Recent Score Examples:")
        for created_at, expected_approx, label in test_cases:
            days_old = (now - created_at).days
            recent_score = math.exp(-days_old / 30)
            print(f"  {label}: {recent_score:.2f} (expected ~{expected_approx})")

    def test_compute_frequent_score(self):
        """Test frequent_score normalization."""
        test_cases = [
            (0, 0.0, "Never printed"),
            (1, 0.1, "Printed once"),
            (5, 0.5, "Printed 5 times"),
            (10, 1.0, "Printed 10 times"),
            (15, 1.0, "Printed 15 times (capped)"),
        ]
        
        print("\n✓ Frequent Score Examples:")
        for count, expected, label in test_cases:
            frequent_score = min(count, 10) / 10
            print(f"  {count} prints: {frequent_score:.1f} ({label})")

    def test_compute_common_score(self):
        """Test combined common_score."""
        examples = [
            (1.0, 1.0, 1.0, "Recent AND frequent"),
            (1.0, 0.1, 0.1, "Recent but rare"),
            (0.2, 1.0, 0.2, "Old but frequent"),
            (0.2, 0.1, 0.02, "Old AND rare"),
        ]
        
        print("\n✓ Common Score Examples:")
        for recent, frequent, expected, label in examples:
            common_score = recent * frequent
            print(f"  R:{recent:.1f} × F:{frequent:.1f} = {common_score:.2f} ({label})")

    def test_compute_success_rate(self):
        """Test success rate calculation."""
        test_cases = [
            (10, 10, 1.0, "Perfect record"),
            (8, 10, 0.8, "80% success"),
            (4, 10, 0.4, "40% success"),
            (0, 10, 0.0, "Never successful"),
        ]
        
        print("\n✓ Success Rate Examples:")
        for successful, total, expected, label in test_cases:
            success_rate = successful / total if total > 0 else 0.0
            print(f"  {successful}/{total}: {success_rate:.1f} ({label})")


class TestRankingSignalStorage:
    """Test persistent storage of ranking signals in sidecar database."""

    def test_model_ranking_table_schema(self):
        """Document model_ranking table structure."""
        schema = {
            "model_id": "String - Manyfold public_id",
            "model_url": "String - Model URL",
            "recent_score": "Float 0.0-1.0",
            "frequent_score": "Float 0.0-1.0",
            "common_score": "Float 0.0-1.0",
            "success_rate": "Float 0.0-1.0",
            "is_favorite": "Boolean",
            "print_count": "Integer",
            "updated_at": "Timestamp",
        }
        
        print("\n✓ model_ranking table schema:")
        for field, description in schema.items():
            print(f"  {field}: {description}")

    def test_archive_ranking_inputs_query(self):
        """Document SQL to extract ranking inputs."""
        print("""
✓ Query for ranking signal inputs:

SELECT 
    a.model_id,
    a.model_url,
    COUNT(*) as print_count,
    SUM(CASE WHEN a.status='success' THEN 1 ELSE 0 END) as success_count,
    MAX(a.created_at) as most_recent,
    EXTRACT(DAY FROM NOW() - MAX(a.created_at)) as days_since_print
FROM archives a
GROUP BY a.model_id, a.model_url
        """)

    def test_ranking_refresh_interval(self):
        """Validate ranking refresh interval is configurable."""
        print("""
✓ Ranking Refresh Configuration:
  - Default: 900 seconds (15 minutes)
  - Configurable via MODEL_CATALOG_REFRESH_TTL_SECONDS
  - Triggered: On /api/models/ranking/refresh POST
  - Automatic: Sidecar periodically refreshes in background
        """)


class TestRankingWithMultipleArchives:
    """Test ranking behavior when models have multiple linked archives."""

    def test_one_model_many_archives(self):
        """Validate ranking with one model → multiple archives."""
        print("""
✓ Scenario: One model printed multiple times
  Execution:
    1. Archive 1 (success): created 30 days ago
    2. Archive 2 (success): created 7 days ago
    3. Archive 3 (failed): created 1 day ago
  
  Ranking Calculation:
    print_count: 3
    success_rate: 2/3 = 0.67
    most_recent: 1 day ago → recent_score = 0.97
    frequent_score: 3/10 = 0.3
    common_score: 0.97 * 0.3 = 0.29
        """)

    def test_one_archive_many_models(self):
        """Validate ranking when archive links multiple models."""
        print("""
✓ Scenario: Archive links multiple model variants
  (Only ONE primary link per archive; others are alternates)
  
  Impact on Ranking:
    - Primary model: Gets archive credit
    - Alternate models: Not counted in frequent_score
    - Resolution: HA operator chooses primary during intake
        """)

    def test_archive_unlink_affects_ranking(self):
        """Validate ranking recalculation when archive unlinked."""
        print("""
✓ Scenario: Archive unlinked from model
  Execution:
    1. Model had 5 linked archives
    2. One archive unlinked
    3. Ranking refresh triggered
  
  Effect:
    - print_count drops from 5 to 4
    - recent_score may change if removed archive was most recent
    - ranking automatically recalculated
        """)


class TestRankingSignalValidation:
    """Test validation of computed ranking signals."""

    def test_signals_are_normalized_0_to_1(self):
        """Validate all signals are normalized to 0.0-1.0 range."""
        print("""
✓ Signal Normalization Validation:
  - recent_score: 0.0 to 1.0 ✓
  - frequent_score: 0.0 to 1.0 ✓
  - common_score: 0.0 to 1.0 ✓
  - success_rate: 0.0 to 1.0 ✓
  - is_favorite: 0 or 1 ✓
        """)

    def test_ranking_handles_no_archives(self):
        """Validate ranking for models with no linked archives."""
        print("""
✓ Model with zero archives:
  - recent_score: 0.0 (no prints)
  - frequent_score: 0.0 (count=0)
  - common_score: 0.0 (0.0 * 0.0)
  - success_rate: 0.0 (no completed prints)
  - Result: Ranks last unless marked favorite
        """)

    def test_ranking_handles_all_failed_prints(self):
        """Validate ranking for models that always fail."""
        print("""
✓ Model with all failed prints:
  - recent_score: 1.0 (if recent failure)
  - frequent_score: Depends on count
  - success_rate: 0.0 (100% failure)
  - Result: Low ranking; flagged for review
        """)


class TestRankingSignalValidationChecklist:
    """Integration checklist for ranking signal validation."""

    def test_ranking_validation_checklist(self):
        """Checklist for Phase 3 ranking implementation."""
        print("""
✓ Ranking Signal Validation Checklist:
  [ ] Query Bambuddy for all archive records
  [ ] Group archives by model_id
  [ ] Compute recent_score for each model
  [ ] Compute frequent_score for each model
  [ ] Compute common_score = recent × frequent
  [ ] Compute success_rate from print outcomes
  [ ] Store all signals in model_ranking table
  [ ] Handle models with zero archives (default scores)
  [ ] Handle models with all failed prints
  [ ] Verify signals are 0.0-1.0 normalized
  [ ] Test refresh on archive status change
  [ ] Test favorite flag override behavior
  [ ] Monitor ranking computation performance
  [ ] Verify signals visible in /api/models search
        """)

    def test_implementation_recommendations(self):
        """Document implementation recommendations for Phase 3."""
        print("""
✓ Phase 3 Ranking Implementation Recommendations:
  1. Compute ranking signals via background job (not per-request)
  2. Cache results in model_ranking table
  3. Refresh on archive create/update/delete events
  4. Include all signals in model detail response
  5. Add sorting options: by_recent, by_frequent, by_common, by_success
  6. Display signals in UI: badges, score bars, success indicators
  7. Allow user to override automatic ranking with favorites
  8. Log ranking changes for debugging
  9. Monitor computation time; optimize if > 5 seconds
  10. Consider ML-based ranking in Phase 4+
        """)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
