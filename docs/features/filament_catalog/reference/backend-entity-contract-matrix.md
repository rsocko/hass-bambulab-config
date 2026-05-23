# Filament Catalog Backend Entity Contract Matrix

> **Status**: Proposed
> **Last updated**: 2026-04-13

## Purpose

This document is a design-only contract matrix for the filament catalog backend migration.

It answers one question explicitly:

For each important current field or payload, should the backend migration **preserve**, **split**, **move**, **shrink**, or **drop** it?

Related docs:

- [Backend Migration Plan](../planning/backend-migration-plan.md)
- [Backend Migration Phase 0 Checklist](../planning/backend-phase0-contract-checklist.md)
- [Backend Integration Design](../design/backend-integration-design.md)

## Decision Legend

| Decision | Meaning |
|---|---|
| **Preserve** | Keep the field/entity contract materially the same |
| **Preserve, narrower** | Keep the contract concept, but shrink or simplify payload |
| **Split** | Break one current payload into multiple smaller backend-owned entities/attrs |
| **Move** | Keep the information, but relocate it to a different backend entity or service |
| **Drop** | Remove from the primary contract because it is redundant or not worth carrying |
| **Defer** | Do not decide until a later migration phase |

## Entity-Level Contract Matrix

| Current entity / payload | Current role | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| `sensor.spoolman_filament_totals` | Per-filament active inventory aggregate | **Preserve, narrower** | Backend-owned `sensor.spoolman_filament_totals` | Preserve entity ID if feasible because of wide consumer surface |
| `sensor.filament_catalog_metrics` | KPI + chart + alert + quality umbrella payload | **Split** | Multiple backend summary entities | Main replacement target |
| `sensor.filament_catalog_filtered_spools` | Grouped datasource for single-`auto-entities` catalog view | **Defer** | YAML initially; maybe backend later | Not first migration target |

## `sensor.spoolman_filament_totals` Field Matrix

Current shape:

```text
totals[filament_id] = {
  weight,
  count,
  spools: [{id, entity_id, name, location, remaining}]
}
```

| Current field | Used for | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| `totals[*].weight` | Stock checks, popup context, card context, filament summaries | **Preserve** | `sensor.spoolman_filament_totals` | Core contract |
| `totals[*].count` | Stock checks, zero-spool logic, card/popup context | **Preserve** | `sensor.spoolman_filament_totals` | Core contract |
| `totals[*].spools[].id` | Popup sibling context | **Move or preserve, narrower** | Detail entity/service or narrower inline detail list | Keep only if proven necessary |
| `totals[*].spools[].entity_id` | Popup/detail navigation | **Move or preserve, narrower** | Detail entity/service or narrower inline detail list | Likely detail-only concern |
| `totals[*].spools[].name` | Popup sibling list | **Move** | Detail entity/service | Not required for most summary consumers |
| `totals[*].spools[].location` | Popup sibling list | **Move** | Detail entity/service | Not needed for stock logic |
| `totals[*].spools[].remaining` | Popup sibling list | **Move** | Detail entity/service | Not needed for most consumers |

### Recommended contract outcome

Preserve the per-filament aggregate shape, but treat `spools[]` as the first thing to shrink, segment, or relocate if payload size remains a problem.

## `sensor.filament_catalog_metrics` Field Matrix

### State

| Current field | Used for | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| sensor state = active spool count | Some summary/derivative uses | **Move** | `sensor.filament_catalog_inventory_summary` state or attribute | Avoid keeping count as an overloaded umbrella sensor state |

### KPI summary payload

| Current field | Used for | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| `inventory_summary_json.spool_count` | KPI chips | **Preserve** | `sensor.filament_catalog_inventory_summary` | First-class summary field |
| `inventory_summary_json.filament_count` | KPI chips | **Preserve** | `sensor.filament_catalog_inventory_summary` | First-class summary field |
| `inventory_summary_json.total_weight_grams` | KPI chips | **Preserve** | `sensor.filament_catalog_inventory_summary` | First-class summary field |
| `inventory_summary_json.average_cost_per_kg` | KPI chips | **Preserve** | `sensor.filament_catalog_inventory_summary` | First-class summary field |

### Chart-bucket payloads

