from app.routers.models import (
    _apply_frequents_layer2_derivation,
    _normalize_enrichment_changes,
    _structured_detail_metadata,
)


def test_apply_frequents_manual_override_marks_frequent_even_below_threshold() -> None:
    payload = {
        "ranking": {
            "recent_score": 0.5,
            "frequent_score": 0.2,
            "common_score": 0.1,
        }
    }

    _apply_frequents_layer2_derivation(
        payload,
        weighted_print_count=0.2,
        window_print_count=0,
        window_backfill_count=0,
        frequent_min_prints=3,
        frequent_window_days=90,
        frequent_backfill_weight=0.5,
        frequent_override=True,
    )

    assert payload["model_frequent"] is True
    assert payload["model_frequent_override"] is True
    assert payload["ranking"]["is_frequent"] is True
    assert payload["ranking"]["frequent_score"] == 3.0
    assert payload["frequents"]["source"] == "manual_override"
    assert payload["frequents"]["is_frequent_inferred"] is False


def test_apply_frequents_without_override_uses_inference() -> None:
    payload = {
        "ranking": {
            "recent_score": 1.0,
            "frequent_score": 0.0,
            "common_score": 0.0,
        }
    }

    _apply_frequents_layer2_derivation(
        payload,
        weighted_print_count=4.5,
        window_print_count=4,
        window_backfill_count=1,
        frequent_min_prints=3,
        frequent_window_days=90,
        frequent_backfill_weight=0.5,
    )

    assert payload["model_frequent"] is True
    assert payload["model_frequent_override"] is None
    assert payload["ranking"]["is_frequent"] is True
    assert payload["ranking"]["frequent_score"] == 4.5
    assert payload["frequents"]["source"] == "inferred"
    assert payload["frequents"]["is_frequent_inferred"] is True


def test_normalize_enrichment_accepts_and_clears_frequent_override() -> None:
    normalized, clears = _normalize_enrichment_changes(
        {
            "structured_metadata": {
                "catalog_signals": {
                    "model_frequent_override": True,
                }
            }
        }
    )

    assert normalized.get("model_frequent_override") is True
    assert "model_frequent_override" not in clears

    normalized_clear, clears_clear = _normalize_enrichment_changes(
        {
            "structured_metadata": {
                "catalog_signals": {
                    "model_frequent_override": None,
                }
            }
        }
    )

    assert "model_frequent_override" not in normalized_clear
    assert "model_frequent_override" in clears_clear


def test_structured_metadata_exposes_frequent_override_signal() -> None:
    metadata = _structured_detail_metadata({"model_frequent_override": True})
    catalog_signals = metadata.get("catalog_signals") or {}
    assert catalog_signals.get("model_frequent_override") is True
