# Variant 3 Metadata Schema And Variant 4 Carry-Forward

## Purpose

This document turns the external-services review into a concrete storage and ownership plan for print history.

It is intentionally aligned to the active architecture:

- **Variant 3** is the current target and current implementation direction
- **Variant 4** remains deferred, but any new metadata work should be portable into it without redefining the model

The main design rule is:

> Extend the existing Variant 3 integration-owned local store rather than creating a second metadata path.

That avoids three failure modes:

- reinventing a new sidecar model inside Home Assistant
- putting view-specific fields into the mirrored archive cache
- creating one schema for Variant 3 and a different one for a future Variant 4

## Alignment With Existing Architecture

### Variant 3 Contract

Variant 3 already defines the correct ownership boundary:

- Bambuddy-owned archive fields are mirrored locally
- local-only review and provenance fields live only in the local store
- derived and query-oriented values are recomputed locally
- Bambuddy remains authoritative for archive-core fields

This document keeps that exact split.

### Variant 4 Contract

Variant 4 should not introduce a different metadata model.

If Variant 4 is ever promoted, the correct move is:

- keep the same normalized metadata concepts
- move query and hydration execution behind a sidecar service boundary
- preserve the same ownership rules
- reuse the same query DTOs and popup/archive contracts where practical

Variant 4 should therefore be treated as a deployment boundary change, not a schema philosophy change.

## What Already Exists

The current Variant 3 store already has the correct foundation.

Existing tables and concepts already in scope:

- `archives`
- `archive_filament_rows`
- `archive_tags`
- `archive_photos`
- `archive_note_payload_rows`
- `archive_enrichment_provenance_rows`
- `archive_event_timeline`
- `archive_repair_lineage`
- `archive_review_state`
- `archive_media_review_state`
- `archive_storage_metrics`

Related compact metadata already projected into the base archive/browser contract:

- `duplicate_count`
- `duplicate_sequence`
- `original_archive_id`

That means the new work should mostly be additive. The repo does not need a fresh parallel metadata store.

Important interpretation for current planning:

- `archive_event_timeline` is already a shipped local-store primitive, so it should no longer be treated as a missing schema foundation item
- `archive_enrichment_provenance_rows` already preserve structured spool and filament evidence, so a future `archive_spool_snapshots` table should backfill from that evidence rather than replacing it blindly
- `archive_storage_metrics` already cover archive-scoped file inventory and size diagnostics, but they are not a substitute for semantic `archive_artifact_metadata`
- compact duplicate metadata plus `archive_repair_lineage` mean a generalized `archive_lineage` should be added only when broader compare, reprint, or mismatch workflows actually need it

## Recommended Schema Extension Strategy

### Keep `archives` Lean And Shared

The `archives` table should continue to hold:

- mirrored Bambuddy archive-core fields needed for browser, popup, and review workflows
- sync metadata such as payload fingerprint or freshness timestamps
- only a small number of broadly useful derived fields when they are stable across multiple consumers

It should not become the place for:

- card-specific wording
- tooltip labels
- per-view display strings
- volatile analytics blobs

That remains consistent with [layering-guidance.md](layering-guidance.md).

### Add New Metadata In Focused Tables

The most useful additions should land in dedicated local-only or derived tables.

Recommended additions:

- `archive_metric_summary`
- `archive_spool_snapshots`
- `archive_artifact_metadata`
- `archive_lineage`
- `archive_binding_snapshots`

`archive_event_timeline` remains part of the normalized metadata model, but it is already present in the active Variant 3 store and should now be treated as an implemented prerequisite rather than a pending addition.

The issue-specific popup timeline contract for `archive_event_timeline` is defined in [archive-popup-timeline-design.md](../ui-media/archive-popup-timeline-design.md).

Additional linkage recommendation:

- when Bambuddy current-print status emits linkage fields such as `current_archive_id` and `current_plate_id`, persist a bind-time snapshot in a dedicated local table rather than flattening those fields into card-level state or hidden notes payloads
- this preserves a stable provenance anchor for plate-aware archive behaviors while keeping mirrored archive-core rows lean

