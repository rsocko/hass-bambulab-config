# Filament Catalog Backend Migration Plan

> **Status**: Proposed
> **Last updated**: 2026-04-13

## Why This Exists

The filament catalog currently gets most of its value from three Home Assistant-side projection layers:

- `sensor.spoolman_filament_totals`
- `sensor.filament_catalog_metrics`
- `sensor.filament_catalog_filtered_spools`

That architecture was the right tradeoff to ship the catalog quickly and keep the dashboard/application layer inspectable in YAML. It is now showing the limits of that approach at current scale:

- `sensor.spoolman_spool_*` and `sensor.spoolman_filament_*` counts are high enough that broad template iteration is expensive.
- The current aggregate sensors publish large JSON attributes, which increases `state_changed` payload size and frontend work.
- Home Assistant recorder is currently warning that `sensor.spoolman_filament_totals` and `sensor.filament_catalog_metrics` exceed the 16384-byte attribute storage threshold.
- The current filter and KPI stack has become a backend-style projection/cache problem, not just a dashboard composition problem.

This document proposes a phased migration of the **heavy Spoolman-derived projection layer** out of YAML template sensors and into a custom integration or integration-owned backend service, while keeping the dashboard shell and user-policy controls in Home Assistant YAML.

## Executive Decision

Do **not** migrate the full filament catalog feature out of YAML.

Do migrate the **high-cardinality aggregation/projection layer** out of YAML if the goal is to reduce CPU, memory churn, oversized state payloads, and template recomputation overhead.

### Keep in Home Assistant YAML / Helpers

- Lovelace dashboards and card composition
- `input_boolean`, `input_select`, `input_text`, and `input_number` controls
- Small helper sensors that only expose narrow, stable values
- User-policy automations and scripts

### Move to a Backend Integration Layer

- Aggregate per-filament spool projection currently exposed by `sensor.spoolman_filament_totals`
- Inventory/analytics projection currently exposed by `sensor.filament_catalog_metrics`
- Potentially the filter datasource projection currently exposed by `sensor.filament_catalog_filtered_spools`
- Any shared cache/coordinator logic that currently forces multiple template passes over all spool entities

## Goals

1. Reduce repeated whole-entity-set Jinja evaluation.
2. Reduce `state_changed` payload size for catalog backing entities.
3. Keep UI-facing entity contracts stable where practical.
4. Preserve the current layering rule: backend projection in code, presentation in YAML/Lovelace.
5. Make the backend projection testable and observable.
6. Avoid a flag-day migration that breaks the catalog, popups, alerts, or helper sync logic.

## Non-Goals

- Rewriting the filament catalog dashboard into a custom frontend card
- Moving user-facing helpers or filter controls into Python
- Replacing all YAML in the repository with integrations
- Changing the catalog's active-only inventory semantics for archived spools

## Current Pain Points

### 1. Repeated Broad Entity Iteration

The current templates iterate across `states.sensor` and regex-match Spoolman entities. That is manageable for a small fleet, but it scales poorly as spool, filament, and derived entity counts grow.

### 2. Large Aggregate Attributes

Two sensors currently concentrate large JSON payloads:

- `sensor.spoolman_filament_totals`
- `sensor.filament_catalog_metrics`

These payloads are useful, but they are also expensive:

- recorder drops oversized attributes
- frontend cards must parse large JSON repeatedly
- each meaningful update can still cause a wide set of dependent cards to refresh

### 3. Mixed Responsibilities in Template Sensors

The current template layer is doing several jobs at once:

- source normalization
- aggregation
- analytics
- filter datasource generation
- compatibility bridging for cards and automations

That is backend projection logic. YAML templates can express it, but they are no longer the cleanest place to own it.

## Architectural Target

### Layering

### Layer A: Source Entities

Remain provided by existing integrations:

- Spoolman spool entities
- Spoolman filament entities
- existing foundation entities where relevant

### Layer B: Backend Projection Integration

Add a narrow backend layer that:

- subscribes to relevant source entities
- computes reusable aggregate state in Python once per source update
- exposes compact, purpose-built entities for the catalog
- avoids publishing giant "everything" payloads when smaller entities or segmented attributes will do

### Layer C: HA Application Shell

Remain in YAML:

- filter helpers
- dashboard cards
- dashboard views
- popup composition
- user-policy scripts/automations

## Proposed Entity Strategy

The key improvement is not just "move code to Python". The key improvement is to **change the projection contract** so Home Assistant is not carrying a few oversized umbrella payloads.

### Preferred Direction

Replace a small number of giant JSON sensors with a mix of:

- one compact summary sensor for inventory totals/KPIs
- one compact per-filament aggregate map or a small family of entities if needed
- dedicated sensors or attributes for alert counts and quality counts
- optional on-demand detail services for heavyweight drill-down data

### Example Split

#### `sensor.filament_catalog_inventory_summary`

Owns only stable KPI-style values:

- spool count
- filament count
- active total weight
- average cost per kg

#### `sensor.filament_catalog_alert_summary`

Owns only alert counts and perhaps a small entity-id index by category.

#### `sensor.filament_catalog_quality_summary`

Owns only data-quality counts plus small issue indexes.

#### `sensor.spoolman_filament_totals`

Either:

- keep the entity id but reduce the payload shape, or
- replace it with a backend-owned successor and update consumers deliberately.

If this entity remains, it should stay focused on **active inventory totals** and avoid growing into a presentation-oriented catch-all object.

#### Filter datasource

The main filtered/grouped catalog projection is the hardest decision.

Options:

1. Keep `sensor.filament_catalog_filtered_spools` in YAML initially, but make it depend on smaller backend summary entities.
2. Move the filtered/grouped datasource into the integration once the summary layer is stable.

