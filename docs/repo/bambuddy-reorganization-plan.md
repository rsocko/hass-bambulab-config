# Bambuddy Reorganization — Execution Tracker

> **Source design document**: [`.github/prompts/plan-bambuddyReorganization.prompt.md`](../../.github/prompts/plan-bambuddyReorganization.prompt.md)
>
> This file tracks execution status. The prompt file is the **source of truth** for all design decisions, architecture, schema, enrichment strategies, and file-level specifications. Refer to it for implementation details.
>
> **API Reference**: All design docs have been cross-referenced against the live OpenAPI spec (Bambuddy v0.2.2.2). See [openapi-correction-notes.md](openapi-correction-notes.md) for per-phase corrections and [api-vs-design-guidance.md](api-vs-design-guidance.md) for development guidance covering all 280+ API endpoints.

## Overview

Break monolithic `bambuddy/` into 5 HA feature packages. HA's role is **READ + SURFACE + ENRICH + REACT** — Bambuddy owns archive creation, maintenance tracking, and queue management.

| Package | Depends On | Design Doc | Status |
|---------|-----------|------------|--------|
| `bambuddy_common` | — | [docs/features/bambuddy_common/README.md](../features/bambuddy_common/README.md) | **Complete** |
| `print_history` | Phase 1 | [docs/features/print_history/README.md](../features/print_history/README.md) | **Core complete** — advanced (photo review scripts/popup) pending |
| `print_queue` | Phase 1 | [docs/features/print_queue/README.md](../features/print_queue/README.md) | Not started |
| `print_statistics` | Phase 1 | [docs/features/print_statistics/README.md](../features/print_statistics/README.md) | Not started |
| `printer_maintenance` | Phase 1 + 4 | [docs/features/printer_maintenance/README.md](../features/printer_maintenance/README.md) | **Unblocked** — API endpoints confirmed via OpenAPI spec |

### Additional Design Docs

| Doc | Package | Purpose |
|-----|---------|---------|
| [photo-capture-design.md](../features/print_history/photo-capture-design.md) | print_history | Multi-camera, multi-stage capture flow |
| [archive-enrichment.md](../features/print_history/archive-enrichment.md) | print_history | Spoolman → Bambuddy tag/notes pipeline |
| [photo-review-design.md](../features/print_history/photo-review-design.md) | print_history | Post-print photo curation (remove/replace/cover) |

---

## Phase 1: `bambuddy_common` — Shared Infrastructure

*No dependencies. Start here.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 1 | Create directory tree | **Done** | automations/, rest_commands/, rest_sensors/, helpers/input_boolean/, helpers/input_text/ |
| 2 | Create `bambuddy_common_loader.yaml` | **Done** | 5 domain includes |
| 3 | Split shared helpers into individual files (2 `input_text` + 1 `input_boolean`) | **Done** | API key stored in `secrets.yaml` as `bambuddy_api_key` — not as an entity |
| 4 | Extract `bambuddy_printer_status` REST sensor | **Done** | list-item format in rest_sensors/ |
| 5 | Extract `bambuddy_refresh_printer_status` REST command | **Done** | |
| 6 | Create `bambuddy_webhook_receiver.yaml` | **Done** | Normalizes API + notification formats; fires `bambuddy_webhook_event`; gated by integration_enabled |
| 7 | Add commented `bambuddy_common_loader` to `_feature_loaders.yaml` | **Done** | All 5 Bambuddy loaders added commented-out |
| 8 | Create docs | **Done** | Design doc drafted earlier; updated below |

## Phase 2: `print_history` — Archive Reading, Photo Capture, Enrichment

