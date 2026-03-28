# Print History — Archive Reading, Photo Capture & Enrichment

## Overview

Reads print archives from Bambuddy's API, captures multi-camera photos at multiple print stages (including errors), uploads them to Bambuddy archives, and enriches completed archives with Spoolman spool data. Provides paginated history browsing in the HA dashboard.

**HA Role**: READ archives + CAPTURE multi-stage photos + ENRICH with Spoolman data + SURFACE in dashboard. Bambuddy owns archive creation (auto-creates at print start with 3MF metadata, thumbnails, filament data).

## Package Structure

```
homeassistant/packages/3d_printing/print_history/
├── print_history_loader.yaml
├── automations/
│   ├── bambuddy_capture_archive_id.yaml          # webhook print_started → store archive_id
│   ├── bambuddy_enrich_archive_on_complete.yaml   # webhook print_complete/failed → PATCH tags/notes
│   ├── bambuddy_capture_print_photos.yaml         # multi-camera, multi-stage photo capture + upload
│   ├── bambuddy_capture_error_photos.yaml         # print_failed/stopped/HMS → immediate capture + upload
│   ├── bambuddy_event_history_refresh.yaml        # webhook → refresh REST sensor
│   └── bambuddy_photo_review_auto_dismiss.yaml    # auto-dismiss review after timeout or next print
├── rest_commands/
│   ├── bambuddy_upload_photo_to_archive.yaml      # POST /archives/{id}/photos
│   ├── bambuddy_delete_archive_photo.yaml         # DELETE /archives/{id}/photos/{photo_id}
│   ├── bambuddy_set_archive_cover.yaml            # PATCH /archives/{id} — set cover photo
│   ├── bambuddy_update_archive.yaml               # PATCH /archives/{id} — tags/notes enrichment
│   └── bambuddy_add_archive_tags.yaml             # POST /archives/{id}/tags
├── rest_sensors/
│   └── bambuddy_print_history_sensor.yaml         # GET /archives (page 1, recent)
├── scripts/
│   ├── load_history_page.yaml                     # fetch specific page (offset-based)
│   ├── navigate_history.yaml                      # prev/next/first/last
│   ├── capture_and_upload_snapshot.yaml            # multi-camera snapshot → save + upload
│   ├── resolve_current_archive_id.yaml            # fallback: query API → match filename
│   ├── review_delete_photo.yaml                   # delete photo from Bambuddy + local + manifest
│   ├── review_replace_photo.yaml                  # capture new → upload → delete old → update manifest
│   ├── review_set_cover.yaml                      # set photo as archive cover thumbnail
│   └── review_dismiss.yaml                        # accept all, set review state → idle
├── template_sensors/
│   ├── bambuddy_last_print_name.yaml
│   ├── bambuddy_last_print_status.yaml
│   ├── bambuddy_last_print_duration.yaml
│   ├── bambuddy_last_print_image_url.yaml
│   ├── print_history_total_pages.yaml
│   └── print_history_page_info.yaml
├── helpers/
│   ├── input_text/
│   │   ├── input_text_bambuddy_current_archive_id.yaml
│   │   ├── input_text_history_page_data.yaml
│   │   └── input_text_secondary_camera_entity.yaml
│   ├── input_boolean/
│   │   ├── input_boolean_bambuddy_history_fetch_enabled.yaml
│   │   ├── input_boolean_capture_at_start.yaml
│   │   ├── input_boolean_capture_at_midprint.yaml
│   │   ├── input_boolean_capture_near_complete.yaml
│   │   └── input_boolean_capture_on_error.yaml
│   ├── input_number/
│   │   ├── input_number_bambuddy_history_limit.yaml
│   │   ├── input_number_history_current_page.yaml
│   │   ├── input_number_midprint_capture_percent.yaml
│   │   └── input_number_photo_review_timeout_hours.yaml
│   └── input_select/
│       └── input_select_bambuddy_photo_review_state.yaml
├── dashboard_cards/
│   ├── print_history.yaml
│   ├── print_history_browser.yaml
│   └── photo_review_chip.yaml                     # conditional chip → opens review popup
└── dashboard_views/
    └── view_print_history.yaml
```

## Loader Domains

```yaml
# print_history_loader.yaml
automation: !include_dir_merge_list automations
sensor: !include_dir_merge_list rest_sensors
rest_command: !include_dir_merge_named rest_commands
script: !include_dir_merge_named scripts
template: !include_dir_merge_list template_sensors
input_text: !include_dir_merge_named helpers/input_text
input_boolean: !include_dir_merge_named helpers/input_boolean
input_number: !include_dir_merge_named helpers/input_number
input_select: !include_dir_merge_named helpers/input_select
```

