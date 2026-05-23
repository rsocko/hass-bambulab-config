# Filament Catalog Template Expand Optimization Design

## Context

Home Assistant has reported a template runtime exception:

- `Template output exceeded maximum size of 262144 characters`
- Trace path: `components/template/coordinator.py -> _handle_triggered -> script_variables.async_render`

This maps to trigger-template variable rendering and strongly suggests that large variable payloads are being materialized before sensor attributes are computed.

The highest risk source is:

- `homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_metrics.yaml`

Specifically, top-level trigger variables currently materialize full expanded state objects:

- `spool_entities` from `expand(spool_ids)`
- `filament_entities` from `expand(filament_ids)`

## Problem Statement

The current trigger-template implementation builds large in-memory objects at render time and repeatedly iterates them across many attribute blocks.

Risks:

1. Exceeding HA template output size limits during variable render
2. Elevated CPU and memory pressure on each trigger
3. Increased chance of startup instability during high-entity loads

## Goals

1. Eliminate oversized coordinator variable payloads
2. Preserve all existing downstream functionality and contracts
3. Improve render efficiency and maintainability
4. Keep behavior stable for dashboards/automations consuming existing attributes

## Non-Goals

1. No user-facing schema changes
2. No renaming/removing existing output attributes
3. No behavior changes in sorting, Unknown fallbacks, or thresholds unless explicitly required

## Current Contract (Must Preserve)

The sensor `Filament Catalog Metrics` in:

- `homeassistant/packages/3d_printing/filament_catalog/template_sensors/filament_catalog_metrics.yaml`

must continue to publish the same state and attribute keys with equivalent semantics, including but not limited to:

- `inventory_summary_json`
- `weight_by_material_json`
- `weight_by_vendor_json`
- `weight_by_color_family_json`
- `count_by_material_json`
- `count_by_vendor_json`
- `count_by_type_json`
- `count_by_color_family_json`
- `count_by_spool_type_clip_type_stack_segments_json`
- `count_by_primary_color_json`
- `primary_color_weight_segments_json`
- `primary_color_count_segments_json`
- `primary_color_weight_stack_segments_json`
- `primary_color_count_stack_segments_json`
- `spools_by_location_json`
- `qty_to_order_by_filament_json`
- `alert_counts_json`
- `alert_entity_ids_json`
- `data_quality_json`
- `total_inventory_value`
- `avg_cost_per_kg`

## Proposed Architecture

### Phase 1 (Minimal-Risk Hardening)

Replace top-level expanded object variables with ID-only variables.

Current:

- `spool_entities: {{ expand(spool_ids) ... | list }}`
- `filament_entities: {{ expand(filament_ids) ... | list }}`

Proposed:

- Keep only `spool_ids` and `filament_ids`
- Resolve attributes on demand via `state_attr(entity_id, ...)` and `states(entity_id)` inside each block

Expected impact:

- Removes large object serialization from coordinator `variables` render path
- Preserves output contract

### Phase 2 (Compact Row Model Per Block)

Inside each heavy attribute block, build a compact list of dict rows with only required fields for that block.

Example row fields:

- `entity_id`
- `archived`
- `remaining_weight`
- `filament_id`
- `vendor`
- `material`
- `color_family`
- `color_hex`
- `sealed`
- `last_used`
- `profile_name`

Do not pass full state objects between steps.

Expected impact:

- Reduced memory pressure and repeated lookup overhead
- Better readability/maintainability

### Phase 3 (Optional Structural Split if Needed)

If performance remains problematic after Phases 1 and 2:

1. Introduce an internal snapshot sensor with compact normalized rows
2. Keep current `Filament Catalog Metrics` output contract unchanged while deriving from snapshot

Expected impact:

- Improved separation of concerns
- Better observability and easier profiling

## Additional Optimization Targets

Similar `integration_entities + expand` patterns exist in related templates, notably spool pin selector templates under:

- `homeassistant/packages/3d_printing/spoolman_sync/template_sensors/template_select_tray_spool_pin_selectors.yaml`

These are not the primary exception source but should be included in follow-up cleanup once the main sensor is stabilized.

## Safety and Regression Strategy

### Contract Validation

For a representative dataset, compare before/after values for all existing attributes.

Validation requirements:

1. Same attribute keys
2. Same data types and schema shapes
3. Semantically equivalent values (allowing only minor ordering differences where order is not contractual)
4. Preserved sorting for attributes that intentionally sort by `count` or `weight`

### Runtime Validation

1. Confirm no recurrence of `Template output exceeded maximum size` in system logs
2. Verify startup behavior remains stable across multiple HA restarts
3. Confirm update cadence remains acceptable

### Rollback Plan

Keep Phase 1 as an isolated commit that can be quickly reverted if needed.

## Implementation Checklist

- [ ] Phase 1: Remove expanded-object top-level variables from filament catalog metrics sensor
- [ ] Phase 1: Update loops to use ID lookups without contract changes
- [ ] Validate all output attributes against baseline
- [ ] Observe logs through at least 3 restart cycles and normal trigger operation
- [ ] Phase 2: Refactor heavy blocks to compact row models
- [ ] Re-validate schema and value parity
- [ ] Optional Phase 3: Snapshot split (only if needed)
- [ ] Follow-up: optimize related spool pin selector templates

## Acceptance Criteria

1. No `Template output exceeded maximum size of 262144 characters` errors for this feature path
2. All existing downstream dashboard and automation consumers continue working unchanged
3. No removed/renamed output attributes in `Filament Catalog Metrics`
4. Measurable reduction in template render pressure (qualitative via log stability; quantitative if available)

## Risks

1. Hidden consumers may rely on incidental ordering in JSON arrays/maps
2. Subtle fallback behavior could drift during refactor if normalization logic is altered
3. Large inventories may still stress templates if additional size-growth paths remain

Mitigations:

- Strict contract-diff validation
- Phase-by-phase rollout
- Fast rollback boundary after Phase 1
