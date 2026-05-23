# Frequents/Favorites Layer 2 Derivation Rules

Issue alignment: #1487 (Catalog: Frequents/Favorites Layer 2 derivation rules)

This document defines the Layer 2 contract backing the Catalog Frequents/Favorites surfaces.

## Scope

- Define the sidecar derivation for `model_frequent` and frequents scoring used by Catalog list/search.
- Keep Layer 1 data unchanged (`sensor.print_history_archives` and archive projection payloads).
- Expose tuning parameters for the UI tune popover and HA helper defaults.

## Layering Contract

- Layer 1 remains archive-centric and stable.
- Layer 2 computes view-facing frequents signals from existing link/ranking data.
- Layer 3 cards/popups render labels and affordances (`Frequents only`, rail pinning, etc.).

No Layer 1 schema/field changes are required for #1487.

## Inputs

Derivation reads accepted active archive links in `model_catalog_links`:

- include only rows where `is_active = 1` and `review_state = 'accepted'`
- use `updated_at` as the link timestamp for recency windowing
- detect historical backfill links by joining archive IDs against
  `model_catalog_print_history_jobs.created_archive_id` where
  `workflow_kind = 'historical_backfill'`

## Tunables

Sidecar API parameters:

- `frequent_window_days` (default `90`)
- `frequent_min_prints` (default `3`)
- `frequent_backfill_weight` (default `0.5`, range `0.0..1.0`)

HA helper defaults (model catalog package):

- `input_number.model_catalog_frequent_window_days` (initial `90`)
- `input_number.model_catalog_frequent_min_prints` (initial `3`)

`model_catalog_search_models` forwards these into sidecar `/api/models/search`.

## Computation

For each model:

- include links with `updated_at >= reference_time - frequent_window_days`
- score each in-window normal link as `1.0`
- score each in-window historical backfill link as `frequent_backfill_weight`
- sum to `weighted_print_count`

Then derive:

- `is_frequent = weighted_print_count >= frequent_min_prints`
- `ranking.frequent_score = weighted_print_count` when frequent, else `0.0`
- `ranking.common_score = ranking.frequent_score * ranking.recent_score` when `recent_score` exists

Notes:

- Backfill links are included, but down-weighted by default.
- Out-of-window links contribute `0` to frequents scoring.

## API Contract Additions

`GET /api/models` and `GET /api/models/search` support:

- request params: `frequent_window_days`, `frequent_min_prints`, `frequent_backfill_weight`, `frequents_only`
- response payload fields per model:
  - `model_frequent` (boolean)
  - `frequents` object:
    - `is_frequent`
    - `weighted_print_count`
    - `print_count_window`
    - `backfill_print_count_window`
    - `min_prints`
    - `window_days`
    - `backfill_weight`

Search/list responses also include normalized tuning values:

- `frequents_tuning.window_days`
- `frequents_tuning.min_prints`
- `frequents_tuning.backfill_weight`

## Test Coverage

Covered by sidecar tests for:

- window boundaries (in-window vs out-of-window)
- threshold edge behavior (`weighted_print_count` around `frequent_min_prints`)
- backfill down-weight impact
- `frequents_only` filter behavior in `/api/models/search`
