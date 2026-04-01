# Bambuddy Reorganization — Execution Tracker

> **Source design document**: [`.github/prompts/plan-bambuddyReorganization.prompt.md`](../../.github/prompts/plan-bambuddyReorganization.prompt.md)
>
> This file tracks execution status. The prompt file is the **source of truth** for all design decisions, architecture, schema, enrichment strategies, and file-level specifications. Refer to it for implementation details.
>
> **API Reference**: All design docs have been cross-referenced against the live OpenAPI spec (Bambuddy v0.2.2.2). See [openapi-correction-notes.md](openapi-correction-notes.md) for per-phase corrections and [api-vs-design-guidance.md](api-vs-design-guidance.md) for development guidance covering all 280+ API endpoints.

## Overview

The root `bambuddy/` folder was an initial design/prototype attempt. It is not the canonical or current implementation. Canonical design lives under `docs/repo/` and `docs/features/`; canonical Home Assistant implementation lives under `homeassistant/packages/3d_printing/`.

This plan tracks the migration away from that early prototype into 5 HA feature packages. HA's role is **READ + SURFACE + ENRICH + REACT** — Bambuddy owns archive creation, maintenance tracking, and queue management.

| Package | Depends On | Design Doc | Status |
|---------|-----------|------------|--------|
| `bambuddy_common` | — | [docs/features/bambuddy_common/README.md](../features/bambuddy_common/README.md) | **Complete** |
| `print_history` | Phase 1 | [docs/features/print_history/README.md](../features/print_history/README.md) | **Core shipped and active** — browser/dashboard complete; advanced review/detail flows pending |
| `print_queue` | Phase 1 | [docs/features/print_queue/README.md](../features/print_queue/README.md) | Not started |
| `print_statistics` | Phase 1 | [docs/features/print_statistics/README.md](../features/print_statistics/README.md) | Not started |
| `printer_maintenance` | Phase 1 + 4 | [docs/features/printer_maintenance/README.md](../features/printer_maintenance/README.md) | **Unblocked** — API endpoints confirmed via OpenAPI spec |

### Additional Design Docs