Recommended order: start with option 1, then reassess.

## Phased Migration Plan

### Phase 0: Measure and Lock Contracts

Before moving logic, freeze what the current system must preserve.

Deliverables:

- document all consumers of `sensor.spoolman_filament_totals`, `sensor.filament_catalog_metrics`, and `sensor.filament_catalog_filtered_spools`
- identify which fields are truly required by cards, scripts, and automations
- capture current update patterns and warning signatures
- define success metrics

Success metrics:

- no recorder oversized-attribute warnings for the migrated entities
- reduced frontend parsing pressure on dashboard loads and updates
- no regression in catalog filtering, KPIs, or popup behavior

### Phase 1: Create the Backend Summary Layer

Create a new backend integration surface for filament-catalog aggregation.

Scope:

- coordinator or event-driven cache over Spoolman source entities
- compact inventory summary entity
- compact alert summary entity
- compact quality summary entity
- diagnostics/logging for projection rebuild time and entity counts

Keep all existing YAML consumers in place for now.

Why first:

- lowest migration risk
- easiest place to cut payload size
- immediate recorder/front-end benefit

### Phase 2: Move `spoolman_filament_totals` Ownership to the Backend

Re-implement the active-inventory totals helper in code.

Requirements:

- preserve the active-only archived-spool contract
- preserve enough compatibility for existing popup and card consumers
- keep the payload minimal; avoid embedding data that can be derived cheaply elsewhere

Recommended constraint:

- if consumer code only needs `count` and `weight`, do not publish full spool lists for every filament by default
- if detailed sibling spool lists are still needed for popups, consider a separate detail attribute or service path rather than making every dashboard consumer carry it

### Phase 3: Rewire Metrics Consumers

Update KPI cards, chart cards, and alert count sensors to read from the new backend summary entities instead of `sensor.filament_catalog_metrics`.

Scope:

- KPI chips
- insights charts
- alert-count helper sensors
- material breakdown sensors

Goal:

- retire `sensor.filament_catalog_metrics` entirely or reduce it to a compatibility shim

### Phase 4: Reassess the Filter Datasource

After Phase 1-3, evaluate whether `sensor.filament_catalog_filtered_spools` is still a meaningful hotspot.

Move it only if one or more of the following remain true:

- filter evaluation remains measurably expensive
- grouped JSON output remains large enough to create noticeable frontend churn
- YAML template complexity continues to slow maintenance or increase bug risk

If the remaining problem is acceptable after the summary migration, leave this layer in YAML. Do not move it just for symmetry.

### Phase 5: Cleanup and Compatibility Removal

After runtime validation:

- remove compatibility shims no longer needed
- simplify dashboard card JS to consume smaller payloads
- remove obsolete template sensors and alert/material derivative sensors where backend entities replaced them
- update design docs and operational docs with the new layering

## Runtime and Operational Improvements Expected

### CPU

- fewer repeated Jinja passes over all spool entities
- less repeated JSON assembly in the template engine
- lower dashboard-side parsing cost for very large attributes

### Memory / State Churn

- smaller state payloads for backing entities
- fewer oversized attributes retained in-memory and shipped through the state machine
- less recorder pressure from giant attribute dictionaries

### Frontend

- smaller card dependencies
- less JS parsing of large JSON strings in button-card/config-template-card snippets
- lower chance of re-render storms when only summary values changed

### Maintainability

- backend projection logic becomes testable with Python fixtures
- clearer separation between backend aggregation and frontend formatting
- easier to instrument timing, cache rebuild count, and error paths

## Risks

### 1. Contract Breakage

These entities are consumed widely across:

- KPI cards
- catalog cards
- popups
- helper-sync automations
- filter logic

Mitigation:

- Phase 0 consumer inventory
- compatibility shims during Phase 2-3
- explicit old-id / new-id reference search before removals

### 2. Moving the Same Problem Without Fixing Payload Shape

If the integration publishes the same giant JSON blobs, CPU may improve somewhat but state payload pressure will remain.

Mitigation:

- redesign entity contracts, not just implementation language

### 3. Over-scoping the Integration

It would be easy to accidentally move dashboard policy and presentation concerns into Python.

Mitigation:

- keep the integration focused on projection/cache/state
- keep helpers, dashboards, and user policy in YAML

## Validation Checklist

After each migration phase, verify:

1. No stale references to replaced entity IDs remain.
2. `Include Archived Spools` still widens browse rows without widening active inventory totals.
3. `All Filaments` still renders filament-summary mode correctly.
4. KPI chips still match source inventory counts.
5. Popups still show sibling spool context where expected.
6. Recorder no longer warns about oversized migrated attributes.
7. HA system logs remain clear of websocket backlog signatures tied to catalog churn.

## Recommended Implementation Order

If only one phase is funded now, do this order:

1. Phase 0
2. Phase 1
3. Phase 2

That sequence gives the best chance of reducing real HA load quickly without forcing a full feature rewrite.

## Decision Gate

Proceed with the backend migration if all of the following remain true:

- recorder oversized-attribute warnings continue on catalog projection sensors
- current template complexity is slowing safe iteration
- the catalog continues to accumulate new analytics or grouping requirements

Defer full datasource migration if, after Phase 1-3, the remaining YAML filter layer is no longer a meaningful operational hotspot.

## Relationship to Repo Strategy

This plan is consistent with the repository-level guidance in `docs/repo/custom-integration-strategy.md`:

- keep the application shell in YAML
- move only backend/domain logic that benefits from code ownership
- avoid converting the entire repo into many integrations

This migration should therefore be treated as a **narrow backend projection integration**, not a rewrite of the filament catalog feature as a whole.