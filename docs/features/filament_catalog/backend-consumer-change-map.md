# Filament Catalog Backend Consumer Change Map

> **Status**: Proposed
> **Last updated**: 2026-04-13

## Purpose

This is the final design-only map of what will need changing if the filament catalog backend migration proceeds.

It translates the earlier planning docs into a consumer-by-consumer migration view:

- what each current consumer depends on
- what data shape it actually needs
- whether it changes in Phase 1, Phase 2, Phase 3, or later
- whether it can stay untouched

Related docs:

- [Backend Migration Plan](backend-migration-plan.md)
- [Backend Migration Phase 0 Checklist](backend-phase0-contract-checklist.md)
- [Backend Integration Design](backend-integration-design.md)
- [Backend Entity Contract Matrix](backend-entity-contract-matrix.md)

## Migration Summary

### What changes first

Phase 1-3 should focus on these backend contracts:

- add `sensor.filament_catalog_inventory_summary`
- add `sensor.filament_catalog_alert_summary`
- add `sensor.filament_catalog_quality_summary`
- move ownership of `sensor.spoolman_filament_totals` to backend while preserving its core aggregate contract

### What changes later, only if needed

- `sensor.filament_catalog_filtered_spools`
- grouped JSON datasource contract for the single-`auto-entities` catalog view

## Classification Legend

| Class | Meaning |
|---|---|
| **Summary only** | Consumer needs only counts, totals, or compact KPI values |
| **Aggregate context** | Consumer needs per-filament `count` / `weight` but not sibling detail rows |
| **Detail** | Consumer needs sibling spool lists or richer per-item context |
| **Datasource** | Consumer depends on grouped or flat entity-id output for view rendering |
| **Derivative** | Consumer is a compatibility/helper entity that can likely disappear after rewiring |

## Final Consumer Map

### A. Consumers of `sensor.spoolman_filament_totals`

| Consumer | Current use | Data class | Needs after migration | Planned action | Phase |
|---|---|---|---|---|---|
| `template_sensor_filament_catalog_filter.yaml` | Reads per-filament `count` / `weight` for stock and repurchase logic | **Aggregate context** | `count`, `weight` only | Re-point only if entity ID changes; otherwise no logic change required | 2 |
| `filament_catalog_metrics.yaml` | Triggers on totals changes | **Aggregate context** | trigger source only until metrics is retired | Removed when YAML metrics sensor is retired | 1-3 |
| `sync_filter_options.yaml` | trigger + totals availability for hybrid dropdown options | **Aggregate context** | likely trigger + maybe aggregate lookup | Re-point only if entity ID changes | 2 |
| `catalog_filament_card.yaml` | uses `totals[*].count` for spool count | **Aggregate context** | `count` only | No material change if ID preserved | 2 |
| `catalog_filament_card_compact.yaml` | same as full filament card | **Aggregate context** | `count` only | No material change if ID preserved | 2 |
| `catalog_filament_popup_content.yaml` | uses `count` for active spool summary | **Aggregate context** | `count` only | No material change if ID preserved | 2 |
| `catalog_spool_card.yaml` | uses `count` and `weight` for purchase/stock logic | **Aggregate context** | `count`, `weight` only | No material change if ID preserved | 2 |
| `catalog_spool_card_compact.yaml` | same as full spool card | **Aggregate context** | `count`, `weight` only | No material change if ID preserved | 2 |
| `catalog_spool_popup.yaml` | popup trigger references totals-backed context | **Aggregate context** | aggregate context only | Validate after backend ownership switch | 2 |
| `catalog_spool_popup_content.yaml` | shows total weight / count for same filament | **Aggregate context** | `count`, `weight` only | No material change if ID preserved | 2 |
| `ams_tray_popup.yaml` | shows total filament weight/count and sibling spools | **Detail** | aggregate + sibling spool detail | May need new detail path if `spools[]` is moved/shrunk | 2 |
| `catalog_location_header.yaml` | only uses entity as a stable trigger target | **Aggregate context** | trigger target only | Could be repointed later to smaller summary entity, but not required | 2 or later |
| `catalog_group_header.yaml` | only uses entity as a stable trigger target | **Aggregate context** | trigger target only | Could be repointed later to smaller summary entity, but not required | 2 or later |
| `view_filament_catalog.yaml` | uses entity for group header trigger/update stability | **Aggregate context** | trigger target only | No functional rewrite if ID preserved | 2 |

