# Print Statistics — Bambuddy Stats in HA

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
| `sensor.bambuddy_statistics` | `GET /api/v1/statistics` | 10 min | `total_prints` |

Attributes: `total_prints`, `successful_prints`, `failed_prints`, `cancelled_prints`, `total_print_time_hours`, `total_filament_used_grams`, `success_rate_percent`, `prints_this_month`, `prints_this_week`, `avg_print_time_hours`, `most_used_filament`, `top_models`

### Template Sensors

| Entity | Source Attribute | Unit | Purpose |
|---|---|---|---|
| `sensor.bambuddy_success_rate` | `success_rate_percent` | % | Overall print success rate |
| `sensor.bambuddy_total_print_time` | `total_print_time_hours` | h | All-time print hours |
| `sensor.bambuddy_total_filament_used` | `total_filament_used_grams` | g | All-time filament usage |
| `sensor.bambuddy_prints_this_week` | `prints_this_week` | prints | Prints completed this week |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_event_stats_refresh` | `bambuddy_webhook_event` where event=`print_complete` or `print_failed` | `homeassistant.update_entity` on statistics sensor |

## Migration Notes

### Sources (from `bambuddy/`)
- **REST sensor**: `bambuddy_statistics` from `bambuddy/sensors.yaml`
- **Template sensors**: 4 derived sensors from `bambuddy/sensors.yaml` (converted to modern `template:` format)
- **Dashboard card**: `bambuddy/dashboards/statistics.yaml` → `dashboard_cards/statistics.yaml`
- **Webhook handling**: Stats refresh logic extracted from `bambuddy/automations/webhook_handler.yaml`

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

## Open Items

None — this is a straightforward extraction with no design gaps.
