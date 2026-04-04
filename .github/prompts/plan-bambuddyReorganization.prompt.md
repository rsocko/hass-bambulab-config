# Plan: Bambuddy Reorganization into Feature Packages (v3)

## TL;DR
Break monolithic `bambuddy/` into 5 feature HA packages. Leverage Bambuddy's native auto-archiving, maintenance tracker — HA's role is READ + SURFACE + ENRICH + REACT, not recreate. HA adds multi-camera photo capture at strategic print stages (including errors), enriches archives with Spoolman spool data via PATCH tags/notes, and surfaces Bambuddy data in HA dashboards. Delete root `bambuddy/` after migration. Print Log skipped (strict subset of archives).

> Historical planning note: this prompt captures migration design context, not the exact live archive-enrichment contract currently shipped in `homeassistant/packages/3d_printing/print_history/`. For the implemented current-state contract, use `docs/features/print_history/archive-enrichment.md`.

## Decisions
- **Package naming**: Feature-first (`print_history/`, `printer_maintenance/`)
- **Shared API config**: Dedicated `bambuddy_common/` loaded first
- **Root `bambuddy/`**: Delete after migration
- **Webhook**: Single receiver in `bambuddy_common/` fires `bambuddy_webhook_event`; features listen. API webhook payload includes `archive_id` in `data` object.
- **Archive creation**: Bambuddy creates archive at/near print START (confirmed: user observes archive with 3MF, 3D viewer, filament data for in-progress print). Archive progressively updated with duration, status, camera snapshot on completion.
- **Archive ID availability**: Available early via two paths:
  1. **Primary**: API webhook events include `archive_id` in `data` payload (confirmed from API Reference docs)
  2. **Fallback**: Query `GET /archives?printer_id=X&sort=-created_at&limit=1` and match by filename — archive exists from print start
- **Photo capture**: HA owns multi-camera, multi-stage photo capture. Photos can be uploaded to Bambuddy MID-PRINT since archive exists from start. Includes error/failure photos.
- **Enrichment**: Current shipped behavior PATCHes Bambuddy archives with managed `Filament:<id>` / `Spool:<id>` / `ha_enriched:true` tags, a hidden `[HA_ENRICHMENT_V1]` notes payload, and native `cost`. This prompt still includes broader target-state ideas for later refinement, but they are not the live source of truth.
- **Maintenance**: Bambuddy is source of truth. HA reads maintenance status via API, surfaces in dashboard, allows mark-complete from HA. No local shadow counters.
- **Print Log**: SKIPPED — strict subset of archive data. Only unique field is per-user tracking (requires Advanced Auth, not useful for single-user setup).
- **AMS History**: SKIPPED — HA already records AMS humidity/temperature history via ha-bambulab integration sensors + HA recorder. Bambuddy's AMS history (30-day charts) is a UI visualization with no dedicated API endpoints. No new value for HA.
- **Error photos**: INCLUDED — capture on print_failed, print_stopped, and printer_error (HMS). Uploaded directly to Bambuddy archive (archive exists by then).
- **REST sensors**: `sensor: !include_dir_merge_list rest_sensors` (new loader pattern)
- **Two webhook formats**: Notifications webhook (human-readable) vs API webhook (structured with archive_id). HA should receive the API webhook format.

## Bambuddy Settings (Recommended)
| Setting | Value | Rationale |
|---|---|---|
| Auto-archive prints | ON | Bambuddy creates archives with 3MF metadata, thumbnails, filament data, duplicate detection |
| Save thumbnails | ON | Slicer preview images extracted natively — richer than camera snapshots |
| Capture finish photo | ON | Bambuddy captures its own completion photo; HA's multi-stage photos supplement this |

## Archive Schema (from Bambuddy API docs)

**List**: `GET /archives?limit=N&offset=N&printer_id=&status=&start_date=&end_date=&search=&project_id=`