These should be integration-owned in Variant 3. If Variant 4 happens later, the same tables or equivalent collections should move behind the sidecar without changing their semantic contract.

## Proposed Tables

### 1. `archive_metric_summary`

Purpose:

- store explicitly derived or reconciled per-print numeric summaries
- separate estimated values from actual values
- preserve provenance for calculations inspired by the Node-RED warehouse pattern and 3D Print Log style reporting

Recommended columns:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `archive_id` | integer FK | local | one row per archive |
| `estimated_weight_g` | real | derived | from artifact or slicer hints |
| `actual_weight_g` | real | derived | from Bambuddy or reconciled row sums |
| `estimated_duration_s` | integer | derived | slicer or file-derived |
| `actual_duration_s` | integer | mirrored/derived | prefer Bambuddy runtime values |
| `estimated_filament_cost` | real | derived | from slicer or spool pricing |
| `actual_filament_cost` | real | derived | from spool snapshot and measured/recorded usage |
| `estimated_energy_cost` | real | derived | fallback-only |
| `actual_energy_cost` | real | derived | from power monitoring join |
| `estimated_power_wh` | real | derived | optional |
| `actual_power_wh` | real | derived | optional |
| `source_weight_basis` | text | derived | `artifact`, `archive`, `progress_estimate`, `unknown` |
| `source_cost_basis` | text | derived | `spool_snapshot`, `slicer_cost`, `default_price`, `power_join` |
| `derivation_confidence` | text | derived | `high`, `medium`, `low` |
| `computed_at` | text/datetime | local | audit trail |

Why this should be a separate table:

- it keeps the mirrored archive row clean
- it avoids pretending every derived metric belongs to Bambuddy
- it gives Variant 3 and Variant 4 a stable analytics-ready contract

### 2. `archive_event_timeline`

Purpose:

- preserve the actual lifecycle and enrichment timeline of a print
- make `#235`-style event-ledger behavior available without adding Node-RED as a required dependency

Recommended columns:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `id` | integer PK | local | |
| `archive_id` | integer FK | local | |
| `event_type` | text | local | `print_paused`, `print_resumed`, `photo_captured`, `enrichment_applied`, `repair_applied`, `favorite_toggled` |
| `event_time` | text/datetime | local | event timestamp |
| `event_source` | text | local | `bambuddy_webhook`, `bambu_lab`, `ha_script`, `repair_sidecar`, `artifact_scan` |
| `event_status` | text | local | optional normalized status snapshot |
| `payload_json` | text | local | raw supporting context |
| `derived_from` | text | local | when event was inferred rather than directly emitted |

Why this belongs in Variant 3:

- it improves diagnostics, audits, and future repair review immediately
- it does not conflict with Bambuddy archive ownership
- it can back a future popup timeline without widening the archive row

Additional rules for the active implementation slice:

- event rows must be idempotent so repeated webhook delivery or replayed HA workflows do not create duplicates
- archive start and terminal anchors must continue to come from archive-core fields rather than duplicated event rows
- detail hydration should expose compact normalized event DTOs to the popup rather than forcing card-local provenance parsing
- page rows must not gain serialized event lists or popup-only legend labels

### 3. `archive_spool_snapshots`

Purpose:

- preserve a trustworthy per-print spool attribution snapshot
- make spool linkage explainable instead of opaque
- absorb the strongest ideas from OpenSpoolman and SpoolSync while staying within the current architecture