### `spoolman_filament_totals` conclusion

Most consumers are **not** true detail consumers.

Only one confirmed heavyweight detail consumer remains clearly dependent on sibling spool lists:

- `ams_tray_popup.yaml`

Potential light-detail consumer:

- `catalog_spool_popup_content.yaml` if future UX requires sibling spool listing beyond current aggregate summary

Design implication:

- preserve `count` and `weight`
- treat `spools[]` as optional/detail-oriented payload that can move out of the primary aggregate contract

## B. Consumers of `sensor.filament_catalog_metrics`

| Consumer | Current use | Data class | Needs after migration | Planned action | Phase |
|---|---|---|---|---|---|
| `catalog_inventory_kpi.yaml` | parses `inventory_summary_json` | **Summary only** | spool count, filament count, total weight, avg cost | Rewire to `sensor.filament_catalog_inventory_summary` | 1-3 |
| `chart_alert_counts.yaml` | chart source entity | **Summary only** | alert counts | Rewire to `sensor.filament_catalog_alert_summary` | 3 |
| `chart_count_by_material.yaml` | chart source entity | **Summary only** | material count buckets | Rewire to backend chart/summary entity | 3 |
| `chart_count_by_primary_color.yaml` | chart source entity | **Summary only** | color count buckets | Rewire to backend chart/summary entity | 3 |
| `chart_count_by_spool_type_clip_type.yaml` | chart source entity | **Summary only** | spool/clip bucket payload | Rewire to backend chart/summary entity | 3 |
| `chart_count_by_vendor.yaml` | chart source entity | **Summary only** | vendor count buckets | Rewire to backend chart/summary entity | 3 |
| `chart_qty_to_order_by_filament.yaml` | chart source entity | **Summary only** | qty/order summary buckets | Rewire to backend chart/summary entity | 3 |
| `chart_spools_by_location.yaml` | chart source entity | **Summary only** | location buckets | Rewire to backend chart/summary entity | 3 |
| `chart_weight_by_color_family.yaml` | chart source entity | **Summary only** | weight buckets | Rewire to backend chart/summary entity | 3 |
| `chart_weight_by_material.yaml` | chart source entity | **Summary only** | weight buckets | Rewire to backend chart/summary entity | 3 |
| `chart_weight_by_primary_color.yaml` | chart source entity | **Summary only** | weight buckets | Rewire to backend chart/summary entity | 3 |
| `chart_weight_by_primary_color_stacked.yaml` | chart source entity | **Summary only** | stacked color segments | Rewire to backend chart/summary entity | 3 |
| `chart_weight_by_vendor.yaml` | chart source entity | **Summary only** | weight buckets | Rewire to backend chart/summary entity | 3 |
| `template_sensor_filament_catalog_filter.yaml` | reads `data_quality_json` | **Summary only** | quality counts or compact issue index | Rewire to `sensor.filament_catalog_quality_summary` | 3 |
| `filament_catalog_alert_count_sensors.yaml` | derives alert sensors from `alert_counts_json` | **Derivative** | none if direct backend alert summary is used | Remove after consumers are rewired | 3 or cleanup |
| `filament_catalog_material_breakdown_sensors.yaml` | derives material sensors from `count_by_material_json` | **Derivative** | none if direct backend summary/chart entities are used | Remove after consumers are rewired | 3 or cleanup |

### `filament_catalog_metrics` conclusion

This entity has the largest guaranteed rewrite surface, but the rewrite is structurally simple:

- nearly all consumers are summary/chart readers
- most do **not** require a giant umbrella payload
- the derivative helper sensors are cleanup candidates, not long-term migration anchors

Design implication:

- this is the best replacement target for Phase 1-3

## C. Consumers of `sensor.filament_catalog_filtered_spools`

