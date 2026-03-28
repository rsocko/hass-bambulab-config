# Bambuddy Common — Shared API Infrastructure

> **Status**: Implemented (Phase 1 complete)
> **Package path**: `homeassistant/packages/3d_printing/bambuddy_common/`
> **Loader**: `bambuddy_common_loader.yaml` (commented-out in `_feature_loaders.yaml` — uncomment to activate)

## Overview

Shared infrastructure for all Bambuddy feature packages. Provides API configuration helpers, a unified webhook receiver, printer status sensor, and shared REST commands. All other Bambuddy packages depend on this package.

**HA Role**: Configuration layer — holds API credentials, fires normalized events from Bambuddy webhooks, and provides the photo upload command shared by `print_history`.

## Package Structure

```
homeassistant/packages/3d_printing/bambuddy_common/
├── bambuddy_common_loader.yaml
├── automations/
│   └── bambuddy_webhook_receiver.yaml       # webhook → fires bambuddy_webhook_event
├── rest_commands/
│   ├── bambuddy_refresh_printer_status.yaml
│   ├── bambuddy_upload_photo_to_archive.yaml
│   ├── bambuddy_delete_archive_photo.yaml        # DELETE photo (used by photo review)
│   └── bambuddy_set_archive_cover.yaml           # PATCH archive cover (used by photo review)
├── rest_sensors/
│   └── bambuddy_printer_status.yaml
└── helpers/
    ├── input_boolean/
    │   └── input_boolean_bambuddy_integration_enabled.yaml
    └── input_text/
        ├── input_text_bambuddy_api_base_url.yaml
        └── input_text_bambuddy_printer_id.yaml
```

> **Secrets**: The API key is stored in `secrets.yaml` as `bambuddy_api_key` (not as an entity). All REST sensors/commands reference it via `!secret bambuddy_api_key`.

## Loader Domains

```yaml
# bambuddy_common_loader.yaml
automation: !include_dir_merge_list automations
sensor: !include_dir_merge_list rest_sensors
rest_command: !include_dir_merge_named rest_commands
input_boolean: !include_dir_merge_named helpers/input_boolean
input_text: !include_dir_merge_named helpers/input_text
```

## Entity Reference

### Input Helpers

| Entity | Type | Purpose | Source |
|---|---|---|---|
| `input_text.bambuddy_api_base_url` | input_text | Bambuddy server URL (e.g., `http://localhost:8000`) | bambuddy/helpers.yaml |
| `input_text.bambuddy_printer_id` | input_text | Bambuddy printer ID | bambuddy/helpers.yaml |
| `input_boolean.bambuddy_integration_enabled` | input_boolean | Master on/off switch | bambuddy/helpers.yaml |

### Secrets (secrets.yaml)

| Key | Purpose |
|---|---|
| `bambuddy_api_key` | API key for Bambuddy authentication — used in all REST sensor/command headers via `!secret` |

### REST Sensors

| Entity | Endpoint | Interval | Source |
|---|---|---|---|
| `sensor.bambuddy_printer_status` | `GET /api/v1/printers/{id}/status` | 30s | bambuddy/sensors.yaml |

Attributes: `status`, `current_print`, `maintenance`, `error`, `nozzle_temp`, `bed_temp`, `chamber_temp`, `print_progress`, `time_remaining_minutes`, `fan_speed`, `filament`

### REST Commands

| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_refresh_printer_status` | POST | `/api/v1/printers/{id}/refresh-status` | Force printer status refresh |
| `rest_command.bambuddy_upload_photo_to_archive` | POST | `/api/v1/archives/{archive_id}/photos` | Upload photo to archive |
| `rest_command.bambuddy_delete_archive_photo` | DELETE | `/api/v1/archives/{archive_id}/photos/{photo_id}` | Delete a photo from archive (used by photo review) |
| `rest_command.bambuddy_set_archive_cover` | PATCH | `/api/v1/archives/{archive_id}` | Set cover photo for archive thumbnail (used by photo review) |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_webhook_receiver` | Webhook at `/api/webhook/bambuddy_events` | Normalizes payload → fires `bambuddy_webhook_event` HA event |

## Webhook Receiver Design

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

> **Open Item**: Need to confirm which format HA receives when configured as "Webhook (Custom)" provider in Bambuddy settings. The receiver handles both formats, but the primary path (archive_id from payload) only works with the API format. If flat format is received, downstream features use the fallback archive_id lookup.

## Migration Notes

### Sources
- **Helpers**: Extracted from `bambuddy/helpers.yaml` (3 input_text + 1 input_boolean — shared subset only)
- **Printer Status REST sensor**: Extracted from `bambuddy/sensors.yaml` (`bambuddy_printer_status`)
- **Refresh command**: Extracted from `bambuddy/rest_commands.yaml` (`bambuddy_refresh_printer_status`)
- **Photo upload command**: Extracted from `bambuddy/rest_commands.yaml` (`bambuddy_upload_archive_photo`)
- **Webhook receiver**: Replaces `bambuddy/automations/webhook_handler.yaml` — fires events instead of handling inline

### Eliminated
- `bambuddy_create_archive` REST command — Bambuddy auto-creates archives at print start; HA no longer creates them

### Photo Upload: REST vs Shell Command

The existing `bambuddy_upload_archive_photo` REST command sends a JSON payload with `photo_url`. If the Bambuddy API actually requires `multipart/form-data` file upload, a `shell_command` (curl) is needed instead:

```yaml
# shell_command alternative if multipart required
shell_command:
  bambuddy_upload_snapshot: >
    curl -s -X POST
    -H "X-API-Key: {{ api_key }}"
    -F "file=@{{ file_path }}"
    "{{ base_url }}/api/v1/archives/{{ archive_id }}/photos"
```

> **Decision**: Start with the REST command (JSON photo_url). If Bambuddy rejects it, switch to shell_command. The existing code uses shell_command for upload, suggesting multipart is the actual requirement.

## Dependencies

### External
| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Self-hosted print archive server |

### Downstream (packages that depend on this)
- `print_history` (Phase 2)
- `print_queue` (Phase 3)
- `print_statistics` (Phase 4)
- `printer_maintenance` (Phase 5)

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | Confirm webhook format received by "Webhook (Custom)" provider | Determines if archive_id is available in payload or requires fallback | No — both paths designed |
| 2 | Photo upload content type (JSON vs multipart) | Determines REST command vs shell_command | No — start with REST, fall back to curl |
| 3 | Photo DELETE endpoint — confirm `DELETE /archives/{id}/photos/{photo_id}` | Required for photo review delete action | No — review dismiss still works without it |
| 4 | Cover photo field — confirm `cover_photo_id` on PATCH | Required for set-as-cover action | No — omit button if unavailable |