| Doc | Package | Purpose |
|-----|---------|---------|
| [photo-capture-design.md](../features/print_history/photo-capture-design.md) | print_history | Multi-camera, multi-stage capture flow |
| [archive-enrichment.md](../features/print_history/archive-enrichment.md) | print_history | Spoolman → Bambuddy tag/notes pipeline |
| [photo-review-design.md](../features/print_history/photo-review-design.md) | print_history | Post-print photo curation (remove/replace/cover) |
| [archive-detection-recovery-design.md](../features/print_history/archive-detection-recovery-design.md) | print_history | Detect incomplete Bambuddy archives and define no-code-change repair options |
| [archive-detection-phase1-scope.md](../features/print_history/archive-detection-phase1-scope.md) | print_history | Collapsed recommended first build slice: detection and visibility only |
| [archive-detection-implementation-plan.md](../features/print_history/archive-detection-implementation-plan.md) | print_history | Design-only phased plan for HA detection, exception UX, and future recovery orchestration |
| [archive-recovery-n8n-design.md](../features/print_history/archive-recovery-n8n-design.md) | print_history | `n8n` recovery workflow contract, retry policy, and outcome model |
| [archive-exception-ux-design.md](../features/print_history/archive-exception-ux-design.md) | print_history | UX design for row markers, exception card, and status chip |
| [archive-detection-execution-checklist.md](../features/print_history/archive-detection-execution-checklist.md) | print_history | Design-to-build execution checklist for phased delivery |

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
| 13 | REST commands: delete photo, set cover, update archive, fetch archives, query recent archive | **Done** | JSON-hint photo upload artifact removed; multipart upload remains a separate shell/external bridge |
| 14 | Archive ID capture automation | **Done** | Triggers on `print_started` webhook; stores archive_id; fallback query; snapshots tray map; resets manifest |
| 15 | Photo capture automation | **Done** | Multi-trigger capture for start, mid-print, near-complete, and finish/error-adjacent flows — see [photo-capture-design.md](../features/print_history/photo-capture-design.md) |
| 16 | Error photo automation | **Done** | Triggers: print_failed, print_stopped, HMS error; queued mode (max: 3) |
| 17 | Snapshot capture+upload script | **Done** | Light → capture → Python shell upload; archive-detail verification; count-based runtime state |
| 18 | Archive ID fallback script | **Done** | `GET /archives/?printer_id=X&limit=1` + filename match |
| 19 | Enrichment automation | **Done** | Spoolman tags + notes via PATCH; tray map snapshot; cost data; see [archive-enrichment.md](../features/print_history/archive-enrichment.md) |
| 20 | History refresh automation | **Done** | Webhook completion/failure/stop events and manual refresh drive the Layer 1 archive cache via `print_history_refresh_requested` |
| 21 | Browser paging scripts | **Done** | `load_history_page.yaml`, `navigate_history.yaml`, `refresh_print_history_archives.yaml`, `clear_print_history_filters.yaml`, `toggle_print_history_color_filter.yaml` |
| 22 | Template sensors (modern format) | **Done** | Layer 1 cache (`print_history_archives`), Layer 2 filter metadata (`print_history_filtered`), page label, and current page slice |
| 23 | Helpers | **Done** | 28 helpers across `input_text`, `input_boolean`, `input_number`, and `input_select` |
| 24 | Dashboard cards | **Done** | `print_history_browser.yaml` (header + filter surface), `print_history_top_controls.yaml` (nav/page size/layout/refresh), `print_history.yaml` (archive grid), `photo_review_chip.yaml` (conditional status chip) |
| 25 | Dashboard view: `view_print_history.yaml` | **Done** | Registered in `common/dashboards/3d_printing.yaml` views list |
| 26 | Wire loader, finalize docs | **Done** | `print_history_loader` is active in `_feature_loaders.yaml`; docs track the shipped browser-first panel layout |
| 26a | Photo review scripts (advanced) | Not started | `review_delete_photo`, `review_replace_photo`, `review_set_cover`, `review_dismiss` |
| 26b | Photo review auto-dismiss automation (advanced) | Not started | `bambuddy_photo_review_auto_dismiss.yaml` |
| 26c | Photo review popup card (advanced) | Not started | browser_mod popup with per-photo actions | |

### Phase 2 Current State Snapshot

Implemented now:

- `print_history` is loaded by default via [homeassistant/packages/3d_printing/_feature_loaders.yaml](../../homeassistant/packages/3d_printing/_feature_loaders.yaml).
- The dashboard is a browser-first `panel: true` view with this flow: review chip, browser header, top control strip, archive grid, repeated bottom control strip.
- Filter/sort/page state is handled server-side by `sensor.print_history_archives`, `sensor.print_history_filtered`, `sensor.print_history_page_info`, and `sensor.print_history_page_archives`.
- The renderer supports `Compact`, `Media`, and `Detail` card variants plus live multi-select color chips.

Still to do:

- Add richer per-photo metadata/retries or move fully to the planned Python worker.
- Build the actual photo-review actions and popup flow; today the chip is only a status entry point.
- Add archive-detail drilldown actions such as favorite toggle, compare, and richer Bambuddy deep links.
- Reconcile the advanced photo-review API contracts before enabling delete/set-cover in the shipped UI.

## Phase 3: `print_queue`

*Depends on Phase 1. Can run parallel with Phase 2.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 27 | Create directory tree + loader | Not started | |
| 28 | Webhook listener for `queue_ready` | Not started | |
| 29 | Extract queue REST commands, including lifecycle controls (`add`, `remove`, `start`, `stop`, `cancel`, `update`, `reorder`, `bulk`) | Not started | Promoted into near-core scope after API review |
| 30 | Extract queue REST sensor + `queue_count` template sensor | Not started | |
| 31 | Move queue dashboard card and add actionable lifecycle affordances | Not started | Start/stop/cancel/manual-start visibility should be in the base queue UX |
| 32 | Wire loader, create docs | Not started | |

