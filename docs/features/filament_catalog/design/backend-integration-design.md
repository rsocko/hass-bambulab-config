# Filament Catalog Backend Integration Design

> **Status**: Proposed
> **Last updated**: 2026-04-13

## Purpose

This document describes a **design-only** backend integration shape for moving heavy filament-catalog projection work out of YAML template sensors.

It does **not** implement a custom integration. It defines the recommended boundary, entity model, coordinator/cache structure, and rollout constraints.

Primary planning docs:

- [Backend Migration Plan](../planning/backend-migration-plan.md)
- [Backend Migration Phase 0 Checklist](../planning/backend-phase0-contract-checklist.md)
- [Backend Entity Contract Matrix](../reference/backend-entity-contract-matrix.md)
- [Backend Consumer Change Map](../planning/backend-consumer-change-map.md)

## Recommended Integration Boundary

### Recommended domain

`filament_catalog`

Reasoning:

- keeps scope explicitly tied to the filament catalog feature
- avoids turning the integration into a generic replacement for Spoolman itself
- aligns with the existing feature package name and user mental model

### Explicit non-scope

This integration should **not** own:

- raw Spoolman CRUD or lifecycle management
- spool replacement/refill workflows already owned elsewhere
- filament tag workflows
- general-purpose printer orchestration
- Lovelace card rendering
- user-facing filter helpers and UI state

It is a backend projection/cache layer for catalog consumers.

## High-Level Architecture

### Inputs

- `sensor.spoolman_spool_*`
- `sensor.spoolman_filament_*`
- selected helper states only if a future grouped datasource phase requires them

### Core runtime pieces

#### 1. Source snapshot collector

Responsible for:

- discovering relevant spool and filament entities
- normalizing source attributes
- enforcing active-vs-archived semantics consistently

#### 2. Projection engine

Responsible for:

- per-filament totals
- KPI summary projection
- alert summary projection
- quality summary projection
- optional chart-bucket projection

#### 3. Integration coordinator / cache

Responsible for:

- listening for relevant state changes
- rebuilding only affected projections where possible
- holding compact in-memory projection state
- driving backend-owned entities from a stable cache

#### 4. Entity surface

Responsible for:

- exposing compact HA entities
- separating summary entities from heavyweight drill-down data
- preserving compatibility where required

## Recommended Entity Model

### Tier 1: Stable summary entities

These should be the first backend entities built.

#### `sensor.filament_catalog_inventory_summary`

Fields:

- `spool_count`
- `filament_count`
- `total_weight_grams`
- `average_cost_per_kg`

Use cases:

- KPI chips
- lightweight summary checks

#### `sensor.filament_catalog_alert_summary`

Fields:

- per-alert counts
- optional compact entity-id index per alert group

Use cases:

- alert charts
- alert badges
- filter-bar status summaries

#### `sensor.filament_catalog_quality_summary`

Fields:

- per-quality counts
- optional compact issue indexes

Use cases:

- quality filters
- quality alert displays

### Tier 2: Compatibility / aggregate entity

#### `sensor.spoolman_filament_totals`

Recommended ownership target: backend integration.

Recommended contract:

- active-only totals
- stable per-filament `count`
- stable per-filament `weight`
- detail payload only if a confirmed consumer needs it

Design rule:

- do not let this entity regrow into a giant all-purpose payload just because many consumers exist today

### Tier 3: Optional chart or detail entities

Build only if Phase 0 proves they are justified.

Examples:

- `sensor.filament_catalog_chart_inventory`
- `sensor.filament_catalog_chart_materials`
- `sensor.filament_catalog_chart_colors`
- `sensor.filament_catalog_popup_detail_index`

These are optional because some chart datasets may be small enough to derive from Tier 1 + Tier 2.

## Recommended Update Model

### Event-driven first

Preferred trigger model:

- rebuild projections when relevant Spoolman source entities change
- avoid synthetic hourly keepalive updates for heavy entities unless there is a correctness requirement

### Granularity

Preferred order:

1. start with whole-cache rebuilds if they are fast enough and simple
2. only add partial incremental rebuild logic if profiling justifies the complexity

Reasoning:

