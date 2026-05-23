# Print History — Archive Reading, Photo Capture & Enrichment

> **⚠️ OpenAPI Corrections Applied**: See [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for full cross-reference against Bambuddy v0.2.2.2 OpenAPI spec. Key fixes already in code: trailing slash URLs, flat array responses (not dict wrapper), offset-based pagination (not page-based), no `sort`/`order` query params.

## Overview

Reads print archives from Bambuddy's API, captures multi-camera photos at multiple print stages (including errors), enriches completed archives with Spoolman spool data, and exposes a full-width dashboard browser with an always-visible control bar in Home Assistant.

**HA Role**: READ archives + CAPTURE multi-stage photos + ENRICH with Spoolman data + SURFACE in dashboard. Bambuddy owns archive creation (auto-creates at print start with 3MF metadata, thumbnails, filament data).

**Current Status**: The browser-first dashboard, filter/sort/page pipeline, and archive card variants are implemented and active. The active browser backend is the `bambuddy` custom integration in `homeassistant/custom_components/bambuddy/`, with large page and activity payloads now fetched directly by Lovelace custom cards over websocket instead of being materialized into Home Assistant entity state. The `List` variant renders as a full-width single-row layout, while `Compact` and `Media` remain grid-oriented and responsive to available width. The top control strip now also supports a shipped browser multi-select mode for visible-page bulk actions across `Compact`, `Media`, and `List`, including tag edits, project assignment, favorite/unfavorite, and delete. Multi-stage photos are captured locally and now use a shipped multipart upload bridge with archive-detail verification. The archive browser opens a per-print detail popup from each card, the popup supports helper-backed edits for `print_name`, `tags`, `notes`, `project`, `status`, and `failure_reason`, and the popup also exposes shipped manual actions for `Re-Enrich`, primary-photo selection, `Delete Photo`, `Dismiss Review`, phone-driven manual photo upload, and timelapse scan/upload/viewer flows. The media-review slice now persists per-archive state in the Bambuddy Variant 3 store. The first project-assignment slice intentionally only allows picking from existing Bambuddy projects; project creation or broader project-admin flows remain deferred. Remaining advanced mutation flows are mostly compare/deep-link, replace-photo, broader recovery/review lifecycle work, and deeper timelapse processing rather than basic archive editing.

The local Variant 3 archive snapshot now also preserves archive `plate_id` and can hydrate it from live Bambuddy printer status (`current_archive_id` + `current_plate_id`) when the current printer/archive binding is known, so plate-aware local UI flows do not have to rely only on `print_name` suffix inference.

Manual phone-photo upload is documented in `/docs/features/print_history/reference/ui-media/manual-photo-upload.md`.

Timelapse scan/upload/viewer behavior is documented in `/docs/features/print_history/design/ui-media/timelapse-actions-and-viewer.md`.

Tag color assignment for archive tags is documented in `reference/tag-color-contract.md`.

Source `.3mf` import workflow and long-term storage policy are documented in:

- `/docs/features/print_history/design/imports/folder-3mf-catalog-design.md`
- `/docs/features/print_history/design/imports/source-3mf-import-design.md`
- `/docs/features/print_history/planning/imports/source-3mf-import-implementation-plan.md`
- `/docs/features/print_history/design/imports/source-3mf-storage-strategy.md`

Cross-system model-catalog strategy, including the active Manyfold/sidecar/Home Assistant split and archive-to-model linkage planning, is documented in:

- `../model_catalog/README.md`
- `../model_catalog/architecture-overview.md`
- `../model_catalog/integration/ha-model-library-integration.md`

Important current boundary:

- the print-history Variant 3 local SQLite store remains print-history-owned
- cross-feature model-catalog linkage should anchor on archive identity and integration/service contracts, not direct reads of print-history internal tables

For the active print-history control-strip structure and mobile pagination guardrails, see `/docs/features/print_history/reference/browser/top-controls-contract.md`.

## Documentation Map

The print-history docs use lane-first organization with sub-areas nested inside each lifecycle lane.

- `reference/<sub-area>/` - API contracts and canonical operational docs by sub-area
- `design/<sub-area>/` - implementation designs and feature workflow proposals by sub-area
- `planning/<sub-area>/` - roadmap and phased planning docs by sub-area
- `archive/<sub-area>/` - historical documents retained for context
- `examples/` - example payloads and working notes kept alongside the feature docs

Legacy root sub-area folders were removed after link migration; use lane-first sub-area paths only.

## Archived Browser Variants

The retired browser backends remain in-repo for reference only and are no longer part of the Home Assistant deploy path or active GitHub workflows.

- Legacy YAML browser backend: `archive/print_history/legacy-yaml-browser/`
- Variant 1 AppDaemon sidecar: `archive/print_history/appdaemon-browser/`
- Retired AppDaemon image workflow: `archive/print_history/workflows/build-print-history-browser-appdaemon.yml`

Historical design notes:

- `/docs/features/print_history/archive/browser/appdaemon-query-cache.md`
- `/docs/features/print_history/design/browser/filter-sort-design.md`
- `design/external-services-review.md` - now includes a direct O.D.I.N. vs Bambuddy comparison covering archive schema depth, API shape, Vigil AI/local inference, licensing gates, and transition recommendation
- `planning/variant3-metadata-schema-and-variant4-carry-forward.md`
- `planning/print-history-er-diagrams.md` - Issue #1122 ER baseline for local Variant 3 schema plus Bambuddy/sidecar touchpoints
- `planning/metadata-implementation-roadmap.md`

## Related Runtime Repair Docs

For fallback-archive canonical timestamp repair and adjacent orchestration design, see:

- `reference/archive-runtime-db-repair-guide.md`
- `reference/archive-runtime-field-impact-matrix.md`
- `/docs/features/print_history/planning/runtime-repair/archive-runtime-repair-deployment-options.md`
- `/docs/features/print_history/reference/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md`
- `/docs/features/print_history/reference/runtime-repair/archive-runtime-ha-contract.md`
- `/docs/features/print_history/planning/runtime-repair/archive-runtime-restore-implementation-plan.md`
- `reference/archive-runtime-restore-ha-service-and-popup-contract.md`
- `/docs/features/print_history/design/runtime-repair/archive-runtime-restore-ha-ux-design.md`
- `/docs/features/print_history/reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md`
- `/docs/features/print_history/reference/imports/archive-historical-backfill-from-sd-card.md`

## Historical Backfill Execution

If you want to execute the new historical-import tooling, use this order.

### 1. Generate a manifest from the SD backup

```powershell
c:/dev/hass-bambulab-config/.venv/Scripts/python.exe .\tools\bambuddy\generate_archive_backfill_manifest.py --source-root '.\bambuddy\Backup SD Card - 2026-04-03' --output '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json'
```

What this does:

- scans `.3mf` candidates
- computes `MD5` and `SHA-256`
- records basic sliced-versus-source classification
- captures best-effort timestamp evidence from filesystem metadata, ZIP member times, sibling `.bbl` files, and selected config members inside the `.3mf`

### 2. Inspect candidates without creating archives

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' -BackfillAction Inspect
```

What this does:

- loads the manifest
- fetches existing Bambuddy archives
- skips exact `content_hash` duplicates
- reports which candidates are ready, skipped, or need manual review

### 3. Create and annotate new historical archives

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' -BackfillAction Full
```

What this does:

- uploads non-duplicate candidates
- skips raw source-project `.3mf` files by default
- annotates created archives with `historical_import` tags and `[HISTORICAL_IMPORT_V1]` notes

### 4. Optional: allow raw source-project imports

Only do this for manual experiments or provenance-grade imports:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' -BackfillAction Full -AllowSourceProjectImport
```

### 5. Optional: repair canonical runtime fields after import

If you have strong timing evidence, use the existing runtime repair tooling after upload. See:

- `reference/archive-runtime-db-repair-guide.md`
- `/docs/features/print_history/reference/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md`
- `/docs/features/print_history/reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md`

When you know the historical print start time and the archive already exists, the HA integration now provides `bambuddy.repair_print_history_archive_from_start` as the direct operator action for this case. It derives `completed_at` from duration and defaults `created_at` to the same timestamp as `started_at` to match normal Bambuddy archive behavior.

Recommended use of that service:

- use it for existing archives when start-time evidence is trustworthy
- preview first with `dry_run: true`
- supply `duration_seconds` explicitly only when the archive's own duration fields are missing or untrustworthy
- use restore or replacement workflows instead when the archive content itself must change

Primary design reference for the historical-import workflow:

- `/docs/features/print_history/reference/imports/archive-historical-backfill-from-sd-card.md`

### 6. Interpret the results

The Backfill helper returns one result object per manifest candidate.

Most important statuses:

- `skipped_existing_content_hash` - Bambuddy already has an archive whose `content_hash` matches the source file
- `skipped_manifest_state` - the manifest already records that this candidate was handled earlier
- `inspect_ready` - candidate passed the current automatic checks and is eligible for upload
- `manual_review_source_only` - candidate is a raw source-project `.3mf`; inspect manually before importing, or rerun with `-AllowSourceProjectImport` if you accept lower fidelity
- `uploaded` - archive was created, but no provenance notes or tags were written because action was `Upload`
- `uploaded_and_annotated` - archive was created and received historical-import provenance notes and tags

Recommended decision rule:

- import immediately when the candidate is `inspect_ready` and `source_type` is `sd_cache_3mf`
- review manually when the candidate is source-project only, filename/date matching is ambiguous, or you expect canonical runtime repair afterward
- skip confidently when the result is `skipped_existing_content_hash`

What to look for in the manifest before importing:

- `source_type` should usually be `sd_cache_3mf`
- `confidence` should usually be `high` or at least defensible for the intended use
- `structural_signals.has_embedded_gcode` is a strong sign that the file is a sliced artifact
- `structural_signals.bbl_hash_match` is helpful supporting evidence when present
- `timestamp_evidence.timestamp_candidates` should be treated as evidence, not canonical truth, unless validated against known-good history

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
│   ├── bambuddy_event_history_refresh.yaml        # webhook/native lifecycle events → refresh REST sensor + reset browser page; integration refresh is internal
│   └── print_history_reset_page_on_filter_change.yaml # reset browser page on filter/sort changes
├── rest_commands/
│   ├── bambuddy_get_archive_detail.yaml           # GET /archives/{id} for upload verification and future detail flows
│   ├── bambuddy_update_archive.yaml               # PATCH /archives/{id} — enrichment + popup edit fields
│   └── bambuddy_query_recent_archive.yaml         # GET /archives — fallback archive_id resolution
├── scripts/
│   ├── load_history_page.yaml                     # set current browser page
│   ├── navigate_history.yaml                      # prev/next/first/last within Layer 2 totals
│   ├── capture_and_upload_snapshot.yaml            # multi-camera snapshot → save + upload
│   ├── set_print_history_capture_cameras.yaml      # persist chosen camera.* entities via multi-select selector
│   ├── resolve_current_archive_id.yaml            # fallback: query API → match filename
│   ├── refresh_print_history_archives.yaml        # manual trigger for archive cache refresh
│   ├── reenrich_print_history_archive.yaml        # rebuild managed enrichment for older archives
│   ├── backfill_print_history_archive_enrichment.yaml # batch re-enrich a targeted archive list
│   ├── enter_print_history_multi_select_mode.yaml # enter browser multi-select mode and reset shared selection summary helpers
│   ├── cancel_print_history_multi_select_mode.yaml # leave browser multi-select mode and clear shared selection summary helpers
│   ├── request_print_history_multi_select_action.yaml # send one-shot bulk-action requests from the toolbar to the browser card
│   ├── bulk_update_print_history_user_tags.yaml   # add/remove user tags across selected archives while preserving system tags
│   ├── bulk_assign_print_history_project.yaml     # assign or clear one project across selected archives
│   ├── bulk_set_print_history_archive_favorite.yaml # bulk set favorite state across selected archives
│   ├── bulk_delete_print_history_archives.yaml    # bulk delete selected archives
│   ├── save_print_history_archive_popup_edits.yaml # persist popup edits while preserving hidden enrichment metadata
│   ├── toggle_print_history_archive_favorite.yaml # toggle archive favorite state from cards/popup
│   ├── clear_print_history_filters.yaml           # reset browser controls to defaults
│   └── toggle_print_history_color_filter.yaml     # toggle a color in the multi-select chip row
├── template_sensors/
│   ├── active_print_display_name.yaml             # current print display name from archive detail + printer fallback
│   ├── bambuddy_archive_binding_health.yaml       # runtime archive-binding guardrail
│   ├── print_history_payload_diagnostics.yaml     # confirms large page/activity payloads stay out of HA state
│   └── print_history_popup_archive_detail.yaml    # popup detail materialization for the selected archive
├── helpers/
│   ├── input_text/
│   │   ├── input_text_bambuddy_current_archive_id.yaml
│   │   ├── input_text_bambuddy_capture_camera_entities.yaml
│   │   ├── input_text_bambuddy_last_photo_upload_result.yaml
│   │   ├── input_text_bambuddy_tray_map_snapshot.yaml
│   │   ├── input_text_print_history_activity_selected_date.yaml
│   │   ├── input_text_print_history_filter_colors.yaml
│   │   ├── input_text_print_history_multi_select_request.yaml
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
│   │   ├── input_boolean_print_history_multi_select_mode.yaml
│   │   ├── input_boolean_print_history_multi_select_all_favorites.yaml
│   │   ├── input_boolean_print_history_show_activity_heatmap.yaml
│   │   └── input_boolean_print_history_filter_favorites_only.yaml
│   ├── input_number/
│   │   ├── input_number_history_current_page.yaml
│   │   ├── input_number_midprint_capture_percent.yaml
│   │   ├── input_number_print_history_multi_select_count.yaml
│   │   ├── input_number_print_history_page_size.yaml
│   │   ├── input_number_print_history_max_archives.yaml
│   │   └── input_number_photo_review_timeout_hours.yaml
│   └── input_select/
│       ├── input_select_bambuddy_photo_review_state.yaml
│       ├── input_select_print_history_activity_metric.yaml
│       ├── input_select_print_history_filter_*.yaml
│       ├── input_select_print_history_popup_failure_reason.yaml
│       ├── input_select_print_history_popup_project.yaml
│       ├── input_select_print_history_popup_status.yaml
│       ├── input_select_print_history_sort.yaml
│       └── input_select_print_history_card_variant.yaml
├── dashboard_cards/
│   ├── print_history_activity_panel.yaml          # wrapper: separator-bar controls and heatmap
│   ├── print_history_activity_heatmap.yaml        # GitHub-style heatmap card config
│   ├── print_history.yaml                         # responsive archive renderer (Compact / Media / List)
│   ├── print_history_browser.yaml                 # browser header: search, filters, matches, settings, color chips
│   ├── print_history_top_controls.yaml            # top/bottom control strip: page nav, page size, layout, refresh
│   └── photo_review_chip.yaml                     # conditional review-status chip; remaining work is smarter chip → popup targeting
└── dashboard_views/
    └── view_print_history.yaml

archive/print_history/
├── legacy-yaml-browser/                          # retired Layer 1/2/3 browser backend, not deployed
├── appdaemon-browser/                            # retired Variant 1 sidecar, not deployed
└── workflows/                                    # retired AppDaemon image-build workflow, not active
```

## Loader Domains

```yaml
# print_history_loader.yaml
automation: !include_dir_merge_list automations
rest_command: !include_dir_merge_named rest_commands
shell_command: !include_dir_merge_named shell_commands
recorder:
    exclude:
        entities:
            - sensor.bambuddy_print_history_browser_status
            - sensor.bambuddy_print_history_browser_filtered
            - sensor.bambuddy_print_history_browser_page_archives
            - sensor.bambuddy_print_history_browser_page_info
            - sensor.bambuddy_print_history_browser_activity
script: !include_dir_merge_named scripts
template: !include_dir_merge_list template_sensors
counter: !include_dir_merge_named helpers/counter
input_text: !include_dir_merge_named helpers/input_text
input_boolean: !include_dir_merge_named helpers/input_boolean
input_number: !include_dir_merge_named helpers/input_number
input_select: !include_dir_merge_named helpers/input_select
```

## Entity Reference

### REST Commands

| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_get_archive_detail` | GET | `/api/v1/archives/{id}` | Point lookup used for upload verification and future detail flows |
| `rest_command.bambuddy_update_archive` | PATCH | `/api/v1/archives/{id}` | Update archive metadata such as name, notes, tags, project, favorite state, cost, status, and failure reason; payload fields are intentionally optional for safe bulk updates |
| `rest_command.bambuddy_query_recent_archive` | GET | `/api/v1/archives/?limit=1` | Fallback archive_id resolution |

### Template Sensors / Integration Entities

| Entity | Source | Purpose |
|---|---|---|
| `sensor.bambuddy_print_history_browser_status` | Bambuddy custom integration | Browser backend health, sync state, and store path |
| `sensor.bambuddy_print_history_browser_filtered` | Bambuddy custom integration | Filtered-count summary, page info, active filters, and color options |
| `sensor.bambuddy_print_history_browser_page_info` | Bambuddy custom integration | Current page label and total page count |
| `sensor.bambuddy_print_history_browser_activity` | Bambuddy custom integration | Activity-summary entity backing the heatmap and activity controls |
| `sensor.print_history_payload_diagnostics` | Template sensor | Confirms the live browser path stays frontend-only and keeps large payloads out of HA state |
| `sensor.print_history_popup_archive_detail` | Template sensor | Popup-scoped detail cache for one selected archive |

> The older REST-derived `sensor.bambuddy_print_history` and `sensor.bambuddy_last_print_*` entities were retired and moved to `archive/print_history/legacy-yaml-browser/`. The active browser contract now comes from the Bambuddy custom integration entities above.
>
> Recorder policy: all five Bambuddy browser entities are excluded from Home Assistant history. `status`, `filtered`, `page_archives`, `page_info`, and `activity` are all live browser-health or view-state outputs rather than useful long-term historical signals.

### Helpers

| Entity | Type | Purpose | Persists? |
|---|---|---|---|
| `input_text.bambuddy_current_archive_id` | input_text | Current print's archive_id (set by webhook, cleared on complete) | No `initial:` — survives restart |
| `input_text.bambuddy_capture_camera_entities` | input_text | Persisted comma-separated `camera.*` entity list for photo capture; blank falls back to the built-in Bambu camera | No `initial:` — survives restart |
| `input_text.bambuddy_last_photo_upload_result` | input_text | Last capture/upload verification summary for operator debugging | No `initial:` |
| `input_text.print_history_activity_selected_date` | input_text | Selected day for the activity heatmap drill-in (`YYYY-MM-DD`) | - |
| `input_text.print_history_search` | input_text | Browser search text | — |
| `input_text.print_history_filter_colors` | input_text | Multi-select color filter state as comma-separated hex values | — |
| `input_text.print_history_multi_select_request` | input_text | One-shot toolbar request channel for browser multi-select actions | — |
| `input_text.bambuddy_tray_map_snapshot` | input_text | Simplified tray→spool_id snapshot captured at print start (Tier 2 matching) | No `initial:` |
| `input_boolean.bambuddy_history_sync_enabled` | input_boolean | Enable/disable history sync features (refresh, cache sync, capture sync) | — |
| `input_boolean.capture_at_start` | input_boolean | Enable photo capture at print start | — |
| `input_boolean.capture_at_midprint` | input_boolean | Enable photo capture at mid-print % | — |
| `input_boolean.capture_near_complete` | input_boolean | Enable photo capture at ~99% | — |
| `input_boolean.capture_on_error` | input_boolean | Enable photo capture on error/failure | — |
| `input_boolean.print_history_multi_select_mode` | input_boolean | Shared browser toolbar/card flag for whether archive multi-select mode is active | — |
| `input_boolean.print_history_multi_select_all_favorites` | input_boolean | Summary flag indicating whether every currently selected archive is already favorited | — |
| `input_boolean.print_history_show_activity_heatmap` | input_boolean | Collapse/expand the heatmap body while keeping the activity separator controls visible | — |
| `input_boolean.print_history_debug_instrumentation` | input_boolean | Enable browser and heatmap performance instrumentation for future debugging sessions | Off by default |
| `input_number.history_current_page` | input_number | Current pagination page | — |
| `input_number.print_history_multi_select_count` | input_number | Shared selected-count summary for the toolbar while multi-select mode is active | — |
| `input_number.print_history_page_size` | input_number | Browser page size for Layer 2 paging | — |
| `input_number.print_history_max_archives` | input_number | Max archives fetched into the browser cache | — |
| `input_number.midprint_capture_percent` | input_number | Progress % for mid-print capture (e.g., 50) | — |
| `input_number.photo_review_timeout_hours` | input_number | Timeout control reserved for follow-on media-review auto-dismiss lifecycle | — |
| `counter.bambuddy_captured_photo_count` | counter | Number of photos captured in the current print cycle | Reset on `print_started` |
| `input_select.bambuddy_photo_review_state` | input_select | Coarse mirrored review lifecycle signal; per-archive source of truth now lives in store-backed `archive_media_review_state` | — |
| `input_select.print_history_activity_metric` | input_select | Heatmap mode: count, weight, dominant color, outcome, objects, cost, filaments used, or total printing time | - |
| `input_select.print_history_filter_*` | input_select | Browser filter state (status/material/printer/date/designer/project/layer/tag) | — |
| `input_text.print_history_popup_*` | input_text | Helper-backed popup edit state for archive ID, print name, tags, and notes | — |
| `input_select.print_history_popup_*` | input_select | Helper-backed popup edit state for archive status and failure reason | — |
| `input_boolean.print_history_filter_favorites_only` | input_boolean | Favorites-only toggle in the browser header | — |
| `input_select.print_history_sort` | input_select | Browser sort mode | — |
| `input_select.print_history_card_variant` | input_select | Compact / Media / List renderer selection | — |

### Scripts

| Script | Purpose |
|---|---|
| `script.load_history_page` | Set a specific browser page |
| `script.navigate_history` | Prev/next/first/last navigation, calls `load_history_page` |
| `script.capture_and_upload_snapshot` | Multi-camera capture + local save + count tracking + upload verification via archive detail |
| `script.set_print_history_capture_cameras` | Persist the photo-capture camera list using a multi-select camera entity picker |
| `script.resolve_current_archive_id` | Fallback: query Bambuddy API, match by filename, store archive_id |
| `script.reenrich_print_history_archive` | Manual popup action: rebuild managed enrichment for an older archive while preserving user notes/tags; now resolves filament first from color/material/profile hints, then uses location and strict time-window fallback to pick the actual spool when needed |
| `script.backfill_print_history_archive_enrichment` | Batch re-enrich a CSV archive list while deferring browser refresh until the batch completes |
| `script.enter_print_history_multi_select_mode` | Enter browser multi-select mode and reset the shared count/favorite/request helpers |
| `script.cancel_print_history_multi_select_mode` | Leave browser multi-select mode and clear the shared count/favorite/request helpers |
| `script.request_print_history_multi_select_action` | Send a one-shot bulk action request from the toolbar to the browser card |
| `script.bulk_update_print_history_user_tags` | Bulk add/remove user tags while preserving system tags on each selected archive |
| `script.bulk_assign_print_history_project` | Bulk assign one project, or clear it, across selected archives |
| `script.bulk_set_print_history_archive_favorite` | Bulk set the favorite state across selected archives |
| `script.bulk_delete_print_history_archives` | Bulk delete selected archives from Bambuddy |
| `script.save_print_history_archive_popup_edits` | Save popup edits while preserving hidden enrichment metadata |
| `script.toggle_print_history_archive_favorite` | Toggle an archive's favorite state from the card or popup |
| `script.refresh_print_history_archives` | Fire a manual Bambuddy browser refresh through the custom integration |
| `script.clear_print_history_filters` | Reset browser controls back to defaults |
| `script.toggle_print_history_color_filter` | Add/remove a color from the active color-chip filter |

Deferred advanced scripts:

- `script.review_replace_photo`
- `script.review_set_cover`

### Automations

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_capture_archive_id` | `bambuddy_webhook_event` where event=`print_started` | Store archive_id from payload (or fallback lookup) |
| `bambuddy_capture_print_photos` | Print running + progress milestones | Multi-stage photo capture via `capture_and_upload_snapshot` |
| `bambuddy_capture_error_photos` | print_failed webhook, print_stopped webhook or native cancel event, print_error + HMS error sensors | Error photo capture via `capture_and_upload_snapshot` |
| `bambuddy_enrich_archive_on_complete` | during-print weight readiness, archive ID availability, HA startup, and `bambuddy_webhook_event` where event=`print_complete`/`print_failed`/`print_stopped` | PATCH archive with managed `f:` / `s:` tags, hidden `+>` notes payload, and native `cost`; clear archive_id on terminal pass |
| `print_history_browser_refresh_on_event` | `bambuddy_webhook_event` where event=`print_complete`/`print_failed`/`print_stopped`, plus native cancel event for cancelled outcomes | Reset browser paging after lifecycle events; the Bambuddy integration refreshes its own store-backed browser state directly |

The active enrichment payload now uses five completeness tiers in the hidden `+>` note payload: `complete`, `near complete`, `mostly complete`, `partially complete`, and `unavailable`. `Near complete` means only tray information is still missing. `Mostly complete` means every row has a filament ID but at least one row still lacks a spool ID. `Partially complete` means at least one row still lacks a filament ID.
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
- `print_history_browser_refresh_on_event` immediate recent-print sensor refresh and page reset; the Bambuddy integration handles its own post-print store refresh internally

If both Bambuddy webhook reception and the native `bambu_lab` cancel trigger are enabled, a single user stop/cancel can reach HA twice. Any automation listening to both sources can therefore run twice unless it has explicit deduplication.

The current archive fallback is intentionally minimal and should be treated as a convenience path, not as an exact replacement for lifecycle events. Today it uses `GET /api/v1/archives/?limit=1` and a task-name substring match.

## Key Design Details

### Implemented vs Deferred

Implemented now:

- Bambuddy custom integration with local materialized store as the browser cache boundary
- Integration-owned filtering, sorting, page metadata, current-page summary, and activity summary entities
- Frontend websocket queries for archive rows and heatmap activity, plus integration-backed archive-detail lookups for popup flows
- Browser header with search, matches, filter pills, settings popup, clear actions, and color chips
- GitHub-style activity heatmap with count, weight, dominant-color, and outcome-mix modes, plus a separator chevron to collapse or expand the heatmap body
- Day drill-in cards that can follow the active browser filters or ignore them
- Repeated top/bottom control strip with page navigation, page-size slider, layout toggles, and refresh
- Archive grid renderer with `Compact`, `Media`, and `List` variants
- Browser multi-select mode with visible-page selection and bulk tag/project/favorite/delete actions
- Popup edit/save flows for `print_name`, `tags`, `notes`, `project`, `status`, and `failure_reason`
- Store-backed media review primitives plus popup/gallery actions for primary-photo selection, photo upload, photo delete, and dismiss review
- Archive-issue detection and browser/popup surfacing for missing core 3MF, source-only, and missing-thumbnail states

Still deferred:

- Replace-photo orchestration, smarter chip-target handoff, and auto-dismiss lifecycle for media review
- Compare/deep-link actions and richer follow-on archive workflows
- Feature-local popup/card template ownership inside `print_history`; today the live templates still sit in the shared button-card registry under `common/dashboard_cards/card_templates`

Popup implementation notes for the current shipped path:

- The archive renderer is the active `custom:print-history-browser-card` resource under `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`.
- The browser card queries Bambuddy directly over websocket with `bambuddy/print_history_query`, so the visible archive rows are not materialized into Home Assistant entity state.
- Popup open now follows a `browser_mod.sequence` flow from the browser card itself: helper state is set first, then the popup renders the photo gallery, popup content card, tag editor, and edit controls.
- `sensor.bambuddy_print_history_browser_page_archives` and `sensor.bambuddy_print_history_browser_activity` remain lightweight summary entities for status and counts; detailed page/activity payloads stay frontend-only.
- The show/hide image toggle is still controlled by `input_boolean.print_history_show_images`, but the rendering logic now lives in the custom browser and gallery cards rather than shared archive card templates.

For detailed design of the two major subsystems, see:

- **[photo-capture-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/ui-media/photo-capture-design.md


)** — Multi-camera, multi-stage photo capture with error photos
- **[archive-enrichment-current.md](reference/archive-enrichment-current.md)** — Current archive enrichment contract (managed system tags + hidden notes payload + native cost)
- **[archive-enrichment-metadata-services.md](reference/archive-enrichment-metadata-services.md)** — Read and write contract for operator-facing managed enrichment tag and hidden note metadata services
- **[photo-review-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/ui-media/photo-review-design.md


)** — Store-backed post-print media review in the existing popup/gallery: delete, replace, dismiss, and local primary-photo selection
- **[source-3mf-import-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/imports/source-3mf-import-design.md


)** — Archive-popup workflow for parsing a user-supplied source `.3mf`, previewing embedded images and metadata, and selectively importing them into Bambuddy as archive photos
- **[source-3mf-import-implementation-plan.md](
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/imports/source-3mf-import-implementation-plan.md


)** — Phased implementation plan, backend contracts, parser scope, and rollout order for the source-3MF import workflow
- **[folder-3mf-catalog-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/imports/folder-3mf-catalog-design.md


)** — Nondestructive folder-driven catalog, reconciliation, editable viewer, browser queue actions, and confirmed backfill workflow for historical `.3mf` collections
- **[filter-sort-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/browser/filter-sort-design.md


)** — Server-side archive browsing with projected full-archive fields, filters, sorting, and paging
- **[multi-select-actions-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/browser/multi-select-actions-design.md


)** — Issue #919 shipped browser multi-select mode, toolbar/card coordination, and bulk action semantics
- **[archive-detail-popup-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/ui-media/archive-detail-popup-design.md


)** — Issue #753 phased popup plan and current implementation status: per-card drilldown plus the initial helper-backed edit slice are shipped
- **[archive-compare-similar.md](design/archive-compare-similar.md)** — Issue #757 design for popup `Related` and `Compare` actions, HA-native compare rendering, and browser multi-select compare
- **[archive-runtime-restore-ha-ux-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/runtime-repair/archive-runtime-restore-ha-ux-design.md


)** — Proposed Home Assistant UX, phased rollout, and service contract for sidecar-backed source-to-target restore workflows
- **[archive-runtime-restore-implementation-plan.md](
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/runtime-repair/archive-runtime-restore-implementation-plan.md


)** — Concrete file-by-file rollout plan for backend upload sessions, workflow state, popup summary entities, and restore UI delivery
- **[archive-runtime-restore-ha-service-and-popup-contract.md](reference/archive-runtime-restore-ha-service-and-popup-contract.md)** — Proposed HA upload endpoint, service names, summary entity shape, and popup wiring contract for the restore workflow
- **[archive-metadata-correction-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/runtime-repair/archive-metadata-correction-design.md


)** — Issue #953 design for sidecar-backed single-archive metadata correction, warning UX, derived-field policy, and local audit history
- **[advanced-features-design.md](planning/advanced-features-design.md)** — Follow-on history capabilities such as favorites, compare, timelapses, repair diagnostics, and reprint preflight
- **[archive-detection-recovery-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/recovery/archive-detection-recovery-design.md


)** — Detection and no-code-change repair architecture for incomplete Bambuddy archives
- **[archive-detection-phase1-scope.md](
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/recovery/archive-detection-phase1-scope.md


)** — Recommended first build slice: detection and visibility only
- **[archive-detection-implementation-plan.md](
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/recovery/archive-detection-implementation-plan.md


)** — Design-only phased implementation plan for detection and recovery orchestration
- **[archive-recovery-n8n-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/recovery/archive-recovery-n8n-design.md


)** — Recommended `n8n` workflow design for manual and future automated recovery
- **[archive-exception-ux-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/recovery/archive-exception-ux-design.md


)** — Dashboard and interaction design for incomplete archive visibility
- **[archive-detection-execution-checklist.md](
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/recovery/archive-detection-execution-checklist.md


)** — Task-level execution checklist before implementation
- **[archive-recovery-live-matrix-2026-04-04.md](
docs/features/print_history/archive/
docs/features/print_history/archive/
docs/features/print_history/archive/recovery/archive-recovery-live-matrix-2026-04-04.md


)** — Point-in-time recovery matrix for the current live fallback archive set
- **[archive-recovery-interim-test-plan.md](
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/recovery/archive-recovery-interim-test-plan.md


)** — Staged manual test method before HA or `n8n` automation creates records

## Migration Notes

### Prototype Lineage
- **REST sensor**: `bambuddy_print_history` from the root `bambuddy/sensors.yaml` prototype
- **REST commands**: `bambuddy_update_archive_status` prototype evolved into `bambuddy_update_archive` (generalized to support notes, tags, name, cost, status, and failure_reason)
- **Template sensors**: 4 "last print" sensors from the root `bambuddy/sensors.yaml` prototype (converted to modern `template:` format)
- **Dashboard cards**: root `bambuddy/dashboards/print_history.yaml` prototype evolved into `dashboard_cards/`
- **Helpers**: `bambuddy_current_archive_id` and `bambuddy_history_sync_enabled` originated in the root `bambuddy/helpers.yaml` prototype; the old `bambuddy_history_limit` helper is retired

### Eliminated
- `bambuddy/automations/sync_print_history.yaml` — Bambuddy auto-creates archives; HA no longer calls `POST /archives`
- `rest_command.bambuddy_create_archive` — same reason
- `rest_command.bambuddy_update_archive_status` — replaced by generalized `bambuddy_update_archive` (PATCH with any fields)

### New (not in root prototype)
- Archive ID capture from webhook events
- Multi-stage photo capture automations (start, mid, near-complete, error)
- `capture_and_upload_snapshot` script with multi-camera + light control + verified upload bridge
- `set_print_history_capture_cameras` script backed by a camera-domain multi-select selector
- `resolve_current_archive_id` fallback script
- Enrichment automation (managed `f:` / `s:` tags + hidden `+>` note payload + native cost)
- Pagination scripts and template sensors
- Configurable capture stage toggles plus persisted multi-camera selection
- Dedicated history view (`view_print_history.yaml`)
- Dashboard cards: `print_history_browser.yaml` (browser header), `print_history_top_controls.yaml` (control strip), `print_history.yaml` (archive grid), `photo_review_chip.yaml` (conditional review chip)
- Wired into main dashboard via `common/dashboards/3d_printing.yaml` views list

## Known Limitations

## Near-Term Follow-Ons

These are worth planning immediately after the core package is stable, but they should stay out of the base Phase 2 migration scope:

- **Browser refinements** — See [filter-sort-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/browser/filter-sort-design.md


). The Layer 1/Layer 2 browser is now implemented; remaining work is mostly refinement: better printer labels, richer tag chips, optional server-side pre-filtering at very large archive counts, and more polished media/list card layouts.
- **Configurable browser instrumentation** — See [browser-instrumentation.md](reference/browser-instrumentation.md). This is now available as a dormant debug path for future filter/reset and heatmap analysis.
- **Heatmap backend unification** — See [filter-sort-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/browser/filter-sort-design.md


). The current heatmap is correct against the projected archive cache, but a future cleanup could move activity filtering to a dedicated backend activity payload so the card no longer reconstructs its own full filtered working set.
- **Photo review actions** — See [photo-review-design.md](
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/ui-media/photo-review-design.md


). The next concrete slice is store-backed review state plus chip-to-popup handoff, dismiss, and delete actions in the existing archive popup.
- **Timelapse lifecycle + media review** — See [advanced-features-design.md](planning/advanced-features-design.md). Valuable follow-on once the basic photo review loop is shipped.
- **Archive repair/capability diagnostics** — See [advanced-features-design.md](planning/advanced-features-design.md). Good for exception handling and admin recovery after upgrades or storage changes.
- **Reprint preflight** — See [advanced-features-design.md](planning/advanced-features-design.md). Worth doing only once queue lifecycle controls and AMS mapping are in place.

### Implemented Browser Layer

The Print History view now includes the configurable browser described in the filter/sort design:

1. **Filter and sort layer** — search, filter, sort, and page over a projected in-memory archive dataset.
2. **Always-visible browser header** — Open Bambuddy, settings, filter pills, search, matches, clear actions, and multi-select color chips stay pinned above the archive grid.
3. **Repeated control strip** — page navigation, page-size slider, card-variant toggles, and refresh appear both above and below the archive grid.
4. **Multi-select archive actions** — the control strip can swap into a multi-select mode, archive cards become selectable instead of opening, and visible-page bulk actions can update tags, project, favorite state, or delete selected archives.
5. **Archive card variants** — the history renderer switches between compact, media, and list cards while keeping a two-column desktop layout and a single-column mobile fallback.
6. **Archive detail popup is live and now actionable** — each archive card opens a `browser_mod.popup`; favorites can be toggled from the card and popup, popup-backed `print_name` / `tags` / `notes` / `status` / `failure_reason` edits can be saved, and a manual `Re-Enrich` action is available. Compare/deep-link and richer follow-on actions remain deferred.

### Debug Instrumentation

The print history browser now includes optional, helper-controlled instrumentation for future debugging and analysis.

- Helper: `input_boolean.print_history_debug_instrumentation`
- UI toggle: debug row in the Print History settings popup opened from the browser header cog button
- Output: browser console plus `window.__printHistoryDebug`

See [browser-instrumentation.md](reference/browser-instrumentation.md) for the full workflow and payload description.

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
│  │ Status  Archive Issue  Material  Printer  Date                        │ │
│  │ Designer  Project  Layer Height  Tag  Favorites  Sort                │ │
│  │ Search  Matches  Clear actions (including tag clear when active)      │ │
│  │ Multi-select color chips (one chip per archive color)                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Control Strip ───────────────────────────────────────────────────────┐ │
│  │ ⏮ ◀  1 of 3  Prints/Page  Compact  Media  List  🔄  ▶ ⏭            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Print Records ───────────────────────────────────────────────────────┐ │
│  │ Compact / Media / List card mode                                     │ │
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
│  │ ⏮ ◀  1 of 3  Prints/Page  Compact  Media  List  🔄  ▶ ⏭            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

Popup launched from `Settings` button:

```
┌─────────────────────────────────────────────┐
│  Print History Settings                     │
│  Capture Timing                             │
│  Start [✓]  Mid-Print [✓]  Near End [✓]    │
│  Complete [✓]  Error [✓]  Threshold   50%  │
│  Cameras                                    │
│  Capture Cameras      [stored list helper]  │
│  Configure Capture Cameras      [selector]  │
│  History Browser                            │
│  History Sync [✓]   Max Cached Archives 175 │
│  Review and Diagnostics                     │
│  Review Timeout (hrs) 24   Debug [off/on]   │
└─────────────────────────────────────────────┘
```

#### Visual Layout (Mobile — 1 column)

On narrow screens, the browser remains a single stacked flow: review chip, browser header, top control strip, archive cards, then bottom control strip. The color chips wrap naturally into additional rows.

The settings popup remains off-canvas on both desktop and mobile so the primary browsing surface stays dominant.

#### Key Design Decisions

1. **One full-width browser flow** — The photo review chip, browser header, archive cards, and both control strips live inside one `panel: true` vertical stack. This prevents navigation or layout controls from jumping into a secondary column.

2. **Settings move to popup, not a permanent column** — Photo-capture and history/view settings are still important, but they are configuration controls rather than daily browsing content. Moving them into a popup keeps the page focused, scales better on mobile, and allows the controls to be grouped by task instead of shown as one long helper list.

3. **Archive card variants are a first-class view choice** — The page should support at least three presentation modes: compact card, media-first card, and list card. This allows the same data layer to support quick scanning and richer visual review.

4. **Workflow state stays out of settings UI** — Archive ID, review state, and similar runtime internals should support automations and review flows, but they should not appear as editable settings.

5. **Color filter chips are generated from live archive data** — The browser header exposes one clickable swatch per discovered filament color. The chips use `custom:auto-entities` to build simple built-in `button` cards, and the selected state is stored as a comma-separated hex list in `input_text.print_history_filter_colors`.

6. **Photo review chip stays with the browser** — The chip is contextual to the history workflow and currently acts as a lightweight status surface. It belongs in the same full-width browsing flow as the archive browser.

7. **Archive issues stay visible in both browse and inspect flows** — The filter bar includes an `Archive Issue` selector (`All`, `Any Error`, `Missing Core 3MF`, `Source 3MF Only`, `Missing Thumbnail`), archive cards add a severity-colored left rail plus issue chip when repair-worthy data problems exist, and the per-print popup repeats the issue summary with operator-facing detail chips rather than raw `file_path` / `no_3mf_available` fields.

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