## Phase 4: `print_statistics`

*Depends on Phase 1. Can run parallel with Phases 2–3.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 33 | Create directory tree + loader | Not started | |
| 34 | Webhook listener for stats refresh | Not started | |
| 35 | Extract statistics REST sensor | Not started | `/archives/stats` is the single core source for both base KPIs and richer efficiency metrics |
| 36 | Convert template sensors, including success rate plus energy/time-accuracy derivatives | Not started | Promoted into near-core scope after API review |
| 37 | Move statistics dashboard card and expose richer operational metrics | Not started | Include energy and per-printer efficiency where the current payload already supports it |
| 38 | Wire loader, create docs | Not started | |

## Phase 5: `printer_maintenance`

*Depends on Phase 1 + Phase 4. **UNBLOCKED** — all maintenance API endpoints confirmed via OpenAPI spec v0.2.2.2. See [openapi-correction-notes.md](openapi-correction-notes.md#phase-5-printer_maintenance--unblocked).*

| Step | Description | Status | Blocked? | Notes |
|------|------------|--------|----------|-------|
| 39 | Create directory tree | Not started | | |
| 40 | Create `printer_maintenance_loader.yaml` | Not started | | |
| 41 | REST sensor: maintenance status per printer | Not started | | `GET /api/v1/maintenance/printers/{printer_id}` → `PrinterMaintenanceOverview` |
| 42 | REST command: mark task complete | Not started | | `POST /api/v1/maintenance/items/{item_id}/perform` with optional `{"notes": "..."}` |
| 43 | Template sensors: due_count, due_list, health_score, fleet summary rollups | Not started | | Include cross-printer summary from `/maintenance/summary` or `/maintenance/overview` |
| 44 | Script: complete_maintenance_task | Not started | | Calls REST command → refresh |
| 45 | Automations: due_alert + webhook refresh | Not started | | |
| 46 | Helper: maintenance_alerts_enabled boolean | Not started | | |
| 47 | Dashboard cards (3+): due chip, catalog, health, optional fleet summary section | Not started | | Fleet rollup promoted into near-core scope after API review |
| 48 | Dashboard view: `view_maintenance.yaml` | Not started | | Register in `_dashboards.yaml` |
| 49 | Wire loader, create docs | Not started | | |

## Phase 6: Cleanup

*Depends on all Phases 1–5.*

| Step | Description | Status | Notes |
|------|------------|--------|-------|
| 50 | Delete root `bambuddy/` directory | Not started | Legacy prototype only; not canonical implementation |
| 51 | Delete `homeassistant/packages/3d_printing/bambuddy_integration/` | Not started | |
| 52 | Delete `docs/features/bambuddy_integration/` | Not started | Already marked SUPERSEDED |
| 53 | Remove old `#bambuddy_integration_loader` from `_feature_loaders.yaml` | Not started | |
| 54 | Update cross-references | Not started | |
| 55 | Migrate any still-useful prototype notes from `bambuddy/README.md` | Not started | Only if the content is still valid; canonical docs remain under `docs/` |

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
| 3 | **Photo upload content type** — `POST /archives/{id}/photos` expects `multipart/form-data`. HA `rest_command` doesn't natively support file uploads. | No — first phase is now in place | 1, 2 | Invalid JSON-hint upload YAML removed; active package now uses a `shell_command` bridge, with Python worker still the recommended hardening path |
| 4 | **Webhook format for HA** — "Webhook (Custom)" provider: does it send flat notifications format or structured API format with `archive_id`? | No — receiver normalizes both | 1 | Test during Phase 1 step 7 |
| 5 | **`print_started` includes `archive_id`?** — API docs confirm it for `print_complete`. Likely yes for `print_started` since archive exists from start. | No — fallback script handles missing ID | 2 | Verify during Phase 2 step 14 |
| 6 | **Photo delete contract mismatch** — current YAML uses `/photos/{photo_id}`, while earlier API review suggested filename-based deletes. | No — advanced review only | 2 | Reconcile OpenAPI/source review with the shipped `rest_command` before enabling review delete actions |
| 7 | **Set-cover-photo endpoint** — current YAML assumes `PATCH /archives/{id}` with `cover_photo_id`, but this still needs live confirmation. | No — blocks photo review only | 2 | Verify against Bambuddy source/live API before wiring cover selection into the dashboard |
| 8 | **Dashboard view registration** — `view_print_history.yaml` and `view_maintenance.yaml` must be added to `common/dashboards/3d_printing.yaml` views list. | No | 2, 5 | `view_print_history.yaml` **Done** (added during Phase 2 step 25). Phase 5 still pending. |
| 9 | **Enrichment idempotency** — PATCHing tags/notes twice shouldn't create duplicates. | No | 2 | Verify Bambuddy behavior during testing |
| 10 | **Webhook image field** — payload can include base64 JPEG for some events. Could be decoded as bonus data. | No — nice-to-have | 2 | Defer to post-MVP enhancement |

## Recommended Next Backlog

The API review makes the next implementation order clearer than the original tracker implied.

1. **Phase 3 core with lifecycle controls** — Build `print_queue` with `start`, `stop`, `cancel`, `PATCH`, `reorder`, and `bulk` support, not just add/remove. This closes the biggest gap between Bambuddy's queue API and the planned HA surface.
2. **Phase 4 core plus richer stats surface** — Build `print_statistics` with the current base KPIs plus energy and time-accuracy signals from the same `/archives/stats` response.
3. **Phase 5 core plus fleet summary read path** — Build `printer_maintenance` around per-printer status and task completion, but also include cross-printer due/warning rollups from `/maintenance/summary` or `/maintenance/overview`.
4. **Phase 2 follow-on history work** — After Phases 3–5 are wired, return to `print_history` for multipart photo upload, archive-detail drilldown, favorites, and selective advanced history/media workflows.

## Scope Adjustments After API Review

### Promote Into Near-Core Scope

- **`print_queue` lifecycle controls** — `start`, `stop`, `cancel`, `PATCH`, `reorder`, `bulk`.
- **`print_statistics` energy and efficiency metrics** — `total_energy_kwh`, `total_energy_cost`, `prints_by_printer`, `time_accuracy_by_printer`.
- **`printer_maintenance` fleet summary reads** — `/maintenance/summary` and/or `/maintenance/overview`.

### Keep As Advanced / Backlog

- **`print_history` timelapse lifecycle, repair diagnostics, and reprint preflight** — high value, but depends on multipart media flows, admin actions, or queue context.
- **`print_queue` plate-clear verified auto-start** — needs camera calibration/reference management.
- **`print_statistics` rolling-window anomaly sensors** — needs additional date-window REST calls and more tuning.
- **`printer_maintenance` policy tuning, defaults recovery, and custom type creation** — useful admin flows, but not required for the base read/surface/react package split.

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
- **Photo Review**: Current UI ships a status chip only; full post-print curation popup remains advanced follow-on work (see [design](../features/print_history/photo-review-design.md))

## Readiness Summary

| Phase | Ready? | Blockers |
|-------|--------|----------|
| 1 — bambuddy_common | **Yes** | None |
| 2 — print_history | **Core shipped and active** | Photo upload is first-phase only; photo-review actions/popup and archive-detail actions remain deferred |
| 3 — print_queue | **Yes** | None |
| 4 — print_statistics | **Yes** | None |
| 5 — printer_maintenance | **Yes** | API endpoints confirmed via OpenAPI spec |
| 6 — Cleanup | N/A | Depends on 1–5 |
| 7 — Verification | N/A | Depends on 6 |

**Recommendation**: Phase 1 is complete and Phase 2 is live as a browser-first history surface. Run Phases 3–5 in parallel, then return to Phase 2 advanced work for multipart media upload, review actions, and archive-detail workflows. See [api-vs-design-guidance.md](api-vs-design-guidance.md) for per-phase implementation notes and priority order.