- correctness matters more than premature micro-optimization
- a compact backend cache plus compact entities may already be a large win over the YAML/Jinja version

## Data Model Guidelines

### Normalize once

The backend should normalize these recurring source problems in one place:

- archived flag coercion
- quoted string cleanup
- missing/unknown/unavailable handling
- inventory rule label normalization
- color hex cleanup

### Separate summary from detail

Do not put every popup/detail field on summary entities.

Preferred rule:

- summary entities for cards and charts
- detail entities or service responses for heavyweight drill-down data

### Preserve current catalog semantics

The backend must preserve:

1. active-only inventory totals
2. archived-spool browse widening only in scope modes that request it
3. zero-spool filament fallback behavior
4. `All Filaments` filament-summary mode

## Diagnostics and Observability

The integration design should include diagnostics from the beginning.

Recommended diagnostic fields:

- source spool entity count
- source filament entity count
- last projection rebuild duration
- last successful rebuild timestamp
- last rebuild reason
- count of migrated entities emitted

Recommended logging events:

- initial source discovery
- rebuild start/end
- oversized payload prevention or truncation decisions
- compatibility fallback usage

## Coordinator and Entity Layout

### Suggested package shape

If implemented later, a reasonable layout would be:

```text
homeassistant/custom_components/filament_catalog/
├── __init__.py
├── manifest.json
├── config_flow.py            # optional later; not required for first internal-only iteration
├── const.py
├── coordinator.py           # source subscription + rebuild orchestration
├── models.py                # normalized spool/filament records and projection dataclasses
├── projections/
│   ├── inventory.py
│   ├── alerts.py
│   ├── quality.py
│   └── totals.py
├── sensor.py                # summary / compatibility entities
└── diagnostics.py
```

### Suggested internal models

Normalize source entities into Python dataclasses or typed dicts such as:

- `NormalizedSpoolRecord`
- `NormalizedFilamentRecord`
- `InventorySummaryProjection`
- `AlertSummaryProjection`
- `QualitySummaryProjection`
- `FilamentTotalsProjection`

This keeps card-facing entity logic separate from source parsing.

## Rollout Design

### Stage 1: Additive

First backend release should be additive:

- create new backend summary entities
- leave existing YAML entities intact
- compare values side-by-side

### Stage 2: Compatibility ownership switch

Next stage:

- move `sensor.spoolman_filament_totals` ownership to backend
- leave compatibility behavior in place for dependent cards/popups/templates

### Stage 3: Metrics rewiring

Then:

- rewire KPI and chart consumers off `sensor.filament_catalog_metrics`
- retire or shrink the old metrics sensor

### Stage 4: Filter datasource decision

Only after the above:

- decide whether moving `sensor.filament_catalog_filtered_spools` is still worth the complexity

## Key Design Decisions to Make Before Implementation

1. Should the integration require a config entry, or begin as an internal/no-options integration?
2. Should popup sibling-spool detail stay entity-based or move to a service/detail-entity pattern?
3. Which chart datasets deserve first-class backend ownership?
4. Is compatibility via preserved entity IDs preferred over shim entities?

## Recommended Answers

1. Start with a narrow internal config-entry integration only if you need diagnostics/options; otherwise keep the first version simple.
2. Move heavyweight popup sibling detail away from always-present summary payloads if possible.
3. Start with KPI, alert, quality, and totals only.
4. Preserve `sensor.spoolman_filament_totals` if feasible; treat `sensor.filament_catalog_metrics` as the most likely replacement target.

## Anti-Goals

Avoid these design mistakes:

1. Recreating one giant JSON entity in Python and calling that a performance migration.
2. Pulling filter helper state and dashboard policy into the backend too early.
3. Bundling unrelated Spoolman or printer orchestration into this integration.
4. Migrating the grouped datasource before proving the summary layer was insufficient.

## Exit Criteria for Design Completeness

This design is ready to hand off for implementation planning when:

1. Phase 0 contract decisions are complete.
2. The first backend entity set is finalized.
3. Compatibility strategy for `sensor.spoolman_filament_totals` is chosen.
4. Runtime success metrics are agreed upon.
5. The implementation team can build Phase 1 without reopening architectural scope.