# Print Statistics — Bambuddy Stats in HA

> The first production slice of this package is now implemented in the active 3D Printing dashboard. See the `Current State` section below for what is live and the `Recommended Next Steps` section for the next phases.

## Overview

Surfaces Bambuddy's aggregate printing statistics in HA as REST sensors, derived template sensors, and a dedicated dashboard view. Auto-refreshes on Bambuddy terminal print webhook events.

**HA Role**: READ statistics + SURFACE in dashboard. Bambuddy owns all statistical aggregation (success rates, totals, trends).

## Current State

The package is now wired into the active 3D Printing dashboard and ships a production first slice.

Implemented now:
- `print_statistics_loader` is enabled in [homeassistant/packages/3d_printing/_feature_loaders.yaml](../../../homeassistant/packages/3d_printing/_feature_loaders.yaml)
- the 3D Printing dashboard includes [homeassistant/packages/3d_printing/print_statistics/dashboard_views/view_print_statistics.yaml](../../../homeassistant/packages/3d_printing/print_statistics/dashboard_views/view_print_statistics.yaml)
- corrected Bambuddy stats REST sensors are live for all-time, this-week, this-month, and failure-analysis queries
- derived KPI sensors are live for success rate, print hours, filament used, print cost, energy used, energy cost, time accuracy, and top failure reason
- a chart-ready metrics sensor is live for first-slice donut/bar charts
- the Statistics view currently renders an overview panel and an insights panel
- a Statistics handoff card now reads URL scope such as `printer_id`, `project_id`, and date-window params, then loads filtered failure analysis over the Bambuddy websocket API

Intentionally deferred:
- utilization-rate analytics
- trustworthy per-print derived cost and energy joins
- spool-history crossover and empty-filament-risk reporting
- archive-filter-aware analytics that depend on the Variant 3 metadata roadmap

Those deferred items should build on the Variant 3 metadata work in [../print_history/planning/metadata-implementation-roadmap.md](../print_history/planning/metadata-implementation-roadmap.md), especially `archive_metric_summary` and `archive_spool_snapshots`.

## Package Structure

```
homeassistant/packages/3d_printing/print_statistics/
├── print_statistics_loader.yaml
├── automations/
│   └── bambuddy_event_stats_refresh.yaml
├── rest_sensors/
│   └── bambuddy_statistics_sensor.yaml
├── template_sensors/
│   └── bambuddy_statistics_derived.yaml
├── dashboard_cards/
│   ├── statistics_overview.yaml
│   ├── statistics_insights.yaml
│   └── insights/
│       ├── chart_failure_reasons.yaml
│       ├── chart_failure_rate_trend.yaml
│       ├── chart_failures_by_filament_type.yaml
│       ├── chart_prints_by_filament_type.yaml
│       ├── chart_prints_by_printer.yaml
│       ├── failure_recent_summary.yaml
│       └── chart_time_accuracy_by_printer.yaml
└── dashboard_views/
    └── view_print_statistics.yaml

homeassistant/www/3d_printing/print_statistics/
└── print-statistics-failure-analysis-card.js
```

## Loader Domains

```yaml
# print_statistics_loader.yaml
automation: !include_dir_merge_list automations
sensor: !include_dir_merge_list rest_sensors
template: !include_dir_merge_list template_sensors
recorder:
    exclude:
        entities:
            - sensor.bambuddy_statistics_metrics
```

## Entity Reference

### REST Sensors

| Entity | Endpoint | Interval | State |
|---|---|---|---|
| `sensor.bambuddy_statistics` | `GET /api/v1/archives/stats` | 10 min | `total_prints` |
| `sensor.bambuddy_statistics_this_week` | `GET /api/v1/archives/stats?date_from=<monday>` | 15 min | `total_prints` |
| `sensor.bambuddy_statistics_this_month` | `GET /api/v1/archives/stats?date_from=<month_start>` | 30 min | `total_prints` |
| `sensor.bambuddy_failure_analysis` | `GET /api/v1/archives/analysis/failures` | 30 min | `failure_rate` |

