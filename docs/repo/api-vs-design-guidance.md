# Bambuddy API vs Design — Development Guidance Notes

> **Generated**: 2026-03-28 — Cross-referencing live OpenAPI spec (Bambuddy v0.2.2.2) against all phase design docs.
> **Purpose**: Guide future development by documenting API capabilities not yet leveraged, design corrections still needed, and new integration opportunities.

---

## Table of Contents

- [Bambuddy API vs Design — Development Guidance Notes](#bambuddy-api-vs-design--development-guidance-notes)
  - [Table of Contents](#table-of-contents)
  - [1. API Domains Not Covered by Any Phase](#1-api-domains-not-covered-by-any-phase)
  - [2. Phase-by-Phase Corrections \& Enhancements](#2-phase-by-phase-corrections--enhancements)
    - [Phase 1: bambuddy\_common — COMPLETE ✅](#phase-1-bambuddy_common--complete-)
    - [Phase 2: print\_history — Core Complete, Advanced Pending](#phase-2-print_history--core-complete-advanced-pending)
    - [Phase 3: print\_queue — NOT STARTED](#phase-3-print_queue--not-started)
    - [Phase 4: print\_statistics — NOT STARTED](#phase-4-print_statistics--not-started)
    - [Phase 5: printer\_maintenance — NOT STARTED](#phase-5-printer_maintenance--not-started)
  - [3. Queue API Is Far Richer Than Documented](#3-queue-api-is-far-richer-than-documented)
  - [4. Timelapse Management — Missing from Print History](#4-timelapse-management--missing-from-print-history)
  - [5. Camera Endpoints — Direct Snapshot Alternative](#5-camera-endpoints--direct-snapshot-alternative)
  - [6. Inventory System — Parallel to Spoolman Sync](#6-inventory-system--parallel-to-spoolman-sync)
  - [7. Projects System — Batch Print Tracking](#7-projects-system--batch-print-tracking)
  - [8. Smart Plugs — Native HA Entity Discovery](#8-smart-plugs--native-ha-entity-discovery)
  - [9. Webhook Endpoints — External Queue \& Printer Control](#9-webhook-endpoints--external-queue--printer-control)
  - [10. New Schema Fields Worth Surfacing](#10-new-schema-fields-worth-surfacing)
  - [11. Global API Patterns to Remember](#11-global-api-patterns-to-remember)
  - [12. Recommended Priority Order for New Work](#12-recommended-priority-order-for-new-work)
    - [Immediate (Before Phase 3-5 Core)](#immediate-before-phase-3-5-core)
    - [High Priority (Phase 3-5 Core Implementation)](#high-priority-phase-3-5-core-implementation)
    - [Medium Priority (Advanced Features)](#medium-priority-advanced-features)
    - [Low Priority (Future Consideration)](#low-priority-future-consideration)
  - [Appendix: API Endpoint Count by Domain](#appendix-api-endpoint-count-by-domain)

---

## 1. API Domains Not Covered by Any Phase

The live Bambuddy v0.2.2.2 API has **34 tag groups** with hundreds of endpoints. The current 5-phase plan covers only **6 of these** (auth/common, archives, queue, stats, maintenance, printers). The following major API domains have no HA integration plan:

| API Domain | Endpoints | Potential HA Value | Notes |
|---|---|---|---|
| **Inventory** (`/inventory/`) | ~20 endpoints | **High** | Full spool management: catalog, spools, AMS assignments, K-profiles, usage history. Could complement or consolidate with `spoolman_sync`. |
| **Projects** (`/projects/`) | ~18 endpoints | **Medium-High** | Project tracking with BOM, timeline, archive/queue linking. Natural HA integration for "batch print" workflows. |
| **Library** (`/library/`) | ~15 endpoints | **Medium** | File management with folder tree, 3MF plate selection, STL thumbnails, direct-print dispatch. |
| **Camera** (`/printers/{id}/camera/`) | 4 endpoints | **Medium** | MJPEG stream proxy, snapshot capture, build plate empty detection. Could supplement HA camera entity. |
| **Smart Plugs** (`/smart-plugs/`) | ~10 endpoints | **Low-Medium** | Bambuddy already discovers HA entities; bidirectional. Scripts per printer for power on/off sequencing. |
| **Notifications** (`/notifications/`) | ~12 endpoints | **Low** | Bambuddy's own notification system. HA already has its own; mainly useful if you want Bambuddy-native alerts. |
| **SpoolBuddy** (`/spoolbuddy/`) | ~15 endpoints | **Low** | Hardware NFC/scale device management. Only relevant if SpoolBuddy hardware is deployed. |
| **Cloud** (`/cloud/`) | ~12 endpoints | **Low** | Bambu Cloud account, slicer presets, filament profiles. Read-only reference data. |
| **Filament Catalog** (`/filament-catalog/`) | 5 endpoints | **Low** | Bambuddy's own filament type database. Overlaps with spoolman filaments. |
| **Local Presets** (`/local-presets/`) | 5 endpoints | **Low** | Slicer preset management. Not typically surfaced in HA. |
| **Print Log** (`/print-log/`) | 2 endpoints | **Low** | Subset of archives; design already decided to skip. |
| **External Links** (`/external-links/`) | 5 endpoints | **None** | UI-only feature for Bambuddy's sidebar. |
| **Firmware** (`/firmware/`) | 2 endpoints | **Low-Medium** | Firmware update tracking. Could add a "firmware outdated" sensor. |
| **K-Profiles** (`/printers/{id}/kprofiles/`) | 4 endpoints | **Low** | Pressure advance calibration profiles. Niche. |
| **Virtual Printers** (`/virtual-printers/`) | 3 endpoints | **None** | Testing/demo feature. |
| **Metrics** (`/metrics`) | 1 endpoint | **Low** | Prometheus endpoint; redundant if HA already scrapes via Prometheus integration. |
| **Discovery** (`/discovery/`) | 3 endpoints | **None** | Printer auto-discovery, not needed from HA. |
| **System/Support** | 5 endpoints | **Low** | Debug logging, support bundles. |

---

## 2. Phase-by-Phase Corrections & Enhancements

### Phase 1: bambuddy_common — COMPLETE ✅

No corrections needed. Webhook receiver, MQTT status sensor, and API config all implement correctly.

**Enhancement opportunity**: Add a `sensor.bambuddy_server_version` using `GET /api/v1/updates/version` (unauthenticated) to detect when Bambuddy updates are available.

### Phase 2: print_history — Core Complete, Advanced Pending

**Corrections already applied** (documented in `openapi-correction-notes.md`):
- Flat array response, no sort/order params, offset pagination — all fixed in code
- `print_name` not `name`, `actual_time_seconds` not `duration_seconds`

**Still needs verification**:
- Confirm default sort order on `GET /archives/` returns newest-first (no sort param exists in OpenAPI)
- Photo upload response: confirm it returns the generated `filename` (needed for delete/set-cover flows)
- `resolve_current_archive_id` fallback matches by `task_name` — may differ from archive `print_name`

**New endpoints to leverage**:

| Endpoint | Use Case | Priority |
|---|---|---|
| `GET /archives/slim` | **Use for statistics dashboards** instead of full `/archives/`. Returns only needed fields, supports up to 50,000 records. Already exists but not in any design doc. | High |
| `POST /archives/{id}/reprint` | One-button reprint from dashboard. Takes `printer_id`, `ams_mapping`, print options. Simpler than queue-add. | Medium |
| `GET /archives/{id}/filament-requirements` | Show required filaments before reprint. Has `plate_id` filter for multi-plate models. | Medium |
| `GET /archives/{id}/similar` | "You also printed X" recommendations. Matches by print_name, content_hash, filament_type. | Low |
| `POST /archives/recalculate-costs` | Batch cost recalculation if filament prices change. Surface as a dashboard button. | Low |
| `GET /archives/export` | CSV/XLSX export for spreadsheet users. Link in dashboard. | Low |

**Timelapse endpoints** — see [Section 4](#4-timelapse-management--missing-from-print-history).

### Phase 3: print_queue — NOT STARTED

**Critical**: Queue API is **significantly richer** than the design docs assume. See [Section 3](#3-queue-api-is-far-richer-than-documented).

**Corrections needed before implementation**:

| Issue | Current Design | Actual API | Fix |
|---|---|---|---|
| Add-to-queue body | `file_id`, `copies` | `archive_id` OR `library_file_id` + print options | Rewrite `bambuddy_queue_add` REST command entirely |
| Per-item operations | Only delete | GET, PATCH, DELETE + cancel/stop/start per item | Add REST commands for cancel, stop, start |
| Bulk operations | None | `PATCH /queue/bulk` (bulk update), `POST /queue/reorder` | Add REST commands |
| Next-up query | None | `GET /queue/next-up/{printer_id}` | Use for filament readiness (Phase 4.1) |
| Item status values | Assumed: pending/printing/done | Actual enum: `pending`, `printing`, `completed`, `failed`, `skipped`, `cancelled` | Update template sensor filters |
| Response fields | Minimal | Rich: `archive_name`, `archive_thumbnail`, `library_file_name`, `printer_name`, `print_time_seconds`, `filament_used_grams`, `filament_type`, `filament_color`, `created_by_username` | Use for richer dashboard cards |

**New design consideration**: `PrintQueueItemCreate` supports `target_model` (e.g., "Any X1C") for model-based queue items that can print on any matching printer. The design docs don't mention this — it enables fleet-aware queue management.

### Phase 4: print_statistics — NOT STARTED

**All corrections documented** in `openapi-correction-notes.md` and the README's open items. Key reminders:

- Endpoint is `/api/v1/archives/stats` (NOT `/api/v1/statistics`)
- `success_rate`, `prints_this_week`, `avg_print_time_hours`, `most_used_filament` must ALL be computed in Jinja templates
- `cancelled_prints` does not exist — use `stopped_prints`
- `total_filament_grams` (not `total_filament_used_grams`)

**Enhancement**: Use `/archives/stats?date_from=YYYY-MM-DD` for time-windowed stats. A second REST sensor could call `/archives/stats?date_from={monday}` to power `prints_this_week` without counting from `/archives/slim`.

**New endpoint**: `GET /archives/stats/export` — CSV/XLSX export of statistics. Surface as a dashboard link.

### Phase 5: printer_maintenance — NOT STARTED

**All endpoints confirmed** in the OpenAPI spec. No corrections needed — the advanced-features-design doc already has the correct endpoint reference table.

**Additional endpoint not in design**: `GET /api/v1/maintenance/summary` — returns cross-printer aggregate with `total_due`, `total_warning`, `printers_with_issues`. The Phase 5.1 fleet summary design references this but it warrants emphasis: this single endpoint replaces the need to poll `/overview` and iterate.

**Enhancement**: `MaintenanceStatus` schema includes `maintenance_type_wiki_url` — surface this as a help link in the dashboard catalog card (the design mentions this but doesn't show the card template).

---

## 3. Queue API Is Far Richer Than Documented

The design docs model the queue as a simple list (GET/POST/DELETE). The actual API supports **full lifecycle management**:

```
GET    /queue/                        — List (filter: printer_id, status, target_model)
POST   /queue/                        — Add item
GET    /queue/{item_id}               — Get single item
PATCH  /queue/{item_id}               — Update item (reassign printer, change options)
DELETE /queue/{item_id}               — Remove item
POST   /queue/{item_id}/cancel        — Cancel pending item
POST   /queue/{item_id}/stop          — Stop currently printing item
POST   /queue/{item_id}/start         — Start a manual_start item
POST   /queue/reorder                 — Reorder all items (array of IDs)
PATCH  /queue/bulk                    — Bulk update (same settings on multiple items)
GET    /queue/next-up/{printer_id}    — What's printing next on this printer
```

**Implications for print_queue package**:

1. **REST commands to add** (beyond core GET/POST/DELETE):
   - `bambuddy_queue_cancel` — Cancel a pending item without deleting it
   - `bambuddy_queue_start` — Start a manual-start item from HA
   - `bambuddy_queue_stop` — Emergency stop the currently printing queue item
   - `bambuddy_queue_update` — Move item to different printer or change options

2. **Dashboard enhancements**:
   - Per-item action buttons: Cancel, Start (if manual_start), Stop (if printing)
   - Drag-reorder via `POST /queue/reorder` (may need custom card)
   - "Next up" chip showing what will print next on each printer

3. **Automation opportunities**:
   - `manual_start` items: HA notification "Job X is staged — tap to start" → calls `POST /queue/{id}/start`
   - Queue item failed: detect `status=failed` transition → send error_message in notification
   - Queue empty: all items completed/cancelled → "Queue complete" notification

4. **`PrintQueueItemCreate` key fields** not in design docs:
   - `target_model` — "Any X1C" style model-based assignment
   - `target_location` — location-based assignment  
   - `required_filament_types` — filament type requirements
   - `filament_overrides` — AMS slot overrides
   - `scheduled_time` — future scheduling
   - Print options: `bed_levelling`, `flow_cali`, `vibration_cali`, `layer_inspect`, `timelapse`, `use_ams`

---

## 4. Timelapse Management — Missing from Print History

The OpenAPI spec reveals a complete **timelapse subsystem** under archives that is not mentioned anywhere in the Phase 2 (print_history) design:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/archives/{id}/timelapse` | Get timelapse video (unauthenticated, for `<video>` tags) |
| `DELETE` | `/archives/{id}/timelapse` | Delete timelapse |
| `POST` | `/archives/{id}/timelapse/scan` | Scan printer for matching timelapse file |
| `POST` | `/archives/{id}/timelapse/select` | Manually attach a specific timelapse file |
| `GET` | `/archives/{id}/timelapse/thumbnail?width=160` | Get timelapse thumbnail |
| `POST` | `/archives/{id}/timelapse/process` | Post-process: trim, speed adjust, audio overlay |

**Recommendation**: Add timelapse integration to Phase 2 as a sub-phase (2.9):

- **REST command**: `bambuddy_scan_timelapse` — trigger scan after print completes (automation)
- **Dashboard card**: Display timelapse video/thumbnail alongside photos in the history detail view
- **Automation**: On `print_complete` webhook, call `POST /archives/{id}/timelapse/scan` to auto-discover the timelapse file
- **Template sensor**: `sensor.last_print_has_timelapse` — boolean from archive data (`timelapse_path` not null)

The timelapse video URL is **unauthenticated** (like thumbnails/photos), so it can be embedded directly in HA dashboard via `<video>` or `picture-entity` card.

---

## 5. Camera Endpoints — Direct Snapshot Alternative

The design docs describe photo capture via HA's camera entities (`camera.snapshot` service). The Bambuddy API also offers **direct camera access**:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/printers/{id}/camera/stream` | MJPEG stream proxy (unauthenticated) |
| `GET` | `/printers/{id}/camera/snapshot` | Single frame capture |
| `POST` | `/printers/{id}/camera/test` | Test camera connectivity |
| `GET` | `/printers/{id}/camera/check-plate` | ML-based build plate empty detection |

**When to prefer Bambuddy camera over HA camera entity**:
- Bambuddy proxies the P1S's encrypted RTSP stream (no HA RTSP setup needed)
- Snapshot is pre-decoded and ready for upload
- No dependency on HA camera entity being correctly configured

**Build plate detection** (`check-plate`) is particularly interesting:
- Uses calibration-based difference detection comparing current frame to empty-plate reference
- Requires chamber light ON for reliability
- Could power a "plate is clear, start next print" automation for queue management

**Recommendation**: Document as an alternative path in Phase 2 photo capture design. For `check-plate`, add to Phase 4 (Queue) as queue automation prerequisite — auto-start next print only when plate is confirmed empty.

---

## 6. Inventory System — Parallel to Spoolman Sync

Bambuddy v0.2.2.2 has its own **full spool inventory system** at `/api/v1/inventory/`:

| Group | Endpoints | Purpose |
|---|---|---|
| Spool Catalog | GET/POST/PATCH/DELETE `/catalog/` | Spool weight/material type definitions |
| Color Catalog | GET `/colors` | Color reference data |
| Spools | GET/POST/PATCH/DELETE `/spools/` | Individual spool CRUD with brand, material, color, weight, purchase info |
| Bulk Spools | POST `/spools/bulk` | Create multiple identical spools |
| K-Profiles | GET/PUT `/spools/{id}/k-profiles` | Pressure advance calibration per spool |
| Tag Linking | POST `/spools/{id}/link-tag` | Link NFC tag to spool |
| Assignments | GET/POST/DELETE `/assignments/` | AMS slot ↔ spool assignments |
| Usage History | GET/DELETE `/spools/{id}/usage` | Track per-spool usage across prints |

**Relationship to `spoolman_sync`**: This is a **parallel inventory system** to Spoolman. If a user runs both Bambuddy inventory AND Spoolman, data could drift. Current design correctly chose Spoolman as the spool-of-record with Bambuddy for archive/queue.

**Potential integration points**:
1. **Assignment sync**: When `spoolman_sync` assigns a tray, also call `POST /inventory/assignments` to keep Bambuddy's AMS view in sync
2. **Usage deduction**: After print_complete, Bambuddy may already track usage via its inventory. If so, avoid double-deduction against Spoolman.
3. **Tag linking**: If using SpoolBuddy NFC hardware, tag UIDs flow through Bambuddy inventory → could bridge to Spoolman tags

**Recommendation**: For now, **do not** build a separate Bambuddy inventory integration. Document the overlap and revisit if Spoolman is ever deprecated or if users request consolidation.

---

## 7. Projects System — Batch Print Tracking

The `/api/v1/projects/` API provides **full project lifecycle management**:

- Project CRUD with status (`active`, `completed`, `paused`, `archived`), target count, budget, color, priority
- BOM (Bill of Materials) items with quantity tracking, sourcing URLs, STL filenames
- Archive ↔ project linking (prints assigned to projects)
- Queue ↔ project linking (queue items assigned to projects)
- Attachments (file upload/download)
- Templates (create reusable project patterns)
- Timeline events (chronological activity log)
- Import/export (JSON + ZIP formats)
- Sub-projects via `parent_id`

**Potential HA integration** (future Phase 6+):

1. **Project status sensor**: `sensor.bambuddy_active_projects` — count of active projects with progress
2. **Project progress dashboard**: Per-project card showing completion % (`completed_count / target_count`), BOM status, budget tracking
3. **Queue-to-project linking**: When adding to queue from HA, optionally assign to project
4. **Project completion automation**: When project reaches target_count → send notification

**Recommendation**: Low priority for now. Projects are primarily managed in Bambuddy's web UI. Consider a lightweight "project summary" REST sensor in a future phase if multi-project tracking becomes a user workflow.

---

## 8. Smart Plugs — Native HA Entity Discovery

Bambuddy can discover and control HA entities directly:

| Endpoint | Purpose |
|---|---|
| `GET /smart-plugs/ha/entities` | List HA switch/light/input_boolean entities |
| `GET /smart-plugs/ha/sensors` | List HA power/energy sensors (W, kW, kWh, Wh) |
| `GET /smart-plugs/by-printer/{id}/scripts` | Per-printer smart plug scripts |

Bambuddy also supports Tasmota device discovery and direct MQTT control.

**Key insight**: Bambuddy **reads HA state** via configured `ha_url` + `ha_token` in settings. This means Bambuddy can:
- Turn printers on/off via HA smart plug entities
- Read power consumption from HA energy sensors
- Execute per-printer scripts (power-on sequence, cool-down, etc.)

**Impact on HA integration**: The smart plug API is primarily about Bambuddy calling HA, not the other way around. No HA-side integration needed. However, if Bambuddy is configured with HA access:
- Bambuddy's queue can auto-power-on printers before jobs start
- Energy cost tracking (`total_energy_kwh`, `total_energy_cost` in stats) is populated from HA sensors
- The `auto_off_after` queue option triggers HA entity state changes via Bambuddy

**Recommendation**: Ensure Bambuddy's HA connection settings are configured correctly (Settings > Home Assistant). No separate HA package needed — this is Bambuddy's built-in HA awareness.

---

## 9. Webhook Endpoints — External Queue & Printer Control

The `/api/v1/webhook/` endpoints provide **lightweight API-key-scoped** access for external automation:

| Endpoint | Method | Purpose |
|---|---|---|
| `POST /webhook/queue` | POST | Add to queue (uses `QueueAddRequest` + `Authorization` header) |
| `POST /webhook/printer/{id}/start` | POST | Start next queued print (requires `can_control_printer`) |
| `GET /webhook/printer/{id}/status` | GET | Get printer status (requires `can_read_status`) |
| `GET /webhook/queue` | GET | Get queue status for all/specific printers |

**Key difference from regular API**: Webhook endpoints use a dedicated API key permissions model (`can_queue`, `can_control_printer`, `can_read_status`, `printer_ids` scoping). This is designed for external callers like HA automations that need limited-scope access.

**Recommendation**: For HA→Bambuddy calls, the regular `/api/v1/` endpoints with `X-API-Key` are simpler and already used by all phases. The webhook endpoints are more useful for scenarios like:
- Voice assistant integration ("Hey Google, add this to the print queue")
- NFC tag scans triggering HA automations that add to queue
- Third-party dashboards or mobile shortcuts

---

## 10. New Schema Fields Worth Surfacing

From cross-referencing the `ArchiveResponse` schema against Phase 2 template sensors:

| Field | Type | Current Status | Recommendation |
|---|---|---|---|
| `is_favorite` | boolean | Phase 2.1 planned (toggle) | Add to dashboard card (star icon) |
| `designer` | string | Phase 2.4 planned | Show in history detail card |
| `makerworld_url` | string | Phase 2.4 planned | Link button in history card |
| `external_url` | string | Supported in Bambuddy UI/API; not yet fully surfaced in HA design | Link to source (Printables, etc.) |
| `failure_reason` | string | Supported in Bambuddy UI/API; only lightly surfaced in current HA design | Show in failed print cards and popup detail |
| `quantity` | integer | Supported in Bambuddy UI/API; not yet meaningfully surfaced in HA history views | Show print quantity / object-count context where useful |
| `energy_kwh` | float | Phase 2.6 planned | Show in cost breakdown |
| `energy_cost` | float | Phase 2.6 planned | Add to total cost display |
| `content_hash` | string | Not surfaced | Used internally for dedup/similar |
| `created_by_username` | string | Not yet used in HA design | Show who started the print (multi-user) |
| `project_id` | integer | Supported in Bambuddy UI/API; future HA action slot already planned | Link to project if assigned |

Archive field caveats from Bambuddy source:

- `notes` and `tags` are `Text` fields with no app-level max-length validators, so treat performance and readability as the real limit.
- both fields are part of Bambuddy's FTS index, so large enrichment payloads carry search/index cost
- there is no archive custom-fields feature; `extra_data` is not a normal mutable archive extension point

From `PrintQueueItemResponse`:

| Field | Type | Not in Design | Recommendation |
|---|---|---|---|
| `archive_thumbnail` | string (URL) | Not mentioned | Use for queue card thumbnails |
| `library_file_name` | string | Not mentioned | Show for library-sourced queue items |
| `library_file_thumbnail` | string (URL) | Not mentioned | Thumbnail for library items |
| `created_by_username` | string | Not mentioned | Show who queued the job |
| `target_model` | string | Not in design | Show "Any X1C" label for model-targeted items |
| `manual_start` | boolean | Not in design | Dashboard indicator + start button |
| `scheduled_time` | datetime | Not in design | Show scheduled time for future-scheduled items |

From `MaintenanceStatus`:

| Field | Type | Current Status | Recommendation |
|---|---|---|---|
| `maintenance_type_icon` | string | In design | Map to mdi: icons in dashboard |
| `maintenance_type_wiki_url` | string | Mentioned but no template | Add help link icon per task |
| `days_since_maintenance` | float | Not used | Alternative display: "3.5 days ago" vs "45.2 hours ago" |
| `days_until_due` | float | Not used | "Due in 2.1 days" alternative for time-based tasks |
| `interval_type` | string (hours/days) | In design | Conditionally show hours vs days in UI |

---

## 11. Global API Patterns to Remember

These patterns are documented in `openapi-correction-notes.md` but bear repeating:

1. **Trailing slashes**: Collection endpoints (lists) have trailing slashes (`/archives/`, `/queue/`). Item endpoints do not (`/archives/{id}`, `/queue/{id}`). FastAPI returns 307 redirects otherwise.

2. **Flat array responses**: Almost all collection endpoints return `Type[]` flat arrays, NOT `{items: [], total: N}` wrappers. The ONLY exception is `GET /print-log/` which returns `PrintLogResponse{items, total}`.

3. **Pagination**: All via `offset` + `limit` (0-based). No `page` parameter exists anywhere. Default limits vary: 50 (archives, queue, search), 10000 (archives/slim), 200 (logs).

4. **Auth**: `X-API-Key` header (preferred for HA) or `HTTPBearer` token. Some endpoints are **unauthenticated**: thumbnails, photos, timelapse videos, camera streams, app version.

5. **No sort/order params**: `GET /archives/` has no `sort` or `order` query parameter in the OpenAPI spec. Default ordering appears to be newest-first but is unspecified. The `search` endpoint also has no sort.

6. **PATCH semantics**: Partial update — only send fields you want to change. Omitted fields are unchanged.

7. **Tags are strings**: Archive tags are comma-separated strings in the PATCH body, NOT JSON arrays. E.g., `"tags": "favorite, customer-sample"`.

---

## 12. Recommended Priority Order for New Work

Based on API capability, user value, and implementation effort:

### Immediate (Before Phase 3-5 Core)

| Item | Where | Why |
|---|---|---|
| **Add `/archives/slim` sensor** | Phase 4 (statistics) | Lightweight data source for dashboard widgets, 50K limit. Better than full archives for aggregation. |
| **Verify default sort order** | Phase 2 | Confirm `GET /archives/` returns newest-first without explicit sort param. Test with live API call. |
| **Document timelapse auto-scan** | Phase 2 design | Add `POST /{id}/timelapse/scan` to print_complete automation sequence. Free timelapse attachment. |

### High Priority (Phase 3-5 Core Implementation)

| Item | Phase | Notes |
|---|---|---|
| **Queue: use full `PrintQueueItemCreate` schema** | 3 | Include `target_model`, `scheduled_time`, print options. Don't over-simplify. |
| **Queue: add cancel/start/stop REST commands** | 3 | Per-item lifecycle control is the biggest gap between design and API. |
| **Queue: surface `next-up/{printer_id}`** | 3/4.1 | Enables filament readiness check without parsing the full queue. |
| **Maintenance: use `/summary` for fleet chip** | 5 | Single endpoint for total due/warning across all printers. |
| **Statistics: second REST sensor for this-week** | 4 | `GET /archives/stats?date_from={monday}` for time-windowed counts. |

### Medium Priority (Advanced Features)

| Item | Phase | Notes |
|---|---|---|
| **Reprint from dashboard** | 2.3/3 | `POST /archives/{id}/reprint` — simpler than queue-add for repeat jobs. |
| **Filament requirements pre-check** | 2/3 | `GET /archives/{id}/filament-requirements` before reprint/queue-add. |
| **Camera plate-empty detection** | 3/4.3 | `GET /camera/check-plate` for auto-start queue workflows. |
| **Timelapse thumbnail in history** | 2 | `GET /{id}/timelapse/thumbnail` — unauthenticated, easy to display. |
| **Firmware version sensor** | Common | `GET /firmware/{printer_id}` + `GET /firmware/latest` — "update available" binary sensor. |

### Low Priority (Future Consideration)

| Item | Notes |
|---|---|
| **Bambuddy inventory sync** | Only if consolidating away from Spoolman |
| **Projects dashboard** | Only if multi-project tracking becomes a workflow |
| **Bambuddy notification integration** | HA notifications are sufficient |
| **Archive export links** | Nice-to-have dashboard buttons |
| **Cost recalculation button** | Nice-to-have when filament prices change |
| **Library file printing** | Niche — most users print from slicer |

---

## Appendix: API Endpoint Count by Domain

| Domain | Tag | Endpoints | In Plan? |
|---|---|---|---|
| Authentication | `authentication` | 6 | Common (API key) |
| Archives | `archives` | ~30 | Phase 2 (partial) |
| Queue | `queue` (implied) | 10 | Phase 3 (partial — needs expansion) |
| Maintenance | `maintenance` | 14 | Phase 5 (complete) |
| Printers | `printers` | ~18 | Phase 1 (status only) |
| Camera | `camera` | 4 | Not planned |
| Inventory | `inventory` | ~20 | Not planned |
| Projects | `projects` | ~18 | Not planned |
| Library | `library` | ~15 | Not planned |
| Smart Plugs | `smart-plugs` | ~10 | Not planned (reverse integration) |
| Notifications | `notifications` | ~12 | Not planned |
| Notification Templates | `notification-templates` | 5 | Not planned |
| Spoolman | `spoolman` | 8 | Indirect (via spoolman_sync) |
| Settings | `settings` | 8 | Not planned |
| Cloud | `cloud` | ~12 | Not planned |
| Filament Catalog | `filament-catalog` | 5 | Not planned |
| Local Presets | `local-presets` | 5 | Not planned |
| Print Log | `print-log` | 2 | Skipped (by design) |
| K-Profiles | `kprofiles` | 4 | Not planned |
| Users/Groups | `users`, `groups` | 10 | Not planned |
| Updates | `updates` | 4 | Not planned |
| External Links | `external-links` | 5 | Not planned |
| Firmware | `firmware` | 2 | Not planned |
| SpoolBuddy | `spoolbuddy` | ~15 | Not planned |
| Bug Report | `bug-report` | 3 | Not planned |
| API Keys | `api-keys` | 3 | Not planned |
| Webhook | `webhook` | 4 | Indirect (HA receives) |
| System/Support | `system`, `support` | 5 | Not planned |
| Discovery | `discovery` | 3 | Not planned |
| Virtual Printers | `virtual-printers` | 3 | Not planned |
| Pending Uploads | `pending-uploads` | 2 | Not planned |
| Metrics | `metrics` | 1 | Not planned |
| **TOTAL** | | **~280** | **~72 covered (~26%)** |