| Consumer | Current use | Data class | Needs after migration | Planned action | Phase |
|---|---|---|---|---|---|
| `view_filament_catalog.yaml` | grouped datasource for main catalog rendering | **Datasource** | grouped entity list + counts | Keep as-is initially | 4 review gate |
| `catalog_filter_bar.yaml` | entity binding and match-count UX | **Datasource** | filtered count + filter summary | Keep as-is initially | 4 review gate |
| `template_sensor_filament_catalog_filter.yaml` | self-derived `entity_ids_json`, `entity_ids`, `active_filter_summary` | **Datasource** | unchanged initially | Keep in YAML initially | 4 review gate |

### `filament_catalog_filtered_spools` conclusion

This entity is the view datasource layer. It is not the first change target.

Design implication:

- do not touch it during Phase 1-3 unless profiling later proves it is still a meaningful hotspot after the summary migration

## What Will Need Changing By Phase

### Phase 1: Add backend summary entities

Will need to change:

- nothing mandatory in cards/popups yet if the release is additive
- design comparison and validation only

Will be added:

- `sensor.filament_catalog_inventory_summary`
- `sensor.filament_catalog_alert_summary`
- `sensor.filament_catalog_quality_summary`

### Phase 2: Move `sensor.spoolman_filament_totals` ownership to backend

Will need validation or minor rewiring:

- `template_sensor_filament_catalog_filter.yaml`
- `sync_filter_options.yaml`
- `catalog_filament_card*.yaml`
- `catalog_spool_card*.yaml`
- `catalog_spool_popup*.yaml`
- `catalog_filament_popup_content.yaml`
- `view_filament_catalog.yaml`
- `catalog_*_header.yaml`

May need actual contract change handling:

- `ams_tray_popup.yaml` if sibling spool detail moves off the main aggregate payload

### Phase 3: Replace `sensor.filament_catalog_metrics` consumers

Will need rewiring:

- `catalog_inventory_kpi.yaml`
- all `dashboard_cards/insights/chart_*.yaml` that point at `sensor.filament_catalog_metrics`
- `template_sensor_filament_catalog_filter.yaml` quality-data read path

Will likely be removed during or after this phase:

- `filament_catalog_alert_count_sensors.yaml`
- `filament_catalog_material_breakdown_sensors.yaml`
- the YAML `sensor.filament_catalog_metrics` entity itself, or reduced to a temporary shim

### Phase 4: Reassess grouped datasource migration

Potentially affected only if still justified:

- `template_sensor_filament_catalog_filter.yaml`
- `view_filament_catalog.yaml`
- `catalog_filter_bar.yaml`

Default recommendation:

- leave these unchanged unless post-Phase-3 profiling still shows them as a real bottleneck

## Final Preserve / Rewire / Remove Map

### Preserve with minimal or no consumer changes

- `sensor.spoolman_filament_totals` concept and ideally entity ID
- most card logic that only uses per-filament `count` and `weight`
- `sensor.filament_catalog_filtered_spools` during Phase 1-3

### Rewire to new backend entities

- KPI cards reading `inventory_summary_json`
- chart cards reading `sensor.filament_catalog_metrics`
- quality-filter logic reading `data_quality_json`

### Remove after rewiring

- alert-count derivative YAML sensors
- material-breakdown derivative YAML sensors
- the oversized umbrella role of `sensor.filament_catalog_metrics`

### Highest-risk edge case

- sibling-spool detail currently surfaced through `sensor.spoolman_filament_totals` for `ams_tray_popup.yaml`

That is the most likely place where a preserve-in-place strategy may still need a small compatibility layer or detail-specific backend path.

## Final Recommendation

The final migration map is:

1. Add backend summary entities first.
2. Preserve and backend-own `sensor.spoolman_filament_totals`, but shrink its contract to aggregate-first data.
3. Replace `sensor.filament_catalog_metrics` consumers aggressively, because they are mostly simple summary/chart rewires.
4. Leave `sensor.filament_catalog_filtered_spools` alone unless later profiling proves it is still worth moving.

That sequence minimizes blast radius while directly addressing the verified oversized-payload and recomputation problems.