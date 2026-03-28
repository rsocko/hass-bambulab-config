# Print Queue — Bambuddy Queue in HA

## Overview

Surfaces Bambuddy's print queue in HA as a REST sensor and dashboard card. Provides queue management REST commands (add/remove jobs) and auto-refreshes on webhook events.

**HA Role**: READ queue state + SURFACE in dashboard + MANAGE via REST commands. Bambuddy owns queue ordering, scheduling, and multi-printer dispatch.

## Package Structure

```
homeassistant/packages/3d_printing/print_queue/
├── print_queue_loader.yaml
├── automations/
│   └── bambuddy_event_queue_refresh.yaml
├── rest_commands/
│   ├── bambuddy_queue_add.yaml
│   └── bambuddy_queue_remove.yaml
├── rest_sensors/
│   └── bambuddy_print_queue_sensor.yaml
├── template_sensors/
│   └── bambuddy_queue_count.yaml
└── dashboard_cards/
    └── queue.yaml
```

## Loader Domains

```yaml
# print_queue_loader.yaml
automation: !include_dir_merge_list automations
sensor: !include_dir_merge_list rest_sensors
rest_command: !include_dir_merge_named rest_commands
template: !include_dir_merge_list template_sensors
```

## Entity Reference

### REST Sensors

| Entity | Endpoint | Interval | Attributes |
|---|---|---|---|
| `sensor.bambuddy_print_queue` | `GET /api/v1/queue` | 60s | `jobs`, `total` |

State value: number of jobs in queue.

### REST Commands

| Service | Method | Endpoint | Fields |
|---|---|---|---|
| `rest_command.bambuddy_queue_add` | POST | `/api/v1/queue` | `file_id`, `printer_id` (default from helper), `copies` (default 1) |
| `rest_command.bambuddy_queue_remove` | DELETE | `/api/v1/queue/{job_id}` | `job_id` |

### Template Sensors

| Entity | Source | Purpose |
|---|---|---|
| `sensor.bambuddy_queue_count` | `sensor.bambuddy_print_queue` state | Friendly queue count with unit "jobs" |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_event_queue_refresh` | `bambuddy_webhook_event` where event=`queue_ready` | `homeassistant.update_entity` on queue sensor |

## Migration Notes

### Sources (from `bambuddy/`)
- **REST sensor**: `bambuddy_print_queue` from `bambuddy/sensors.yaml`
- **REST commands**: `bambuddy_queue_add`, `bambuddy_queue_remove` from `bambuddy/rest_commands.yaml`
- **Template sensor**: `bambuddy_queue_count` from `bambuddy/sensors.yaml`
- **Dashboard card**: `bambuddy/dashboards/queue.yaml` → `dashboard_cards/queue.yaml`
- **Webhook handler**: Queue-specific logic extracted from `bambuddy/automations/webhook_handler.yaml`

### Changes from Current
- Webhook handling: Instead of inline `if event == queue_ready` in monolithic webhook handler, this package listens to the `bambuddy_webhook_event` HA event fired by `bambuddy_common`
- No new entities or functionality — this is a clean extraction

## Dashboard Cards

### `queue.yaml`
Displays the current print queue:
- Header with queue count badge
- Job list with position numbers, names, status icons, printer name
- Empty state message when queue is empty
- Link to manage queue in Bambuddy's web UI

## Dependencies

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [bambuddy_common](../bambuddy_common/README.md) | **Yes** | API config helpers, webhook event source |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Queue API |
| [button-card](https://github.com/custom-cards/button-card) (HACS) | **Yes** | Dashboard card rendering |

## Open Items

None — this is a straightforward extraction with no design gaps.