**Response**:
```json
{
  "total": 1234,
  "archives": [{
    "id": 1, "name": "Benchy", "filename": "benchy.3mf",
    "printer_id": 1, "printer_name": "Workshop X1C",
    "created_at": "2024-01-15T14:30:00Z",
    "duration": 8100, "status": "success",
    "filament_used": 45.2, "filament_type": "PLA"
  }]
}
```

**PATCH**: `PATCH /archives/{id}` — `{"name": "...", "notes": "...", "tags": ["..."]}`
**Photos**: `POST /archives/{id}/photos` — upload image
**Download**: `GET /archives/{id}/3mf`
**Export**: `GET /archives/export?format=csv|xlsx`
**Print Log**: `GET /api/v1/print-log/?search=&printer_id=&status=&date_from=&date_to=&limit=&offset=`

## Enrichment Data Available from HA

At print-start and print-complete, HA already captures:
- **Spoolman spool ID** per tray (from `sensor.spoolman_tray_map`)
- **Filament vendor, name, color hex** per tray
- **Print cost** (from `sensor.print_cost` — weight × price)
- **Per-tray weight used** (from `sensor.*_print_weight` attributes: `AMS Tray 1`, etc.)
- **Task name, print weight, active tray info**

**Enrichment strategy**: On webhook `print_complete`, HA PATCHes the Bambuddy archive with:
- Managed tags: `Filament:<id>`, `Spool:<id>`, `ha_enriched:true`
- Notes: user notes preserved plus hidden `[HA_ENRICHMENT_V1]` JSON payload
- Native field: `cost`

Historical-context note: older sections of this prompt may still discuss broader tag families or human-readable note summaries as design ideas. Treat those as planning context only unless they match the live docs under `docs/features/print_history/`.

## Photo Capture Design

### Multi-Camera, Multi-Stage (with Error Capture)
HA captures photos from multiple cameras at multiple print stages and uploads directly to the Bambuddy archive.

**Cameras** (configured via input helpers):
- Primary: `camera.ntk_ryansoffice_3dprinter_camera` (printer built-in)
- Secondary: Any additional USB/IP cameras (configurable `input_text`)

**Capture Stages** (configurable via input_boolean per stage):
1. **Print started** — first layer visible (delay ~2-5 min after `running` status)
2. **Mid-print** — at configurable progress % (e.g., 25%, 50%, 75%) via `sensor.*_print_progress`
3. **Near-complete** — at ~95% progress, before bed lowers
4. **Print finished** — after completion event (Bambuddy also captures this natively)
5. **Print failed/stopped** — on failure/cancellation event
6. **HMS error** — on printer_error event (immediate diagnostic capture)

**Snapshot light integration**: Reuse existing `input_text.3dprinter_snapshot_light` + brightness pattern from `print_complete_notification.yaml`.

**Archive ID resolution** (for linking photos to the correct archive):
1. **Primary**: `print_started` webhook → HA receives payload with `archive_id` in `data` → stores in `input_text.bambuddy_current_archive_id`
2. **Fallback** (if webhook missed or archive_id not in event): Query `GET /archives?printer_id=X&sort=-created_at&limit=1` → match by filename against current `sensor.*_task_name` → store archive_id
3. Archive exists from print START (confirmed by user observation), so mid-print uploads work immediately

**Photo upload flow**:
1. Capture triggered → save locally to `/config/www/printer_snapshots/{task}_{stage}_{timestamp}.jpg`
2. If `archive_id` is known → upload immediately to Bambuddy via `POST /archives/{id}/photos`
3. If `archive_id` not yet resolved → run fallback lookup, then upload
4. Local copy always retained for HA dashboard use

**Error photo flow**: Same as above but triggered by failure/HMS events. Archive exists since print already started.

## Target Package Structures

### Package 1: `bambuddy_common/`
```
homeassistant/packages/3d_printing/bambuddy_common/
├── bambuddy_common_loader.yaml
├── automations/
│   └── bambuddy_webhook_receiver.yaml       # webhook → fires bambuddy_webhook_event
├── rest_commands/
│   └── bambuddy_refresh_printer_status.yaml
├── rest_sensors/
│   └── bambuddy_printer_status.yaml
└── helpers/
    ├── input_boolean/
    │   └── input_boolean_bambuddy_integration_enabled.yaml
    └── input_text/
        ├── input_text_bambuddy_api_base_url.yaml
        └── input_text_bambuddy_printer_id.yaml
```
Loader domains: automation, sensor, rest_command, input_boolean, input_text

