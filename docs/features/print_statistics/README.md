# Print Statistics — Bambuddy Stats in HA

> **⚠️ OpenAPI Corrections Needed**: See [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for full cross-reference. Key issues: endpoint is `/api/v1/archives/stats` (NOT `/api/v1/statistics`), several assumed attributes don't exist in `ArchiveStats` schema and must be computed in templates.

## Overview

Surfaces Bambuddy's aggregate printing statistics in HA as a REST sensor with derived template sensors and a dashboard card. Auto-refreshes on print completion webhook events.

**HA Role**: READ statistics + SURFACE in dashboard. Bambuddy owns all statistical aggregation (success rates, totals, trends).

## Package Structure

```
homeassistant/packages/3d_printing/print_statistics/
├── print_statistics_loader.yaml
├── automations/
│   └── bambuddy_event_stats_refresh.yaml
├── rest_sensors/
│   └── bambuddy_statistics_sensor.yaml
├── template_sensors/
│   ├── bambuddy_success_rate.yaml
│   ├── bambuddy_total_print_time.yaml
│   ├── bambuddy_total_filament_used.yaml
│   └── bambuddy_prints_this_week.yaml
└── dashboard_cards/
    └── statistics.yaml
```

## Loader Domains

```yaml
# print_statistics_loader.yaml
automation: !include_dir_merge_list automations
sensor: !include_dir_merge_list rest_sensors
template: !include_dir_merge_list template_sensors
```

## Entity Reference

### REST Sensors

| Entity | Endpoint | Interval | State |
|---|---|---|---|
| `sensor.bambuddy_statistics` | `GET /api/v1/archives/stats` | 10 min | `total_prints` |

> **OpenAPI note**: The endpoint is `/api/v1/archives/stats` (NOT `/api/v1/statistics`). No trailing slash needed (not a collection). Optional query params: `date_from`, `date_to` (YYYY-MM-DD format).

Attributes from `ArchiveStats` schema:
- `total_prints`, `successful_prints`, `failed_prints`, `stopped_prints`
- `total_print_time_hours`, `total_filament_grams`, `total_cost`
- `prints_by_filament_type` (dict: `{"PLA": 800, "PETG": 300}`)
- `prints_by_printer` (dict: `{"1": 700, "2": 534}`)
- `average_time_accuracy`, `time_accuracy_by_printer`
- `total_energy_kwh`, `total_energy_cost`

> **NOT in API** (must be computed in templates): `success_rate_percent`, `cancelled_prints`, `prints_this_month`, `prints_this_week`, `avg_print_time_hours`, `most_used_filament`, `top_models`

### Template Sensors

| Entity | Source | Unit | Purpose |
|---|---|---|---|
| `sensor.bambuddy_success_rate` | **Computed**: `(successful_prints / total_prints * 100)` | % | Overall print success rate |
| `sensor.bambuddy_total_print_time` | `total_print_time_hours` | h | All-time print hours |
| `sensor.bambuddy_total_filament_used` | `total_filament_grams` | g | All-time filament usage |
| `sensor.bambuddy_prints_this_week` | **Not in API** — see open items | prints | Prints completed this week |

> **OpenAPI note — template sensor source corrections**:
> - `success_rate_percent` does NOT exist in `ArchiveStats`. Compute via Jinja: `{{ (attr.successful_prints / attr.total_prints * 100) | round(1) }}`
> - `total_filament_used_grams` → actual field is `total_filament_grams` (no `_used_`)
> - `prints_this_week` does NOT exist. Options: (a) drop sensor, (b) make a 2nd REST sensor calling `/api/v1/archives/stats?date_from=YYYY-MM-DD` with Monday's date, or (c) count from `/api/v1/archives/slim?date_from=...&limit=50000`
> - **New fields available**: `stopped_prints`, `average_time_accuracy`, `time_accuracy_by_printer`, `total_energy_kwh`, `total_energy_cost`, `prints_by_filament_type`, `prints_by_printer` — consider exposing these as template sensors or dashboard attributes

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_event_stats_refresh` | `bambuddy_webhook_event` where event=`print_complete` or `print_failed` | `homeassistant.update_entity` on statistics sensor |

## Migration Notes

### Prototype Lineage
- **REST sensor**: `bambuddy_statistics` from the root `bambuddy/sensors.yaml` prototype
- **Template sensors**: 4 derived sensors from the root `bambuddy/sensors.yaml` prototype (converted to modern `template:` format)
- **Dashboard card**: root `bambuddy/dashboards/statistics.yaml` prototype evolved into `dashboard_cards/statistics.yaml`
- **Webhook handling**: stats refresh logic extracted from the root `bambuddy/automations/webhook_handler.yaml` prototype

### Changes from Current
- Template sensors converted from legacy `platform: template` → modern `template:` format
- `sensor.bambuddy_prints_this_week` icon changes from `icon_template` to `icon:`
- Webhook handling: listens to `bambuddy_webhook_event` HA event instead of inline webhook logic

## Dashboard Cards

### `statistics.yaml`
Displays printing statistics:
- **Row 1**: Prints this week, this month, all-time totals
- **Row 2**: Success rate (color-coded), filament used, print hours
- **Outcome bar**: Stacked bar showing success/failed/cancelled percentages
- Link to full statistics in Bambuddy's web UI

## Dependencies

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [bambuddy_common](../bambuddy_common/README.md) | **Yes** | API config helpers, webhook event source |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Statistics API |
| [button-card](https://github.com/custom-cards/button-card) (HACS) | **Yes** | Dashboard card rendering |

## Related

- [printer_maintenance](../printer_maintenance/README.md) — Uses statistics data for maintenance health scoring (depends on this package for `sensor.bambuddy_statistics`)
- [advanced-features-design.md](../print_history/planning/advanced-features-design.md) — Rolling exception windows, energy analytics, and per-printer efficiency follow-ons

## Scope Decision After API Review

The current stats endpoint already returns more operational value than the original core plan used.

- **Promote into near-core Phase 4**: expose `total_energy_kwh`, `total_energy_cost`, `prints_by_printer`, and `time_accuracy_by_printer` in the base dashboard/templates. These are read-only and come from the same API response.
- **Keep as advanced**: rolling-window anomaly sensors that require extra date-window REST calls and failure-analysis correlation.

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | **Endpoint URL must be `/api/v1/archives/stats`** — NOT `/api/v1/statistics`. No trailing slash needed. | REST sensor URL | **Yes — wrong URL will 404** |
| 2 | **`prints_this_week` not in API** — `ArchiveStats` has no time-windowed counts. Options: drop sensor, add 2nd REST call with `date_from`, or use `/archives/slim` count. | Template sensor redesign | No — design decision |
| 3 | **Several attributes renamed or missing** — `total_filament_used_grams` → `total_filament_grams`; `cancelled_prints` → `stopped_prints`; `success_rate_percent` must be computed; `avg_print_time_hours`, `most_used_filament`, `top_models` not in API. | Template sensor sources | No — template math |
| 4 | **New stats available** — `average_time_accuracy`, `time_accuracy_by_printer`, `total_energy_kwh`, `total_energy_cost`, `prints_by_filament_type`, `prints_by_printer` should feed the base Phase 4 dashboard where practical. | Recommended scope expansion | No — same endpoint, low-risk |
| 5 | **Date-filtered queries** — `date_from` and `date_to` (YYYY-MM-DD) are optional params on `/archives/stats`. Could power "this month" / "this week" dashboard widgets via separate REST sensors. | Future dashboard widgets | No — enhancement |
