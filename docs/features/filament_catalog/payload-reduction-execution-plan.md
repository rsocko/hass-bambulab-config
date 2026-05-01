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

### Planned focus

- Identify cards using `sensor.spoolman_filament_totals` only as a trigger anchor
- Reduce unnecessary `Object.values(states)` scans where a smaller scoped input can be used
- Repoint trigger-only consumers to smaller summary entities if that can be done without reopening the single-grid catalog architecture

### Examples already identified

- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_location_header.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_group_header.yaml`
- `homeassistant/packages/3d_printing/filament_catalog/dashboard_views/view_filament_catalog.yaml`

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