| Current field | Used for | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| `weight_by_material_json` | Chart cards | **Split** | backend chart/summary entity | Keep only if chart still needs server-side bucket payload |
| `weight_by_vendor_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `weight_by_color_family_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `count_by_material_json` | Chart cards + derivative sensors | **Split** | backend chart/summary entity | Derivative YAML sensors may disappear |
| `count_by_vendor_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `count_by_type_json` | Chart/filter analytics | **Split** | backend chart/summary entity | Same pattern |
| `count_by_color_family_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `count_by_spool_type_clip_type_stack_segments_json` | Chart cards | **Split** | backend chart/summary entity | Candidate for optional tier |
| `count_by_primary_color_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `primary_color_weight_segments_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `primary_color_count_segments_json` | Chart cards | **Split** | backend chart/summary entity | Same pattern |
| `primary_color_weight_stack_segments_json` | Chart cards | **Split** | backend chart/summary entity | Likely optional tier |

### Alert and quality payloads

| Current field | Used for | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| `alert_counts_json` | Alert cards and derivative sensors | **Move** | `sensor.filament_catalog_alert_summary` | First-class summary entity |
| `alert_entity_ids_json` | Alert drill-down/filter logic | **Move, smaller if possible** | `sensor.filament_catalog_alert_summary` or detail entity | Prefer compact indexes over giant inline lists |
| `data_quality_json` | Filter logic and quality analysis | **Move** | `sensor.filament_catalog_quality_summary` plus optional detail payload | Keep counts separate from detail issue payloads |

### Derivative YAML sensors that likely become unnecessary

| Current entity | Current dependency | Design decision | Notes |
|---|---|---|---|
| `sensor.filament_catalog_alert_count_*` family | `alert_counts_json` | **Drop after rewiring** | Prefer direct cards/consumers on backend alert summary |
| `sensor.filament_catalog_material_breakdown_*` family | `count_by_material_json` | **Drop after rewiring** | Prefer direct cards/consumers on backend summary/chart entities |

## `sensor.filament_catalog_filtered_spools` Field Matrix

| Current field | Used for | Design decision | Proposed future home | Notes |
|---|---|---|---|---|
| sensor state = filtered count | Match count / quick summary | **Preserve for now** | `sensor.filament_catalog_filtered_spools` | Keep in YAML initially |
| `grouped_entity_ids_json` | Main grouped datasource for catalog view | **Defer** | YAML initially; maybe backend later | Review after Phase 1-3 |
| `entity_ids_json` | Flat compatibility list / count source | **Preserve for now** | `sensor.filament_catalog_filtered_spools` | Derived from grouped output |
| `entity_ids` | Compatibility copy of `entity_ids_json` | **Preserve for now** | `sensor.filament_catalog_filtered_spools` | Remove only if all consumers disappear |
| `active_filter_summary` | Filter-bar UX | **Preserve for now** | `sensor.filament_catalog_filtered_spools` or a small helper sensor later | Not a backend-priority concern |

### Recommended contract outcome

Do not redesign this datasource contract until the summary migration is done. The current grouped-view contract is presentation-coupled, and moving it too early adds risk without directly addressing the largest verified runtime problem.

## Proposed Future Backend Entity Set

This is the recommended first-pass target set.

| Proposed entity | Purpose | Replaces / absorbs |
|---|---|---|
| `sensor.filament_catalog_inventory_summary` | KPI summary | `inventory_summary_json`, active spool count state |
| `sensor.filament_catalog_alert_summary` | Alert counts + compact drill-down index | `alert_counts_json`, part of `alert_entity_ids_json` |
| `sensor.filament_catalog_quality_summary` | Quality counts + compact issue index | `data_quality_json` summary role |
| backend-owned `sensor.spoolman_filament_totals` | Active per-filament inventory aggregate | current YAML `sensor.spoolman_filament_totals` |

## Recommended Preserve / Replace / Shim Decisions

| Entity | Preserve ID | Replace with new entities | Temporary shim |
|---|---|---|---|
| `sensor.spoolman_filament_totals` | **Yes, preferred** | No | Only if preserve-in-place fails |
| `sensor.filament_catalog_metrics` | No | **Yes** | **Yes, if needed during consumer rewiring** |
| `sensor.filament_catalog_filtered_spools` | Yes for now | No for now | No |

## Design Summary

The current design recommendation is:

1. Preserve `sensor.spoolman_filament_totals` as a concept and ideally as an entity ID, but shrink it.
2. Split `sensor.filament_catalog_metrics` into smaller backend summary entities.
3. Leave `sensor.filament_catalog_filtered_spools` alone until the summary migration proves insufficient.

That sequence addresses the verified recorder/payload problem first while minimizing migration blast radius.