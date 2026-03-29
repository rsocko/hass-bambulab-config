# Printer Maintenance — Bambuddy Maintenance Tracking in HA

> **⚠️ UNBLOCKED**: Maintenance API endpoints have been discovered in the OpenAPI spec (Bambuddy v0.2.2.2). See [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for full cross-reference. All 4 blocking open items are now resolved.

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
| `sensor.bambuddy_maintenance_status` | `GET /api/v1/maintenance/printers/{printer_id}` | 10 min | `due_count` |

> **OpenAPI note**: Endpoint is `/api/v1/maintenance/printers/{printer_id}` (NOT `/printers/{id}/maintenance`). Returns `PrinterMaintenanceOverview` schema. Also available: `GET /api/v1/maintenance/overview` returns `PrinterMaintenanceOverview[]` for ALL printers.

Response schema — `PrinterMaintenanceOverview`:
```json
{
  "printer_id": 1,
  "printer_name": "Workshop P1S",
  "printer_model": "P1S",
  "total_print_hours": 500.5,
  "maintenance_items": [/* MaintenanceStatus[] */],
  "due_count": 2,
  "warning_count": 1
}
```

Each `MaintenanceStatus` item in `maintenance_items[]`:
```json
{
  "id": 42,
  "printer_id": 1,
  "printer_name": "Workshop P1S",
  "printer_model": "P1S",
  "maintenance_type_id": 3,
  "maintenance_type_name": "Nozzle Cleaning",
  "maintenance_type_icon": "mdi:spray",
  "maintenance_type_wiki_url": "https://...",
  "enabled": true,
  "interval_hours": 100.0,
  "interval_type": "hours",
  "current_hours": 145.2,
  "hours_since_maintenance": 45.2,
  "hours_until_due": -5.2,
  "days_since_maintenance": 3.5,
  "days_until_due": -0.5,
  "is_due": true,
  "is_warning": false,
  "last_performed_at": "2026-03-20T10:00:00"
}
```

> **Key design impact**: Maintenance is tracked in **hours** (or days via `interval_type`), NOT print count. There is no `interval_prints` or `current_count` — all intervals are time-based. The health score calculation must use `is_due`/`is_warning` booleans and `hours_until_due` (negative when overdue).

### REST Commands

| Service | Method | Endpoint | Fields |
|---|---|---|---|
| `rest_command.bambuddy_complete_maintenance_task` | POST | `/api/v1/maintenance/items/{item_id}/perform` | `item_id`, `notes` (optional) |

> **OpenAPI note**: Endpoint is `/api/v1/maintenance/items/{item_id}/perform` (NOT `/maintenance/{task_id}/complete`). Accepts optional body `PerformMaintenanceRequest: {"notes": "Cleaned with brass brush"}`. Returns the updated `MaintenanceStatus` object.

Additional maintenance REST commands available:
| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_update_maintenance_item` | PATCH | `/api/v1/maintenance/items/{item_id}` | Update interval, enabled state |
| `rest_command.bambuddy_assign_maintenance_type` | POST | `/api/v1/maintenance/printers/{printer_id}/assign/{type_id}` | Assign a maintenance type to a printer |

### Template Sensors (from REST attributes)

| Entity | Source | Purpose |
|---|---|---|
| `sensor.maintenance_tasks_due_count` | `due_count` from `PrinterMaintenanceOverview` | Badge count for main view chip |
| `sensor.maintenance_tasks_due_list` | Filtered `maintenance_items` where `is_due=true` (names) | Text summary for notifications |
| `sensor.maintenance_health_score` | Derived from `is_due`/`is_warning` counts | 0–100 health score for dashboard |

> **OpenAPI note**: The `PrinterMaintenanceOverview` response already provides `due_count` and `warning_count` directly — no need to count items manually in Jinja. The `maintenance_tasks_due_list` still needs to filter `maintenance_items[]` where `is_due == true` for task names.

### Health Score Calculation

> **Redesigned**: Uses hours-based `is_due`/`is_warning` booleans from the API instead of count-based intervals.

```
score = 100
For each item in maintenance_items:
  if is_due:
    score -= 15 (per overdue task)
  elif is_warning:
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
- Task name (`maintenance_type_name`), interval (`interval_hours` / `interval_type`), hours since last (`hours_since_maintenance`), last performed date (`last_performed_at`)
- Status indicator: `is_due` (red), `is_warning` (orange), normal (green)
- Wiki link icon (if `maintenance_type_wiki_url` is set)
- "Mark Complete" button per task → calls `script.complete_maintenance_task` with `item_id`

### `maintenance_health_card.yaml` (Health Overview)
Health score visualization:
- Score number with color-coded indicator
- Summary text ("Excellent", "Fair — check printer", etc.)
- Count of due vs total tasks

### `view_maintenance.yaml` (Dedicated View)
Full maintenance dashboard view assembling all 3 cards plus a link to Bambuddy's maintenance UI.

> **Note**: `view_maintenance.yaml` must be registered in `common/dashboards/_dashboards.yaml`.

## Advanced Design

- [advanced-features-design.md](advanced-features-design.md) — fleet summary, maintenance history, custom types, calibration suggestions, policy tuning, and wiki-guided exception flows

## Scope Decision After API Review

The live maintenance API supports a bit more low-risk value than the original base plan assumed.

- **Promote into near-core Phase 5**: add read-only fleet summary data from `/maintenance/summary` or `/maintenance/overview` so the package can surface cross-printer due counts without waiting for later phases.
- **Keep as advanced**: policy tuning writes, defaults recovery, history drilldown, and custom maintenance-type creation. Those are useful, but they add more admin surface area and confirmation requirements.

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
| 1 | ~~**Discover maintenance API endpoints**~~ | ~~Cannot implement REST sensor~~ | **RESOLVED** — endpoints found in OpenAPI spec v0.2.2.2. See correction notes above. |
| 2 | ~~**Maintenance task schema**~~ | ~~Template sensors depend on correct names~~ | **RESOLVED** — `MaintenanceStatus` and `PrinterMaintenanceOverview` schemas fully documented above. |
| 3 | ~~**Mark-complete endpoint**~~ | ~~REST command depends on this~~ | **RESOLVED** — `POST /api/v1/maintenance/items/{item_id}/perform` with optional `{"notes": "..."}` body. |
| 4 | **View registration** — `view_maintenance.yaml` must be added to `common/dashboards/_dashboards.yaml` | View won't appear in dashboard navigation without this | No — done during wiring |
| 5 | **Health score uses hours, not counts** — the design assumed `interval_prints`/`current_count` but the API tracks in hours. The `is_due`/`is_warning` booleans simplify the calculation. | Health score template redesign | No — simpler implementation |
| 6 | **`interval_type` can be "hours" or "days"** — some tasks may use day-based intervals. Template should display the correct unit. | Display logic | No — minor |
| 7 | **Maintenance history** — `GET /api/v1/maintenance/items/{item_id}/history` returns `MaintenanceHistoryResponse[]`. Could surface a "last 5 completions" list per task. | Enhancement opportunity | No |
| 8 | **All-printers overview available** — `GET /api/v1/maintenance/overview` returns data for all printers at once. If multiple printers are tracked, a single REST sensor could pull all maintenance data. | Multi-printer support | No — enhancement |

### ~~Unblocking Strategy~~ — COMPLETE

All maintenance API endpoints confirmed via OpenAPI spec. Phase 5 can proceed immediately.

**Full maintenance endpoint list:**
| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/maintenance/types` | List all maintenance types |
| `POST` | `/api/v1/maintenance/types` | Create custom type |
| `GET` | `/api/v1/maintenance/printers/{printer_id}` | Per-printer overview |
| `GET` | `/api/v1/maintenance/overview` | All-printers overview |
| `POST` | `/api/v1/maintenance/items/{item_id}/perform` | Mark as performed |
| `GET` | `/api/v1/maintenance/items/{item_id}/history` | Task completion history |
| `PATCH` | `/api/v1/maintenance/items/{item_id}` | Update item (interval, enabled) |
| `DELETE` | `/api/v1/maintenance/items/{item_id}` | Remove item |
| `POST` | `/api/v1/maintenance/printers/{printer_id}/assign/{type_id}` | Assign type to printer |
| `GET` | `/api/v1/maintenance/summary` | Cross-printer summary |
| `PATCH` | `/api/v1/maintenance/printers/{printer_id}/hours` | Set total print hours |
| `POST` | `/api/v1/maintenance/types/restore-defaults` | Restore default types |