> **OpenAPI note**: The endpoint is `/api/v1/archives/stats` (NOT `/api/v1/statistics`). No trailing slash needed (not a collection). Optional query params: `date_from`, `date_to` (YYYY-MM-DD format).

> **Failure-analysis contract note**: Bambuddy's failure-analysis payload already returns `failure_rate` as a percentage value and exposes `trend` plus `recent_failures`. HA should mirror that payload directly instead of multiplying the rate again or expecting a `weekly_trend` field.

Attributes from `ArchiveStats` schema:
- `total_prints`, `successful_prints`, `failed_prints`, `stopped_prints`
- `total_print_time_hours`, `total_filament_grams`, `total_cost`
- `prints_by_filament_type` (dict: `{"PLA": 800, "PETG": 300}`)
- `prints_by_printer` (dict: `{"1": 700, "2": 534}`)
- `average_time_accuracy`, `time_accuracy_by_printer`
- `total_energy_kwh`, `total_energy_cost`

> **NOT in API** (must be computed or approximated in HA): `success_rate_percent`, `prints_this_month`, `prints_this_week`, `avg_print_time_hours`, `most_used_filament`, `top_models`

### Template Sensors

| Entity | Source | Unit | Purpose |
|---|---|---|---|
| `sensor.bambuddy_success_rate` | **Computed**: `(successful_prints / total_prints * 100)` | % | Overall print success rate |
| `sensor.bambuddy_total_print_time` | `total_print_time_hours` | h | All-time print hours |
| `sensor.bambuddy_total_filament_used` | `total_filament_grams / 1000` | kg | All-time filament usage |
| `sensor.bambuddy_total_print_cost` | `total_cost` | $ | All-time print cost |
| `sensor.bambuddy_total_energy_used` | `total_energy_kwh` | kWh | All-time energy usage |
| `sensor.bambuddy_total_energy_cost` | `total_energy_cost` | $ | All-time energy cost |
| `sensor.bambuddy_average_time_accuracy` | `average_time_accuracy` | % | Fleet-level slicer estimate accuracy |
| `sensor.bambuddy_prints_this_week` | `sensor.bambuddy_statistics_this_week.state` | prints | Prints completed this week |
| `sensor.bambuddy_prints_this_month` | `sensor.bambuddy_statistics_this_month.state` | prints | Prints completed this month |
| `sensor.bambuddy_top_failure_reason` | `failures_by_reason` max key | text | Most common failure reason |
| `sensor.bambuddy_statistics_metrics` | Computed JSON attributes | n/a | Chart-ready attributes for the dashboard |

