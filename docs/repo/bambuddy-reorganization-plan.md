# Bambuddy Reorganization — Execution Tracker

> **Source design document**: [`.github/prompts/plan-bambuddyReorganization.prompt.md`](../../.github/prompts/plan-bambuddyReorganization.prompt.md)
>
> This file tracks execution status. The prompt file is the **source of truth** for all design decisions, architecture, schema, enrichment strategies, and file-level specifications. Refer to it for implementation details.

## Overview

Break monolithic `bambuddy/` into 5 HA feature packages. HA's role is **READ + SURFACE + ENRICH + REACT** — Bambuddy owns archive creation, maintenance tracking, and queue management.

| Package | Depends On | Design Doc | Status |
|---------|-----------|------------|--------|
| `bambuddy_common` | — | [docs/features/bambuddy_common/README.md](../features/bambuddy_common/README.md) | **Complete** |
| `print_history` | Phase 1 | [docs/features/print_history/README.md](../features/print_history/README.md) | Not started |
| `print_queue` | Phase 1 | [docs/features/print_queue/README.md](../features/print_queue/README.md) | Not started |
| `print_statistics` | Phase 1 | [docs/features/print_statistics/README.md](../features/print_statistics/README.md) | Not started |
| `printer_maintenance` | Phase 1 + 4 | [docs/features/printer_maintenance/README.md](../features/printer_maintenance/README.md) | **Blocked** |

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
| 10 | Create directory tree | Not started | automations, rest_commands, rest_sensors, scripts, template_sensors, helpers/*, dashboard_cards, dashboard_views |
| 11 | Create `print_history_loader.yaml` | Not started | 8 domain types |
| 12 | REST sensor: `bambuddy_print_history_sensor.yaml` | Not started | Read-only, page 1 |
| 13 | REST commands: `bambuddy_upload_photo_to_archive.yaml` (POST photos), `bambuddy_delete_archive_photo.yaml` (DELETE photo), `bambuddy_set_archive_cover.yaml` (PATCH cover), `bambuddy_update_archive.yaml` (PATCH tags/notes), `bambuddy_add_archive_tags.yaml` (POST tags) | **Partial** | 3 photo commands already created (moved from bambuddy_common); 2 enrichment commands not started |
| 14 | Archive ID capture automation | Not started | Triggers on `print_started` webhook; stores archive_id; fallback query |
| 15 | Photo capture automation | Not started | Multi-trigger: start, mid, near-complete — see [photo-capture-design.md](../features/print_history/photo-capture-design.md) |
| 16 | Error photo automation | Not started | Triggers: print_failed, print_stopped, HMS error |
| 17 | Snapshot capture+upload script | Not started | Light → capture → upload; multipart upload concern |
| 18 | Archive ID fallback script | Not started | `GET /archives?printer_id=X&sort=-created_at&limit=1` + filename match |
| 19 | Enrichment automation | Not started | See [archive-enrichment.md](../features/print_history/archive-enrichment.md) |
| 20 | History refresh automation | Not started | Webhook print_complete/print_failed → refresh REST sensor |
| 21 | Pagination scripts | Not started | `load_history_page.yaml`, `navigate_history.yaml` |
| 22 | Template sensors (modern format) | Not started | 4 last-print + 2 pagination |
| 23 | Helpers | Not started | ~13 helpers: archive_id, page_data, camera, fetch_enabled, capture booleans (4), mid-capture %, limit, current_page, photo manifest, review state |
| 24 | Dashboard cards | Not started | print_history.yaml (compact), print_history_browser.yaml (paginated), photo_review chip |
| 25 | Dashboard view: `view_print_history.yaml` | Not started | Register in `_dashboards.yaml` |
| 26 | Wire loader, finalize docs | Not started | |

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

*Depends on Phase 1 + Phase 4. **Currently blocked** — see [Open Items](#open-items).*

| Step | Description | Status | Blocked? | Notes |
|------|------------|--------|----------|-------|
| 39 | Create directory tree | Not started | | |
| 40 | Create `printer_maintenance_loader.yaml` | Not started | | |
| 41 | REST sensor: maintenance status per printer | Not started | **Yes** | Need endpoint discovery |
| 42 | REST command: mark task complete | Not started | **Yes** | Need endpoint discovery |
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
| 1 | **Maintenance API endpoints** — wiki documents the feature but REST API reference doesn't list explicit endpoints. Need to discover `/api/v1/printers/{id}/maintenance` or similar. | **Yes** — blocks Phase 5 steps 41–42 | 5 | Test via Bambuddy's built-in API browser |
| 2 | **Maintenance task schema** — field names, task types, intervals, completion payload unknown. | **Yes** — blocks Phase 5 | 5 | Discover via API browser alongside #1 |
| 3 | **Photo upload content type** — `POST /archives/{id}/photos` likely expects `multipart/form-data`. HA `rest_command` doesn't natively support file uploads. | No — design includes `shell_command` (curl) fallback | 1, 2 | Implement both paths; test during Phase 2 step 17 |
| 4 | **Webhook format for HA** — "Webhook (Custom)" provider: does it send flat notifications format or structured API format with `archive_id`? | No — receiver normalizes both | 1 | Test during Phase 1 step 7 |
| 5 | **`print_started` includes `archive_id`?** — API docs confirm it for `print_complete`. Likely yes for `print_started` since archive exists from start. | No — fallback script handles missing ID | 2 | Verify during Phase 2 step 14 |
| 6 | **Photo delete endpoint** — `DELETE /archives/{id}/photos/{photo_id}` assumed but not confirmed in API docs. | No — blocks photo review only | 2 | Verify via API browser; needed for photo review feature |
| 7 | **Set-cover-photo endpoint** — assumed PATCH or dedicated endpoint for setting archive cover image. | No — blocks photo review only | 2 | Verify via API browser |
| 8 | **Dashboard view registration** — `view_maintenance.yaml` and `view_print_history.yaml` must be added to `common/dashboards/_dashboards.yaml`. | No | 2, 5 | Add during Phase 2 step 25 and Phase 5 step 48 |
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
| 2 — print_history | **Yes** | Photo upload method TBD (has fallback) |
| 3 — print_queue | **Yes** | None |
| 4 — print_statistics | **Yes** | None |
| 5 — printer_maintenance | **No** | Maintenance API endpoints unknown |
| 6 — Cleanup | N/A | Depends on 1–5 |
| 7 — Verification | N/A | Depends on 6 |

**Recommendation**: Begin Phase 1. Run Phases 2–4 in parallel after Phase 1 completes. Discover maintenance API endpoints during Phases 2–4 to unblock Phase 5.
