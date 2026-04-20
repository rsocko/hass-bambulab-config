# Photo Capture Design — Multi-Camera, Multi-Stage

> **OpenAPI Cross-Reference**: Photo upload (`POST /archives/{id}/photos`) confirmed as multipart/form-data in OpenAPI spec. Photo GET/DELETE endpoints confirmed unauthenticated. Bambuddy also offers a direct camera snapshot API (`GET /printers/{id}/camera/snapshot`) as an alternative to HA camera entities — see [api-vs-design-guidance.md](../../repo/api-vs-design-guidance.md#5-camera-endpoints--direct-snapshot-alternative). Full API corrections in [openapi-correction-notes.md](../../repo/openapi-correction-notes.md).

## Overview

HA owns multi-camera, multi-stage photo capture during print jobs. Photos are saved locally for HA dashboard use and are designed to be handed off to a multipart-capable uploader for attachment to the corresponding Bambuddy archive. Error/failure photos are included.

Bambuddy also captures its own completion photo natively (when "Capture finish photo" is enabled); HA's photos supplement this with additional stages and cameras.

## Webhook Requirement

The current shipped package supports two practical operating modes:

| Mode                              | Webhook configured? | What works                                                                                                                                                                          | What is degraded or missing                                                                                                                                                                             |
| --------------------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Full event-driven mode**        | Yes                 | Current archive_id is captured at `print_started`; finish/error lifecycle automations fire from Bambuddy events; enrichment and cache refresh run immediately on completion/failure | None of the current known gaps are caused by transport choice; remaining limits are the existing fallback heuristics and deferred review flows                                                          |
| **Reduced archive-API-only mode** | No                  | Start, mid-print, and near-complete captures still work from HA printer state/progress sensors; upload can still succeed if the fallback archive lookup resolves the active archive | No `print_started` reset path, no webhook-driven `finish` capture, no reliable webhook-driven `print_failed` capture, no completion enrichment trigger, and no immediate history refresh trigger |

The webhook is therefore not strictly required for basic photo capture and upload in a single-printer setup, because Bambuddy creates archives at print start and the active script can fall back to querying the archive API. It is still required for the full shipped lifecycle as currently implemented.

### Recommended Direction

- Remove webhook listeners for lifecycle stages that HA already receives natively from `bambu_lab`.
- Keep webhook handling only for Bambuddy-specific data that HA cannot infer, especially `archive_id` at `print_started`, and any failure outcome that is not yet proven equivalent on the current printer model.

For this design, that means the long-term recommendation is:

- replace webhook-driven stopped handling with native `event_print_canceled`
- replace webhook-driven finish handling with native `event_print_finished` where archive timing allows
- keep webhook-driven `print_started` only if it is still needed for exact archive binding
- keep webhook-driven `print_failed` only until native failed-event behavior is validated on P1S

## Camera Configuration

### Capture Camera List
- Persisted in `input_text.bambuddy_capture_camera_entities`
- Managed via `script.set_print_history_capture_cameras`, which uses a camera-domain entity selector with `multiple: true`
- Leave the helper blank to fall back to the built-in printer camera (`camera.ntk_ryansoffice_3dprinter_camera`)
- When one or more cameras are selected, the shipped YAML captures each valid `camera.*` entity in the stored list in order
- Invalid, duplicate, or unavailable camera entities are ignored for the current capture run

## Capture Stages

Start, mid-print, near-complete, and error capture use helper gates. Finish capture is unconditional so the archive gets a final HA photo whenever the `print_complete` webhook arrives.

| Stage | Trigger | Boolean Gate | Notes |
|---|---|---|---|
| **Start** | Print status → `running` (after configurable delay ~2-5 min) | `input_boolean.capture_at_start` | Delay allows first layer to be visible |
| **Mid-print** | `sensor.*_print_progress` crosses `input_number.midprint_capture_percent` | `input_boolean.capture_at_midprint` | Default: 50% |
| **Near-complete** | `sensor.*_print_progress` ≥ 99% | `input_boolean.capture_near_complete` | Captures before bed lowers |
| **Finished** | `bambuddy_webhook_event` where event=`print_complete` | None | Always capture a final HA snapshot; Bambuddy may also capture natively |
| **Error** | `print_failed` webhook, `print_stopped` webhook, or `binary_sensor.*_print_error` / `binary_sensor.*_hms_errors` → on | `input_boolean.capture_on_error` | Immediate diagnostic capture |

### Stage Automations

Two automations cover all stages:

**`bambuddy_capture_print_photos.yaml`** — Normal stages (start, mid, near-complete, finish):
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
  # Near-complete: progress ≥ 99%
  - trigger: numeric_state
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_progress
    above: 98
    id: "near_complete"
  # Finish: unconditional print_complete capture
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_complete"
    id: "finish"
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
  # Print-error sensor
  - trigger: state
    entity_id: binary_sensor.ntk_ryansoffice_3dprinter_print_error
    to: "on"
    id: "print_error"
  # HMS error sensor
  - trigger: state
    entity_id: binary_sensor.ntk_ryansoffice_3dprinter_hms_errors
    to: "on"
    id: "hms_error"
```

## Snapshot Capture + Upload Script

**`script.capture_and_upload_snapshot`** handles all capture stages. Called with a `stage` field (e.g., "start", "midprint", "near_complete", "error").

### Flow

```
1. Check if stage is gated → skip if boolean is off
2. Finish-stage only: call the reusable printer LED photo-lighting script, which waits briefly for the WLED state machine to settle, snapshots live `light.magwled` state into a temporary scene, then forces MagWLED to solid cool white
3. Turn on snapshot light (if configured via input_text.3dprinter_snapshot_light, excluding the finish-stage MagWLED override path)
4. Wait 1 second for light to reach brightness
5. Resolve the configured capture camera list (or built-in default)
6. Capture each valid camera sequentially → save to /config/www/printer_snapshots/{task}_{stage}_{timestamp}[ _camN ].jpg
7. Turn off snapshot light
8. Finish-stage only: call the reusable printer LED photo-lighting script to restore the saved MagWLED scene
9. If input_text.bambuddy_current_archive_id is set:
  → Hand off the saved file to the shipped multipart uploader (`shell_command` using Python stdlib)
10. If archive_id is empty:
  → Call script.resolve_current_archive_id first, then hand off if resolved
11. Local copy always retained regardless of upload success
```

### Snapshot Light Integration

Reuses the existing pattern from `notifications/automations/print_complete_notification.yaml`:
- Light entity: `input_text.3dprinter_snapshot_light`
- Brightness: `input_number.3dprinter_snapshot_light_brightness`
- These helpers belong to the `notifications` package; if not deployed, the light step is skipped (template check for empty/unavailable)

### Finish-Stage MagWLED Override

Successful completion photos now treat `light.magwled` as a dedicated capture light instead of depending on the generic snapshot-light helper.

- The finish capture now uses `script.printer_led_magwled_photo_lighting`, owned by the `printer_led` package, so MagWLED photo-lighting behavior stays consistent across any future camera workflows.
- The reusable script waits 2 seconds after the `print_complete` trigger so the WLED state machine can first settle into its normal completion state, including the green finish look.
- It snapshots the live MagWLED state into a temporary HA scene, temporarily forces `light.magwled` to `Solid` with RGBW cool white for the camera capture, then restores the saved scene afterward.
- This preserves the intended post-complete green appearance instead of leaving MagWLED white or turning it off.
- If `input_text.3dprinter_snapshot_light` ever points to `light.magwled`, the generic helper path is automatically suppressed during finish capture so MagWLED is only controlled once.

### Local File Naming

```
/config/www/printer_snapshots/{task_name}_{stage}_{YYYYMMDD_HHMMSS}.jpg
/config/www/printer_snapshots/{task_name}_{stage}_{YYYYMMDD_HHMMSS}_cam2.jpg
/config/www/printer_snapshots/{task_name}_{stage}_{YYYYMMDD_HHMMSS}_cam3.jpg
```

Examples:
- `Benchy_start_20260328_143000.jpg`
- `Benchy_midprint_20260328_150000_cam2.jpg`
- `Benchy_error_20260328_151500_cam3.jpg`

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

**`script.resolve_current_archive_id`** is called when archive_id is empty, or when the currently stored archive_id fails validation against the current task (webhook missed, stale helper state, or flat webhook format without archive_id):

```
1. Query a recent archive window from `GET /api/v1/archives/`
2. Filter candidates to the configured Bambuddy printer when printer id is available
3. Keep only archives that are currently `printing`
4. Prefer an exact task-name match, then a loose task-name match, then a unique active archive only when it is still unambiguous
5. If no safe match exists → log warning, publish degraded binding state, and skip archive writes rather than binding the wrong archive
```

> **OpenAPI note**: The `sort` param does not exist on `GET /archives/`. Default ordering appears newest-first. The endpoint requires a trailing slash. Response is a flat `ArchiveResponse[]` array.

> **Note**: Archives exist from print START (confirmed by user observation: archive appears with 3MF, 3D viewer, filament data while print is in progress). This means mid-print uploads work immediately — there is no window where the archive doesn't yet exist.

### What the Archive Pull Is Good Enough For

The current archive list pull is good enough to answer two narrow questions in the common configured-printer case:

1. What is the newest archive in Bambuddy right now?
2. What archive is most likely associated with the currently running print, if Bambuddy exposes one active `printing` archive for the configured printer and the task context validates cleanly enough?

That is why the current manual and in-print upload flow can work without webhook configuration.

### What the Archive Pull Does Not Replace

The archive pull is not a full replacement for webhook events in the current package design:

- It does not provide a start-of-print event to reset `counter.bambuddy_captured_photo_count`, clear `input_text.bambuddy_last_photo_upload_result`, snapshot the tray map, and reset review state.
- It does not provide a completion/failure event to trigger finish capture, completion enrichment, or immediate history refresh.
- It is still heuristic rather than exact: the current fallback narrows by printer id, active `printing` status, and task context, but it is still resolving from recent archive data instead of using a server-issued binding token. Repeated or highly similar print names can still remain ambiguous.

### Stale Archive Guard

`script.capture_and_upload_snapshot` now validates the currently stored `input_text.bambuddy_current_archive_id` against the current print task before upload. If the stored archive detail does not match the active task, the script treats it as stale, attempts fallback resolution again, and skips upload rather than attaching photos to the wrong archive.

As of the latest hardening pass, the guard is stricter than task-name matching alone:

- native print start clears any stale retained archive binding when the exact Bambuddy webhook path has not run yet
- fallback resolution now checks the configured Bambuddy printer id and searches the recent archive window instead of trusting a single newest archive
- while the printer is active, fallback resolution rejects terminal archives such as `completed`, `failed`, or `archived`
- enrichment and photo upload both re-validate the candidate archive against the active task context before writing anything

This means the system now prefers to skip upload/enrichment and raise a repair warning rather than risk updating the prior archive.

### Archive Binding Health Signal

The package now exposes `sensor.bambuddy_archive_binding_health` to make degraded binding visible when print-history sync is enabled without an exact webhook-bound archive.

| State | Meaning |
|---|---|
| `ok` | Exact webhook binding is present, or no active print needs archive binding |
| `warn` | Sync is running on validated API fallback for the current print |
| `repair` | No safe current archive binding is available for an active print |
| `disabled` | Bambuddy integration or print-history sync is disabled |

When the sensor enters `warn` or `repair`, the package publishes a persistent notification so the degraded mode is visible during the print instead of silently continuing.

### Current Recommendation

- If the goal is only start/mid/near-complete photo capture with upload verification on a single printer, webhook can remain optional.
- If the goal is the full current package behavior, including archive lifecycle state, finish/error event handling, and completion enrichment, webhook should be configured or the package should be intentionally refactored away from webhook-triggered automations.

## Automation Mode

- **`bambuddy_capture_print_photos`**: `mode: single` — one print at a time; only one set of stage triggers active
- **`bambuddy_capture_error_photos`**: `mode: queued` (max: 3) — multiple errors can fire rapidly (HMS cascade)
- **`script.capture_and_upload_snapshot`**: `mode: queued` (max: 5) — overlapping camera+upload operations

## Duplicate Trigger Note

If both Bambuddy webhook reception and native `bambu_lab` cancel triggers are enabled, a single stop/cancel action can emit both `print_stopped` and `event_print_canceled`. Any automation wired to both will run twice unless it has explicit deduplication.

## Upload Transport Guidance

`POST /api/v1/archives/{id}/photos` requires `multipart/form-data` with a real `file` field. That rules out HA `rest_command` for the upload itself.

| Option | Recommendation | Pros | Cons |
|---|---|---|---|
| `shell_command` + Python stdlib | **Recommended shipped Phase 1** | Native HA service trigger, real multipart upload, no `curl` dependency inside HA Core, easiest path to match Bambuddy's contract | Response handling is still coarse compared with a dedicated worker |
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
4. The shell command uses Python stdlib multipart upload to POST to Bambuddy
5. HA queries `GET /archives/{id}` before/after upload and verifies that the archive photo count increased
6. HA stores a short last-result summary plus a captured-photo count for runtime state; a richer manifest remains future work

Why first:

- no new orchestration platform
- minimal change to current HA package layout
- directly compatible with the live Swagger contract
- good enough to prove end-to-end upload behavior quickly

Known limitations:

- no structured per-photo metadata is persisted yet
- retries and richer diagnostics still want a dedicated worker
- later photo-review features will still want richer returned metadata

#### Repo-Specific Phase 1 Draft

What already exists in this repo:

- `script.capture_and_upload_snapshot` already captures local files and increments current-print photo state
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
  python3 -c '... multipart upload using stdlib urllib ...'
```

```yaml
# script.capture_and_upload_snapshot call contract
- action: shell_command.bambuddy_upload_archive_photo
  data:
    archive_id: "{{ archive_id }}"
    file_path: "/config/www/printer_snapshots/{{ primary_filename }}"
```

Prefer explicit `file_path` passing over any "latest file" upload strategy. The current phase verifies uploads by comparing archive detail before/after the upload and stores only compact runtime state that fits inside HA helpers.

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

## Current Runtime State

The shipped Phase 1 runtime now keeps two compact helpers instead of a JSON manifest:

- `counter.bambuddy_captured_photo_count` — number of captured photos in the current print cycle
- `input_text.bambuddy_last_photo_upload_result` — short verification summary for the latest capture/upload attempt

This keeps current automations within Home Assistant helper limits. A richer per-photo manifest is still future work for the advanced review flow.

### Integration with Post-Print Review

After enrichment completes, the enrichment automation sets `input_select.bambuddy_photo_review_state` → `pending` if `counter.bambuddy_captured_photo_count` is greater than zero. This surfaces a review chip on the dashboard while the advanced review flow remains deferred.