Recommended columns:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `id` | integer PK | local | |
| `archive_id` | integer FK | local | |
| `snapshot_phase` | text | local | `start`, `terminal`, `recovered`, `manual_review` |
| `tray_key` | text | local | `ams_1_tray_1`, `external`, etc. |
| `tray_uuid` | text | local | if present |
| `rfid_uuid` | text | local | if present |
| `spool_id` | integer | local/derived | current Spoolman id if matched |
| `filament_id` | integer | local/derived | |
| `vendor` | text | snapshot | stable captured label |
| `material` | text | snapshot | stable captured label |
| `color_hex` | text | snapshot | stable captured label |
| `profile_name` | text | snapshot | stable captured label |
| `matching_method` | text | local | `archive_uuid`, `tray_map_snapshot`, `color_fallback`, `manual_override` |
| `ambiguity_code` | text | local | optional |
| `weight_used_g` | real | derived | if attributable |
| `snapshot_time` | text/datetime | local | |

Why this should not just be hidden in notes:

- searchable provenance needs first-class rows
- future compare/reprint logic will need structured spool attribution
- this prevents repeated re-parsing of enrichment payload blobs for every new feature

### 4. `archive_artifact_metadata`

Purpose:

- preserve print-start file-derived metadata when `.3mf` or related artifacts are accessible
- adopt the strongest part of the Node-RED pipeline without bringing in its runtime dependency

Recommended columns:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `archive_id` | integer FK | local | one row per archive |
| `artifact_type` | text | local | `3mf`, `gcode`, `source_project` |
| `artifact_path` | text | local | optional reference |
| `content_hash` | text | mirrored/local | if known |
| `plate_name` | text | derived | |
| `plate_index` | integer | derived | |
| `preview_image_path` | text | derived/local | optional local or Bambuddy reference |
| `estimated_weight_g` | real | derived | file-derived |
| `estimated_cost` | real | derived | file-derived |
| `material_names_json` | text | derived | stable raw extraction |
| `project_name` | text | derived | |
| `designer_name` | text | derived | if recovered from artifact |
| `extracted_at` | text/datetime | local | |
| `extraction_status` | text | local | `complete`, `partial`, `failed` |

Important boundary:

- this is file-derived context, not UI wording
- artifact extraction results should feed Layer 2 and popup detail, but not become card-specific formatting in storage

Current repo boundary:

- archive file inventory, asset-size totals, and artifact presence diagnostics already belong to `archive_storage_metrics`
- `archive_artifact_metadata` should therefore be reserved for semantic extraction results such as plate identity, parsed material names, project/designer recovery, preview selection, and estimated print metrics
- do not duplicate generic path/size facts from `archive_storage_metrics` into this table

### 5. `archive_lineage`

Purpose:

- support compare, reprint, duplicates, project/model grouping, and mismatch review without overloading `archive_repair_lineage`

Recommended columns:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `id` | integer PK | local | |
| `archive_id` | integer FK | local | |
| `relation_type` | text | local | `duplicate_of`, `reprint_of`, `recovered_from`, `same_project_as`, `compare_candidate`, `mismatch_target` |
| `related_archive_id` | integer | local | nullable for group-only links |
| `group_key` | text | local/derived | model or project lineage key |
| `evidence_type` | text | local | `content_hash`, `project_name`, `artifact_metadata`, `manual_review`, `api_compare` |
| `confidence` | text | local | `high`, `medium`, `low` |
| `created_at` | text/datetime | local | |

Why this should not be merged into `archive_repair_lineage`:

- repair lineage is only one kind of relationship
- compare/reprint/grouping needs a broader relationship model

Current repo boundary:

- duplicate-aware browser filtering and compact duplicate summaries already use `duplicate_count`, `duplicate_sequence`, and `original_archive_id` from the archive projection
- that shipped duplicate slice means `archive_lineage` is not needed just to support current browser duplicate UX
- add this table only when compare, reprint, project-grouping, or mismatch-review consumers need relationship types beyond compact duplicate metadata and `archive_repair_lineage`

### 6. `archive_binding_snapshots`

Purpose:

- persist the exact linkage evidence available when an active print is bound to an archive
- capture current-print fields that may not be mirrored as first-class archive API fields
- provide deterministic provenance for plate-aware UI behavior and later repair/debug decisions

