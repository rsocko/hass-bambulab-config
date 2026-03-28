# Printer Maintenance — Bambuddy Maintenance Tracking in HA

## Overview

Reads printer maintenance status from Bambuddy's API, surfaces tasks due/overdue in HA dashboard cards and alerts, and allows marking tasks complete from HA. Replaces the current heuristic-based maintenance alerts (success rate thresholds, print count milestones) with Bambuddy's actual maintenance tracker.

**HA Role**: READ maintenance status from Bambuddy + SURFACE in dashboard + ALERT when tasks are due + WRITE task completion back to Bambuddy. Bambuddy is source of truth for maintenance schedules, intervals, and tracking — no local shadow counters.

## Package Structure

```
homeassistant/packages/3d_printing/printer_maintenance/
├── printer_maintenance_loader.yaml
├── automations/
│   ├── bambuddy_maintenance_due_alert.yaml           # due_count 0→>0 → persistent notification
│   └── bambuddy_event_maintenance_refresh.yaml       # webhook print events → refresh sensor
├── rest_commands/
│   └── bambuddy_complete_maintenance_task.yaml       # mark task done in Bambuddy
├── rest_sensors/
│   └── bambuddy_maintenance_status_sensor.yaml       # polls maintenance endpoint
├── scripts/
│   └── complete_maintenance_task.yaml                # calls REST command → refreshes sensor
├── template_sensors/
│   ├── maintenance_tasks_due_count.yaml
│   ├── maintenance_tasks_due_list.yaml
│   └── maintenance_health_score.yaml
├── helpers/
│   └── input_boolean/
│       └── input_boolean_bambuddy_maintenance_alerts_enabled.yaml
├── dashboard_cards/
│   ├── maintenance_due_section.yaml                  # chip for main view
│   ├── maintenance_catalog_card.yaml                 # full table with mark-complete
│   └── maintenance_health_card.yaml
└── dashboard_views/
    └── view_maintenance.yaml
```

## Loader Domains

```yaml
# printer_maintenance_loader.yaml
automation: !include_dir_merge_list automations
sensor: !include_dir_merge_list rest_sensors
rest_command: !include_dir_merge_named rest_commands
script: !include_dir_merge_named scripts
template: !include_dir_merge_list template_sensors
input_boolean: !include_dir_merge_named helpers/input_boolean
```

## Entity Reference

### REST Sensors

| Entity | Endpoint | Interval | State |
|---|---|---|---|
| `sensor.bambuddy_maintenance_status` | `GET /api/v1/printers/{id}/maintenance` (TBD) | 10 min | total task count or "ok"/"due" |

Expected attributes: list of maintenance tasks, each with:
- `task_id`, `name`, `description`
- `interval_prints` or `interval_hours` — how often it's due
- `last_completed_at` — timestamp of last completion
- `current_count` — prints/hours since last completion
- `is_due` — boolean: current_count ≥ interval
- `urgency` — how far overdue (percentage or count)

> **Open Item**: The Bambuddy wiki documents the maintenance feature but the REST API reference doesn't list explicit maintenance endpoints. The actual endpoint path needs to be discovered via the built-in API browser or testing. Likely candidates: `/api/v1/printers/{id}/maintenance` or `/api/v1/maintenance?printer_id={id}`.

### REST Commands

| Service | Method | Endpoint | Fields |
|---|---|---|---|
| `rest_command.bambuddy_complete_maintenance_task` | POST | `/api/v1/maintenance/{task_id}/complete` (TBD) | `task_id` |

> **Open Item**: Exact endpoint for marking a task complete needs discovery. Could be POST `/maintenance/{id}/complete`, PATCH `/maintenance/{id}`, or similar.

### Template Sensors (from REST attributes)

| Entity | Source | Purpose |
|---|---|---|
| `sensor.maintenance_tasks_due_count` | Count of tasks where `is_due=true` | Badge count for main view chip |
| `sensor.maintenance_tasks_due_list` | Filtered list of due tasks (names) | Text summary for notifications |
| `sensor.maintenance_health_score` | Derived from due counts and urgency | 0–100 health score for dashboard |

### Health Score Calculation

```
score = 100
For each task:
  if is_due:
    score -= 15 (per overdue task)
  elif current_count > interval * 0.8:
    score -= 5 (approaching due)
score = max(0, score)
```

Score ranges:
- 90–100: Excellent (green)
- 70–89: Good (no action needed)
- 50–69: Fair — check printer (orange)
- 0–49: Poor — maintenance needed (red)

