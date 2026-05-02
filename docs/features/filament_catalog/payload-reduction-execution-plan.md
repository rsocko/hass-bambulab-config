# Filament Catalog Payload Reduction Execution Plan

> **Status**: In progress
> **Last updated**: 2026-05-01

## Purpose

This document records the concrete two-phase execution plan for reducing filament catalog websocket pressure without reopening the larger backend-migration scope.

It is intentionally narrower than the broader backend migration documents. The immediate goal is to reduce steady-state `state_changed` payload size and unnecessary browser rerender pressure while preserving existing catalog behavior.

## Problem Statement

Recent Home Assistant logs showed frontend websocket backlog pressure tied to catalog churn, with heavy updates centered on `sensor.spoolman_filament_totals` and downstream catalog subscribers.

The current aggregate shape is:

```text
totals[filament_id] = {
  weight,
  count,
  spools: [{id, entity_id, name, location, remaining}]
}
```

The main issue is not the existence of a per-filament aggregate. The main issue is that the aggregate is carrying popup-detail payload that most consumers do not need.

## Verified Consumer Split

### Requires `spools[]` detail today

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup.yaml`

### Uses summary only or trigger-only

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card_compact.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_filament_popup_content.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_location_header.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_group_header.yaml`
- `homeassistant/packages/3d_printing/filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml`
- `homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml`
- `homeassistant/packages/3d_printing/filament_catalog/dashboard_views/view_filament_catalog.yaml`

## Phase 1

### Goal

Shrink `sensor.spoolman_filament_totals` in place while preserving the stable entity ID and its aggregate contract.

### Planned change

Reduce each `totals[*]` entry to:

```json
{
  "weight": 842.5,
  "count": 3
}
```

### Compatibility strategy

- Preserve `totals[*].weight`
- Preserve `totals[*].count`
- Remove `totals[*].spools`
- Rework the two popup/detail consumers to derive sibling spools directly from live `states` at render time

### Why this is the first cut

- It removes the largest detail payload from a globally-broadcast aggregate sensor
- It keeps the main entity ID stable for existing `triggers_update` consumers
- It limits functional rewrites to the two confirmed detail consumers
- It tests the payload-size hypothesis before widening into broader frontend rewrites

### Validation target

- Home Assistant configuration still loads cleanly
- Popup behavior remains correct for same-filament sibling spool display
- No regression in count/weight-based card logic

## Phase 2

### Goal

Reduce downstream rerender fan-out after the aggregate payload is slimmed.

### Planned Optimization

Separate **shortage detection logic** from the main filter computation by creating a dedicated helper sensor (`sensor.filament_shortage_status`).

### What Changed

**Before Phase 2:**
- `sensor.filament_catalog_filtered_spools` recalculated the entire filter on every upstream change:
  - All `sensor.spoolman_spool_*` updates
  - All `sensor.spoolman_filament_*` updates  
  - All input_select/input_boolean filter changes
  - **AND** every `sensor.spoolman_filament_totals` update
- Within the filter loop, each spool recalculated its own shortage status by reading totals and inventory rules

**After Phase 2:**
- New helper `sensor.filament_shortage_status` pre-computes shortage mapping once per totals change
  - State: count of filaments with shortage
  - Attribute `totals_and_shortage_json`: {filament_id → {count, weight, shortage_flag}}
- Filter template no longer recalculates shortage; instead looks up pre-computed flag
- Filter template uses `totals_and_shortage` from helper instead of scanning totals directly

### Removed

- ~~`catalog_location_header.yaml`~~ — Template was deferred for Phase 4 and not used in current view. Removed to reduce template clutter.

### Validation target

- Home Assistant configuration still loads cleanly
- Filament catalog grouping and filtering unchanged
- No regression in popup or spool-detail flows
- WebSocket pressure reduced on `sensor.spoolman_filament_totals` updates

### Constraint

Phase 2 must preserve the existing single-`auto-entities` catalog model. It should not reintroduce the abandoned multi-grid/per-group architecture.

## Tracking

- GitHub issue: `#1200` - Phase 1 payload slimming and popup compatibility work
- GitHub issue: `#1201` - Phase 2 trigger and client-scan reduction work

## Non-Goals

- This plan does not move the catalog projection layer into a backend integration yet
- This plan does not redesign the catalog UI
- This plan does not change active-vs-archived inventory semantics
- This plan does not solve the entire `sensor.filament_catalog_metrics` split