> **Secrets**: The API key is stored in `secrets.yaml` as `bambuddy_api_key` — not as an input_text entity. All REST sensors/commands reference it via `!secret bambuddy_api_key`.

### Package 2: `print_history/`
```
homeassistant/packages/3d_printing/print_history/
├── print_history_loader.yaml
├── automations/
│   ├── bambuddy_capture_archive_id.yaml          # webhook print_started → store archive_id
│   ├── bambuddy_enrich_archive_on_complete.yaml   # during-print + terminal reconciliation → PATCH managed tags/notes/cost
│   ├── bambuddy_capture_print_photos.yaml         # multi-camera, multi-stage photo capture + upload to archive
│   ├── bambuddy_capture_error_photos.yaml         # print_failed/stopped/HMS → immediate capture + upload
│   └── bambuddy_event_history_refresh.yaml        # webhook → refresh REST sensor
├── rest_commands/
│   ├── bambuddy_upload_photo_to_archive.yaml      # POST /archives/{id}/photos
│   ├── bambuddy_delete_archive_photo.yaml         # DELETE /archives/{id}/photos/{photo_id}
│   ├── bambuddy_set_archive_cover.yaml            # PATCH /archives/{id} — set cover_photo_id
│   └── bambuddy_update_archive.yaml               # PATCH /archives/{id} for enrichment + popup edit fields
├── rest_sensors/
│   └── bambuddy_print_history_sensor.yaml         # GET /archives (page 1, recent)
├── scripts/
│   ├── load_history_page.yaml                     # fetch specific page (offset-based)
│   ├── navigate_history.yaml                      # prev/next/first/last
│   ├── capture_and_upload_snapshot.yaml            # multi-camera snapshot → save local + upload to archive
│   └── resolve_current_archive_id.yaml            # fallback: query API by printer_id + match filename
├── template_sensors/
│   ├── bambuddy_last_print_name.yaml
│   ├── bambuddy_last_print_status.yaml
│   ├── bambuddy_last_print_duration.yaml
│   ├── bambuddy_last_print_image_url.yaml
│   ├── print_history_total_pages.yaml
│   └── print_history_page_info.yaml
├── helpers/
│   ├── input_text/
│   │   ├── input_text_bambuddy_current_archive_id.yaml  # set by webhook or fallback lookup
│   │   ├── input_text_history_page_data.yaml
│   │   └── input_text_secondary_camera_entity.yaml      # configurable 2nd camera
│   ├── input_boolean/
│   │   ├── input_boolean_bambuddy_history_sync_enabled.yaml
│   │   ├── input_boolean_capture_at_start.yaml
│   │   ├── input_boolean_capture_at_midprint.yaml
│   │   ├── input_boolean_capture_near_complete.yaml
│   │   └── input_boolean_capture_on_error.yaml
│   └── input_number/
│       ├── input_number_bambuddy_history_limit.yaml
│       ├── input_number_history_current_page.yaml
│       └── input_number_midprint_capture_percent.yaml   # e.g., 50
├── dashboard_cards/
│   ├── print_history.yaml
│   └── print_history_browser.yaml
└── dashboard_views/
    └── view_print_history.yaml
```
Loader domains: automation, sensor, rest_command, script, template, input_text, input_boolean, input_number

### Package 3: `print_queue/`
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
Loader domains: automation, sensor, rest_command, template

### Package 4: `print_statistics/`
```
homeassistant/packages/3d_printing/print_statistics/
├── print_statistics_loader.yaml
├── automations/
│   └── bambuddy_event_stats_refresh.yaml
├── rest_sensors/
│   └── bambuddy_statistics_sensor.yaml
├── template_sensors/
│   ├── bambuddy_success_rate.yaml
│   ├── bambuddy_total_print_time.yaml
│   ├── bambuddy_total_filament_used.yaml
│   └── bambuddy_prints_this_week.yaml
└── dashboard_cards/
    └── statistics.yaml
```
Loader domains: automation, sensor, template