### Scripts

| Script | Purpose |
|---|---|
| `script.complete_maintenance_task` | Calls REST command with `task_id` → refreshes maintenance sensor |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_maintenance_due_alert` | `sensor.maintenance_tasks_due_count` changes from 0 to >0 | Persistent notification listing due tasks |
| `bambuddy_event_maintenance_refresh` | `bambuddy_webhook_event` where event=`print_complete` or `print_failed` | Refresh maintenance sensor (counts may have changed) |

### Helpers

| Entity | Type | Purpose |
|---|---|---|
| `input_boolean.bambuddy_maintenance_alerts_enabled` | input_boolean | Enable/disable maintenance due notifications |

## Migration Notes

### Sources (from `bambuddy/`)
- **Maintenance alerts boolean**: `bambuddy_maintenance_alerts_enabled` from `bambuddy/helpers.yaml`
- **Dashboard card**: `bambuddy/dashboards/maintenance.yaml` → split into 3 cards

### Eliminated
- `bambuddy/automations/maintenance_alerts.yaml` — Replaced entirely. Old automation used heuristic thresholds (success rate < 80%, every 500 prints) against statistics. New package reads actual maintenance task data from Bambuddy's dedicated maintenance tracker.
- Maintenance checklist in old dashboard card (JavaScript hardcoded intervals like "clean nozzle every 50 prints") — replaced by Bambuddy's configurable maintenance schedules

### New (not in existing bambuddy/)
- REST sensor for actual maintenance status (not derived from statistics)
- REST command to mark tasks complete from HA
- `complete_maintenance_task` script (UI-callable from dashboard buttons)
- Health score template sensor
- Due count / due list template sensors
- Alert automation triggered by due_count state change (instead of time-based polling)
- 3 specialized dashboard cards (chip, catalog table, health)
- Dedicated maintenance view (`view_maintenance.yaml`)

## Dashboard Cards

### `maintenance_due_section.yaml` (Main View Chip)
Conditional chip for the main 3D printing view. Shows when `maintenance_tasks_due_count > 0`:
- Wrench icon with count badge
- Tapping navigates to the maintenance view

### `maintenance_catalog_card.yaml` (Full Catalog)
Table showing all maintenance tasks:
- Task name, interval, current count, last completed date
- Status indicator (due/ok/approaching)
- "Mark Complete" button per task → calls `script.complete_maintenance_task`

### `maintenance_health_card.yaml` (Health Overview)
Health score visualization:
- Score number with color-coded indicator
- Summary text ("Excellent", "Fair — check printer", etc.)
- Count of due vs total tasks

### `view_maintenance.yaml` (Dedicated View)
Full maintenance dashboard view assembling all 3 cards plus a link to Bambuddy's maintenance UI.

> **Note**: `view_maintenance.yaml` must be registered in `common/dashboards/_dashboards.yaml`.

## Dependencies

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [bambuddy_common](../bambuddy_common/README.md) | **Yes** | API config helpers, webhook event source |
| [print_statistics](../print_statistics/README.md) | **Yes** | `sensor.bambuddy_statistics` attributes (total_prints, etc.) used in health dashboard context |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Maintenance API |
| [button-card](https://github.com/custom-cards/button-card) (HACS) | **Yes** | Dashboard card rendering |

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | **Discover maintenance API endpoints** — Bambuddy wiki documents the feature but REST API reference doesn't list explicit endpoints. Need to test with the built-in API browser. | Cannot implement REST sensor or REST command without endpoint paths | **Yes — blocking for Phase 5 implementation** |
| 2 | Maintenance task schema — need to confirm attribute names (`task_id`, `name`, `interval_prints`, `is_due`, `last_completed_at`, etc.) | Template sensors depend on correct attribute names | **Yes — blocking for template sensors** |
| 3 | Mark-complete endpoint — need to confirm method (POST vs PATCH) and path | REST command depends on this | **Yes — blocking for REST command** |
| 4 | View registration — `view_maintenance.yaml` must be added to `common/dashboards/_dashboards.yaml` | View won't appear in dashboard navigation without this | No — done during wiring |

### Unblocking Strategy

Before starting Phase 5 implementation:
1. Open Bambuddy's built-in API browser (accessible at `http://bambuddy:8000/api/docs` or similar)
2. Find the maintenance-related endpoints
3. Test a GET request to understand the response schema
4. Test a POST/PATCH to mark a task complete
5. Update this document with the actual endpoints and schema