## Entity Reference

### REST Sensors

| Entity | Endpoint | Interval | Attributes |
|---|---|---|---|
| `sensor.bambuddy_print_history` | `GET /archives?limit=N&sort=created_at&order=desc` | 5 min | `archives`, `total`, `page` |

### REST Commands

| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_upload_photo_to_archive` | POST | `/api/v1/archives/{id}/photos` | Upload photo to archive |
| `rest_command.bambuddy_delete_archive_photo` | DELETE | `/api/v1/archives/{id}/photos/{photo_id}` | Delete a photo from archive (photo review) |
| `rest_command.bambuddy_set_archive_cover` | PATCH | `/api/v1/archives/{id}` | Set cover photo for archive thumbnail (photo review) |
| `rest_command.bambuddy_update_archive` | PATCH | `/api/v1/archives/{id}` | Update name, notes, tags |
| `rest_command.bambuddy_add_archive_tags` | POST | `/api/v1/archives/{id}/tags` | Add tags to an archive |

### Template Sensors (from REST attributes)

| Entity | Source | Purpose |
|---|---|---|
| `sensor.bambuddy_last_print_name` | `archives[0].name` | Most recent print name |
| `sensor.bambuddy_last_print_status` | `archives[0].status` | Most recent print result |
| `sensor.bambuddy_last_print_duration` | `archives[0].duration_seconds` | Most recent print time (hours) |
| `sensor.bambuddy_last_print_image_url` | `archives[0].photo_url` | Most recent print photo (full URL) |
| `sensor.print_history_total_pages` | `total / limit` | Total pages for pagination |
| `sensor.print_history_page_info` | `current_page / total_pages` | Display string for pagination UI |

### Helpers

| Entity | Type | Purpose | Persists? |
|---|---|---|---|
| `input_text.bambuddy_current_archive_id` | input_text | Current print's archive_id (set by webhook, cleared on complete) | No `initial:` — survives restart |
| `input_text.history_page_data` | input_text | JSON storage for current page results | — |
| `input_text.secondary_camera_entity` | input_text | Configurable secondary camera entity_id | — |
| `input_boolean.bambuddy_history_fetch_enabled` | input_boolean | Enable/disable history REST polling | — |
| `input_boolean.capture_at_start` | input_boolean | Enable photo capture at print start | — |
| `input_boolean.capture_at_midprint` | input_boolean | Enable photo capture at mid-print % | — |
| `input_boolean.capture_near_complete` | input_boolean | Enable photo capture at ~95% | — |
| `input_boolean.capture_on_error` | input_boolean | Enable photo capture on error/failure | — |
| `input_number.bambuddy_history_limit` | input_number | Number of history entries per page (5–50) | — |
| `input_number.history_current_page` | input_number | Current pagination page | — |
| `input_number.midprint_capture_percent` | input_number | Progress % for mid-print capture (e.g., 50) | — |
| `input_number.photo_review_timeout_hours` | input_number | Hours before review auto-dismisses (default: 24) | — |
| `input_text.bambuddy_photo_manifest` | input_text | JSON manifest of captured photos for current print | No `initial:` |
| `input_select.bambuddy_photo_review_state` | input_select | Review lifecycle: `idle`, `pending`, `reviewing` | — |

### Scripts

| Script | Purpose |
|---|---|
| `script.load_history_page` | Fetch a specific page of archive history (offset-based) |
| `script.navigate_history` | Prev/next/first/last navigation, calls `load_history_page` |
| `script.capture_and_upload_snapshot` | Multi-camera capture + local save + Bambuddy upload |
| `script.resolve_current_archive_id` | Fallback: query Bambuddy API, match by filename, store archive_id |
| `script.review_delete_photo` | Delete photo from Bambuddy + local file + update manifest |
| `script.review_replace_photo` | Capture new snapshot, upload, delete old, update manifest |
| `script.review_set_cover` | Set selected photo as archive cover thumbnail |
| `script.review_dismiss` | Accept all photos, set review state → `idle` |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_capture_archive_id` | `bambuddy_webhook_event` where event=`print_started` | Store archive_id from payload (or fallback lookup) |
| `bambuddy_capture_print_photos` | Print running + progress milestones | Multi-stage photo capture via `capture_and_upload_snapshot` |
| `bambuddy_capture_error_photos` | print_failed/stopped webhook, HMS error sensor | Error photo capture via `capture_and_upload_snapshot` |
| `bambuddy_enrich_archive_on_complete` | `bambuddy_webhook_event` where event=`print_complete`/`print_failed`/`print_stopped` | PATCH archive with Spoolman tags/notes, clear archive_id |
| `bambuddy_event_history_refresh` | `bambuddy_webhook_event` where event=`print_complete`/`print_failed` | Refresh REST sensor |
| `bambuddy_photo_review_auto_dismiss` | Timeout elapsed since `pending`, OR next `print_started` event | Set review state → `idle` |

