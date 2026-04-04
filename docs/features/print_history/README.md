# Print History — Archive Reading, Photo Capture & Enrichment

> **⚠️ OpenAPI Corrections Applied**: See [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for full cross-reference against Bambuddy v0.2.2.2 OpenAPI spec. Key fixes already in code: trailing slash URLs, flat array responses (not dict wrapper), offset-based pagination (not page-based), no `sort`/`order` query params.

## Overview

Reads print archives from Bambuddy's API, captures multi-camera photos at multiple print stages (including errors), enriches completed archives with Spoolman spool data, and exposes a full-width dashboard browser with an always-visible control bar in Home Assistant.

**HA Role**: READ archives + CAPTURE multi-stage photos + ENRICH with Spoolman data + SURFACE in dashboard. Bambuddy owns archive creation (auto-creates at print start with 3MF metadata, thumbnails, filament data).

**Current Status**: The browser-first dashboard, filter/sort/page pipeline, and archive card variants are implemented and active. The `Detail` variant renders as a full-width single-row layout, while `Compact` and `Media` remain grid-oriented and responsive to available width. Multi-stage photos are captured locally and now use a shipped first-phase multipart upload bridge with archive-detail verification. The archive browser now opens a per-print detail popup from each card using the same Lovelace pattern as the filament catalog: `custom:auto-entities` generates one `custom:button-card` per archive, shared button-card templates render the cards, and a shared popup template provides the `browser_mod.popup` action. Archive favorites are toggleable from both the card views and the popup, the popup supports helper-backed edits for `print_name`, `tags`, `notes`, `status`, and `failure_reason`, and the popup also exposes a shipped manual `Re-Enrich` action for older archives. Remaining advanced mutation flows are mostly compare/deep-link and full photo-review workflows rather than basic archive editing.

## Event Source Split

The current implementation mixes two data sources:

- **Archive REST pulls** provide the archive list, the most recent print, archive detail, and a fallback way to infer the active archive during a running print.
- **Lifecycle events** come from a mix of `bambuddy_webhook_event` (`print_started`, `print_complete`, `print_failed`, `print_stopped`) and native `bambu_lab` device triggers (`event_print_started`, `event_print_finished`, `event_print_canceled`, printer error events).

That means the archive API is already enough for browsing history and, in a simple single-printer setup, often enough to infer the current archive for in-progress photo uploads. It is not enough to preserve the full shipped event-driven behavior by itself, because several automations still trigger only from webhook-derived events.

### Recommended Direction

- Prefer native `bambu_lab` triggers and printer sensors whenever they already represent the same lifecycle event in Home Assistant.
- Remove Bambuddy webhook listeners for events that are already replicated by the Bambu integration, to avoid duplicate firing and split lifecycle ownership.
- Keep Bambuddy webhook handling only where it adds information HA does not otherwise have, such as direct `archive_id` delivery at `print_started`, or any printer outcome that cannot be reproduced reliably on the current printer model from native triggers and sensors.

In practical terms for the current P1S-oriented design:

- `print_complete` should trend toward native `event_print_finished`.
- `print_stopped` should trend toward native `event_print_canceled`.
- Printer/HMS fault handling should trend toward native printer error events or the existing `print_error` and `hms_errors` entities.
- `print_started` webhook should be retained if it remains the only clean source of Bambuddy `archive_id`.
- `print_failed` webhook should be retained until native failure semantics are verified as equivalent on this printer model.

For the activity heatmap, the live metric contract is now: `Print Count` = archive rows, `Number of Printed Objects` = summed API `object_count`, and `Filaments Used` = summed per-archive populated filament slots. A backend-only single-source-of-truth heatmap filter path was analyzed and deferred pending a dedicated full-scope activity payload.

## Package Structure

```
homeassistant/packages/3d_printing/print_history/
├── print_history_loader.yaml
├── automations/
│   ├── bambuddy_capture_archive_id.yaml          # webhook print_started → store archive_id
│   ├── bambuddy_enrich_archive_on_complete.yaml   # during-print + terminal enrichment → PATCH managed tags/notes/cost
│   ├── bambuddy_capture_print_photos.yaml         # multi-camera, multi-stage photo capture + upload
│   ├── bambuddy_capture_error_photos.yaml         # print_failed/stopped + native cancel + print_error/HMS sensors → immediate capture + upload
│   ├── bambuddy_event_history_refresh.yaml        # webhook/native lifecycle events → refresh REST sensor + archive cache
│   ├── print_history_sync_filter_options.yaml     # populate dynamic filter options from archive cache
│   └── print_history_reset_page_on_filter_change.yaml # reset browser page on filter/sort changes
├── rest_commands/
│   ├── bambuddy_fetch_archives.yaml               # GET /archives — bulk fetch for browser cache
│   ├── bambuddy_delete_archive_photo.yaml         # DELETE /archives/{id}/photos/{filename} (advanced review flow)
│   ├── bambuddy_get_archive_detail.yaml           # GET /archives/{id} for upload verification and future detail flows
│   ├── bambuddy_set_archive_cover.yaml            # PATCH /archives/{id} — cover-photo contract still needs live validation
│   ├── bambuddy_update_archive.yaml               # PATCH /archives/{id} — enrichment + popup edit fields
│   └── bambuddy_query_recent_archive.yaml         # GET /archives — fallback archive_id resolution
├── rest_sensors/
│   └── bambuddy_print_history_sensor.yaml         # GET /archives (page 1, recent)
├── scripts/
│   ├── load_history_page.yaml                     # set current browser page
│   ├── navigate_history.yaml                      # prev/next/first/last within Layer 2 totals
│   ├── capture_and_upload_snapshot.yaml            # multi-camera snapshot → save + upload
│   ├── resolve_current_archive_id.yaml            # fallback: query API → match filename
│   ├── refresh_print_history_archives.yaml        # manual trigger for archive cache refresh
│   ├── reenrich_print_history_archive.yaml        # rebuild managed enrichment for older archives
│   ├── save_print_history_archive_popup_edits.yaml # persist popup edits while preserving hidden enrichment metadata
│   ├── toggle_print_history_archive_favorite.yaml # toggle archive favorite state from cards/popup
│   ├── clear_print_history_filters.yaml           # reset browser controls to defaults
│   └── toggle_print_history_color_filter.yaml     # toggle a color in the multi-select chip row
├── template_sensors/
│   ├── print_history_archives.yaml                # Layer 1 bulk archive cache + field projection
│   ├── print_history_filtered.yaml                # Layer 2 filter/sort/page metadata
│   ├── print_history_page_info.yaml               # human-readable page label
│   └── print_history_archive_data.yaml            # current page slice for dashboard rendering
├── helpers/
│   ├── input_text/
│   │   ├── input_text_bambuddy_current_archive_id.yaml
│   │   ├── input_text_bambuddy_last_photo_upload_result.yaml
│   │   ├── input_text_bambuddy_tray_map_snapshot.yaml
│   │   ├── input_text_print_history_activity_selected_date.yaml
│   │   ├── input_text_print_history_filter_colors.yaml
│   │   ├── input_text_print_history_popup_archive_id.yaml
│   │   ├── input_text_print_history_popup_notes.yaml
│   │   ├── input_text_print_history_popup_print_name.yaml
│   │   ├── input_text_print_history_popup_tags.yaml
│   │   └── input_text_print_history_search.yaml
│   ├── counter/
│   │   └── bambuddy_captured_photo_count.yaml
│   ├── input_boolean/
│   │   ├── input_boolean_bambuddy_history_sync_enabled.yaml
│   │   ├── input_boolean_capture_at_start.yaml
│   │   ├── input_boolean_capture_at_midprint.yaml
│   │   ├── input_boolean_capture_near_complete.yaml
│   │   ├── input_boolean_capture_on_error.yaml
│   │   ├── input_boolean_print_history_show_activity_heatmap.yaml
│   │   └── input_boolean_print_history_filter_favorites_only.yaml
│   ├── input_number/
│   │   ├── input_number_bambuddy_history_limit.yaml
│   │   ├── input_number_history_current_page.yaml
│   │   ├── input_number_midprint_capture_percent.yaml
│   │   ├── input_number_print_history_page_size.yaml
│   │   ├── input_number_print_history_max_archives.yaml
│   │   └── input_number_photo_review_timeout_hours.yaml
│   └── input_select/
│       ├── input_select_bambuddy_photo_review_state.yaml
│       ├── input_select_secondary_camera_entity.yaml
│       ├── input_select_print_history_activity_metric.yaml
│       ├── input_select_print_history_filter_*.yaml
│       ├── input_select_print_history_popup_failure_reason.yaml
│       ├── input_select_print_history_popup_status.yaml
│       ├── input_select_print_history_sort.yaml
│       └── input_select_print_history_card_variant.yaml
├── dashboard_cards/
│   ├── print_history_activity_panel.yaml          # wrapper: separator-bar controls and heatmap
│   ├── print_history_activity_heatmap.yaml        # GitHub-style heatmap card config
│   ├── print_history.yaml                         # responsive archive renderer (Compact / Media / Detail)
│   ├── print_history_browser.yaml                 # browser header: search, filters, matches, settings, color chips
│   ├── print_history_top_controls.yaml            # top/bottom control strip: page nav, page size, layout, refresh
│   └── photo_review_chip.yaml                     # conditional review-status chip; full popup flow still deferred
└── dashboard_views/
    └── view_print_history.yaml
```

## Loader Domains

```yaml
# print_history_loader.yaml
automation: !include_dir_merge_list automations
rest: !include_dir_merge_list rest_sensors
rest_command: !include_dir_merge_named rest_commands
shell_command: !include_dir_merge_named shell_commands
script: !include_dir_merge_named scripts
template: !include_dir_merge_list template_sensors
counter: !include_dir_merge_named helpers/counter
input_text: !include_dir_merge_named helpers/input_text
input_boolean: !include_dir_merge_named helpers/input_boolean
input_number: !include_dir_merge_named helpers/input_number
input_select: !include_dir_merge_named helpers/input_select
```

## Entity Reference

### REST Sensors

| Entity | Endpoint | Interval | Attributes |
|---|---|---|---|
| `sensor.bambuddy_print_history` | `GET /api/v1/archives/?limit=N` | 5 min | Flat array — count via `value_json \| count`, first item via `value_json[0]` |

> **OpenAPI note**: No `sort` or `order` query params exist. Default ordering is assumed newest-first. No `total` or `page` attributes — response is a flat `ArchiveResponse[]` array.

### REST Commands

| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_delete_archive_photo` | DELETE | `/api/v1/archives/{id}/photos/{filename}` | Advanced review placeholder; filename-based delete confirmed |
| `rest_command.bambuddy_get_archive_detail` | GET | `/api/v1/archives/{id}` | Point lookup used for upload verification and future detail flows |
| `rest_command.bambuddy_set_archive_cover` | PATCH | `/api/v1/archives/{id}` | Advanced review placeholder; cover contract still needs live verification |
| `rest_command.bambuddy_update_archive` | PATCH | `/api/v1/archives/{id}` | Update archive metadata such as name, notes, tags, cost, status, and failure reason |
| `rest_command.bambuddy_query_recent_archive` | GET | `/api/v1/archives/?limit=1` | Fallback archive_id resolution |
| `rest_command.bambuddy_fetch_archives` | GET | `/api/v1/archives/?limit=N` | Bulk archive fetch for Layer 1 browser cache |

### Template Sensors

| Entity | Source | Purpose |
|---|---|---|
| `sensor.print_history_archives` | Trigger-based template sensor + `rest_command.bambuddy_fetch_archives` | Layer 1 projected archive cache |
| `sensor.print_history_filtered` | `sensor.print_history_archives` + browser helpers | Layer 2 filtered/sorted/paged browser output |
| `sensor.bambuddy_last_print_name` | `archives[0].print_name` | Most recent print name |
| `sensor.bambuddy_last_print_status` | `archives[0].status` | Most recent print result |
| `sensor.bambuddy_last_print_duration` | `archives[0].actual_time_seconds` | Most recent print time (hours) |
| `sensor.bambuddy_last_print_image_url` | `{base_url}/api/v1/archives/{id}/thumbnail` | Most recent print thumbnail (constructed URL) |
| `sensor.print_history_page_info` | `history_current_page + filtered total_pages` | Display string for pagination UI |
| `sensor.print_history_page_archives` | `sensor.print_history_archives` + helpers | Current visible archive slice for dashboard rendering |

> **OpenAPI note**: The field is `print_name` (not `name`), `actual_time_seconds` (not `duration_seconds`), and thumbnail is accessed via `GET /api/v1/archives/{id}/thumbnail` (unauthenticated). There is no `photo_url` field.

### Helpers

| Entity | Type | Purpose | Persists? |
|---|---|---|---|
| `input_text.bambuddy_current_archive_id` | input_text | Current print's archive_id (set by webhook, cleared on complete) | No `initial:` — survives restart |
| `input_text.bambuddy_last_photo_upload_result` | input_text | Last capture/upload verification summary for operator debugging | No `initial:` |
| `input_text.print_history_activity_selected_date` | input_text | Selected day for the activity heatmap drill-in (`YYYY-MM-DD`) | - |
| `input_text.print_history_search` | input_text | Browser search text | — |
| `input_text.print_history_filter_colors` | input_text | Multi-select color filter state as comma-separated hex values | — |
| `input_select.secondary_camera_entity` | input_select | Configurable secondary camera choice from the known auxiliary cameras, or `None` | — |
| `input_text.bambuddy_tray_map_snapshot` | input_text | Simplified tray→spool_id snapshot captured at print start (Tier 2 matching) | No `initial:` |
| `input_boolean.bambuddy_history_sync_enabled` | input_boolean | Enable/disable history sync features (refresh, cache sync, capture sync) | — |
| `input_boolean.capture_at_start` | input_boolean | Enable photo capture at print start | — |
| `input_boolean.capture_at_midprint` | input_boolean | Enable photo capture at mid-print % | — |
| `input_boolean.capture_near_complete` | input_boolean | Enable photo capture at ~99% | — |
| `input_boolean.capture_on_error` | input_boolean | Enable photo capture on error/failure | — |
| `input_boolean.print_history_show_activity_heatmap` | input_boolean | Collapse/expand the heatmap body while keeping the activity separator controls visible | — |
| `input_number.bambuddy_history_limit` | input_number | Number of history entries per page (5–50) | — |
| `input_number.history_current_page` | input_number | Current pagination page | — |
| `input_number.print_history_page_size` | input_number | Browser page size for Layer 2 paging | — |
| `input_number.print_history_max_archives` | input_number | Max archives fetched into the browser cache | — |
| `input_number.midprint_capture_percent` | input_number | Progress % for mid-print capture (e.g., 50) | — |
| `input_number.photo_review_timeout_hours` | input_number | Hours before review auto-dismisses (default: 24) | — |
| `counter.bambuddy_captured_photo_count` | counter | Number of photos captured in the current print cycle | Reset on `print_started` |
| `input_select.bambuddy_photo_review_state` | input_select | Review lifecycle: `idle`, `pending`, `reviewing` | — |
| `input_select.print_history_activity_metric` | input_select | Heatmap mode: count, weight, dominant color, outcome, objects, cost, filaments used, or total printing time | - |
| `input_select.print_history_filter_*` | input_select | Browser filter state (status/material/printer/date/designer/project/layer/tag) | — |
| `input_text.print_history_popup_*` | input_text | Helper-backed popup edit state for archive ID, print name, tags, and notes | — |
| `input_select.print_history_popup_*` | input_select | Helper-backed popup edit state for archive status and failure reason | — |
| `input_boolean.print_history_filter_favorites_only` | input_boolean | Favorites-only toggle in the browser header | — |
| `input_select.print_history_sort` | input_select | Browser sort mode | — |
| `input_select.print_history_card_variant` | input_select | Compact / Media / Detail renderer selection | — |

### Scripts

| Script | Purpose |
|---|---|
| `script.load_history_page` | Set a specific browser page |
| `script.navigate_history` | Prev/next/first/last navigation, calls `load_history_page` |
| `script.capture_and_upload_snapshot` | Multi-camera capture + local save + count tracking + upload verification via archive detail |
| `script.resolve_current_archive_id` | Fallback: query Bambuddy API, match by filename, store archive_id |
| `script.reenrich_print_history_archive` | Manual popup action: rebuild managed enrichment for an older archive while preserving user notes/tags |
| `script.save_print_history_archive_popup_edits` | Save popup edits while preserving hidden enrichment metadata |
| `script.toggle_print_history_archive_favorite` | Toggle an archive's favorite state from the card or popup |
| `script.refresh_print_history_archives` | Fire a manual Layer 1 refresh event |
| `script.clear_print_history_filters` | Reset browser controls back to defaults |
| `script.toggle_print_history_color_filter` | Add/remove a color from the active color-chip filter |

Deferred advanced scripts:

- `script.review_delete_photo`
- `script.review_replace_photo`
- `script.review_set_cover`
- `script.review_dismiss`

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_capture_archive_id` | `bambuddy_webhook_event` where event=`print_started` | Store archive_id from payload (or fallback lookup) |
| `bambuddy_capture_print_photos` | Print running + progress milestones | Multi-stage photo capture via `capture_and_upload_snapshot` |
| `bambuddy_capture_error_photos` | print_failed webhook, print_stopped webhook or native cancel event, print_error + HMS error sensors | Error photo capture via `capture_and_upload_snapshot` |
| `bambuddy_enrich_archive_on_complete` | during-print weight readiness, archive ID availability, HA startup, and `bambuddy_webhook_event` where event=`print_complete`/`print_failed`/`print_stopped` | PATCH archive with managed `Filament:` / `Spool:` tags, hidden `[HA_ENRICHMENT_V1]` notes payload, and native `cost`; clear archive_id on terminal pass |
| `bambuddy_event_history_refresh` | `bambuddy_webhook_event` where event=`print_complete`/`print_failed`/`print_stopped`, plus native cancel event for cancelled outcomes | Refresh REST sensor + Layer 1 archive cache |
| `print_history_sync_filter_options` | `sensor.print_history_archives` changes, HA startup | Update dynamic filter dropdown options |
| `print_history_reset_page_on_filter_change` | filter/sort helper changes | Reset browser page to 1 |

### Operating Without Webhook

If `bambuddy_common` webhook reception is not configured, the package still has partial value:

- History browsing still works because it is archive-API driven.
- Start, mid-print, and near-complete photo captures still work because those triggers come from HA printer sensors.
- Upload can still work because `script.capture_and_upload_snapshot` falls back to `script.resolve_current_archive_id`, which queries the newest archive and matches against the current task name.

But these shipped behaviors are currently webhook-dependent and will not fire reliably without it:

- `bambuddy_capture_archive_id` startup reset path for current-print runtime state
- `finish` capture in `bambuddy_capture_print_photos`
- `print_failed` error captures unless the HMS or print-error sensors happen to catch the case
- `bambuddy_enrich_archive_on_complete`
- `bambuddy_event_history_refresh` immediate post-print refresh

If both Bambuddy webhook reception and the native `bambu_lab` cancel trigger are enabled, a single user stop/cancel can reach HA twice. Any automation listening to both sources can therefore run twice unless it has explicit deduplication.

The current archive fallback is intentionally minimal and should be treated as a convenience path, not as an exact replacement for lifecycle events. Today it uses `GET /api/v1/archives/?limit=1` and a task-name substring match.

## Key Design Details

### Implemented vs Deferred

Implemented now:

- Layer 1 archive fetch + projection via `sensor.print_history_archives`
- Layer 2 filtering, sorting, page metadata, and page slice sensors
- Browser header with search, matches, filter pills, settings popup, clear actions, and color chips
- GitHub-style activity heatmap with count, weight, dominant-color, and outcome-mix modes, plus a separator chevron to collapse or expand the heatmap body
- Day drill-in cards that can follow the active browser filters or ignore them
- Repeated top/bottom control strip with page navigation, page-size slider, layout toggles, and refresh
- Archive grid renderer with `Compact`, `Media`, and `Detail` variants

Still deferred:

- Photo review popup plus delete/replace/set-cover/dismiss actions
- Compare/deep-link actions and richer follow-on archive workflows
- Feature-local popup/card template ownership inside `print_history`; today the live templates still sit in the shared button-card registry under `common/dashboard_cards/card_templates`

Popup implementation notes for the current shipped path:

- The archive renderer is now YAML-only; the removed custom Lovelace JS card path is no longer part of the active implementation.
- `sensor.print_history_page_archives` remains the only archive-grid data source; popup content is rendered from that projected page payload rather than a live detail fetch.
- The show/hide image toggle is consumed directly inside the archive card templates, so thumbnail display stays controlled by `input_boolean.print_history_show_images` across all three variants.

For detailed design of the two major subsystems, see:

- **[photo-capture-design.md](photo-capture-design.md)** — Multi-camera, multi-stage photo capture with error photos
- **[archive-enrichment.md](archive-enrichment.md)** — Current archive enrichment contract (managed system tags + hidden notes payload + native cost)
- **[photo-review-design.md](photo-review-design.md)** — Post-print photo review: remove, replace, set cover
- **[filter-sort-design.md](filter-sort-design.md)** — Server-side archive browsing with projected full-archive fields, filters, sorting, and paging
- **[archive-detail-popup-design.md](archive-detail-popup-design.md)** — Issue #753 phased popup plan and current implementation status: per-card drilldown plus the initial helper-backed edit slice are shipped
- **[advanced-features-design.md](advanced-features-design.md)** — Follow-on history capabilities such as favorites, compare, timelapses, repair diagnostics, and reprint preflight
- **[archive-detection-recovery-design.md](archive-detection-recovery-design.md)** — Detection and no-code-change repair architecture for incomplete Bambuddy archives
- **[archive-detection-phase1-scope.md](archive-detection-phase1-scope.md)** — Recommended first build slice: detection and visibility only
- **[archive-detection-implementation-plan.md](archive-detection-implementation-plan.md)** — Design-only phased implementation plan for detection and recovery orchestration
- **[archive-recovery-n8n-design.md](archive-recovery-n8n-design.md)** — Recommended `n8n` workflow design for manual and future automated recovery
- **[archive-exception-ux-design.md](archive-exception-ux-design.md)** — Dashboard and interaction design for incomplete archive visibility
- **[archive-detection-execution-checklist.md](archive-detection-execution-checklist.md)** — Task-level execution checklist before implementation

## Migration Notes

### Prototype Lineage
- **REST sensor**: `bambuddy_print_history` from the root `bambuddy/sensors.yaml` prototype
- **REST commands**: `bambuddy_update_archive_status` prototype evolved into `bambuddy_update_archive` (generalized to support notes, tags, name, cost, status, and failure_reason)
- **Template sensors**: 4 "last print" sensors from the root `bambuddy/sensors.yaml` prototype (converted to modern `template:` format)
- **Dashboard cards**: root `bambuddy/dashboards/print_history.yaml` prototype evolved into `dashboard_cards/`
- **Helpers**: `bambuddy_current_archive_id`, `bambuddy_history_sync_enabled`, `bambuddy_history_limit` originated in the root `bambuddy/helpers.yaml` prototype

### Eliminated
- `bambuddy/automations/sync_print_history.yaml` — Bambuddy auto-creates archives; HA no longer calls `POST /archives`
- `rest_command.bambuddy_create_archive` — same reason
- `rest_command.bambuddy_update_archive_status` — replaced by generalized `bambuddy_update_archive` (PATCH with any fields)

### New (not in root prototype)
- Archive ID capture from webhook events
- Multi-stage photo capture automations (start, mid, near-complete, error)
- `capture_and_upload_snapshot` script with multi-camera + light control + verified upload bridge
- `resolve_current_archive_id` fallback script
- Enrichment automation (managed `Filament:` / `Spool:` tags + hidden `[HA_ENRICHMENT_V1]` note payload + native cost)
- Pagination scripts and template sensors
- Configurable capture stage toggles and secondary camera helper
- Dedicated history view (`view_print_history.yaml`)
- Dashboard cards: `print_history_browser.yaml` (browser header), `print_history_top_controls.yaml` (control strip), `print_history.yaml` (archive grid), `photo_review_chip.yaml` (conditional review chip)
- Wired into main dashboard via `common/dashboards/3d_printing.yaml` views list

## Known Limitations

## Near-Term Follow-Ons

These are worth planning immediately after the core package is stable, but they should stay out of the base Phase 2 migration scope:

- **Browser refinements** — See [filter-sort-design.md](filter-sort-design.md). The Layer 1/Layer 2 browser is now implemented; remaining work is mostly refinement: better printer labels, richer tag chips, optional server-side pre-filtering at very large archive counts, and more polished media/detail card layouts.
- **Heatmap backend unification** — See [filter-sort-design.md](filter-sort-design.md). The current heatmap is correct against the projected archive cache, but a future cleanup could move activity filtering to a dedicated backend activity payload so the card no longer reconstructs its own full filtered working set.
- **Timelapse lifecycle + media review** — See [advanced-features-design.md](advanced-features-design.md). Valuable, but depends on multipart upload and more media-state handling.
- **Archive repair/capability diagnostics** — See [advanced-features-design.md](advanced-features-design.md). Good for exception handling and admin recovery after upgrades or storage changes.
- **Reprint preflight** — See [advanced-features-design.md](advanced-features-design.md). Worth doing only once queue lifecycle controls and AMS mapping are in place.

### Implemented Browser Layer

The Print History view now includes the configurable browser described in the filter/sort design:

1. **Filter and sort layer** — search, filter, sort, and page over a projected in-memory archive dataset.
2. **Always-visible browser header** — Open Bambuddy, settings, filter pills, search, matches, clear actions, and multi-select color chips stay pinned above the archive grid.
3. **Repeated control strip** — page navigation, page-size slider, card-variant toggles, and refresh appear both above and below the archive grid.
4. **Archive card variants** — the history renderer switches between compact, media, and detail cards while keeping a two-column desktop layout and a single-column mobile fallback.
5. **Archive detail popup is live and now actionable** — each archive card opens a `browser_mod.popup`; favorites can be toggled from the card and popup, popup-backed `print_name` / `tags` / `notes` / `status` / `failure_reason` edits can be saved, and a manual `Re-Enrich` action is available. Compare/deep-link and richer follow-on actions remain deferred.

### Thumbnail Images Require Local Network Access

The print history table renders thumbnail images directly from the Bambuddy API (`/api/v1/archives/{id}/thumbnail`). These `<img>` tags execute in the **browser**, not on the HA server. This means:

- **Local access (LAN)**: Thumbnails load correctly, provided the browser can resolve `bambuddy.socko.us` and the connection uses HTTPS (to avoid mixed-content blocking if HA itself is served over HTTPS).
- **Remote access (Nabu Casa / VPN)**: Thumbnails will **not load** because the browser cannot reach the local Bambuddy instance. A broken-image icon or empty space will appear.

The dashboard code includes an `onerror` handler that hides failed images gracefully.

#### Potential Future Workarounds

1. **Server-side relay through HA** — Build an HA automation or proxy endpoint that fetches thumbnails from Bambuddy server-side and streams them back to the browser. No duplicate storage; images work from any access method. HA does not currently offer a built-in generic HTTP proxy, so this would require a custom component or add-on.

2. **Selective reverse proxy exposure** — Use Traefik (or similar) to expose only the read-only thumbnail path (`/api/v1/archives/*/thumbnail`) to the internet over HTTPS, keeping the rest of the Bambuddy API local-only. Minimal attack surface since the thumbnail endpoint is already unauthenticated.

3. **Accept local-only thumbnails** (current approach) — Images work on LAN; a fallback is shown when accessed remotely. Simplest, no infrastructure changes, matches the "Bambuddy stays local" stance.

---

## Dashboard

The Print History view is registered as a tab in the 3D Printing dashboard.

- **View**: `dashboard_views/view_print_history.yaml` — `path: print-history`, `icon: mdi:history`
- **Registration**: `!include ../../print_history/dashboard_views/view_print_history.yaml` in `common/dashboards/3d_printing.yaml`
- **View type**: `panel: true` with a single `vertical-stack` so the review chip, browser header, both control strips, and archive grid stay in one full-width flow

### Layout Design

The dashboard is organized around **a single browser-first surface**. Settings remain part of the feature, but they no longer permanently occupy dashboard real estate. Instead, the print history page exposes them through a popup launched from an in-page button.

#### Visual Layout (Desktop)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Section 1: Print History Browser                                         │
│                                                                             │
│  ┌─ Photo Review Chip (conditional) ─────────────────────────────────────┐ │
│  │ 📸 Photos to Review  (status-only chip; opens more-info today)         │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Browser Header ──────────────────────────────────────────────────────┐ │
│  │ Open Bambuddy  Settings                                               │ │
│  │ Status  Material  Printer  Date                                       │ │
│  │ Designer  Project  Layer Height  Tag  Favorites  Sort                │ │
│  │ Search  Matches  Clear actions (including tag clear when active)      │ │
│  │ Multi-select color chips (one chip per archive color)                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Control Strip ───────────────────────────────────────────────────────┐ │
│  │ ⏮ ◀  1 of 3  Prints/Page  Compact  Media  Detail  🔄  ▶ ⏭            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Print Records ───────────────────────────────────────────────────────┐ │
│  │ Compact / Media / Detail card mode                                   │ │
│  │ ┌───────────────────────────────────────────────────────────────────┐ │ │
│  │ │ [thumb] Benchy                                            ✅      │ │ │
│  │ │ Mar 27 · 2.3h · PLA · 44.8g                                      │ │ │
│  │ ├───────────────────────────────────────────────────────────────────┤ │ │
│  │ │ [larger cover/photo when enabled]                                 │ │ │
│  │ │ Phone Case · PETG · failure detail                                │ │ │
│  │ ├───────────────────────────────────────────────────────────────────┤ │ │
│  │ │ ...                                                               │ │ │
│  │ └───────────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Control Strip ───────────────────────────────────────────────────────┐ │
│  │ ⏮ ◀  1 of 3  Prints/Page  Compact  Media  Detail  🔄  ▶ ⏭            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

Popup launched from `Settings` button:

```
┌─────────────────────────────────────────────┐
│  Print History Settings                     │
│  At Start [✓]  Mid-Print [✓]  Near End [✓] │
│  On Error [✓]  Mid-Print Threshold   50%   │
│  Secondary Camera               [dropdown] │
│  History Sync                        [✓]   │
│  Max Cached Archives                175    │
│  Review Timeout (hrs)                24    │
└─────────────────────────────────────────────┘
```

#### Visual Layout (Mobile — 1 column)

On narrow screens, the browser remains a single stacked flow: review chip, browser header, top control strip, archive cards, then bottom control strip. The color chips wrap naturally into additional rows.

The settings popup remains off-canvas on both desktop and mobile so the primary browsing surface stays dominant.

#### Key Design Decisions

1. **One full-width browser flow** — The photo review chip, browser header, archive cards, and both control strips live inside one `panel: true` vertical stack. This prevents navigation or layout controls from jumping into a secondary column.

2. **Settings move to popup, not a permanent column** — Photo-capture and history/view settings are still important, but they are configuration controls rather than daily browsing content. Moving them into a popup keeps the page focused and also scales better on mobile.

3. **Archive card variants are a first-class view choice** — The page should support at least three presentation modes: compact list, media-first card, and detail card. This allows the same data layer to support quick scanning and richer visual review.

4. **Workflow state stays out of settings UI** — Archive ID, review state, and similar runtime internals should support automations and review flows, but they should not appear as editable settings.

5. **Color filter chips are generated from live archive data** — The browser header exposes one clickable swatch per discovered filament color. The chips use `custom:auto-entities` to build simple built-in `button` cards, and the selected state is stored as a comma-separated hex list in `input_text.print_history_filter_colors`.

6. **Photo review chip stays with the browser** — The chip is contextual to the history workflow and currently acts as a lightweight status surface. It belongs in the same full-width browsing flow as the archive browser.

#### Previous Layout (v1) — Issues

The original layout used **6 separate sections**, each with a single card:

```
Section 1: photo_review_chip     Section 4: capture_settings
Section 2: print_history_table   Section 5: history_settings
Section 3: pagination_browser    Section 6: current_print_diagnostics
```

**Problems:**
- HA's `sections` masonry distributes sections into the shortest column. With 6 small sections, the grid interleaved history and settings cards unpredictably.
- The pagination browser often landed in the right column, visually disconnected from the table it controls.
- The photo review chip floated alone as a tiny section, wasting vertical space.
- Settings had equal visual weight to the history table, making the page feel cluttered.
- On mobile, 6 sections stacked in declaration order, putting capture settings between the table and diagnostics.

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
| 2 | Photo upload content type (multipart file only) | Determines upload mechanism in `capture_and_upload_snapshot` | No — valid transport options are documented |
| 3 | Confirm `input_text.3dprinter_snapshot_light` availability cross-package | If notifications package not deployed, need local fallback | No — gated with template check |
| 4 | Enrichment idempotency — verify PATCH tags doesn't create duplicates | Could pollute tag lists on retry | Low risk — test during Phase 7 |
| 5 | Base64 `image` field in webhook payload — bonus data capture | Bambuddy webhooks can include base64 JPEG for some events | No — nice-to-have, not blocking |
| 6 | Photo list/delete API — confirm `GET` and `DELETE` on `/archives/{id}/photos/{photo_id}` | Required for review delete action | No — review/dismiss still works without it |
| 7 | Cover photo API — confirm `cover_photo_id` field on PATCH | Required for set-as-cover action | No — omit button if unavailable |
| 8 | Upload response schema — does POST photos return `photo_id`? | Manifest needs photo_id for delete/replace mapping | No — can fall back to listing photos |