### Package 5: `printer_maintenance/`
```
homeassistant/packages/3d_printing/printer_maintenance/
├── printer_maintenance_loader.yaml
├── automations/
│   ├── bambuddy_maintenance_due_alert.yaml           # sensor due_count 0→>0 → persistent notification
│   └── bambuddy_event_maintenance_refresh.yaml       # webhook print events → refresh catalog sensor
├── rest_commands/
│   └── bambuddy_complete_maintenance_task.yaml       # mark task done in Bambuddy
├── rest_sensors/
│   └── bambuddy_maintenance_status_sensor.yaml       # polls maintenance endpoint per printer
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
Loader domains: automation, sensor, rest_command, script, template, input_boolean

### Documentation Structure
```
docs/features/
├── bambuddy_common/
│   └── README.md
├── print_history/
│   ├── README.md
│   ├── archive-enrichment.md          # Spoolman → Bambuddy tag/notes pipeline
│   └── photo-capture-design.md        # multi-camera, multi-stage capture
├── print_queue/
│   └── README.md
├── print_statistics/
│   └── README.md
└── printer_maintenance/
    └── README.md
```

## Additional Advanced Scenarios Worth Keeping on the Backlog

These are not required for the core 5-package migration, but the live Bambuddy OpenAPI surface makes them realistic follow-on phases once the base packages are stable.

### `print_history/`

- **Timelapse lifecycle** — Beyond auto-scan, Bambuddy supports timelapse info, thumbnail browsing, manual select/upload, delete, and post-processing. This enables a dedicated media-review view for missing or bad timelapses.
- **Archive repair + capability diagnostics** — `rescan`, `rescan-all`, `backfill-hashes`, and `capabilities` endpoints can power an exception dashboard for archives missing source files, previews, hashes, or timelapses.
- **Search + saved views** — `GET /archives/search` gives proper full-text search across print name, filename, tags, notes, designer, and material. This is stronger than local filter-only history browsing.
- **Reprint preflight** — `filament-requirements`, `plates`, `plate-thumbnail`, and `reprint` support a confirmation-driven “reprint from HA” flow when AMS mapping and plate selection are available.
- **Project/source drilldown** — `project-page`, `source`, `f3d`, `gcode`, and `qrcode` endpoints could support an archive detail popup for richer troubleshooting and provenance.

### `print_queue/`

- **Queue lifecycle control** — The queue API supports `start`, `stop`, `cancel`, per-item `PATCH`, bulk updates, and reorder. HA can expose a control surface, not just a passive queue card.
- **Plate-clear verified auto-start** — Bambuddy camera endpoints support `check-plate` plus plate-detection calibration/reference management. This could gate auto-start of the next queued job on a verified empty plate.
- **Model-based / fleet-aware queue views** — Queue items can target a printer model instead of a specific printer. HA can surface “Any X1C” style queue intent and printer readiness.

### `print_statistics/`

- **Energy + efficiency analytics** — `archives/stats` includes `total_energy_kwh`, `total_energy_cost`, `prints_by_printer`, and `time_accuracy_by_printer`, which opens up operational efficiency dashboards.
- **Rolling exception windows** — Date-filtered stats calls can power 7-day and 30-day sensors for rising failure rate, stopped-print spikes, no-output alerts, and recent energy/cost changes.

### `printer_maintenance/`

- **Fleet summary dashboard** — `maintenance/summary` and `maintenance/overview` support cross-printer due/warning rollups and “worst printer first” views.
- **Maintenance policy tuning from HA** — `PATCH /maintenance/items/{item_id}` and `restore-defaults` allow per-printer interval tuning, temporary disable/enable, and recovery from experimental customizations.
- **Wiki-guided exception views** — `maintenance_type_wiki_url` can be surfaced directly in overdue cards so the user can jump from alert to remediation steps.

### `bambuddy_common/`

- **Server health/version sensor** — `updates/version`, `updates/check`, and `updates/status` could provide a lightweight “Bambuddy update available” diagnostic sensor.

## Conversion Reference

Same as previous plan version — see helpers (strip domain wrapper), template sensors (modern format), REST sensors (individual list-item files), REST commands (individual named files), automations (list-item format).

## Steps

### Phase 1: `bambuddy_common` — Shared Infrastructure
*No dependencies. Start here.*

1. Create directory tree
2. Create `bambuddy_common_loader.yaml`
3. Split shared helpers from `bambuddy/helpers.yaml` into individual files (2 input_text + 1 input_boolean). API key stored in `secrets.yaml` as `bambuddy_api_key` — not as an entity.
4. Extract `bambuddy_printer_status` REST sensor
5. Extract `bambuddy_refresh_printer_status` REST command
6. Create `bambuddy_webhook_receiver.yaml` — webhook trigger → fires `bambuddy_webhook_event` with full payload. Normalizes both webhook formats (notifications vs API) into a consistent HA event.
7. Add commented `bambuddy_common_loader` to `_feature_loaders.yaml`
8. Create docs

### Phase 2: `print_history` — Archive Reading, Photo Capture, Enrichment *(depends on Phase 1)*

10. Create directory tree (automations, rest_commands, rest_sensors, scripts, template_sensors, helpers/*, dashboard_cards, dashboard_views)
11. Create `print_history_loader.yaml`
12. **REST sensor**: Extract `bambuddy_print_history_sensor.yaml` (read-only, page 1)
13. **REST commands**: Create `bambuddy_upload_photo_to_archive.yaml` (POST photos), `bambuddy_delete_archive_photo.yaml` (DELETE photo), `bambuddy_set_archive_cover.yaml` (PATCH cover), and `bambuddy_update_archive.yaml` (PATCH tags/notes/cost/favorite)
14. **Archive ID capture automation** (`bambuddy_capture_archive_id.yaml`):
    - Triggers on `bambuddy_webhook_event` where event == `print_started`
    - Extracts `archive_id` from `trigger.event.data.data.archive_id`
    - Stores in `input_text.bambuddy_current_archive_id`
    - Fallback: if archive_id not in payload, queries `GET /archives/?printer_id=X&limit=1` and matches by filename vs current `sensor.*_task_name`
15. **Photo capture automation** (`bambuddy_capture_print_photos.yaml`):
    - Multiple triggers:
      a. Print status → `running` (after configurable delay) — "start" photo
      b. `sensor.*_print_progress` crosses `input_number.midprint_capture_percent` — "mid" photo
      c. `sensor.*_print_progress` ≥ 95% — "near-complete" photo (before bed lowers)
    - Each stage gated by its `input_boolean` toggle
    - Actions: call `script.capture_and_upload_snapshot` with stage name
16. **Error photo automation** (`bambuddy_capture_error_photos.yaml`):
    - Triggers: `print_failed`/`print_stopped` webhook events, `binary_sensor.*_print_error` → "on"
    - Gated by `input_boolean.capture_on_error`
    - Actions: immediate capture via `script.capture_and_upload_snapshot` with stage "error"
17. **Snapshot capture+upload script** (`capture_and_upload_snapshot.yaml`):
    - Turns on snapshot light (if configured), waits 1s
    - Captures from primary camera → saves to `/config/www/printer_snapshots/{task}_{stage}_{timestamp}.jpg`
    - Captures from secondary camera (if configured) → saves similarly
    - Turns off light
    - If `input_text.bambuddy_current_archive_id` is set → uploads to Bambuddy via `rest_command.bambuddy_upload_photo_to_archive`
    - If archive_id not yet known → calls `script.resolve_current_archive_id` first, then uploads
18. **Archive ID fallback script** (`resolve_current_archive_id.yaml`):
    - Queries `GET /archives/?printer_id=X&limit=1`
    - Compares returned archive filename with current `sensor.*_task_name`
    - If match → stores archive_id in `input_text.bambuddy_current_archive_id`
    - If no match → logs warning, skips upload (local photo still saved)
19. **Enrichment automation** (`bambuddy_enrich_archive_on_complete.yaml`):
    - Triggers on `bambuddy_webhook_event` where event == `print_complete` or `print_failed` or `print_stopped`
    - Reads Spoolman data: `sensor.spoolman_tray_map` attributes (spool_id, filament vendor/name/color per tray)
    - Reads print cost: `sensor.print_cost`
    - Reads per-tray weight: `sensor.*_print_weight` attributes
    - Calls `rest_command.bambuddy_update_archive` with merged tags (`spoolman:{spool_id}`, `vendor:{name}`, `material:{type}`, `cost:${amount}`) and structured notes
    - Clears `input_text.bambuddy_current_archive_id` (print cycle complete)
20. **History refresh automation**: triggers on webhook print_complete/print_failed → refreshes REST sensor
21. **Pagination scripts**: `load_history_page.yaml`, `navigate_history.yaml` (offset-based)
22. **Template sensors**: Convert 4 last-print sensors (modern format) + 2 pagination sensors
23. **Helpers**: bambuddy_current_archive_id, history_page_data, secondary_camera_entity, history_fetch_enabled, capture booleans (4 — start/mid/near-complete/error), midprint_capture_percent, history_limit, history_current_page
24. **Dashboard cards**: print_history.yaml (compact summary), print_history_browser.yaml (paginated)
25. **Dashboard view**: view_print_history.yaml
26. Wire loader, create docs (including photo-capture-design.md and archive-enrichment.md)

### Phase 3: `print_queue` *(depends on Phase 1; parallel with Phase 2)*

25. Create directory tree, loader
26. Webhook listener for queue_ready
27. Extract 2 queue REST commands
28. Extract queue REST sensor + queue_count template sensor
29. Move queue dashboard card
30. Wire loader, create docs

### Phase 4: `print_statistics` *(depends on Phase 1; parallel with Phases 2-3)*

31. Create directory tree, loader
32. Webhook listener for stats refresh
33. Extract statistics REST sensor
34. Convert 4 template sensors
35. Move statistics dashboard card
36. Wire loader, create docs

### Phase 5: `printer_maintenance` *(depends on Phase 1 + Phase 4)*

37. Create directory tree (automations, rest_commands, scripts, rest_sensors, template_sensors, helpers, dashboard_cards, dashboard_views)
38. Create `printer_maintenance_loader.yaml`
39. **REST sensor**: `bambuddy_maintenance_status_sensor.yaml` — polls Bambuddy maintenance status per printer (task list, due status, last completed, intervals)
40. **REST command**: `bambuddy_complete_maintenance_task.yaml` — mark task done
41. **Template sensors** (3): due_count, due_list, health_score — derived from REST sensor attributes
42. **Script**: `complete_maintenance_task.yaml` — calls REST command → refreshes sensor
43. **Automations**: due_alert (count 0→>0), webhook event listener (refresh after print events)
44. **Helpers**: maintenance_alerts_enabled boolean
45. **Dashboard cards** (3): due_section (main view chip), catalog_card (full table + mark-complete buttons), health_card
46. **Dashboard view**: view_maintenance.yaml
47. Wire loader, create docs

### Phase 6: Cleanup *(depends on Phases 1-5)*

48. Delete root `bambuddy/` directory
49. Delete `homeassistant/packages/3d_printing/bambuddy_integration/`
50. Delete `docs/features/bambuddy_integration/`
51. Remove old `#bambuddy_integration_loader` from `_feature_loaders.yaml`
52. Update cross-references
53. Migrate unique content from `bambuddy/README.md` to `docs/features/bambuddy_common/README.md`

