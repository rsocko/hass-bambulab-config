# Photo Capture Design — Multi-Camera, Multi-Stage

> **OpenAPI Cross-Reference**: Photo upload (`POST /archives/{id}/photos`) confirmed as multipart/form-data in OpenAPI spec. Photo GET/DELETE endpoints confirmed unauthenticated. Bambuddy also offers a direct camera snapshot API (`GET /printers/{id}/camera/snapshot`) as an alternative to HA camera entities — see [api-vs-design-guidance.md](../../repo/api-vs-design-guidance.md#5-camera-endpoints--direct-snapshot-alternative). Full API corrections in [openapi-correction-notes.md](../../repo/openapi-correction-notes.md).

## Overview

HA owns multi-camera, multi-stage photo capture during print jobs. Photos are saved locally for HA dashboard use and are designed to be handed off to a multipart-capable uploader for attachment to the corresponding Bambuddy archive. Error/failure photos are included.

Bambuddy also captures its own completion photo natively (when "Capture finish photo" is enabled); HA's photos supplement this with additional stages and cameras.

## Camera Configuration

### Primary Camera
- Entity: `camera.ntk_ryansoffice_3dprinter_camera` (printer built-in P1S camera)
- Always used for all capture stages

### Secondary Camera (Optional)
- Entity stored in `input_select.secondary_camera_entity`
- Single optional camera selection from the known secondary camera list
- `None` disables the secondary capture path

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
  → Hand off the saved file to a multipart-capable uploader (recommended: shell_command + curl)
8. If archive_id is empty:
  → Call script.resolve_current_archive_id first, then hand off if resolved
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

## Upload Transport Guidance

`POST /api/v1/archives/{id}/photos` requires `multipart/form-data` with a real `file` field. That rules out HA `rest_command` for the upload itself.

| Option | Recommendation | Pros | Cons |
|---|---|---|---|
| `shell_command` + `curl` | **Recommended default** | Native HA service trigger, real multipart upload, simple deployment, easiest path to match Bambuddy's contract | Harder response handling, quoting/escaping can be brittle, success tracking is manual |
| `command_line` | Not recommended for uploads | Good for polling or exposing command output as sensors | Wrong fit for event-driven file upload; better for reads than one-shot actions |
| External Python script | Recommended when richer control is needed | Better retries, structured logging, response parsing, clearer file handling | More moving parts than a shell bridge |
| `n8n` or other orchestrator | Recommended only for larger workflows | Best for multi-step flows, retries, audit trail, branching, future recovery workflows | Extra infrastructure and operational overhead |

Current shipped YAML captures locally and now uses a first-phase `shell_command` multipart uploader. Do not use `rest_command` to upload archive photos.

## Draft Implementation Path

### First Phase: `shell_command` Upload Bridge

This is the intended starting point.

Design shape:

1. `script.capture_and_upload_snapshot` captures the image and writes the local file
2. The script resolves `archive_id` if needed
3. The script calls a `shell_command` with explicit parameters:
  `archive_id`, `file_path`, and optionally `base_url`
4. The shell command uses `curl -F "file=@..."` to POST to Bambuddy
5. HA logs success or failure at a coarse level
6. Manifest entries remain local-first and can mark upload as deferred or best-effort until response parsing exists

Why first:

- no new orchestration platform
- minimal change to current HA package layout
- directly compatible with the live Swagger contract
- good enough to prove end-to-end upload behavior quickly

Known limitations:

- weak response parsing
- awkward quoting and escaping
- retries and structured diagnostics are limited
- later photo-review features will still want richer returned metadata

#### Repo-Specific Phase 1 Draft

What already exists in this repo:

- `script.capture_and_upload_snapshot` already captures local files and records manifest entries
- `script.resolve_current_archive_id` already exists
- an old superseded automation references `shell_command.bambuddy_upload_latest_snapshot`

What was missing before this phase and is now implemented in the active package:

- `shell_command` include in `print_history_loader.yaml`
- `shell_commands/` directory under the active `print_history` package
- explicit upload bridge that receives `archive_id` + `file_path`

Implemented first-phase package shape:

```yaml
# print_history_loader.yaml
automation: !include_dir_merge_list automations
rest: !include_dir_merge_list rest_sensors
rest_command: !include_dir_merge_named rest_commands
shell_command: !include_dir_merge_named shell_commands
script: !include_dir_merge_named scripts
```

```yaml
# shell_commands/bambuddy_upload_archive_photo.yaml
bambuddy_upload_archive_photo: >-
  /bin/sh -c 'api_key=$(python3 -c "import sys, yaml; data = yaml.safe_load(open(\"/config/secrets.yaml\")) or {}; sys.stdout.write(str(data.get(\"bambuddy_api_key\", \"\")))");
  [ -n "$api_key" ] &&
  curl -sS --fail-with-body -X POST
  -H "X-API-Key: $api_key"
  -F "file=@{{ file_path }}"
  "{{ states('input_text.bambuddy_api_base_url') }}/api/v1/archives/{{ archive_id }}/photos"'
```

```yaml
# script.capture_and_upload_snapshot call contract
- action: shell_command.bambuddy_upload_archive_photo
  data:
    archive_id: "{{ archive_id }}"
    file_path: "/config/www/printer_snapshots/{{ primary_filename }}"
```

Prefer explicit `file_path` passing over any "latest file" upload strategy. The current phase still treats upload as best-effort; manifest entries are recorded locally first.

### Potential Final Form: External Python Uploader

Use this if upload becomes a core workflow instead of a thin bridge.

Design shape:

1. HA capture script still owns timing and local file creation
2. HA hands upload work to a Python worker with explicit inputs
3. Python performs multipart upload, parses the response, and returns structured output
4. HA updates the photo manifest with real upload outcome and returned Bambuddy metadata
5. Future review/delete/set-cover flows reuse the returned metadata instead of guessing

Expected advantages over the shell bridge:

- reliable success/failure distinction
- cleaner logging
- easier retries and timeouts
- easier to evolve into photo-review and media-lifecycle workflows

Expected costs:

- more implementation effort
- additional runtime/dependency management
- one more moving part to deploy and maintain

#### Repo-Specific Phase 2 Draft

Recommended Python worker input contract:

```json
{
  "archive_id": "184",
  "file_path": "/config/www/printer_snapshots/Benchy_midprint_20260328_150000.jpg",
  "base_url": "http://bambuddy.socko.us"
}
```

Recommended Python worker output contract:

```json
{
  "ok": true,
  "status": 200,
  "uploaded_filename": "Benchy_midprint_20260328_150000.jpg",
  "response_body": {}
}
```

Recommended manifest change when Phase 2 is implemented:

- current repo state: local-first manifest with `uploaded: false`
- target state: structured upload lifecycle fields

Suggested fields:

- `upload_requested`
- `upload_status`
- `uploaded_filename`
- `upload_error`

This keeps Phase 1 simple while giving Phase 2 a clean forward path into photo-review and delete/set-cover workflows.

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
