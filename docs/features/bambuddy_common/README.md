# Bambuddy Common — Shared API Infrastructure

> **Status**: Implemented (Phase 1 complete)
> **Package path**: `homeassistant/packages/3d_printing/bambuddy_common/`
> **Loader**: `bambuddy_common_loader.yaml` (commented-out in `_feature_loaders.yaml` — uncomment to activate)

## Overview

Shared infrastructure for all Bambuddy feature packages. Provides API configuration helpers, a unified webhook receiver, MQTT-based printer status sensor, and a printer-level REST command. All other Bambuddy packages depend on this package.

**HA Role**: Configuration layer — holds API base URL/printer ID, fires normalized events from Bambuddy webhooks, and subscribes to Bambuddy's MQTT status topic for real-time printer state. Archive-specific commands (photo upload, delete, cover, enrichment) live in `print_history`.

## Related Design Notes

- [Archive Binding And Potential PostgreSQL Migration Guidance](planning/archive-binding-and-postgres-guidance.md)
- [Print History Photo Capture Design](../print_history/design/ui-media/photo-capture-design.md)
- [Print History Runtime Repair Sidecar API Draft](../print_history/reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md)

## Is Webhook Required?

Not for every Bambuddy-related feature.

- If you only need archive browsing and basic archive API access, webhook is not required.
- If you only need in-progress start/mid/near-complete photo capture on a single printer, webhook is also not strictly required, because `print_history` can fall back to querying the newest archive and matching it to the active task name.
- If you want the full current shipped `print_history` lifecycle, webhook is still required in the present design because several automations only listen to `bambuddy_webhook_event`.

In other words, webhook is optional for reduced archive-API-driven operation, but it remains the current event transport for start, finish, failure, stop, enrichment, and immediate refresh behaviors.

## Package Structure

```
homeassistant/packages/3d_printing/bambuddy_common/
├── bambuddy_common_loader.yaml
├── automations/
│   └── bambuddy_webhook_receiver.yaml       # webhook → fires bambuddy_webhook_event
├── mqtt_sensors/
│   └── bambuddy_printer_status.yaml         # MQTT subscription → real-time status
├── rest_commands/
│   └── bambuddy_refresh_printer_status.yaml
└── helpers/
    ├── input_boolean/
    │   └── input_boolean_bambuddy_integration_enabled.yaml
    └── input_text/
        ├── input_text_bambuddy_api_base_url.yaml
        └── input_text_bambuddy_printer_id.yaml
```

> **Secrets**: The API key is stored in `secrets.yaml` as `bambuddy_api_key` — **not** as an `input_text` entity. All REST sensors and commands reference it via `!secret bambuddy_api_key`. This keeps the key out of HA state/history and avoids accidental exposure in dashboards or logs.

## Loader Domains

```yaml
# bambuddy_common_loader.yaml
automation: !include_dir_merge_list automations
mqtt:
  sensor: !include_dir_merge_list mqtt_sensors
rest_command: !include_dir_merge_named rest_commands
input_boolean: !include_dir_merge_named helpers/input_boolean
input_text: !include_dir_merge_named helpers/input_text
```

## Entity Reference

### Input Helpers

| Entity | Type | Purpose | Source |
|---|---|---|---|
| `input_text.bambuddy_api_base_url` | input_text | Bambuddy server URL (e.g., `http://localhost:8000`) | root `bambuddy/` prototype lineage |
| `input_text.bambuddy_printer_id` | input_text | Bambuddy printer ID | root `bambuddy/` prototype lineage |
| `input_boolean.bambuddy_integration_enabled` | input_boolean | Master on/off switch | root `bambuddy/` prototype lineage |

### Secrets (secrets.yaml)

| Key | Purpose |
|---|---|
| `bambuddy_api_key` | API key for Bambuddy authentication — used in all REST sensor/command headers via `!secret` |

### MQTT Sensors

| Entity | Topic | Update Rate | Source |
|---|---|---|---|
| `sensor.bambuddy_printer_status` | `bambuddy/printers/{serial}/status` | ~1/sec (retained) | Bambuddy MQTT Publishing |

Attributes (auto-extracted from full JSON payload): `printer_id`, `printer_name`, `printer_serial`, `timestamp`, `connected`, `state`, `current_print`, `subtask_name`, `gcode_file`, `progress`, `remaining_time`, `layer_num`, `total_layers`, `temperatures` (nested: bed, bed_target, nozzle, nozzle_target, chamber), `wifi_signal`, `chamber_light`, `speed_level`, `cooling_fan_speed`, `big_fan1_speed`, `big_fan2_speed`, `cover_url`, `hms_errors`, `ams`

