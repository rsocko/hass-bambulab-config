# Filament Catalog Backend Migration Phase 0 Checklist

> **Status**: Proposed
> **Last updated**: 2026-04-13

## Purpose

This document turns Phase 0 of the backend migration plan into a concrete design-time checklist.

It does **not** implement anything. It defines what must be inventoried, preserved, or deliberately changed before any backend migration of the filament catalog projection layer begins.

Primary source plan: [Backend Migration Plan](backend-migration-plan.md).

## Scope of Phase 0

Phase 0 covers three current projection entities:

- `sensor.spoolman_filament_totals`
- `sensor.filament_catalog_metrics`
- `sensor.filament_catalog_filtered_spools`

Goals:

1. Identify every active consumer.
2. Separate hard contract fields from convenience fields.
3. Define which compatibility guarantees are mandatory for Phase 1-3.
4. Define what runtime evidence will count as an improvement.

## Contract Rules

These rules are already part of the current feature design and must remain true unless there is an explicit design decision to change them:

1. `sensor.spoolman_filament_totals` is **active inventory only**. Archived spools are not included in its totals.
2. `Include Archived Spools` changes browse rows, not active inventory aggregates.
3. `All Filaments` is a separate filament-summary mode and must keep working independently of spool-row mode.
4. The dashboard/application shell remains YAML/Lovelace-owned.
5. Backend migration is allowed to change implementation, but not silently change catalog semantics.

## Consumer Inventory

### `sensor.spoolman_filament_totals`

#### Template / automation consumers

- [homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_metrics.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_metrics.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml)

#### Dashboard / popup / card consumers

- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_card.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_card.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_card_compact.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_card_compact.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_popup_content.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_popup_content.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card_compact.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card_compact.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_location_header.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_location_header.yaml)
- [homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_group_header.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_group_header.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_views/view_filament_catalog.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_views/view_filament_catalog.yaml)

#### Contract significance

This entity is not just a trigger source. It currently provides:

- per-filament count
- per-filament weight
- sibling spool lists used in popups and card context
- a stable trigger target for cards that intentionally avoid `triggers_update: all`

#### Phase 0 questions

1. Which consumers truly require `spools[]` detail, versus only `count` and `weight`?
2. Should popup sibling-spool detail remain on the aggregate entity, or move behind a separate backend detail entity/service?
3. Can `catalog_location_header` and `catalog_group_header` be re-pointed to a smaller summary entity without changing behavior?

### `sensor.filament_catalog_metrics`

#### Template consumers

- [homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_alert_count_sensors.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_alert_count_sensors.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_material_breakdown_sensors.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_material_breakdown_sensors.yaml)

#### Dashboard consumers

- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/catalog_inventory_kpi.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/catalog_inventory_kpi.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_alert_counts.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_alert_counts.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_material.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_material.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_primary_color.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_primary_color.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_spool_type_clip_type.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_spool_type_clip_type.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_vendor.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_count_by_vendor.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_qty_to_order_by_filament.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_qty_to_order_by_filament.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_spools_by_location.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_spools_by_location.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_color_family.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_color_family.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_material.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_material.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_primary_color.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_primary_color.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_primary_color_stacked.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_primary_color_stacked.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_vendor.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/insights/chart_weight_by_vendor.yaml)

#### Contract significance

This entity is doing too many jobs at once. Today it bundles:

- KPI inventory summary
- chart datasource buckets
- alert counts
- alert entity lists
- data-quality reports

#### Phase 0 questions

1. Which chart datasets need first-class backend entities, and which can remain derived?
2. Which consumers need only counts, versus full entity-id lists or issue-detail payloads?
3. Can alert/material derivative sensors be deleted after cards are rewired to smaller backend summary entities?

### `sensor.filament_catalog_filtered_spools`

#### Self / template consumers

- [homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml)

#### Dashboard consumers

- [homeassistant/packages/3d_printing/filament_catalog/dashboard_views/view_filament_catalog.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_views/view_filament_catalog.yaml)
- [homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/catalog_filter_bar.yaml](../../../../homeassistant/packages/3d_printing/filament_catalog/dashboard_cards/catalog_filter_bar.yaml)

#### Contract significance

This entity is the primary grouped datasource for the single-`auto-entities` catalog view. It is coupled directly to view rendering behavior and match counts.

#### Phase 0 questions

1. Is the current hotspot primarily template recomputation cost, or payload/render cost from grouped JSON?
2. Can the current grouped JSON contract remain in YAML while summary data moves to backend entities?
3. If this eventually moves, should the integration expose grouped JSON directly, or expose a smaller normalized dataset that YAML groups client-side?

## Required Compatibility Decisions

