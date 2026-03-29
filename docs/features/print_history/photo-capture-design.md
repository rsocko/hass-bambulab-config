# Photo Capture Design — Multi-Camera, Multi-Stage

> **OpenAPI Cross-Reference**: Photo upload (`POST /archives/{id}/photos`) confirmed as multipart/form-data in OpenAPI spec. Photo GET/DELETE endpoints confirmed unauthenticated. Bambuddy also offers a direct camera snapshot API (`GET /printers/{id}/camera/snapshot`) as an alternative to HA camera entities — see [api-vs-design-guidance.md](../../repo/api-vs-design-guidance.md#5-camera-endpoints--direct-snapshot-alternative). Full API corrections in [openapi-correction-notes.md](../../repo/openapi-correction-notes.md).

## Overview

HA owns multi-camera, multi-stage photo capture during print jobs. Photos are saved locally for HA dashboard use and uploaded to the corresponding Bambuddy archive. Error/failure photos are included.

Bambuddy also captures its own completion photo natively (when "Capture finish photo" is enabled); HA's photos supplement this with additional stages and cameras.

## Camera Configuration

### Primary Camera
- Entity: `camera.ntk_ryansoffice_3dprinter_camera` (printer built-in P1S camera)
- Always used for all capture stages

### Secondary Camera (Optional)
- Entity stored in `input_text.secondary_camera_entity`
- Can be any HA camera entity (USB cam, IP cam, etc.)
- If empty/unavailable, only primary camera captures

## Capture Stages

Each stage is gated by its own `input_boolean` toggle, allowing the user to enable/disable individual stages without modifying automations.

| Stage | Trigger | Boolean Gate | Notes |
|---|---|---|---|
| **Start** | Print status → `running` (after configurable delay ~2-5 min) | `input_boolean.capture_at_start` | Delay allows first layer to be visible |
| **Mid-print** | `sensor.*_print_progress` crosses `input_number.midprint_capture_percent` | `input_boolean.capture_at_midprint` | Default: 50% |
| **Near-complete** | `sensor.*_print_progress` ≥ 95% | `input_boolean.capture_near_complete` | Captures before bed lowers |
| **Finished** | `bambuddy_webhook_event` where event=`print_complete` | (always, no gate) | Bambuddy also captures natively |
| **Error** | `print_failed`/`print_stopped` webhook or `binary_sensor.*_print_error` → on | `input_boolean.capture_on_error` | Immediate diagnostic capture |

### Stage Automations

Two automations cover all stages:

**`bambuddy_capture_print_photos.yaml`** — Normal stages (start, mid, near-complete):
```yaml
triggers:
  # Start: print status changes to running
  - trigger: state
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_status
    to: "running"
    id: "start"
  # Mid: progress crosses threshold
  - trigger: numeric_state
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_progress
    above: "{{ states('input_number.midprint_capture_percent') | int }}"
    id: "midprint"
  # Near-complete: progress ≥ 95%
  - trigger: numeric_state
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_progress
    above: 94
    id: "near_complete"
```

**`bambuddy_capture_error_photos.yaml`** — Error stages:
```yaml
triggers:
  # Webhook: print_failed or print_stopped
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_failed"
    id: "failed"
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_stopped"
    id: "stopped"
  # HMS error sensor
  - trigger: state
    entity_id: binary_sensor.ntk_ryansoffice_3dprinter_print_error
    to: "on"
    id: "hms_error"
```

## Snapshot Capture + Upload Script

**`script.capture_and_upload_snapshot`** handles all capture stages. Called with a `stage` field (e.g., "start", "midprint", "near_complete", "error").

### Flow

```
1. Check if stage is gated → skip if boolean is off
2. Turn on snapshot light (if configured via input_text.3dprinter_snapshot_light)
3. Wait 1 second for light to reach brightness
4. Capture primary camera → save to /config/www/printer_snapshots/{task}_{stage}_{timestamp}.jpg
5. Capture secondary camera (if configured) → save similarly with "_cam2" suffix
6. Turn off snapshot light
7. If input_text.bambuddy_current_archive_id is set:
   → Upload to Bambuddy via rest_command.bambuddy_upload_photo_to_archive
8. If archive_id is empty:
   → Call script.resolve_current_archive_id first, then upload if resolved
9. Local copy always retained regardless of upload success
```

### Snapshot Light Integration

Reuses the existing pattern from `notifications/automations/print_complete_notification.yaml`:
- Light entity: `input_text.3dprinter_snapshot_light`
- Brightness: `input_number.3dprinter_snapshot_light_brightness`
- These helpers belong to the `notifications` package; if not deployed, the light step is skipped (template check for empty/unavailable)

### Local File Naming

```
/config/www/printer_snapshots/{task_name}_{stage}_{YYYYMMDD_HHMMSS}.jpg
/config/www/printer_snapshots/{task_name}_{stage}_{YYYYMMDD_HHMMSS}_cam2.jpg  (secondary)
```

Examples:
- `Benchy_start_20260328_143000.jpg`
- `Benchy_midprint_20260328_150000.jpg`
- `Benchy_error_20260328_151500.jpg`

## Archive ID Resolution

Photos must link to the correct Bambuddy archive. Two paths:

### Primary: Webhook Payload

When Bambuddy sends the `print_started` webhook (API format), the payload includes:
```json
{ "event": "print_started", "data": { "archive_id": 42, ... } }
```

**`bambuddy_capture_archive_id.yaml`** automation extracts this and stores it:
```yaml
- action: input_text.set_value
  target:
    entity_id: input_text.bambuddy_current_archive_id
  data:
    value: "{{ trigger.event.data.data.archive_id | default('') }}"
```

### Fallback: API Query

**`script.resolve_current_archive_id`** is called when archive_id is empty (webhook missed, or flat webhook format without archive_id):

```
1. Query GET /api/v1/archives/?printer_id={id}&limit=1  (trailing slash required, no sort param)
2. Compare returned archive filename with current sensor.*_task_name
3. If match → store archive_id in input_text.bambuddy_current_archive_id
4. If no match → log warning, skip upload (local photo still saved)
```

> **OpenAPI note**: The `sort` param does not exist on `GET /archives/`. Default ordering appears newest-first. The endpoint requires a trailing slash. Response is a flat `ArchiveResponse[]` array.

> **Note**: Archives exist from print START (confirmed by user observation: archive appears with 3MF, 3D viewer, filament data while print is in progress). This means mid-print uploads work immediately — there is no window where the archive doesn't yet exist.

## Automation Mode

- **`bambuddy_capture_print_photos`**: `mode: single` — one print at a time; only one set of stage triggers active
- **`bambuddy_capture_error_photos`**: `mode: queued` (max: 3) — multiple errors can fire rapidly (HMS cascade)
- **`script.capture_and_upload_snapshot`**: `mode: queued` (max: 5) — overlapping camera+upload operations

## Bambuddy Settings (Recommended)

| Setting | Value | Rationale |
|---|---|---|
| Auto-archive prints | ON | Bambuddy creates archives with 3MF metadata, thumbnails, filament data |
| Save thumbnails | ON | Slicer preview images extracted natively — richer than camera snapshots |
| Capture finish photo | ON | Bambuddy captures its own completion photo; HA photos supplement this |

## Photo Manifest

Each capture appends an entry to `input_text.bambuddy_photo_manifest` (JSON array). This manifest drives the [post-print photo review](photo-review-design.md) feature. See that document for manifest schema, review popup design, and cleanup strategy.

### Integration with Post-Print Review

After enrichment completes, the enrichment automation sets `input_select.bambuddy_photo_review_state` → `pending` if the manifest is non-empty. This surfaces a review chip on the dashboard where the user can remove, replace, or set a cover photo before the review auto-dismisses.