> **Prerequisites**: Bambuddy MQTT Publishing must be enabled (Settings → Network → MQTT Publishing) and pointed at the same Mosquitto broker HA uses. See [Bambuddy MQTT Setup](#bambuddy-mqtt-setup) below.

### REST Commands

| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_refresh_printer_status` | POST | `/api/v1/printers/{id}/refresh-status` | Force printer status refresh |

> **Note**: Archive-specific REST commands (photo upload, photo delete, set cover, update archive, add tags) live in `print_history/rest_commands/`. See [print_history README](../print_history/README.md).

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_webhook_receiver` | Webhook at `/api/webhook/bambuddy_events` | Normalizes payload → fires `bambuddy_webhook_event` HA event |

## Webhook Receiver Design

The webhook receiver exists to provide exact lifecycle timing and archive association to downstream packages. It is not the only way HA can learn about Bambuddy data, but it is the only current source for several event-driven automations.

### Two Webhook Formats

Bambuddy has two webhook payload formats:

**1. Notifications webhook (flat)** — used by human-readable notification providers:
```json
{
  "event": "print_finished",
  "print_name": "Benchy",
  "printer_name": "Workshop X1C",
  "status": "success"
}
```

**2. API webhook (structured)** — includes `data` object with `archive_id`:
```json
{
  "event": "print_complete",
  "data": {
    "archive_id": 42,
    "printer_id": 1,
    "name": "Benchy",
    "status": "success"
  }
}
```

### Normalization Strategy

The receiver extracts fields from whichever format it receives and fires a consistent HA event:

```yaml
event_type: bambuddy_webhook_event
event_data:
  event: "print_complete"        # normalized event name
  archive_id: "42"               # from data.archive_id or "" if flat format
  print_name: "Benchy"           # from data.name or top-level print_name
  printer_name: "Workshop X1C"   # from data.printer_name or top-level printer_name
  status: "success"              # from data.status or top-level status
  raw_payload: { ... }           # full original payload preserved
```

> **Current conclusion**: the generic custom webhook path can send flattened top-level fields that are still useful for event normalization, but it does not reliably solve archive binding. Keep the receiver tolerant of both shapes. Treat `archive_id` in payload as the exact path when present, and keep API fallback for operational archive resolution when it is absent.

### Current Practical Value

Without webhook, the system can still answer "what is the most recent archive?" from `GET /archives` and can often infer the current running print's archive in a single-printer setup. With webhook, the system gains an explicit event stream that tells HA when to initialize per-print runtime state and when to run post-print actions immediately.

## Migration Notes

### Prototype Lineage
- **Helpers**: Originated in the root `bambuddy/helpers.yaml` prototype (2 input_text + 1 input_boolean). API key moved to `secrets.yaml` instead of an entity.
- **Printer Status sensor**: Prototype started as a REST sensor polling every 30s; migrated to MQTT subscription (`bambuddy/printers/{serial}/status`) for real-time updates
- **Refresh command**: Prototype lineage from `bambuddy/rest_commands.yaml` (`bambuddy_refresh_printer_status`)
- **Webhook receiver**: Replaces the old prototype logic in `bambuddy/automations/webhook_handler.yaml` with normalized HA events

### Eliminated
- `bambuddy_create_archive` REST command — Bambuddy auto-creates archives at print start; HA no longer creates them
- `input_text.bambuddy_api_key` — replaced by `!secret bambuddy_api_key` in `secrets.yaml`

### Moved to `print_history`
- `bambuddy_upload_photo_to_archive` REST command — archive-specific, not shared infrastructure
- `bambuddy_delete_archive_photo` REST command — archive-specific (photo review)
- `bambuddy_set_archive_cover` REST command — archive-specific (photo review)

## Dependencies

### External
| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Self-hosted print archive server |
| Mosquitto MQTT broker | **Yes** | Bambuddy publishes printer state; HA subscribes via MQTT integration |

### Downstream (packages that depend on this)
- `print_history` (Phase 2)
- `print_queue` (Phase 3)
- `print_statistics` (Phase 4)
- `printer_maintenance` (Phase 5)

## Bambuddy MQTT Setup

Bambuddy publishes printer events and real-time status to an MQTT broker. HA subscribes via the built-in MQTT integration (auto-configured by the Mosquitto addon).

### Bambuddy Settings → Network → MQTT Publishing

| Setting | Value | Notes |
|---|---|---|
| Enable MQTT | **On** | |
| Broker Hostname | `192.168.1.5` | HA IP address (Mosquitto runs on HA) |
| Port | `1883` | Default non-TLS |
| Username | *(HA user)* | Mosquitto addon uses HA user credentials |
| Password | *(HA password)* | Same password as the HA user |
| Topic Prefix | `bambuddy` | Default — matches `state_topic` in sensor YAML |
| Use TLS | **Off** | Local network; no TLS needed |

> **Tip**: Create a dedicated HA user (e.g., `bambuddy_mqtt`) with minimal permissions for MQTT auth rather than using your admin account.

### Verification

1. Open **MQTT Explorer** addon in HA (Settings → Add-ons → MQTT Explorer)
2. Connect to `192.168.1.5:1883` with the same credentials
3. Confirm topic `bambuddy/printers/{serial}/status` appears with retained JSON payload
4. In HA, check `sensor.bambuddy_mqtt_printer_status` for state and attributes

### Available MQTT Topics

| Topic | Retained | Purpose |
|---|---|---|
| `bambuddy/status` | Yes | Bambuddy online/offline |
| `bambuddy/printers/{serial}/status` | Yes | Real-time printer state (~1/sec) |
| `bambuddy/printers/{serial}/print/started` | No | Print job started |
| `bambuddy/printers/{serial}/print/completed` | No | Print completed |
| `bambuddy/printers/{serial}/print/failed` | No | Print failed |
| `bambuddy/printers/{serial}/ams/changed` | No | AMS filament changed |
| `bambuddy/queue/*` | No | Queue events (job_added, job_started, job_completed) |
| `bambuddy/maintenance/*` | No | Maintenance alerts and resets |
| `bambuddy/archive/*` | No | Archive created/updated |

> Future phases will subscribe to event topics (print/started, archive/created, etc.) for automations.

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | Decide whether full print-history lifecycle should remain webhook-triggered or be refactored further toward native or API-driven triggers | Affects how much webhook remains a hard dependency for finish, failure, enrichment, and immediate refresh flows | No |
| 2 | Keep potential upstream PostgreSQL migration scoped to Bambuddy or repair-sidecar boundaries rather than HA automations or the HA local cache | Avoids coupling HA feature logic to upstream DB engine changes | No |
| 3 | Clean up orphaned `sensor.bambuddy_printer_status` REST entity after deploy | Old REST entity stays in registry as unavailable; delete from Settings → Entities | No |