*Depends on Phase 1.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 10 | Create directory tree | **Done** | automations, rest_commands, rest_sensors, scripts, template_sensors, helpers/*, dashboard_cards, dashboard_views |
| 11 | Create `print_history_loader.yaml` | **Done** | 9 domain includes (added input_number, input_select) |
| 12 | REST sensor: `bambuddy_print_history_sensor.yaml` | **Done** | Read-only, page 1 |
| 13 | REST commands: `bambuddy_upload_photo_to_archive.yaml` (POST photos), `bambuddy_delete_archive_photo.yaml` (DELETE photo), `bambuddy_set_archive_cover.yaml` (PATCH cover), `bambuddy_update_archive.yaml` (PATCH tags/notes), `bambuddy_add_archive_tags.yaml` (POST tags), `bambuddy_query_recent_archive.yaml` (GET fallback), `bambuddy_query_history_page.yaml` (GET pagination) | **Done** | 7 REST commands total |
| 14 | Archive ID capture automation | **Done** | Triggers on `print_started` webhook; stores archive_id; fallback query; snapshots tray map; resets manifest |
| 15 | Photo capture automation | **Done** | Multi-trigger: start (3min delay), mid, near-complete, finish — see [photo-capture-design.md](../features/print_history/photo-capture-design.md) |
| 16 | Error photo automation | **Done** | Triggers: print_failed, print_stopped, HMS error; queued mode (max: 3) |
| 17 | Snapshot capture+upload script | **Done** | Light → capture → upload; manifest tracking |
| 18 | Archive ID fallback script | **Done** | `GET /archives?printer_id=X&sort=-created_at&limit=1` + filename match |
| 19 | Enrichment automation | **Done** | Spoolman tags + notes via PATCH; tray map snapshot; cost data; see [archive-enrichment.md](../features/print_history/archive-enrichment.md) |
| 20 | History refresh automation | **Done** | Webhook print_complete/print_failed/print_stopped → 5s delay → refresh REST sensor |
| 21 | Pagination scripts | **Done** | `load_history_page.yaml`, `navigate_history.yaml` |
| 22 | Template sensors (modern format) | **Done** | 4 last-print + 2 pagination |
| 23 | Helpers | **Done** | 15 helpers: archive_id, page_data, camera, tray_map_snapshot, photo_manifest, fetch_enabled, capture booleans (4), mid-capture %, limit, current_page, review_timeout, review_state |
| 24 | Dashboard cards | **Done** | `print_history.yaml` (table), `print_history_browser.yaml` (pagination), `photo_review_chip.yaml` (conditional chip) |
| 25 | Dashboard view: `view_print_history.yaml` | **Done** | Registered in `common/dashboards/3d_printing.yaml` views list |
| 26 | Wire loader, finalize docs | **Done** | Uncommented in `_feature_loaders.yaml`; docs updated |
| 26a | Photo review scripts (advanced) | Not started | `review_delete_photo`, `review_replace_photo`, `review_set_cover`, `review_dismiss` |
| 26b | Photo review auto-dismiss automation (advanced) | Not started | `bambuddy_photo_review_auto_dismiss.yaml` |
| 26c | Photo review popup card (advanced) | Not started | browser_mod popup with per-photo actions | |

## Phase 3: `print_queue`

*Depends on Phase 1. Can run parallel with Phase 2.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 27 | Create directory tree + loader | Not started | |
| 28 | Webhook listener for `queue_ready` | Not started | |
| 29 | Extract 2 queue REST commands | Not started | |
| 30 | Extract queue REST sensor + `queue_count` template sensor | Not started | |
| 31 | Move queue dashboard card | Not started | |
| 32 | Wire loader, create docs | Not started | |

## Phase 4: `print_statistics`

*Depends on Phase 1. Can run parallel with Phases 2–3.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 33 | Create directory tree + loader | Not started | |
| 34 | Webhook listener for stats refresh | Not started | |
| 35 | Extract statistics REST sensor | Not started | |
| 36 | Convert 4 template sensors | Not started | |
| 37 | Move statistics dashboard card | Not started | |
| 38 | Wire loader, create docs | Not started | |

## Phase 5: `printer_maintenance`

*Depends on Phase 1 + Phase 4. **UNBLOCKED** — all maintenance API endpoints confirmed via OpenAPI spec v0.2.2.2. See [openapi-correction-notes.md](openapi-correction-notes.md#phase-5-printer_maintenance--unblocked).*

| Step | Description | Status | Blocked? | Notes |
|------|------------|--------|----------|-------|
| 39 | Create directory tree | Not started | | |
| 40 | Create `printer_maintenance_loader.yaml` | Not started | | |
| 41 | REST sensor: maintenance status per printer | Not started | | `GET /api/v1/maintenance/printers/{printer_id}` → `PrinterMaintenanceOverview` |
| 42 | REST command: mark task complete | Not started | | `POST /api/v1/maintenance/items/{item_id}/perform` with optional `{"notes": "..."}` |
| 43 | Template sensors: due_count, due_list, health_score | Not started | | Derived from REST sensor |
| 44 | Script: complete_maintenance_task | Not started | | Calls REST command → refresh |
| 45 | Automations: due_alert + webhook refresh | Not started | | |
| 46 | Helper: maintenance_alerts_enabled boolean | Not started | | |
| 47 | Dashboard cards (3): due chip, catalog, health | Not started | | |
| 48 | Dashboard view: `view_maintenance.yaml` | Not started | | Register in `_dashboards.yaml` |
| 49 | Wire loader, create docs | Not started | | |

## Phase 6: Cleanup

*Depends on all Phases 1–5.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 50 | Delete root `bambuddy/` directory | Not started | |
| 51 | Delete `homeassistant/packages/3d_printing/bambuddy_integration/` | Not started | |
| 52 | Delete `docs/features/bambuddy_integration/` | Not started | Already marked SUPERSEDED |
| 53 | Remove old `#bambuddy_integration_loader` from `_feature_loaders.yaml` | Not started | |
| 54 | Update cross-references | Not started | |
| 55 | Migrate unique content from `bambuddy/README.md` | Not started | → `bambuddy_common/README.md` |

## Phase 7: Verification

*Depends on Phase 6.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 56 | HA config check | Not started | |
| 57 | Entity audit | Not started | ~5 REST sensors, ~13 template, ~8 REST commands, ~14 helpers, ~9 automations, ~5 scripts |
| 58 | Photo capture test — all stages | Not started | start, mid, near-complete → local save + Bambuddy upload |
| 59 | Enrichment test — Spoolman tags/notes | Not started | Complete print → verify in Bambuddy |
| 60 | Dashboard verification — all cards + views | Not started | Including history + maintenance views |
| 61 | History pagination test | Not started | Navigate past page 1 |
| 62 | Maintenance test — mark complete from HA | Not started | |
| 63 | Uncomment all 5 loaders, deploy, verify | Not started | |

---

## Open Items

| # | Item | Blocking? | Phase | Resolution Path |
|---|------|-----------|-------|-----------------|
| 1 | ~~**Maintenance API endpoints**~~ | ~~**Yes**~~ | 5 | **RESOLVED** — `GET /api/v1/maintenance/printers/{printer_id}`, `POST /items/{item_id}/perform`, etc. Full list in [openapi-correction-notes.md](openapi-correction-notes.md#phase-5-printer_maintenance--unblocked) |
| 2 | ~~**Maintenance task schema**~~ | ~~**Yes**~~ | 5 | **RESOLVED** — `MaintenanceStatus` and `PrinterMaintenanceOverview` schemas fully documented. Hours-based tracking (not print count). |
| 3 | **Photo upload content type** — `POST /archives/{id}/photos` likely expects `multipart/form-data`. HA `rest_command` doesn't natively support file uploads. | No — design includes `shell_command` (curl) fallback | 1, 2 | Implement both paths; test during Phase 2 step 17 |
| 4 | **Webhook format for HA** — "Webhook (Custom)" provider: does it send flat notifications format or structured API format with `archive_id`? | No — receiver normalizes both | 1 | Test during Phase 1 step 7 |
| 5 | **`print_started` includes `archive_id`?** — API docs confirm it for `print_complete`. Likely yes for `print_started` since archive exists from start. | No — fallback script handles missing ID | 2 | Verify during Phase 2 step 14 |
| 6 | ~~**Photo delete endpoint**~~ | No | 2 | **RESOLVED** — `DELETE /api/v1/archives/{id}/photos/{filename}` confirmed in OpenAPI spec. Uses filename, not photo_id. |
| 7 | **Set-cover-photo endpoint** — assumed PATCH or dedicated endpoint for setting archive cover image. | No — blocks photo review only | 2 | Not found in OpenAPI spec — may need to use `PATCH /{id}` with a cover field or check Bambuddy source |
| 8 | **Dashboard view registration** — `view_print_history.yaml` and `view_maintenance.yaml` must be added to `common/dashboards/3d_printing.yaml` views list. | No | 2, 5 | `view_print_history.yaml` **Done** (added during Phase 2 step 25). Phase 5 still pending. |
| 9 | **Enrichment idempotency** — PATCHing tags/notes twice shouldn't create duplicates. | No | 2 | Verify Bambuddy behavior during testing |
| 10 | **Webhook image field** — payload can include base64 JPEG for some events. Could be decoded as bonus data. | No — nice-to-have | 2 | Defer to post-MVP enhancement |

## Key Design Decisions

Refer to the **Decisions** section in the [prompt file](../../.github/prompts/plan-bambuddyReorganization.prompt.md) for the full list. Summary:

- **HA role**: READ + SURFACE + ENRICH + REACT (not recreate)
- **Archive creation**: Bambuddy auto-creates at print start
- **Webhook**: Single receiver → HA event; features listen to the event
- **Photos**: HA owns multi-camera, multi-stage capture; uploads directly to Bambuddy
- **Enrichment**: Spoolman spool IDs + cost + vendor → Bambuddy tags + notes via PATCH
- **Maintenance**: Bambuddy is source of truth; HA reads + surfaces + allows mark-complete
- **Print Log**: Skipped (subset of archives)
- **AMS History**: Skipped (HA already records via ha-bambulab sensors)
- **Photo Review**: Post-print curation popup — delete, replace, set cover (see [design](../features/print_history/photo-review-design.md))

## Readiness Summary

| Phase | Ready? | Blockers |
|-------|--------|----------|
| 1 — bambuddy_common | **Yes** | None |
| 2 — print_history | **Core complete** | Photo review scripts/popup (steps 26a–26c) deferred to advanced phase |
| 3 — print_queue | **Yes** | None |
| 4 — print_statistics | **Yes** | None |
| 5 — printer_maintenance | **Yes** | API endpoints confirmed via OpenAPI spec |
| 6 — Cleanup | N/A | Depends on 1–5 |
| 7 — Verification | N/A | Depends on 6 |

**Recommendation**: Phase 1 complete. Phase 2 core complete (code fixed for OpenAPI corrections). Run Phases 3–5 in parallel. See [api-vs-design-guidance.md](api-vs-design-guidance.md) for per-phase implementation notes and priority order.
