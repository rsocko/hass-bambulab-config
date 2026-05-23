# Frequents/Favorites Layer 2 Derivation (Issue #1487)

Status: Implemented (Phase 0)

This document defines the Layer-2 contract used by catalog model list/search responses for US-1 Frequents/Favorites.

## Scope

- Applies to sidecar responses from:
  - `GET /api/models`
  - `GET /api/models/search`
  - `POST /api/models/ranking/refresh` (derivation snapshot refresh)
- Leaves Layer 1 archive ingestion/projection unchanged.
- Keeps presentation-oriented frequent/favorite derivations in Layer 2.

## Inputs

Layer-2 frequent derivation is controlled by:

- `frequent_window_days` (default `90`, clamped to `1..3650`)
- `frequent_min_prints` (default `3`, clamped to `1..9999`)
- `frequent_backfill_weight` (default `0.5`, clamped to `0.0..1.0`)

Home Assistant helpers for operator tuning:

- `input_number.model_catalog_frequent_window_days`
- `input_number.model_catalog_frequent_min_prints`

## Computation

Accepted + active archive links are evaluated in the selected recency window.

For each in-window link:

- normal link weight = `1.0`
- historical backfill link weight = `frequent_backfill_weight`

Per-model weighted total:

- `weighted_print_count = sum(link_weight)`

Frequent decision:

- `is_frequent = weighted_print_count >= frequent_min_prints`

Derived score fields:

- `ranking.frequent_score = weighted_print_count` when `is_frequent`, else `0.0`
- `ranking.common_score = ranking.recent_score * ranking.frequent_score` when `recent_score` exists

## Response Contract Additions

Per model payload now includes:

- `model_frequent: bool`
- `frequents` object:
  - `is_frequent`
  - `weighted_print_count`
  - `print_count_window`
  - `backfill_print_count_window`
  - `min_prints`
  - `window_days`
  - `backfill_weight`

`GET /api/models` also returns top-level `frequents_tuning` with resolved tuning values.

`GET /api/models/search` supports:

- `frequents_only=true|false`
- `frequent_window_days`
- `frequent_min_prints`
- `frequent_backfill_weight`

## Notes

- Favorites remain independent (`model_favorite` / `favorites_only` behavior unchanged).
- Archived-model exclusion is tracked under the `catalog_visibility` phase and is not part of this Phase 0 implementation.
- Layer 1 sensors/tables are not expanded with UI labels or filter-specific wording.