Recommended columns:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `id` | integer PK | local | |
| `archive_id` | integer FK | local | |
| `printer_id` | integer | mirrored/local | optional when known |
| `binding_source` | text | local | `webhook`, `api_fallback`, `hybrid_status_verified` |
| `status_current_archive_id` | integer/text | local | from current-print status payload |
| `status_current_plate_id` | integer | local | from current-print status payload when present |
| `status_subtask_id` | text | local | optional runtime bridge key |
| `task_name_snapshot` | text | local | normalized active task at bind time |
| `binding_confidence` | text | local | `high`, `medium`, `degraded` |
| `bound_at` | text/datetime | local | |
| `payload_json` | text | local | compact raw evidence for traceability |

Validation rule for this table:

- only mark `binding_confidence=high` when emitted `status_current_archive_id` matches the chosen local `archive_id`
- mismatches should be retained as degraded snapshots for diagnostics, not silently rewritten

## Query-Surface Guidance

The new tables should affect the query surface in a controlled way.

### What Should Surface In Page Rows

Page rows should expose only broadly useful, compact fields such as:

- actual vs estimated badges when meaningful
- a small count or summary for spool certainty
- normalized failure category when available
- derived-cost summary when stable enough for sorting or filtering

### What Should Stay In Detail Hydration

Detail hydration should own richer payloads such as:

- event timeline rows
- spool snapshot details
- artifact extraction details
- lineage and compare relationships
- derivation provenance

For the active popup timeline work, the detail response should include a compact normalized event-timeline DTO that is ready for popup rendering while still keeping raw local provenance available for later diagnostics if needed.

### What Should Stay Out Of Layer 1 And Page Rows

- tooltip-only strings
- popup-specific explanatory copy
- humanized review notes assembled only for one card
- large analytics blobs when only one chart uses them

## Mutation And Sync Rules

To preserve Variant 3 discipline and Variant 4 portability:

- no dual-write between Bambuddy-owned fields and local-only fields
- Bambuddy-owned changes still go through Bambuddy first, then resync
- local-only tables may be written directly by the integration
- derived tables are recomputed or updated by integration-owned services
- repair-sidecar operations, if used, should write through the same sync path rather than bypass it

Recommended rule after any mutation that changes archive-core state:

1. mutate through Bambuddy or the narrow repair boundary
2. re-fetch the affected archive
3. upsert `archives` and child mirrored tables
4. recompute local-only derived tables impacted by the change

## Variant 3 Implementation Guidance

The immediate implementation target should stay inside the current integration files:

- `homeassistant/custom_components/bambuddy/print_history/store.py`
- `homeassistant/custom_components/bambuddy/print_history/query.py`
- `homeassistant/custom_components/bambuddy/manager.py`

Preferred sequence:

1. add schema migrations for the new tables
2. populate the tables from existing enrichment payloads and lifecycle events where possible
3. expose only small summary fields into page rows
4. extend archive-detail hydration to include the richer local-only payloads
5. add analytics or popup features only after the underlying rows exist

This preserves the existing Variant 3 design instead of backfilling features through card-only logic.

## Variant 4 Carry-Forward Rules

If Variant 4 is promoted later:

- keep the same conceptual tables and ownership rules
- expose page, detail, filter-options, and activity queries from the sidecar
- keep Home Assistant as client and orchestration plane
- migrate query execution, not data semantics

In practice, Variant 4 should be able to reuse:

- the same archive page shape
- the same archive detail shape
- the same lineage and metric concepts
- the same spool snapshot and event timeline semantics

The schema should therefore be designed now as if it may later live behind an API, while still being implemented locally in Variant 3 first.

## Decision Summary

The correct path is:

- extend the current Variant 3 local materialized store
- add focused local-only tables for metrics, events, spool snapshots, artifacts, and lineage
- keep Layer 1 lean and shared
- keep page rows compact and push rich provenance into detail hydration
- treat Variant 4 as a future hosting boundary for the same model, not a different model

That gives the repo one coherent print-history metadata architecture instead of separate Variant 3 and Variant 4 approaches.