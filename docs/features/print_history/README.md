# Print History — Archive Reading, Photo Capture & Enrichment

> **⚠️ OpenAPI Corrections Applied**: See [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for full cross-reference against Bambuddy v0.2.2.2 OpenAPI spec. Key fixes already in code: trailing slash URLs, flat array responses (not dict wrapper), offset-based pagination (not page-based), no `sort`/`order` query params.

## Overview

Reads print archives from Bambuddy's API, captures multi-camera photos at multiple print stages (including errors), uploads them to Bambuddy archives, enriches completed archives with Spoolman spool data, and exposes a full-width dashboard browser with an always-visible control bar in Home Assistant.

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
│   ├── bambuddy_event_history_refresh.yaml        # webhook → refresh REST sensor + archive cache
│   ├── print_history_sync_filter_options.yaml     # populate dynamic filter options from archive cache
│   └── print_history_reset_page_on_filter_change.yaml # reset browser page on filter/sort changes
├── rest_commands/
│   ├── bambuddy_fetch_archives.yaml               # GET /archives — bulk fetch for browser cache
│   ├── bambuddy_upload_photo_to_archive.yaml      # POST /archives/{id}/photos
│   ├── bambuddy_delete_archive_photo.yaml         # DELETE /archives/{id}/photos/{photo_id}
│   ├── bambuddy_set_archive_cover.yaml            # PATCH /archives/{id} — set cover photo
│   ├── bambuddy_update_archive.yaml               # PATCH /archives/{id} — tags/notes enrichment
│   ├── bambuddy_query_recent_archive.yaml         # GET /archives — fallback archive_id resolution
│   └── bambuddy_fetch_archives.yaml               # GET /archives — bulk fetch for browser cache
├── rest_sensors/
│   └── bambuddy_print_history_sensor.yaml         # GET /archives (page 1, recent)
├── scripts/
│   ├── load_history_page.yaml                     # set current browser page
│   ├── navigate_history.yaml                      # prev/next/first/last within Layer 2 totals
│   ├── capture_and_upload_snapshot.yaml            # multi-camera snapshot → save + upload
│   ├── resolve_current_archive_id.yaml            # fallback: query API → match filename
│   ├── refresh_print_history_archives.yaml        # manual trigger for archive cache refresh
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
│   │   ├── input_text_bambuddy_photo_manifest.yaml
│   │   ├── input_text_bambuddy_tray_map_snapshot.yaml
│   │   ├── input_text_print_history_filter_colors.yaml
│   │   └── input_text_print_history_search.yaml
│   ├── input_boolean/
│   │   ├── input_boolean_bambuddy_history_fetch_enabled.yaml
│   │   ├── input_boolean_capture_at_start.yaml
│   │   ├── input_boolean_capture_at_midprint.yaml
│   │   ├── input_boolean_capture_near_complete.yaml
│   │   ├── input_boolean_capture_on_error.yaml
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
│       ├── input_select_print_history_filter_*.yaml
│       ├── input_select_print_history_sort.yaml
│       └── input_select_print_history_card_variant.yaml
├── dashboard_cards/
│   ├── print_history.yaml                         # responsive two-column archive renderer
│   ├── print_history_browser.yaml                 # search + filters + layout/settings controls
│   ├── print_history_pagination.yaml              # top/bottom page navigation strip
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
| `sensor.bambuddy_print_history` | `GET /api/v1/archives/?limit=N` | 5 min | Flat array — count via `value_json \| count`, first item via `value_json[0]` |

> **OpenAPI note**: No `sort` or `order` query params exist. Default ordering is assumed newest-first. No `total` or `page` attributes — response is a flat `ArchiveResponse[]` array.

### REST Commands

| Service | Method | Endpoint | Purpose |
|---|---|---|---|
| `rest_command.bambuddy_upload_photo_to_archive` | POST | `/api/v1/archives/{id}/photos` | Upload photo to archive |
| `rest_command.bambuddy_delete_archive_photo` | DELETE | `/api/v1/archives/{id}/photos/{photo_id}` | Delete a photo from archive (photo review) |
| `rest_command.bambuddy_set_archive_cover` | PATCH | `/api/v1/archives/{id}` | Set cover photo for archive thumbnail (photo review) |
| `rest_command.bambuddy_update_archive` | PATCH | `/api/v1/archives/{id}` | Update name, notes, tags |
| `rest_command.bambuddy_query_recent_archive` | GET | `/api/v1/archives/?printer_id=...&limit=1` | Fallback archive_id resolution |
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
| `input_text.print_history_search` | input_text | Browser search text | — |
| `input_text.print_history_filter_colors` | input_text | Multi-select color filter state as comma-separated hex values | — |
| `input_select.secondary_camera_entity` | input_select | Configurable secondary camera choice from the known auxiliary cameras, or `None` | — |
| `input_text.bambuddy_tray_map_snapshot` | input_text | Simplified tray→spool_id snapshot captured at print start (Tier 2 matching) | No `initial:` |
| `input_boolean.bambuddy_history_fetch_enabled` | input_boolean | Enable/disable history REST polling | — |
| `input_boolean.capture_at_start` | input_boolean | Enable photo capture at print start | — |
| `input_boolean.capture_at_midprint` | input_boolean | Enable photo capture at mid-print % | — |
| `input_boolean.capture_near_complete` | input_boolean | Enable photo capture at ~95% | — |
| `input_boolean.capture_on_error` | input_boolean | Enable photo capture on error/failure | — |
| `input_number.bambuddy_history_limit` | input_number | Number of history entries per page (5–50) | — |
| `input_number.history_current_page` | input_number | Current pagination page | — |
| `input_number.print_history_page_size` | input_number | Browser page size for Layer 2 paging | — |
| `input_number.print_history_max_archives` | input_number | Max archives fetched into the browser cache | — |
| `input_number.midprint_capture_percent` | input_number | Progress % for mid-print capture (e.g., 50) | — |
| `input_number.photo_review_timeout_hours` | input_number | Hours before review auto-dismisses (default: 24) | — |
| `input_text.bambuddy_photo_manifest` | input_text | JSON manifest of captured photos for current print | No `initial:` |
| `input_select.bambuddy_photo_review_state` | input_select | Review lifecycle: `idle`, `pending`, `reviewing` | — |
| `input_select.print_history_filter_*` | input_select | Browser filter state (status/material/printer/date/designer/layer) | — |
| `input_boolean.print_history_filter_favorites_only` | input_boolean | Favorites-only toggle in the browser header | — |
| `input_select.print_history_sort` | input_select | Browser sort mode | — |
| `input_select.print_history_card_variant` | input_select | Compact / Media / Detail renderer selection | — |

### Scripts

| Script | Purpose |
|---|---|
| `script.load_history_page` | Set a specific browser page |
| `script.navigate_history` | Prev/next/first/last navigation, calls `load_history_page` |
| `script.capture_and_upload_snapshot` | Multi-camera capture + local save + Bambuddy upload |
| `script.resolve_current_archive_id` | Fallback: query Bambuddy API, match by filename, store archive_id |
| `script.refresh_print_history_archives` | Fire a manual Layer 1 refresh event |
| `script.clear_print_history_filters` | Reset browser controls back to defaults |
| `script.toggle_print_history_color_filter` | Add/remove a color from the active color-chip filter |
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
| `bambuddy_event_history_refresh` | `bambuddy_webhook_event` where event=`print_complete`/`print_failed`/`print_stopped` | Refresh REST sensor + Layer 1 archive cache |
| `print_history_sync_filter_options` | `sensor.print_history_archives` changes, HA startup | Update dynamic filter dropdown options |
| `print_history_reset_page_on_filter_change` | filter/sort helper changes | Reset browser page to 1 |

## Key Design Details

For detailed design of the two major subsystems, see:

- **[photo-capture-design.md](photo-capture-design.md)** — Multi-camera, multi-stage photo capture with error photos
- **[archive-enrichment.md](archive-enrichment.md)** — Spoolman data enrichment pipeline (tags + notes)
- **[photo-review-design.md](photo-review-design.md)** — Post-print photo review: remove, replace, set cover
- **[filter-sort-design.md](filter-sort-design.md)** — Server-side archive browsing with projected full-archive fields, filters, sorting, and paging
- **[advanced-features-design.md](advanced-features-design.md)** — Follow-on history capabilities such as favorites, compare, timelapses, repair diagnostics, and reprint preflight
- **[archive-detection-recovery-design.md](archive-detection-recovery-design.md)** — Detection and no-code-change repair architecture for incomplete Bambuddy archives
- **[archive-detection-phase1-scope.md](archive-detection-phase1-scope.md)** — Recommended first build slice: detection and visibility only
- **[archive-detection-implementation-plan.md](archive-detection-implementation-plan.md)** — Design-only phased implementation plan for detection and recovery orchestration
- **[archive-recovery-n8n-design.md](archive-recovery-n8n-design.md)** — Recommended `n8n` workflow design for manual and future automated recovery
- **[archive-exception-ux-design.md](archive-exception-ux-design.md)** — Dashboard and interaction design for incomplete archive visibility
- **[archive-detection-execution-checklist.md](archive-detection-execution-checklist.md)** — Task-level execution checklist before implementation

## Migration Notes

### Sources (from `bambuddy/`)
- **REST sensor**: `bambuddy_print_history` from `bambuddy/sensors.yaml`
- **REST commands**: `bambuddy_update_archive_status` → `bambuddy_update_archive` (generalized to support notes+tags+name)
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
- Dashboard cards: `print_history.yaml` (history table), `print_history_browser.yaml` (pagination), `photo_review_chip.yaml` (conditional review chip)
- Wired into main dashboard via `common/dashboards/3d_printing.yaml` views list

## Known Limitations

## Near-Term Follow-Ons

These are worth planning immediately after the core package is stable, but they should stay out of the base Phase 2 migration scope:

- **Browser refinements** — See [filter-sort-design.md](filter-sort-design.md). The Layer 1/Layer 2 browser is now implemented; remaining work is mostly refinement: better printer labels, richer tag chips, optional server-side pre-filtering at very large archive counts, and more polished media/detail card layouts.
- **Timelapse lifecycle + media review** — See [advanced-features-design.md](advanced-features-design.md). Valuable, but depends on multipart upload and more media-state handling.
- **Archive repair/capability diagnostics** — See [advanced-features-design.md](advanced-features-design.md). Good for exception handling and admin recovery after upgrades or storage changes.
- **Reprint preflight** — See [advanced-features-design.md](advanced-features-design.md). Worth doing only once queue lifecycle controls and AMS mapping are in place.

### Implemented Browser Layer

The Print History view now includes the configurable browser described in the filter/sort design:

1. **Filter and sort layer** — search, filter, sort, and page over a projected in-memory archive dataset.
2. **Always-visible browser bar** — search, matches, settings, sort, filter pills, layout toggles, page-size slider, clear/refresh, and multi-select color chips all stay pinned above the archive grid.
3. **Archive card variants** — the history renderer switches between compact, media, and detail cards while keeping a two-column desktop layout and a single-column mobile fallback.
4. **Archive detail popup is designed, not yet implemented** — archive cards are now structured for a future tap-through popup, but the popup content remains design-only for now.

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
- **View type**: `panel: true` with a single `vertical-stack` so the browser header, archive grid, and both pagination rows stay in one full-width flow

### Layout Design

The dashboard is organized around **a single browser-first surface**. Settings remain part of the feature, but they no longer permanently occupy dashboard real estate. Instead, the print history page exposes them through a popup launched from an in-page button.

#### Visual Layout (Desktop)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Section 1: Print History Browser                                         │
│                                                                             │
│  ┌─ Photo Review Chip (conditional) ─────────────────────────────────────┐ │
│  │ 📸 Photos to Review                                                    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Browser Header ──────────────────────────────────────────────────────┐ │
│  │ Search  Matches  Open Bambuddy  Settings                             │ │
│  │ Filter pills  Favorites toggle  Sort  Layout toggle  Items/page      │ │
│  │ Color filter summary + swatches                                      │ │
│  │ Multi-select color chips (one chip per archive color)                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─ Pagination ──────────────────────────────────────────────────────────┐ │
│  │ ⏮  ◀  │  Page 1 / 3  │  ▶  ⏭                                        │ │
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
│  ┌─ Pagination ──────────────────────────────────────────────────────────┐ │
│  │ ⏮  ◀  │  Page 1 / 3  │  ▶  ⏭                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

Popup launched from `Settings` button:

```
┌─────────────────────────────────────────────┐
│  Print History Settings                     │
│  At Start [✓]  Mid-Print [✓]  Near End [✓] │
│  On Error [✓]  Mid-Print Threshold   50%   │
│  Secondary Camera               [dropdown] │
│  Auto-Fetch History                  [✓]   │
│  Max Cached Archives                175    │
│  Review Timeout (hrs)                24    │
└─────────────────────────────────────────────┘
```

#### Visual Layout (Mobile — 1 column)

On narrow screens, the browser remains a single stacked flow: review chip, browser header, top pagination, archive cards, then bottom pagination. The color chips wrap naturally into additional rows.

The settings popup remains off-canvas on both desktop and mobile so the primary browsing surface stays dominant.

#### Key Design Decisions

1. **One full-width browser flow** — The photo review chip, browser header, archive cards, and both pagination rows live inside one `panel: true` vertical stack. This prevents layout controls or pagination from jumping into a secondary column.

2. **Settings move to popup, not a permanent column** — Photo-capture and history/view settings are still important, but they are configuration controls rather than daily browsing content. Moving them into a popup keeps the page focused and also scales better on mobile.

3. **Archive card variants are a first-class view choice** — The page should support at least three presentation modes: compact list, media-first card, and detail card. This allows the same data layer to support quick scanning and richer visual review.

4. **Workflow state stays out of settings UI** — Archive ID, review state, and similar runtime internals should support automations and review flows, but they should not appear as editable settings.

5. **Color filter chips are generated from live archive data** — The browser header exposes one clickable swatch per discovered filament color. The chips use `custom:auto-entities` to build simple built-in `button` cards, and the selected state is stored as a comma-separated hex list in `input_text.print_history_filter_colors`.

6. **Photo review chip stays with the browser** — The chip is contextual to the history workflow (you see it → review → it disappears). It belongs in the same full-width browsing flow as the archive browser.

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
| 2 | Photo upload content type (JSON photo_url vs multipart file) | Determines upload mechanism in `capture_and_upload_snapshot` | No — both paths designed |
| 3 | Confirm `input_text.3dprinter_snapshot_light` availability cross-package | If notifications package not deployed, need local fallback | No — gated with template check |
| 4 | Enrichment idempotency — verify PATCH tags doesn't create duplicates | Could pollute tag lists on retry | Low risk — test during Phase 7 |
| 5 | Base64 `image` field in webhook payload — bonus data capture | Bambuddy webhooks can include base64 JPEG for some events | No — nice-to-have, not blocking |
| 6 | Photo list/delete API — confirm `GET` and `DELETE` on `/archives/{id}/photos/{photo_id}` | Required for review delete action | No — review/dismiss still works without it |
| 7 | Cover photo API — confirm `cover_photo_id` field on PATCH | Required for set-as-cover action | No — omit button if unavailable |
| 8 | Upload response schema — does POST photos return `photo_id`? | Manifest needs photo_id for delete/replace mapping | No — can fall back to listing photos |