> **OpenAPI note — template sensor source corrections**:
> - `success_rate_percent` does NOT exist in `ArchiveStats`. Compute via Jinja: `{{ (attr.successful_prints / attr.total_prints * 100) | round(1) }}`
> - `total_filament_used_grams` → actual field is `total_filament_grams` (no `_used_`)
> - `prints_this_week` and `prints_this_month` do NOT exist as direct fields. The implemented package uses separate date-windowed stats sensors.
> - `failure_rate` from `GET /api/v1/archives/analysis/failures` is already a percent value; do not multiply it by 100 in HA.
> - failure analysis uses `trend` and `recent_failures`, not `weekly_trend`.
> - `stopped_prints`, `average_time_accuracy`, `time_accuracy_by_printer`, `total_energy_kwh`, `total_energy_cost`, `prints_by_filament_type`, and `prints_by_printer` are already surfaced in the first production slice.

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_event_stats_refresh` | `bambuddy_webhook_event` where event=`print_complete`, `print_failed`, or `print_stopped` | Refresh all-time, week, month, and failure-analysis sensors |

## Migration Notes

### Prototype Lineage
- **REST sensor**: `bambuddy_statistics` from the root `bambuddy/sensors.yaml` prototype
- **Template sensors**: prototype metrics from the root `bambuddy/sensors.yaml` were consolidated into `template_sensors/bambuddy_statistics_derived.yaml`
- **Dashboard card**: root `bambuddy/dashboards/statistics.yaml` prototype evolved into `dashboard_cards/statistics_overview.yaml` plus `dashboard_cards/statistics_insights.yaml`
- **Webhook handling**: stats refresh logic extracted from the root `bambuddy/automations/webhook_handler.yaml` prototype

### Changes from Current
- package now lives under the canonical `homeassistant/packages/3d_printing/print_statistics/` path and is enabled in `_feature_loaders.yaml`
- stats endpoint corrected from `/api/v1/statistics` to `/api/v1/archives/stats`
- time-windowed week and month totals now use dedicated REST sensors instead of nonexistent API fields
- failure-analysis data is now part of the live package via `sensor.bambuddy_failure_analysis`
- dashboard rendering is split into KPI overview and reusable insights charts rather than a single prototype card

## Dashboard Cards

### `statistics_overview.yaml`
Displays the first KPI slice:
- **Row 1**: Prints this week, this month, all-time totals
- **Row 2**: Success rate, filament used, print hours
- **Row 3**: print cost, energy cost, time accuracy
- **Outcome bar**: stacked bar for successful, failed, and stopped prints
- **Operational cards**: top failure reason, energy used, Bambuddy deep-link
- **Handoff card**: URL-aware filtered failure-analysis summary for Print History or other scoped launches

### `statistics_insights.yaml`
Displays the first reusable chart slice:
- prints by filament type
- prints by printer
- failure reasons
- time accuracy by printer
- failures by material
- recent failure summary with current versus prior trend bucket
- failure-rate trend line from Bambuddy week-bucket trend data

The current implementation only charts failure reasons. Trend and recent-failure payloads are now passed through in `sensor.bambuddy_failure_analysis` and `sensor.bambuddy_statistics_metrics` for the next failure-analysis card slice.

For interactive filtering beyond the default aggregate sensor window, use the Bambuddy integration response service `bambuddy.get_failure_analysis` or the matching websocket command instead of multiplying helper-bound REST sensors. The Statistics view now uses that websocket path in a dedicated custom card for Print History handoff scope.

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
| `custom:apex-direct-bar-card` | **Yes** | Reusable donut/bar chart rendering for insights |

## Related

- [printer_maintenance](../printer_maintenance/README.md) — Uses statistics data for maintenance health scoring (depends on this package for `sensor.bambuddy_statistics`)
- [advanced-features-design.md](advanced-features-design.md) — failure analysis, rolling windows, energy analytics, and per-printer efficiency follow-ons
- [../print_history/planning/metadata-implementation-roadmap.md](../print_history/planning/metadata-implementation-roadmap.md) — prerequisite roadmap for metadata-dependent analytics such as utilization, derived per-print cost truth, and spool-history crossover

## Recommended Next Steps

Recommended next phases after the now-shipped first slice:

1. **Phase B dashboard expansion**: add week and month trend charts, richer printer workload views, and the first material or color usage visuals that fit current data contracts.
2. **Issue-driven chart expansion**: add hours per week and month, color usage, and additional printer or outcome charts without introducing new metadata tables.
3. **Metadata-blocked analytics**: implement `archive_metric_summary` and `archive_spool_snapshots` before shipping utilization rate, per-print cost truth, energy-use-versus-print-time joins, or spool-history crossover reports.
4. **Rolling exception sensors**: add 7-day and 30-day sensors for recent anomaly detection once the base operational dashboard is stable.
5. **Filter-aware analytics**: extend the current URL-aware handoff card into broader scoped charts or controls through integration-side query surfaces rather than Layer 1 expansion.

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | **Trend charts are not shipped yet** — current package has KPI and first-slice comparison charts, but not week-over-week or month-over-month time series. | Next dashboard slice | No |
| 2 | **Metadata-dependent analytics remain deferred** — utilization, derived per-print cost truth, spool-history crossover, and some energy joins should wait for Variant 3 metadata work. | Phase sequencing | No |
| 3 | **Archive-filter-aware charts are only partially wired** — the handoff card supports scoped failure analysis, but the rest of the statistics view remains aggregate-focused. | Future integration work | No |
| 4 | **Experimental visuals remain optional** — treemaps, tag clouds, and iframe/embed workflows should be evaluated after the core stats view is stable. | UI backlog | No |