These decisions must be made before Phase 1 starts:

## Preliminary Migration Decision Table

This table is the current design recommendation based on the verified consumer surface and current runtime pain points. It is still design-only, but it is concrete enough to guide implementation planning.

| Current entity | Consumer blast radius | Runtime pain | Design recommendation | Compatibility strategy | Earliest phase |
|---|---|---|---|---|---|
| `sensor.spoolman_filament_totals` | Very high: templates, automations, cards, popups, view triggers | Medium-high payload size; central trigger target; popup sibling detail pressure | **Preserve entity ID, move ownership to backend, narrow payload deliberately** | Preserve ID in place if feasible; if not, temporary shim only | Phase 2 |
| `sensor.filament_catalog_metrics` | High: KPI cards, chart cards, derivative sensors, filter quality input | Highest oversized attribute risk; too many mixed responsibilities | **Replace with smaller backend summary entities** | New backend summary entities plus temporary compatibility shim if needed | Phase 1-3 |
| `sensor.filament_catalog_filtered_spools` | Medium-high but localized: main view + filter bar + self-derived attrs | Complex grouped JSON generation; primary datasource role | **Defer migration decision until after summary migration** | Keep current entity in YAML initially | Phase 4 review gate |

### Design outcome by entity

#### `sensor.spoolman_filament_totals`

- Decision: preserve the entity ID if at all possible.
- Why: this entity is deeply embedded in cards, popups, templates, and `triggers_update` behavior.
- Acceptable change: reduce or relocate heavyweight sibling spool detail if that is the main payload driver.
- Unacceptable silent change: widening it to include archived inventory, changing per-filament semantics, or removing `count`/`weight` compatibility without a shim.

#### `sensor.filament_catalog_metrics`

- Decision: do not preserve as the long-term primary interface.
- Why: it bundles KPI summary, chart buckets, alert counts, alert entity lists, and quality reports into one oversized object.
- Preferred future: split into compact backend summary entities and only keep a temporary shim while consumers are rewired.

#### `sensor.filament_catalog_filtered_spools`

- Decision: do not migrate first.
- Why: it is a grouped view datasource, not the first-order recorder/payload problem.
- Review trigger: only move it after Phase 1-3 if it still shows up as a real hotspot.

### Decision A: Entity ID preservation

For each migrated entity, choose one:

1. Preserve current entity ID and narrow the payload in place.
2. Introduce a new entity ID and keep a temporary compatibility shim.

Recommendation:

- Preserve `sensor.spoolman_filament_totals` if possible, because its consumer surface includes cards, popups, templates, and automation triggers.
- Replace `sensor.filament_catalog_metrics` with smaller summary entities plus a temporary shim if needed.
- Delay any entity-ID decision for `sensor.filament_catalog_filtered_spools` until after Phase 3.

### Decision B: Detail payload placement

If sibling spool details remain necessary, choose one:

1. keep them on the aggregate entity
2. move them to a detail entity
3. expose them via a backend service/diagnostic endpoint

Recommendation:

- do not keep large sibling detail inline by default unless measurements show it is cheap enough

### Decision C: Alert and quality payload model

Choose whether backend alert/quality entities expose:

1. counts only
2. counts + compact indexes
3. full detailed issue payloads

Recommendation:

- counts + compact indexes by default
- full issue payloads only where a concrete consumer needs them

## Runtime Baseline to Capture Before Any Migration

Phase 0 should record the following baseline facts:

1. Recent recorder warnings involving catalog projection sensors.
2. Current update frequency for:
   - `sensor.spoolman_filament_totals`
   - `sensor.filament_catalog_metrics`
   - `sensor.filament_catalog_filtered_spools`
3. Current frontend render dependencies for the catalog view.
4. Current entity counts for Spoolman spool and filament entities.
5. Current state payload size characteristics for the migrated sensors.

## Success Criteria for Leaving Phase 0

Phase 0 is complete when:

1. Every active consumer of the three target sensors has been listed.
2. Each consumer has been classified as requiring either:
   - summary data
   - chart data
   - detail drill-down data
   - grouped view datasource data
3. The team has chosen the compatibility strategy for each target sensor.
4. The team has chosen the first backend entity set to build in Phase 1.
5. A measurable runtime baseline has been recorded.

## Recommended Output of Phase 0

At the end of Phase 0, the migration should produce a short design packet containing:

1. this checklist with boxes marked complete
2. a final consumer table with required fields per consumer
3. the chosen compatibility decisions
4. the Phase 1 backend entity list
5. a rollback plan if migrated entities need to revert to YAML ownership

Related design doc:

- [Backend Entity Contract Matrix](backend-entity-contract-matrix.md)