### Phase 7: Verification *(depends on Phase 6)*

54. HA config check
55. Entity audit: ~5 REST sensors, ~13 template sensors, ~8 REST commands, ~14 helpers, ~9 automations, ~5 scripts
56. Photo capture test: trigger at each stage (start, mid, near-complete) → verify local save + Bambuddy upload
57. Enrichment test: complete a print → verify Spoolman tags/notes appear in Bambuddy archive
58. Dashboard: all cards + dedicated history view + dedicated maintenance view
59. History pagination: navigate past page 1
60. Maintenance: mark task complete from HA → verify in Bambuddy
61. Uncomment all 5 loaders, deploy, verify

## Relevant Files

### Source (to decompose/eliminate)
- `bambuddy/helpers.yaml` — split shared helpers
- `bambuddy/sensors.yaml` — extract REST sensors + convert template sensors
- `bambuddy/rest_commands.yaml` — extract per-command files; ELIMINATE create_archive (Bambuddy auto-creates at completion); KEEP update_archive
- `bambuddy/automations/sync_print_history.yaml` — ELIMINATE (Bambuddy auto-archives; HA no longer creates archives)
- `bambuddy/automations/update_archive_on_complete.yaml` — REPLACE with enrichment automation (resolve_archive_and_upload script)
- `bambuddy/automations/webhook_handler.yaml` — REPLACE with event-based receiver + per-package listeners
- `bambuddy/automations/maintenance_alerts.yaml` — REPLACE with Bambuddy API-driven maintenance package
- `bambuddy/dashboards/` — move to dashboard_cards/ with updates
- `homeassistant/packages/3d_printing/bambuddy_integration/` — DELETE (replaced)

