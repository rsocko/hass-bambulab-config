# Print Queue — Bambuddy Queue in HA

> **⚠️ OpenAPI Corrections Needed**: See [openapi-correction-notes.md](/docs/repo/reference/openapi-correction-notes.md) for full cross-reference. Key issues: trailing slash on queue URLs, flat array response (not dict wrapper), `add` REST command uses `archive_id`/`library_file_id` (not `file_id`/`copies`), delete uses `item_id` (not `job_id`).

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
| `sensor.bambuddy_print_queue` | `GET /api/v1/queue/` | 60s | Flat array — count via `value_json \| count` |

> **OpenAPI note**: Queue returns `PrintQueueItemResponse[]` flat array (NOT `{jobs, total}` wrapper). Trailing slash required. State value: `value_json | count`. Filter params: `printer_id`, `status`.

State value: number of jobs in queue.

### REST Commands

| Service | Method | Endpoint | Fields |
|---|---|---|---|
| `rest_command.bambuddy_queue_add` | POST | `/api/v1/queue/` | `archive_id` OR `library_file_id`, `printer_id`, `ams_mapping`, `plate_id`, `bed_levelling`, `use_ams`, etc. |
| `rest_command.bambuddy_queue_remove` | DELETE | `/api/v1/queue/{item_id}` | `item_id` |

> **OpenAPI note**: `POST /api/v1/queue/` uses `PrintQueueItemCreate` schema — **no `file_id` or `copies` fields**. Use `archive_id` (for archived prints) or `library_file_id` (for library files). For multiple copies, add the same item multiple times. DELETE uses `item_id` not `job_id`.

### Template Sensors

| Entity | Source | Purpose |
|---|---|---|
| `sensor.bambuddy_queue_count` | `sensor.bambuddy_print_queue` state | Friendly queue count with unit "jobs" |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_event_queue_refresh` | `bambuddy_webhook_event` where event=`queue_ready` | `homeassistant.update_entity` on queue sensor |

## Migration Notes

### Prototype Lineage
- **REST sensor**: `bambuddy_print_queue` from the root `bambuddy/sensors.yaml` prototype
- **REST commands**: `bambuddy_queue_add`, `bambuddy_queue_remove` from the root `bambuddy/rest_commands.yaml` prototype
- **Template sensor**: `bambuddy_queue_count` from the root `bambuddy/sensors.yaml` prototype
- **Dashboard card**: root `bambuddy/dashboards/queue.yaml` prototype evolved into `dashboard_cards/queue.yaml`
- **Webhook handler**: queue-specific logic extracted from the root `bambuddy/automations/webhook_handler.yaml` prototype

### Changes from Current
- Webhook handling: Instead of inline `if event == queue_ready` in monolithic webhook handler, this package listens to the `bambuddy_webhook_event` HA event fired by `bambuddy_common`
- No new entities or functionality — this is a clean extraction

## Mockups

Self-contained HTML mockups for proposed UI evolutions live under
[`mockups/`](/docs/features/print_queue/mockups/index.html):

- [`kanban-board.html`](/docs/features/print_queue/mockups/kanban-board.html) — adds a Kanban view mode
  (columns per state) with drag-and-drop state changes, a per-state color
  palette applied subtly to cards in both list and kanban views, and a
  prominent **Time Remaining** hero tile that excludes plates already marked
  `done`. The original list-style queue mockup remains under
  [`docs/features/model_catalog/design/mockups/production-queue.html`](/docs/features/model_catalog/design/mockups/production-queue.html);
  rationale for the underlying data model lives in
  [`unified-queue.md`](/docs/features/model_catalog/design/unified-queue.md).

## Dashboard Cards

### `queue.yaml`
Displays the current print queue:
- Header with queue count badge
- Job list with position numbers, names, status icons, printer name
- Empty state message when queue is empty
- Link to manage queue in Bambuddy's web UI

## Advanced Design

- [advanced-features-design.md](/docs/features/print_queue/design/advanced-features-design.md) — queue lifecycle controls, camera-gated auto-start, reprint flows, and fleet-aware queue behavior

## Scope Decision After API Review

The live OpenAPI review changed the recommendation for this package:

- **Promote into near-core Phase 3**: queue lifecycle commands for `start`, `stop`, `cancel`, item `PATCH`, `reorder`, and `bulk` updates. The queue card is materially underpowered without them.
- **Keep as advanced**: plate-clear verified auto-start and reprint preflight. Both are high-value, but they depend on camera calibration and print-history context.

## Dependencies

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [bambuddy_common](/docs/features/bambuddy_common/README.md) | **Yes** | API config helpers, webhook event source |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Queue API |
| [button-card](https://github.com/custom-cards/button-card) (HACS) | **Yes** | Dashboard card rendering |

## Open Items

| # | Item | Impact |
|---|---|---|
| 1 | Rewrite REST sensor to handle flat array response (`value_json \| count` for state) | Blocking for Phase 3 implementation |
| 2 | Rewrite `bambuddy_queue_add` REST command body to use `PrintQueueItemCreate` schema | Blocking for queue add functionality |
| 3 | Additional queue endpoints available: cancel, stop, start, reorder, bulk update — **recommended for Phase 3 core scope**, not long-tail enhancement | High-value scope adjustment |