## Key Design Details

For detailed design of the two major subsystems, see:

- **[photo-capture-design.md](photo-capture-design.md)** — Multi-camera, multi-stage photo capture with error photos
- **[archive-enrichment.md](archive-enrichment.md)** — Spoolman data enrichment pipeline (tags + notes)
- **[photo-review-design.md](photo-review-design.md)** — Post-print photo review: remove, replace, set cover

## Migration Notes

### Sources (from `bambuddy/`)
- **REST sensor**: `bambuddy_print_history` from `bambuddy/sensors.yaml`
- **REST commands**: `bambuddy_update_archive_status` → `bambuddy_update_archive` (generalized to support notes+tags+name), `bambuddy_add_archive_tags` kept as-is
- **Template sensors**: 4 "last print" sensors from `bambuddy/sensors.yaml` (converted to modern `template:` format)
- **Dashboard cards**: `bambuddy/dashboards/print_history.yaml` → `dashboard_cards/`
- **Helpers**: `bambuddy_current_archive_id`, `bambuddy_history_fetch_enabled`, `bambuddy_history_limit` from `bambuddy/helpers.yaml`

### Eliminated
- `bambuddy/automations/sync_print_history.yaml` — Bambuddy auto-creates archives; HA no longer calls `POST /archives`
- `rest_command.bambuddy_create_archive` — same reason
- `rest_command.bambuddy_update_archive_status` — replaced by generalized `bambuddy_update_archive` (PATCH with any fields)

### New (not in existing bambuddy/)
- Archive ID capture from webhook events
- Multi-stage photo capture automations (start, mid, near-complete, error)
- `capture_and_upload_snapshot` script with multi-camera + light control
- `resolve_current_archive_id` fallback script
- Enrichment automation (Spoolman tags + notes)
- Pagination scripts and template sensors
- Configurable capture stage toggles and secondary camera helper
- Dedicated history view (`view_print_history.yaml`)

## Dependencies

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [bambuddy_common](../bambuddy_common/README.md) | **Yes** | API config helpers, webhook receiver, printer status sensor |
| [Core](../core/README.md) | **Yes** | `sensor.spoolman_tray_map` (spool IDs per tray), `sensor.print_cost` |
| [Spoolman Sync](../spoolman_sync/README.md) | No | Per-tray weight data (`sensor.*_print_weight` attributes). Enrichment degrades gracefully without it. |
| [Notifications](../notifications/README.md) | No | Snapshot light + brightness helpers reused from notification package |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Archive API (GET, PATCH, POST photos/tags) |
| [ha-bambulab](https://github.com/greghesp/ha-bambulab) | **Yes** | Print status sensors, task name, progress %, camera entity |
| [button-card](https://github.com/custom-cards/button-card) (HACS) | **Yes** | Dashboard card rendering |

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | Verify `print_started` webhook includes `archive_id` in payload | If missing, first photo upload relies on fallback lookup | No — fallback designed |
| 2 | Photo upload content type (JSON photo_url vs multipart file) | Determines upload mechanism in `capture_and_upload_snapshot` | No — both paths designed |
| 3 | Confirm `input_text.3dprinter_snapshot_light` availability cross-package | If notifications package not deployed, need local fallback | No — gated with template check |
| 4 | Enrichment idempotency — verify PATCH tags doesn't create duplicates | Could pollute tag lists on retry | Low risk — test during Phase 7 |
| 5 | Base64 `image` field in webhook payload — bonus data capture | Bambuddy webhooks can include base64 JPEG for some events | No — nice-to-have, not blocking |
| 6 | Photo list/delete API — confirm `GET` and `DELETE` on `/archives/{id}/photos/{photo_id}` | Required for review delete action | No — review/dismiss still works without it |
| 7 | Cover photo API — confirm `cover_photo_id` field on PATCH | Required for set-as-cover action | No — omit button if unavailable |
| 8 | Upload response schema — does POST photos return `photo_id`? | Manifest needs photo_id for delete/replace mapping | No — can fall back to listing photos |