### Reference (existing patterns)
- `notifications/automations/print_complete_notification.yaml` — snapshot light + camera.snapshot pattern to REUSE
- `spoolman_sync/automations/print_started-capture_print_data.yaml` — Spoolman data capture pattern
- `spoolman_sync/automations/print_complete-update_filament_usage.yaml` — per-tray weight data
- `core/template_sensors/spoolman_tray_map.yaml` — spool_id per tray
- `core/template_sensors/print_cost.yaml` — cost sensor
- `spoolman_sync/spoolman_sync_loader.yaml` — loader convention reference
- `filament_catalog/filament_catalog_loader.yaml` — complex loader reference

## Further Considerations

1. **Bambuddy maintenance API**: Confirmed in the live OpenAPI spec. Use `GET /api/v1/maintenance/printers/{printer_id}`, `GET /api/v1/maintenance/overview`, `GET /api/v1/maintenance/summary`, and `POST /api/v1/maintenance/items/{item_id}/perform`.
2. **Photo upload content type**: `POST /archives/{id}/photos` likely expects `multipart/form-data` with a file upload. This may require `shell_command` (curl) rather than `rest_command` (which doesn't support file uploads natively). Design should include both paths with curl fallback.
3. **Two webhook formats**: Bambuddy docs show two different webhook payload formats: (a) Notifications webhook (human-readable, flat, no archive_id) used by notification providers, and (b) API webhook (structured with `data` object containing `archive_id`). The webhook receiver should handle both formats gracefully. HA should be configured as a "Webhook (Custom)" provider in Bambuddy — need to confirm which format that uses. The API Reference shows `archive_id` but the Notifications > Webhook (Custom) section shows the flat format. May need to test both.
4. **print_started webhook archive_id**: The API docs still need a live verification that `print_started` carries `archive_id` in the same way `print_complete` does. Keep the fallback lookup path even if tests confirm it.
5. **Maintenance view registration**: `view_maintenance.yaml` and `view_print_history.yaml` must be added to `common/dashboards/_dashboards.yaml`.
6. **Enrichment idempotency**: `bambuddy_enrich_archive_on_complete` should be idempotent — PATCHing tags/notes twice for the same archive shouldn't create duplicates.
7. **Bambuddy webhook image field**: Bambuddy webhook payloads can include a base64-encoded JPEG `image` field for certain events (First Layer Complete, Print Started, Print Completed). This is separate from HA's own camera capture and could be decoded+saved locally as bonus data.
8. **Timelapse/media follow-on**: The archive API now exposes a full timelapse lifecycle (`scan`, `select`, `upload`, `process`, `info`, `thumbnails`) plus archive repair endpoints (`rescan`, `rescan-all`, `backfill-hashes`). These should stay out of core migration scope but are strong Phase 2.x candidates.
