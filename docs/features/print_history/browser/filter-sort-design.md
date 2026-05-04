# Print History — Filtering, Sorting & Pagination Design

> **Status**: Variant 3 custom integration with local-store path is the only active browser backend; the legacy YAML browser and Variant 1 AppDaemon sidecar were archived out of deploy scope on 2026-04-10, and the active dashboard moved to frontend websocket queries on 2026-04-11 so large page/activity payloads are no longer stored in HA entity state
> **Created**: 2026-03-28
> **Depends on**: [README.md](README.md), [bambuddy-archive-api-catalog.md](../../features/bambuddy_common/bambuddy-archive-api-catalog.md)
> **Pattern reference**: [filament-catalog.md](../filament_catalog/filament-catalog.md) Phase 2 (Filter Architecture)

## Problem Statement

This document captures the implemented baseline for the print history browser: a bulk archive cache in Layer 1, a server-side filter/sort/page layer in Layer 2, and an always-visible top control bar with card variants in Layer 3. It also remains the place to document follow-on refinements and scaling decisions.

## Current Architecture Status

As of 2026-04-10, the repository is no longer only at the original YAML baseline described later in this document.

The implemented runtime state is:

- Variant 3 is live as the `bambuddy` custom integration plus frontend websocket queries from the active dashboard cards.
- The legacy YAML browser backend now lives under `archive/print_history/legacy-yaml-browser/` for reference only.
- The former Variant 1 AppDaemon sidecar now lives under `archive/print_history/appdaemon-browser/` for reference only.

Current architecture decision:

- The `bambuddy` custom integration is now the durable implementation path.
- Treat the archived YAML and AppDaemon variants as historical design references rather than fallback deploy targets.
- Keep Variant 4 deferred unless print history clearly becomes a broader archive service with multiple clients or admin-heavy service semantics.
- The active dashboard path is `custom:print-history-browser-card` plus direct websocket queries; the older Layer 1/Layer 2 page and activity payload sensors are retired and should be treated as historical content below.

## Search Contract

The shipped browser search helper, `input_text.print_history_search`, remains part of the local Variant 3 query pipeline.

Current browser search intentionally behaves as a broad local lookup across archive identifiers and operational fields, not only as a pure full-text search box.

The active local search contract includes:

- archive IDs and original-archive IDs
- printer IDs and printer names
- print name
- designer
- project name
- failure reason
- tags

Bambuddy's `/archives/search` endpoint is not a drop-in replacement for that helper because it searches a different field set, notably adding `filename` and `notes` but not preserving all of the current ID/printer/project/failure lookup behavior.

Issue `#840` was reviewed against the active browser architecture. Current recommendation: keep the existing text box on the local search path and do not add a primary-browser full-text toggle unless a separate advanced search mode is intentionally designed. See [full-text-search-evaluation.md](full-text-search-evaluation.md) for the detailed evaluation.

## Duplicate Filter Contract

Issue `#737` adds duplicate browsing support without expanding Layer 1 into a full duplicate-members cache.

The current contract is:

- Layer 1 archive projection may persist only the reusable scalar fields needed across browser consumers: `duplicate_count`, `duplicate_sequence`, and `original_archive_id`
- Layer 1 should not mirror Bambuddy's full `duplicates` array or card-specific wording
- Layer 2 owns duplicate filter semantics and classification rules for `All`, `Sources`, `Original Only`, `Dupes Only`, and `Source + Dupes`
- Layer 3 owns final wording and chip text for the archive cards and popup

Current filter semantics:

- `Sources` means rows whose explicit duplicate lineage identifies the row as the source archive for a duplicate family
- `Original Only` means rows that are neither duplicate children nor explicit duplicate sources
- `Dupes Only` means duplicate children identified by `original_archive_id` or `duplicate_sequence > 0`
- `Source + Dupes` means the union of explicit sources and duplicate children
- `All` remains the unfiltered view

Follow-on work such as related-item navigation, compare flows, or suspicious same-hash review should use popup detail hydration or a dedicated query path rather than widening the base archive projection.

## Shipped Multi-Select Actions

Issue `#919` adds a shipped browser-side multi-select action flow for archives.

Current contract:

- the top control strip exposes `Select Prints` in normal mode
- entering selection mode swaps the toolbar into a bulk-action row instead of mixing paging and destructive actions together
- actual selected archive IDs stay local to the browser custom card
- shared Home Assistant helpers carry only mode and summary state so the YAML toolbar and JS card stay aligned
- `Select All` applies only to the currently visible page
- bulk actions currently cover user-tag updates, project assignment, favorite/unfavorite, and delete

Important guardrails:

- bulk tag edits must preserve system-managed tags
- bulk project and favorite updates rely on field-optional PATCH payloads and must not clear unrelated fields
- card open, favorite, and media-gallery interactions are suppressed while selection mode is active

See [multi-select-actions-design.md](multi-select-actions-design.md) for the detailed design and implementation contract.

## Planned Multi-Select Filter Expansion

Issue `#784` starts with the tag filter.

Current recommendation:

- keep the existing color filter as the only always-visible multi-select choice row
- move tags to a compact custom multi-select picker opened from the normal `Tag` filter pill
- support one or more selected user tags plus explicit `Any` versus `All` tag logic
- keep filter-specific clear behavior so clearing tags clears the entire tag selection, not only the last chosen value
- keep typeahead local to the picker instead of adding per-keypress backend work

This is intentionally different from the color filter because textual filters benefit from search more than constant visibility.

The follow-on evaluation for designer, project, material, printer, status, and other filters is documented in [multi-select-filter-design.md](multi-select-filter-design.md).

## Reading This Document Today

Use this file as a historical design record for the earlier YAML, AppDaemon, and custom-integration option analysis.

For the current shipped runtime contract, prefer `README.md` in this folder and the live package/custom-component code. In particular:

- large page and activity payloads are no longer stored in Home Assistant entity state
- the active browser queries Bambuddy directly over websocket
- lightweight summary entities such as `sensor.bambuddy_print_history_browser_status`, `sensor.bambuddy_print_history_browser_filtered`, `sensor.bambuddy_print_history_browser_page_info`, and `sensor.bambuddy_print_history_browser_activity` remain part of the active contract
- references below to `sensor.print_history_archives`, `sensor.print_history_filtered`, `sensor.print_history_page_info`, and `sensor.print_history_page_archives` describe superseded designs unless explicitly marked otherwise

## Goals

1. **Consistent UX** — Reuse the repository's existing filter/sort language and visual language from the Filament Catalog, with a permanently visible top control bar rather than modal browsing controls
2. **Server-side browser state** — Keep filter, sort, and page logic in HA template sensors so the dashboard only renders the current slice
3. **Responsive pagination** — Navigate pages without re-polling the API
4. **Scalable** — Work well at 50 archives, degrade gracefully at 1000+
5. **Focused page layout** — Keep the archive browser as the hero surface while keeping the controls accessible on the first screen
6. **Visual flexibility** — Support 2-3 archive record card variants so users can switch between dense browsing and larger media previews
7. **Incremental** — Can be added to the existing print_history package without breaking current functionality

---

## Data Strategy: Slim vs Full Archives

### The Core Question

The `/slim` endpoint returns a minimal set of fields (~200 bytes/archive). But meaningful filtering (e.g., by filament color) and card rendering (e.g., thumbnails, designer info) requires fields that only exist in the full `/archives` response.

### Field Comparison: Slim vs Full vs What We Need

| Field | In Slim? | In Full? | Needed For | Category |
|-------|----------|----------|------------|----------|
| `printer_id` | ✅ | ✅ | Printer filter | Filter |
| `print_name` | ✅ | ✅ | Search, display | Filter + Display |
| `print_time_seconds` | ✅ | ✅ | Sort | Sort |
| `actual_time_seconds` | ✅ | ✅ | Duration sort/display | Sort + Display |
| `filament_used_grams` | ✅ | ✅ | Sort, display | Sort + Display |
| `filament_type` | ✅ | ✅ | Material filter | Filter |
| `filament_color` | ✅ | ✅ | **Color filter**, color swatches | **Filter + Display** |
| `status` | ✅ | ✅ | Status filter | Filter |
| `started_at` | ✅ | ✅ | Date filter, sort | Filter + Sort |
| `completed_at` | ✅ | ✅ | Display | Display |
| `cost` | ✅ | ✅ | Sort, display | Sort + Display |
| `quantity` | ✅ | ✅ | Display | Display |
| `created_at` | ✅ | ✅ | Display | Display |
| **`id`** | ❌ | ✅ | **Thumbnail URL construction**, detail link | **Critical Display** |
| `layer_height` | ❌ | ✅ | Display, potential filter | Display |
| `nozzle_diameter` | ❌ | ✅ | Display | Display |
| `nozzle_temperature` | ❌ | ✅ | Display | Display |
| `total_layers` | ❌ | ✅ | Display | Display |
| `sliced_for_model` | ❌ | ✅ | Display | Display |
| `designer` | ❌ | ✅ | Display, search | Display |
| `makerworld_url` | ❌ | ✅ | Link | Display |
| `is_favorite` | ❌ | ✅ | Filter, display | Filter + Display |
| `tags` | ❌ | ✅ | Filter (enriched tags), search | Filter |
| `notes` | ❌ | ✅ | Search | Search |
| `failure_reason` | ❌ | ✅ | Display (on failures) | Display |
| `thumbnail_path` | ❌ | ✅ | Card image | Display |
| `extra_data.filament_slots[]` | ❌ | ✅ | Per-color grams, color swatches | Display |
| `extra_data._print_data.*` | ❌ | ✅ | Raw AMS tray data | *(Not needed)* |

### What's Missing from Slim That Actually Matters

1. **`id`** — Can't construct thumbnail URLs (`/archives/{id}/thumbnail`) without it. This alone makes slim insufficient for card rendering.
2. **`is_favorite`** — Can't filter or highlight favorites.
3. **`tags`** — Can't filter by operator-managed archive tags.
4. **`designer`** — Can't search by designer name.
5. **`layer_height`** — Nice for display but not critical for filtering.
6. **`filament_slots[]`** — Per-slot color hex codes and gram usage. Richer than the comma-separated `filament_color` string (which IS in slim). Useful for color swatch rendering.

Note: `filament_color` (comma-separated hex string like `#000000,#FFFFFF,#C12E1F`) IS in the slim response, so basic color filtering is possible without full data. However, per-slot breakdown requires `extra_data.filament_slots[]`.

### Options Evaluated

#### Option A: Use `/slim` as originally designed
- **Pro**: Small payload (~200 bytes/archive), fast
- **Con**: No `id` (no thumbnails), no favorites, no tags, no designer. The card would be text-only with no images. Fundamentally insufficient for a good history view.
- **Verdict**: ❌ Rejected — missing `id` is a dealbreaker

#### Option B: Use full `/archives` and trim in template
- **Source**: `GET /archives/?limit=500`
- **Pro**: ALL fields available — thumbnails, tags, favorites, designer, filament_slots
- **Con**: The full response includes `extra_data` with the enormous `_print_data.raw_data.ams[].tray[]` blob (~8-12 KB per archive). At 500 archives, that's 4-6 MB of JSON in a single sensor attribute.
- **Verdict**: ⚠️ Feasible ONLY if we trim `extra_data` down

#### Option C: Full `/archives` with Jinja2 field projection in Layer 1 ← **RECOMMENDED**
- **Source**: `GET /archives/?limit=500`
- **Approach**: The trigger-based template sensor fetches the full response, then the attribute template **projects** (cherry-picks) only the fields we need into a trimmed array before storing as `archives_json`.
- **How**: Jinja2 `for` loop builds a new list of dicts with only the ~20 fields we want, discarding `extra_data._print_data`, `file_path`, `content_hash`, `duplicates`, etc.
- **Per-archive size**: ~400-500 bytes (vs ~200 for slim, vs ~10-15 KB for raw full)
- **500 archives**: ~200-250 KB (comfortable for HA state machine)
- **Pro**: All useful fields available for filtering and display; bloat stripped at ingest
- **Con**: The initial API response is still large (fetched once, processed once, then discarded). Jinja2 projection loop adds ~0.5s processing on each fetch. This happens on trigger events (~5-min interval), NOT on filter changes.
- **Verdict**: ✅ Best balance — rich data for filtering/display, manageable storage

#### Option D: Two-tier fetch — slim for filter + on-demand detail
- **Approach**: Fetch `/slim` for the list. When rendering a card row, fetch `/archives/{id}` for thumbnail + details.
- **Con**: N+1 API calls on each page render. Rate limited. Slow. Complex. Doesn't solve the filter problem (no `id` in slim means we can't even fetch details).
- **Verdict**: ❌ Rejected — impractical

#### Option E: Fetch full JSON → save to disk → read from file
- **Approach**: A `shell_command` or automation fetches the full response to `/config/www/3d_printing/print_history/archives_cache.json`, then a `command_line` sensor reads from disk.
- **Pro**: Decouples fetch frequency from template evaluation. Could store the full raw response with no size concern.
- **Con**: HA's `command_line` sensor still parses the JSON in Jinja2 — same template evaluation cost. The disk roundtrip adds I/O latency. File management (permissions, cleanup) is fragile. And the real bottleneck is Jinja2 iteration, not the fetch or storage — so this doesn't meaningfully help.
- **Verdict**: ❌ Rejected — solves the wrong problem. The bottleneck is template eval speed, not storage.

#### Option F: Fetch full JSON → trim in Python (AppDaemon / custom component)
- **Approach**: A Python-based HA component or AppDaemon app fetches, trims, indexes, and exposes the data as a sensor.
- **Pro**: Python is orders of magnitude faster than Jinja2 for iteration/filtering. Could handle 5000+ archives easily.
- **Con**: Adds a runtime dependency (AppDaemon or custom component). Breaks the "pure YAML" approach. Overkill for <1000 archives.
- **Verdict**: ❌ Deferred — only consider if Jinja2 becomes the bottleneck at 1000+ archives

---

## Future Architecture Escalation Paths

The implemented YAML pipeline is the right baseline for this repository, but it is not the final scaling shape if print history continues to grow in archive count and feature scope.

The important constraint is not just Bambuddy fetch size. It is where the browser cache lives and how much data Home Assistant has to materialize in entity attributes.

### 2026-04-05 Reality Check

Live measurements against the current repository and running system:

- Raw Bambuddy `GET /archives/?limit=200` response: **~1.53 MB** (`~7633` chars/archive)
- Current Layer 1 `sensor.print_history_archives.attributes.archives_json`: **223184 chars** (`~1116` chars/archive)
- Current diagnostics status at 200 archives: **fail**
- Current comfortable archive estimate: **143**
- Current upper bound estimate: **170**

That means the current Layer 1 projection already removes most of the Bambuddy payload, but the remaining HA-side attribute payload is still large enough to breach the browser budget.

### Why Additional Trimming Alone Is Not The Long-Term Answer

Some additional Layer 1 trimming is still worth doing, but the live numbers show the architectural boundary clearly:

- `notes` are the largest single Layer 1 field by serialized share (`~18.8%`)
- `filament_slots` are still larger than `tags`
- `thumbnail_path` is also materially larger than `tags`
- removing all note display names would only recover about `~6300` chars (`~2.8%` of payload)

That is a useful optimization, but it does not change the fact that the browser is still moving a large cache through the HA state machine.

The next-step architecture question is therefore:

> Where should the canonical print-history browser cache, filtering, and paging logic live once YAML/Jinja2 stops being the comfortable boundary?

### The Four Repo-Relevant Variants

This repository has four realistic backend evolution paths:

1. **AppDaemon query/cache layer**
2. **Custom integration with HA-managed in-memory cache**
3. **Custom integration with local materialized store**
4. **Dedicated sidecar-backed browser cache**

The frontend-only custom-card idea is intentionally **not** counted as a backend variant here. It can be paired with any of the four options below, but by itself it does not solve the Layer 1 payload ceiling.

### At-A-Glance Comparison

| Variant | Runtime Boundary | Keeps Browser Inside HA? | Keeps Giant Layer 1 Attribute? | Operational Cost | Best Use |
|--------|------------------|--------------------------|--------------------------------|------------------|----------|
| AppDaemon query/cache layer | AppDaemon app + HA entities/services | Mostly | No | Low-Medium | Fastest escape from Jinja2 |
| Custom integration (in-memory) | HA custom component | Yes | No | Medium | Long-term HA-native browser logic |
| Custom integration (local store) | HA custom component + SQLite/`.storage`-style cache | Yes | No | Medium-High | Durable HA-native indexing/search |
| Dedicated sidecar-backed cache | Separate service + HA integration contract | No, HA becomes client/control plane | No | High | Browser becomes a small application |

---

## Variant 1: AppDaemon Query/Cache Layer

### Target Shape In This Repo

**Goal:** Move fetch, projection, filtering, and pagination out of Jinja2 quickly without committing to a full custom integration.

**What moves:**

- Bambuddy fetch and field projection move from `template_sensors/print_history_archives.yaml` into an AppDaemon app
- filter/sort/page computation moves out of `template_sensors/print_history_filtered.yaml`
- page-slice generation moves out of `template_sensors/print_history_archive_data.yaml`

**What stays in HA YAML:**

- existing filter helpers (`input_select`, `input_text`, `input_number`, `input_boolean`)
- scripts and dashboard actions
- the Lovelace card layouts
- diagnostic/status entities exposed by the AppDaemon app

**Likely entities/services exposed by AppDaemon:**

- `sensor.print_history_browser_status`
- `sensor.print_history_browser_page`
- `sensor.print_history_browser_page_info`
- optional `event` or service to refresh cache immediately

**Suggested contract:**

- AppDaemon reads the same helper values the current Layer 2 pipeline reads
- AppDaemon publishes only the **current page slice** and compact page metadata back to HA
- AppDaemon keeps the full archive index in Python memory, not in a HA attribute

### What Happens To Layer 1?

The current Layer 1 as a giant `archives_json` attribute should stop being authoritative.

Best repo-specific shape:

- retire the current `sensor.print_history_archives.attributes.archives_json`
- replace it with a much smaller status sensor that exposes:
  - cache health
  - last refresh time
  - total archive count
  - sync status/error state

So the answer is: **Layer 1 still exists conceptually, but not as a large HA-side payload cache.** It becomes a lightweight health/status surface over an AppDaemon-owned cache.

### Pros

- fastest path out of Jinja2 bottlenecks
- low ceremony for prototyping filter/index behavior
- can reuse almost all current HA helper and dashboard structure
- minimal migration pressure on the current UI

### Cons

- additional runtime outside normal HA integration patterns
- more ad hoc persistence/recovery choices
- more split-brain debugging between HA and AppDaemon
- not ideal as the final architecture if print history becomes a core feature area

### Best Fit For This Repo

Use this if the immediate goal is:

- prove the next query model quickly
- remove payload pressure fast
- preserve the existing dashboard contract while buying time for a more durable architecture decision

---

## Variant 2: Custom Integration With HA-Managed In-Memory Cache

### Target Shape In This Repo

**Goal:** Keep print history fully HA-native, but move fetch/projection/filter logic into Python using normal HA integration patterns.

**What moves:**

- current Layer 1 fetch/projection becomes a coordinator-backed integration cache
- current Layer 2 filtering and sort logic becomes integration code
- current Layer 3 page payload comes from integration-managed entities or services

**What stays in HA YAML:**

- dashboard composition
- helper-backed controls if desired
- print-history scripts that are still naturally HA automations

**Likely integration surfaces:**

- a coordinator that fetches Bambuddy archives and stores a normalized in-memory list
- one or more lightweight entities such as:
  - `sensor.print_history_archive_count`
  - `sensor.print_history_browser_page_info`
  - `binary_sensor.print_history_cache_stale`
- services like:
  - `print_history.refresh_cache`
  - `print_history.set_browser_filters`
  - `print_history.next_page`
  - `print_history.previous_page`

### What Happens To Layer 1?

The current YAML Layer 1 should be removed.

In this shape, **Layer 1 becomes an integration-owned in-memory cache**, not a template sensor attribute. HA can still expose a tiny summary entity for observability, but the full archive list should not be serialized back into entity attributes unless a tiny debug-only view is needed.

### Pros

- best long-term HA-native developer experience
- Python performance with native HA lifecycle patterns
- easier to test and package than AppDaemon
- avoids turning print history into a separate deployable service too early

### Cons

- more engineering effort than AppDaemon
- custom integration maintenance burden over time
- still requires careful entity contract design so HA is not used as a giant transport bus

### Best Fit For This Repo

Use this if the intended destination is:

- print history remains part of the HA package ecosystem
- browser logic should feel first-class and native
- archive browsing becomes stable, long-lived product surface inside this repository

---

## Variant 3: Custom Integration With Local Materialized Store

### Target Shape In This Repo

**Goal:** Stay HA-native, but introduce a durable indexed store for print history so the browser, popup, search, and future provenance features are not forced through coordinator memory or giant attributes.

### Materialized Store Scope

Variant 3 should not be implemented as either of these extremes:

- an `archive_id`-only local store that keeps almost all useful fields remote in Bambuddy
- a blind full duplicate of the entire Bambuddy schema treated as a second system of record

The intended shape is a **materialized read model** owned by the integration:

- mirror the Bambuddy fields that the browser, popup, search, provenance, and repair-review flows actually need
- store local-only fields that Bambuddy does not own, such as repair lineage, review state, mismatch classification, and local audit metadata
- derive query-friendly rows and indexes locally from those mirrored and local-only fields
- keep Bambuddy as the canonical source of truth for Bambuddy-owned fields

That means Variant 3 is intentionally a **scoped mirrored subset plus local extensions**, not an ID-only pointer layer and not a second authoritative archive database.

### Ownership Rules

To prevent drift and role confusion, Variant 3 should follow explicit ownership boundaries:

- **Bambuddy-owned fields** are mirrored locally and overwritten from Bambuddy on sync
- **local-only fields** are owned only by the integration store
- **derived/query fields** are recomputed locally from mirrored and local-only data
- **mutations to Bambuddy-owned fields** should go through Bambuddy or a narrow repair-sidecar boundary first, then resync the affected archive locally

The integration store should never become the authoring surface for mirrored Bambuddy fields such as runtime timestamps, status, favorite state, or other archive-core values that still belong to Bambuddy.

### Minimal Safe Schema

The minimum useful Variant 3 schema is more than `archive_id`, but still intentionally selective.

Recommended minimum tables:

- `archives`
- `archive_filament_rows`
- `archive_tags`
- `archive_photos`

Recommended minimum mirrored archive-core fields:

- `archive_id`
- `printer_id`
- `print_name`
- `status`
- `started_at`
- `completed_at`
- `created_at`
- `actual_time_seconds`
- `print_time_seconds`
- `filament_used_grams`
- `cost`
- `designer`
- `project_id`
- `project_name`
- `thumbnail_path`
- `is_favorite`

That baseline is enough to support local filter/sort/page behavior, archive card rendering, popup entry hydration, and query-efficient joins to child rows.

### Recommended Schema For Repair Review

If repair-review and provenance work are part of the expected roadmap, the better Variant 3 schema should also include:

- `archive_note_payload_rows`
- `archive_repair_lineage`
- optional review-oriented tables such as `archive_review_state` or `archive_mismatch_flags`

Recommended local-only or extension concepts:

- source-versus-target repair linkage
- duplicate or reprint relationships
- mismatch classification and review status
- local audit metadata for review workflow state
- provenance-oriented derived relationships that do not belong in Bambuddy's core archive schema

This is the point where Variant 3 becomes materially stronger than Variant 2: review and provenance logic can query first-class indexed local rows instead of reconstructing everything from a transient in-memory object graph.

**What changes beyond Variant 2:**

- the custom integration owns a local persistent store (for example SQLite or a disciplined `.storage`-style schema)
- Bambuddy data is normalized into tables/documents suited for browsing and lookup
- the integration exposes query results, not raw archive arrays

**Likely data model in this repo:**

- `archives`
- `archive_filament_rows`
- `archive_tags`
- `archive_note_payload_rows`
- `archive_photos`
- optional `archive_repair_lineage`

**Likely HA contract:**

- small summary entities only
- services for paged/filter queries
- optional per-archive detail service for popup hydration

### Sync And Anti-Drift Rules

Storing mirrored Bambuddy fields locally does create duplication, but the duplication is acceptable if the sync rules are explicit.

Recommended rules:

- store source-sync metadata such as `last_synced_at`, optional source update timestamp, and optional payload fingerprint or hash
- keep local-only review and lineage state in separate columns or separate tables rather than mixing it into mirrored archive-core ownership
- do not let local review metadata overwrite mirrored Bambuddy fields
- after any repair mutation, re-fetch and upsert the affected archive instead of trusting the pre-mutation local copy
- make stale or reconciliation-needed state explicit so review screens can surface uncertainty when sync freshness matters

Practical interpretation:

- Variant 3 should store every Bambuddy field needed to answer browser and review queries locally
- those mirrored fields should still behave like a read-through mirror, not locally authored truth

**Why this matters for this repo specifically:**

The advanced roadmap already points toward richer archive behavior:

- compare-on-failure
- duplicate and reprint intelligence
- searchable provenance
- archive mismatch and repair workflows
- richer popup/detail views

Those features are much easier to support from a local indexed model than from one giant JSON attribute.

### What Happens To Layer 1?

The current Layer 1 no longer exists in its current form.

Repo-specific answer:

- **remove Layer 1 as a browser payload cache**
- keep at most a small integration status entity such as `sensor.print_history_cache_status`
- treat the materialized store as the true archive cache boundary

So in this variant, **Layer 1 is replaced by the local database/store itself**.

### Pros

- durable HA-native cache with good query ergonomics
- strong fit for popup/detail/provenance/search growth
- keeps deployment simpler than a standalone service
- avoids repeated large re-projection work on every reload

### Cons

- meaningfully more code and schema ownership
- migration and recovery become your responsibility
- more complexity than the in-memory integration variant

### Best Fit For This Repo

Use this if:

- you want a serious long-term browser/search backend
- you still want everything to ship as part of Home Assistant
- you expect print history to keep gaining archive-centric features, but do not yet want a separate service boundary

---

## Variant 4: Dedicated Sidecar-Backed Browser Cache

### Target Shape In This Repo

**Goal:** Treat print history as a small archive application with HA as a client, automation plane, and dashboard host rather than the primary data-processing boundary.

This extends naturally from the repair-oriented sidecar direction already described in `../runtime-repair/archive-runtime-sidecar-api-and-compose.md`.

**Service responsibilities would expand to include:**

- Bambuddy archive fetch and normalization
- archive browser cache persistence
- filtering, sorting, paging, and search endpoints
- archive detail hydration
- provenance lookup
- optional repair/recovery/admin endpoints

**HA responsibilities would narrow to:**

- capture browser control state
- render current page and popup views
- call sidecar endpoints through REST commands or a thin integration wrapper
- surface health/status summaries
- continue handling automations that belong in HA

**Likely repo-specific API surface:**

- `GET /browser/archives?page=...&filters=...`
- `GET /browser/archives/{id}`
- `GET /browser/filter-options`
- `POST /browser/refresh`
- existing repair/admin endpoints remain alongside browser endpoints

### What Happens To Layer 1?

The current Layer 1/Layer 2/Layer 3 backend split is largely retired.

Repo-specific answer:

- Layer 1 is no longer needed as a HA entity cache
- Layer 2 is no longer needed as a HA template filter engine
- HA keeps only tiny status entities and action surfaces
- the sidecar becomes the real browser backend

So this is the variant where **Layer 1 should effectively disappear from the HA architecture**.

### Pros

- cleanest separation of concerns
- no HA state-machine pressure from large archive caches
- easiest path to real query/search/index features
- strongest alignment with future repair/recovery/provenance workflows
- easiest place to centralize audit logging and archive-admin operations

### Cons

- highest operational overhead
- separate deployment, auth, backup, migration, and observability concerns
- bigger architecture step than the repository currently needs for simple browsing alone

### Best Fit For This Repo

Use this if print history is becoming:

- a serious archive system
- a long-lived provenance and repair surface
- something expected to scale in both data volume and workflow complexity beyond what should comfortably live inside HA

---

## Recommendation Ladder For This Repository

### 2026-04-09 Decision Update

The original ladder below is still directionally correct, but the repo is now past the "should we prototype AppDaemon" stage.

Current decision after implementing Variant 1:

1. Variant 1 remains valid as the current spike and compatibility bridge.
2. The next step should be a `bambuddy` custom integration rather than expanding the AppDaemon sidecar into Variant 4 immediately.
3. Variant 2 is useful mainly as the first HA-native implementation boundary, not as the intended permanent stop.
4. Variant 3 remains the preferred durable target because the roadmap already points toward popup hydration, provenance, duplicate/reprint relationships, and repair-review workflows.
5. Variant 4 remains available, but deferred; having an existing sidecar container is not by itself a sufficient reason to promote print history into a standalone browser service.

Based on the current implementation, the live payload measurements, and the existing phase roadmap in `../planning/advanced-features-design.md`, the practical sequence is:

1. **Short term:** keep the YAML browser, trim obvious Layer 1 bloat where it is low-risk, and lower archive count when needed
2. **First architectural spike:** AppDaemon if the goal is to validate a non-Jinja cache/query contract quickly
3. **Preferred HA-native destination:** custom integration, ideally upgraded to a local materialized store if provenance/search/detail workflows keep expanding
4. **Full service boundary:** dedicated sidecar-backed browser cache only when the browser and repair/provenance/admin features justify owning a separate archive service

### Preferred Target Architecture

For this repository, the preferred medium-term destination is:

**a custom integration with a local materialized store**

That recommendation is specific to the current shape of this repo, not a general Home Assistant preference.

#### Why this is the best fit here

- The browser is already beyond a simple list view and now has a real data pipeline, dynamic filters, popup/detail flows, favorites, and enrichment-aware rendering.
- The phase roadmap already points toward richer archive behaviors such as compare, duplicate intelligence, searchable provenance, and repair/mismatch workflows.
- The live payload measurements show that simple YAML/Jinja trimming is no longer enough once archive count grows.
- The repository still benefits from staying HA-native for deployment, packaging, and dashboard integration.

In other words, this repo looks more like **"a serious HA feature that needs a real local data model"** than either:

- a lightweight YAML-only browser that can keep scaling indefinitely, or
- a full standalone archive service that must exist outside HA today.

#### Why not stop at AppDaemon

AppDaemon is still the best **spike** path if the goal is to validate the next query contract quickly.

It is not the preferred destination because:

- print history is already central enough in this repository to justify a first-class implementation path
- long-term debugging, packaging, and maintenance are cleaner in a custom integration
- AppDaemon would likely become a transitional cache owner rather than the final home of archive logic

So the recommendation is:

- use AppDaemon only if a short validation step is needed
- do not treat it as the intended final architecture unless implementation speed becomes more important than long-term maintainability

#### Why not stop at an in-memory custom integration

An in-memory integration is a good first landing zone, but the repo-specific roadmap suggests it is likely to age into a local-store design anyway.

The moment the browser needs durable indexed access for:

- popup hydration
- provenance lookups
- duplicate/reprint relationships
- archive mismatch review
- richer search/filter metadata

an integration-owned materialized store becomes the cleaner shape.

That means the recommended practical path is:

1. custom integration if you want the smallest durable HA-native step
2. local materialized store as the intended end state once the archive model expands further

#### Why not choose the dedicated sidecar now

The sidecar-backed browser cache is architecturally strong, but it should be reserved for the point where print history becomes an explicit service boundary rather than an HA-native feature area.

For this repo, that boundary likely starts to make sense only when one or more of the following become true:

- repair/recovery/admin flows become frequent, not exceptional
- the browser needs richer API semantics than HA services and entities should comfortably expose
- archive count and query behavior justify a standalone indexed backend
- the same backend needs to serve multiple clients or non-HA consumers

Until then, the sidecar introduces more operational surface area than this browser likely needs.

#### Recommended adoption sequence

Use this as the intended architecture path unless new constraints emerge:

1. Keep the current AppDaemon path as the active spike and stabilization baseline.
2. Build the durable implementation as a `bambuddy` custom integration.
3. Use an in-memory cache only as the first integration landing zone if that keeps the migration smaller.
4. Prefer a local materialized store once the integration needs durable archive indexing, popup hydration, provenance, or repair-review support.
5. Re-evaluate a dedicated sidecar only if print history clearly grows into a broader archive service.

#### Decision Statement

If development continued on the long-term architecture today, the recommended target for this repository would be:

> **Custom integration with a local materialized store, with AppDaemon allowed only as a validation spike and the dedicated sidecar deferred until print history becomes a true service boundary.**

#### What Variant 3 Can Still Cover

Variant 3 does not remove repair or review capability. It can still support:

- archive mismatch review backed by local indexed archive rows and lineage metadata
- compare-on-failure and source-versus-recovered archive inspection
- repair candidate lists, review queues, and audit-focused popup/detail views
- integration services that call Bambuddy or a narrow repair sidecar for mutation actions while HA keeps the browser/search/review model local

In other words, Variant 3 can own the archive browser, provenance model, and review workflow while still delegating exceptional write-heavy repair operations to a narrow sidecar when that remains the cleaner boundary.

### Decision Guidance

| If your priority is... | Prefer... |
|------------------------|-----------|
| Fastest escape from Jinja2 | AppDaemon |
| Long-term HA-native maintainability | Custom integration |
| HA-native plus durable query/index model | Custom integration with local materialized store |
| Strongest scaling and archive-admin boundary | Dedicated sidecar-backed browser cache |

### Bottom Line On Layer 1

For the current YAML implementation, Layer 1 is required.

For every Python or sidecar evolution path above, the current giant `archives_json` attribute should stop being the browser cache boundary.

In other words:

- **AppDaemon:** Layer 1 becomes a small status surface over an AppDaemon-owned cache
- **Custom integration (in-memory):** Layer 1 becomes an integration-owned cache, not a template sensor payload
- **Custom integration (local store):** Layer 1 is replaced by the local persistent store
- **Dedicated sidecar:** Layer 1 effectively disappears from HA and survives only as lightweight health telemetry

### Decision: Option C — Full Endpoint with Jinja2 Field Projection

The Layer 1 sensor fetches `GET /archives/?limit=500` and projects to a trimmed schema:

```jinja2
{# Project each archive to only the fields we need #}
{% set ns = namespace(trimmed=[]) %}
{% for a in raw_archives %}
  {% set slots = a.get('extra_data', {}).get('filament_slots', [])
       if a.get('extra_data') is mapping else [] %}
  {% set ns.trimmed = ns.trimmed + [dict(
    id=a.get('id'),
    printer_id=a.get('printer_id'),
    project_id=a.get('project_id'),
    project_name=(a.get('project_name') if a.get('project_name') is not none else ''),
    print_name=a.get('print_name', ''),
    print_time_seconds=a.get('print_time_seconds', 0),
    actual_time_seconds=a.get('actual_time_seconds'),
    filament_used_grams=a.get('filament_used_grams', 0),
    filament_type=a.get('filament_type', ''),
    filament_color=a.get('filament_color', ''),
    filament_slots=slots,
    status=a.get('status', ''),
    started_at=a.get('started_at', ''),
    completed_at=a.get('completed_at'),
    cost=a.get('cost', 0),
    object_count=a.get('object_count', 1),
    layer_height=a.get('layer_height'),
    total_layers=a.get('total_layers'),
    nozzle_diameter=a.get('nozzle_diameter'),
    designer=a.get('designer', ''),
    is_favorite=a.get('is_favorite', false),
    tags=a.get('tags', ''),
    notes=a.get('notes', ''),
    failure_reason=a.get('failure_reason', '')
  )] %}
{% endfor %}
{{ ns.trimmed | tojson }}
```

### Projected Archive Schema (~450 bytes per archive)

```json
{
  "id": 171,
  "printer_id": 1,
  "project_id": null,
  "project_name": "",
  "print_name": "Hueforge back to the future",
  "print_time_seconds": 15533,
  "actual_time_seconds": null,
  "filament_used_grams": 44.82,
  "filament_type": "PLA",
  "filament_color": "#000000,#FFFFFF,#C12E1F,#F4EE2A",
  "filament_slots": [
    {"slot_id": 1, "used_g": 29.69, "type": "PLA", "color": "#000000"},
    {"slot_id": 2, "used_g": 2.38, "type": "PLA", "color": "#FFFFFF"},
    {"slot_id": 7, "used_g": 8.45, "type": "PLA", "color": "#C12E1F"},
    {"slot_id": 8, "used_g": 4.3, "type": "PLA", "color": "#F4EE2A"}
  ],
  "status": "printing",
  "started_at": "2026-03-28T13:55:04.674129",
  "completed_at": null,
  "cost": 1.12,
  "object_count": 1,
  "layer_height": 0.08,
  "total_layers": 30,
  "nozzle_diameter": 0.4,
  "designer": "StefBull85",
  "is_favorite": false,
  "tags": "favorite,customer-sample",
  "notes": "",
  "failure_reason": ""
}
```

### Updated Size Estimates (Projected Schema)

| Archive Count | Projected JSON | vs Slim (~200B) | vs Raw Full (~10KB) | Template Eval | Practical? |
|---------------|---------------|-----------------|---------------------|---------------|------------|
| 50 | ~22 KB | +12 KB | -490 KB | <0.1s | ✅ Trivial |
| 200 | ~90 KB | +50 KB | -1.9 MB | ~0.3s | ✅ Comfortable |
| 500 | ~225 KB | +125 KB | -4.8 MB | ~0.8s | ✅ Good default |
| 1,000 | ~450 KB | +250 KB | -9.5 MB | ~2s | ⚠️ Noticeable |
| 2,000 | ~900 KB | +500 KB | -19 MB | ~4-5s | ⚠️ Sluggish |

The projected schema is roughly **2.2x** the size of slim but gives us every field needed for filtering and display. Compared to raw full (~10-15 KB/archive), it's a **95% reduction** (strips `_print_data`, AMS dumps, file paths, content hashes).

`quantity` still exists in the Bambuddy API, but the runtime browser/heatmap cache intentionally omits it. The active print history metrics use `object_count` for object totals and treat archive rows as the source of truth for print totals. If a future archive-detail popup wants to show API `quantity`, it can be added back as a display-only field without changing the current activity metrics.

### Additional Filters Enabled by Full Data

| Filter | Field | Helper Type |
|--------|-------|-------------|
| **Filament Color** | `filament_color` (also in slim) | `input_text` backing store + clickable color-chip row generated from unique colors across all archives |
| **Favorites** | `is_favorite` | `input_boolean` (`on` = favorites only) |
| **Has Tags** | `tags` (non-empty) | `input_boolean` |
| **Designer** | `designer` | `input_select` — dynamic |
| **Project** | `project_name` / `project_id` | `input_select` — dynamic, with persistent `None` for unassigned prints |
| **Layer Height** | `layer_height` | `input_select` — dynamic (`0.04`, `0.08`, `0.12`, `0.16`, `0.20`) |

---

## Architecture Overview

### Why This Differs from the Filament Catalog

The Filament Catalog filters **HA entities** (`sensor.spoolman_spool_*`) that are already in the state machine — the template sensor iterates entity states directly. Print History data lives in an **external API** (Bambuddy). There are no per-archive HA entities.

This creates a data plumbing challenge: we need to get archive data into HA's template engine in a filterable form.

### Layered Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: API Data Fetch + Field Projection                      │
│  Trigger-based template sensor + REST command action              │
│  Calls GET /archives → projects to trimmed schema (~450B/item)   │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: Server-Side Filter + Sort + Page                        │
│  Template sensors read Layer 1 attribute + input helpers          │
│  Output metadata plus the current visible archive slice          │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: Dashboard UI                                           │
│  Always-visible browser header + variant-aware archive records   │
│  Reads from Layer 2 sensor attributes                            │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
                ┌──────────────────┐
                │ Bambuddy API     │
                │ GET /archives/   │
                │ ?limit=500       │
                └────────┬─────────┘
                         │  JSON array (full, ~5 MB)
                         ▼
        ┌─────────────────────────────────────┐
        │ sensor.print_history_archives       │  Layer 1
        │ (trigger-based template)            │
        │                                     │
        │ Jinja2 projects to trimmed schema   │
        │ Strips extra_data._print_data, etc. │
        │                                     │
        │ state: archive count                │
        │ attr.archives_json: trimmed array   │
        │ (~225 KB for 500 archives)          │
        └────────────────┬────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌─────────────┐ ┌──────────┐ ┌──────────────┐
   │ input_select│ │input_text│ │ input_number  │
   │ (status,    │ │ (search) │ │ (page, size)  │
   │ material,   │ │          │ │               │
   │ color,      │ └──────────┘ └───────────────┘
   │ printer,    │
   │ favorites,  │
   │ date_range, │
   │ sort)       │
   └──────┬──────┘
          │
          ▼
  ┌─────────────────────────────────┐
  │ sensor.print_history_filtered   │  Layer 2
  │ (standard template sensor)      │
  │                                 │
  │ state: filtered count           │
  │ attr.page_json: current page    │
  │ attr.total_pages: N             │
  │ attr.active_filters: summary    │
  └───────────────┬─────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────┐
  │ Dashboard                       │  Layer 3
  │ • Browser toolbar + popups      │
  │ • Variant-aware archive cards   │
  │   w/ thumbnails from /archives  │
  │   /{id}/thumbnail               │
  │ • Pagination controls           │
  └─────────────────────────────────┘
```

---

## Layer 1: Data Fetch — Trigger-Based Template Sensor with Action

### Why This Approach

HA's `rest:` integration stores per-sensor values via `value_template`, but cannot store the full response array as an attribute (flat arrays are incompatible with `json_attributes` / `json_attributes_path`).

Starting with HA 2024.11, **trigger-based template sensors** support an `action` block that can call services and store response data as variables. Combined with `rest_command` response handling (HA 2023.7+), this gives us a clean way to fetch API data and store it in sensor attributes — all within native HA YAML.

### REST Command (data fetcher)

```yaml
# rest_commands/bambuddy_fetch_archives.yaml
bambuddy_fetch_archives:
  url: >-
    {{ states('input_text.bambuddy_api_base_url') }}/api/v1/archives/?limit={{
      states('input_number.print_history_max_archives') | int(500)
    }}
  method: GET
  headers:
    X-API-Key: !secret bambuddy_api_key
  content_type: application/json
```

### Trigger-Based Template Sensor (fetch + project + store)

```yaml
# template_sensors/print_history_archives.yaml
- trigger:
    # Regular polling
    - trigger: time_pattern
      minutes: "/5"
    # Refresh on print events (via Bambuddy webhook)
    - trigger: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_complete
    - trigger: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_failed
    - trigger: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_stopped
    # Refresh on HA start
    - trigger: homeassistant
      event: start
  action:
    - action: rest_command.bambuddy_fetch_archives
      response_variable: result
  sensor:
    - name: "Print History Archives"
      unique_id: print_history_archives
      icon: mdi:database-outline
      state: >-
        {% set content = result.get('content', '[]') %}
        {% if content is string %}
          {{ (content | from_json) | length }}
        {% else %}
          0
        {% endif %}
      attributes:
        archives_json: >-
          {# Project full archives to trimmed schema — strip extra_data._print_data #}
          {% set content = result.get('content', '[]') %}
          {% if content is string %}
            {% set raw = content | from_json %}
          {% elif content is iterable %}
            {% set raw = content | list %}
          {% else %}
            {% set raw = [] %}
          {% endif %}
          {% set ns = namespace(trimmed=[]) %}
          {% for a in raw %}
            {% set ed = a.get('extra_data', {}) if a.get('extra_data') is mapping else {} %}
            {% set slots = ed.get('filament_slots', []) %}
            {% set ns.trimmed = ns.trimmed + [dict(
              id=a.get('id'),
              printer_id=a.get('printer_id'),
              print_name=a.get('print_name', ''),
              print_time_seconds=a.get('print_time_seconds', 0),
              actual_time_seconds=a.get('actual_time_seconds'),
              filament_used_grams=a.get('filament_used_grams', 0),
              filament_type=a.get('filament_type', ''),
              filament_color=a.get('filament_color', ''),
              filament_slots=slots,
              status=a.get('status', ''),
              started_at=a.get('started_at', ''),
              completed_at=a.get('completed_at'),
              cost=a.get('cost', 0),
              object_count=a.get('object_count', 1),
              layer_height=a.get('layer_height'),
              total_layers=a.get('total_layers'),
              nozzle_diameter=a.get('nozzle_diameter'),
              designer=a.get('designer', ''),
              is_favorite=a.get('is_favorite', false),
              tags=a.get('tags', ''),
              notes=a.get('notes', ''),
              failure_reason=a.get('failure_reason', '')
            )] %}
          {% endfor %}
          {{ ns.trimmed | tojson }}
        last_fetch: >-
          {{ now().isoformat() }}
```

### Key Characteristics

- **Single entity** (`sensor.print_history_archives`) holds ALL fetched + projected archive data
- **Triggers on events** — immediate refresh when prints complete/fail, plus 5-minute polling
- **Field projection at ingest** — strips `extra_data._print_data` (AMS dumps, raw MQTT data) and other unused fields (`file_path`, `content_hash`, `duplicates`, `source_3mf_path`, etc.), keeping ~21 fields per archive
- **Activity metrics use `object_count`** — Layer 1 projects `object_count`, Layer 2 sums it for object totals, and print totals remain archive-count based
- **Preserves `filament_slots[]`** — extracted from `extra_data` before the rest is discarded. Provides per-slot color hex + grams for color swatch rendering.
- **Uses full `/archives/` endpoint** — not `/slim`, because `/slim` lacks `id` (needed for thumbnail URLs), `is_favorite`, `tags`, `designer`, and `extra_data.filament_slots[]`
- **~450 bytes/archive after projection** — vs ~200B (slim) and ~10-15 KB (raw full). 500 archives ≈ 225 KB.
- **Projection happens once per fetch** (every 5 min or on events), NOT on every filter change. Filter changes re-evaluate the already-trimmed data in Layer 2.
- **Layer 1 is intentionally streamlined** — avoid adding presentation-only labels, tooltip strings, or card-specific wording to the projected archive cache. Keep those transformations in Layer 2/Layer 3 unless the new field is part of the stable shared archive contract.

### What About the Existing REST Sensor?

That earlier recommendation is now superseded.

The old `bambuddy_print_history_sensor.yaml` REST path and its `sensor.bambuddy_last_print_*` derivatives are retired and archived under `archive/print_history/legacy-yaml-browser/`. The active print-history browser stack should use only the Bambuddy custom integration plus the lightweight template sensors that remain in `homeassistant/packages/3d_printing/print_history/`.

---

## Layer 2: Filter + Sort + Page — Template Sensor

### Filter Dimensions

Derived from the projected archive schema (full endpoint, trimmed fields):

| Filter | Helper Type | Options | Source Field |
|--------|-------------|---------|--------------|
| **Status** | `input_select` | `All`, `Completed`, `Failed`, `Cancelled`, `Printing` | `status` |
| **Material** | `input_select` | `All`, + dynamic from fetched data | `filament_type` |
| **Color** | `input_text` + generated buttons | Multi-select color swatches derived from unique `filament_color` values; matches any selected color | `filament_color` (comma-sep hex) |
| **Printer** | `input_select` | `All`, + dynamic from fetched data (printer_id → name) | `printer_id` |
| **Date Range** | `input_select` | `All Time`, `Today`, `This Week`, `This Month`, `Last 30 Days`, `Last 90 Days` | `started_at` |
| **Favorites** | `input_boolean` | `off` = all archives, `on` = favorites only | `is_favorite` |
| **Designer** | `input_select` | `All`, + dynamic unique designers | `designer` |
| **Project** | `input_select` | `All`, `None`, + dynamic unique project names; `None` matches prints without a project assignment | `project_name` / `project_id` |
| **Layer Height** | `input_select` | `All`, + dynamic (e.g., 0.04, 0.08, 0.12, 0.16, 0.20) | `layer_height` |
| **Tag** | `custom multi-select picker` | Planned issue `#784` direction: compact pill opens typeahead multi-select for user tags, with `Any`/`All`; preserve `Untagged` as a special path and keep `All` including tagged and untagged prints when inactive | `tags` |
| **Search** | `input_text` | Free text on `print_name`, `designer`, `tags` | Multiple fields |

> **Color filter note**: The `filament_color` field is a comma-separated hex string (e.g., `#000000,#FFFFFF,#C12E1F`). The live UI exposes these values as clickable color swatches instead of a single dropdown. Multiple swatches can be active at once, and the filter matches any archive that used at least one selected color.

### Sort Options

The Bambuddy API has **no `sort` or `order` query params** (confirmed via OpenAPI spec). All sorting is client-side in the template sensor.

| Sort | Helper Value | Sort Key | Default? |
|------|-------------|----------|----------|
| Date (Newest) | `Date (Newest)` | `started_at` descending | ✅ Yes |
| Date (Oldest) | `Date (Oldest)` | `started_at` ascending | |
| Duration (Longest) | `Duration (Longest)` | `actual_time_seconds` descending | |
| Duration (Shortest) | `Duration (Shortest)` | `actual_time_seconds` ascending | |
| Cost (Highest) | `Cost (Highest)` | `cost` descending | |
| Cost (Lowest) | `Cost (Lowest)` | `cost` ascending | |
| Filament Used (Most) | `Filament (Most)` | `filament_used_grams` descending | |
| Filament Used (Least) | `Filament (Least)` | `filament_used_grams` ascending | |
| Name (A-Z) | `Name (A-Z)` | `print_name` ascending | |
| Name (Z-A) | `Name (Z-A)` | `print_name` ascending reversed | |

### Pagination

| Helper | Type | Purpose | Default |
|--------|------|---------|---------|
| `input_number.print_history_page_size` | input_number | Items per page | 15 (min 5, max 50) |
| `input_number.print_history_current_page` | input_number | Current page (1-indexed) | 1 |

Pagination is computed in the template sensor: the full filtered+sorted list is sliced by `[(page-1)*size : page*size]`.

**Page reset behavior**: When any filter or sort helper changes, an automation resets `print_history_current_page` to 1. This prevents showing an empty page when filters reduce the result set.

### Implemented Color Chip Row

The final working color filter uses a deliberately minimal generated-card structure:

- `custom:auto-entities` generates one built-in `button` card per unique hex color
- the chip action uses `perform-action` to call `script.toggle_print_history_color_filter`
- the active state is rendered with an accent ring in `card_mod`
- the visible chip color is applied through `ha-state-icon { color: <hex> !important; }`
- invalid non-hex values are ignored so placeholder values like `none` do not render as broken cards

This ended up being more reliable than earlier generated `custom:button-card` variants and is now the documented baseline.

### Input Helpers (New)

```yaml
# helpers/input_select/
input_select_print_history_filter_status:
  name: Print History Filter - Status
  options: ["All", "Completed", "Failed", "Cancelled", "Printing"]
  initial: "All"
  icon: mdi:list-status

input_select_print_history_filter_material:
  name: Print History Filter - Material
  options: ["All"]  # Populated dynamically
  initial: "All"
  icon: mdi:flask-outline

input_select_print_history_filter_color:
  name: Print History Filter - Color
  options: ["All"]  # Populated dynamically from filament_color hex values
  initial: "All"
  icon: mdi:palette-outline

input_select_print_history_filter_printer:
  name: Print History Filter - Printer
  options: ["All"]  # Populated dynamically
  initial: "All"
  icon: mdi:printer-3d

input_select_print_history_filter_date_range:
  name: Print History Filter - Date Range
  options:
    - "All Time"
    - "Today"
    - "This Week"
    - "This Month"
    - "Last 30 Days"
    - "Last 90 Days"
  initial: "All Time"
  icon: mdi:calendar-range

input_boolean_print_history_filter_favorites_only:
  name: Print History Filter - Favorites Only
  icon: mdi:star

input_select_print_history_filter_designer:
  name: Print History Filter - Designer
  options: ["All"]  # Populated dynamically
  initial: "All"
  icon: mdi:account-outline

input_select_print_history_filter_project:
  name: Print History Filter - Project
  options: ["All", "None"]  # Project names populated dynamically; None stays available for unassigned prints
  initial: "All"
  icon: mdi:folder-outline

input_select_print_history_filter_layer_height:
  name: Print History Filter - Layer Height
  options: ["All"]  # Populated dynamically (e.g., 0.04, 0.08, 0.12, 0.16, 0.20)
  initial: "All"
  icon: mdi:layers-outline

input_select_print_history_filter_tag:
  name: Print History Filter - Tag
  options: ["All"]  # Populated dynamically from archive tags
  initial: "All"
  icon: mdi:tag-outline

input_select_print_history_sort:
  name: Print History Sort
  options:
    - "Date (Newest)"
    - "Date (Oldest)"
    - "Duration (Longest)"
    - "Duration (Shortest)"
    - "Cost (Highest)"
    - "Cost (Lowest)"
    - "Filament (Most)"
    - "Filament (Least)"
    - "Name (A-Z)"
    - "Name (Z-A)"
  initial: "Date (Newest)"
  icon: mdi:sort

# helpers/input_text/
input_text_print_history_search:
  name: Print History Search
  initial: ""
  max: 100
  icon: mdi:magnify

input_text_print_history_filter_colors:
  name: Print History Filter Colors
  initial: ""
  max: 255
  icon: mdi:palette

# helpers/input_number/
input_number_print_history_page_size:
  name: Print History Page Size
  min: 5
  max: 50
  step: 5
  initial: 10
  mode: slider
  icon: mdi:table-large

input_number_print_history_max_archives:
  name: Print History Max Archives
  min: 50
  max: 2000
  step: 50
  initial: 500
  mode: slider
  icon: mdi:database-cog
```

### Template Sensor: `sensor.print_history_filtered`

Jinja2 template that mirrors the Filament Catalog's `sensor.filament_catalog_filtered_spools` pattern:

```yaml
# template_sensors/print_history_filtered.yaml
- sensor:
    - name: "Print History Filtered"
      unique_id: print_history_filtered
      icon: mdi:filter-variant
      state: >-
        {% set fj = state_attr('sensor.print_history_filtered', 'filtered_count') | default(0) %}
        {{ fj }}
      attributes:
        filtered_count: >-
          {# Computed below — this is the total matching count before paging #}
          {% set raw = state_attr('sensor.print_history_archives', 'archives_json') | default('[]', true) %}
          {% if raw is string %}{% set archives = raw | from_json %}{% else %}{% set archives = raw | default([]) %}{% endif %}
          {%- set filter_status = states('input_select.print_history_filter_status') -%}
          {%- set filter_material = states('input_select.print_history_filter_material') -%}
          {%- set filter_color = states('input_select.print_history_filter_color') -%}
          {%- set filter_printer = states('input_select.print_history_filter_printer') -%}
          {%- set filter_date = states('input_select.print_history_filter_date_range') -%}
          {%- set filter_favorites = states('input_select.print_history_filter_favorites') -%}
          {%- set filter_designer = states('input_select.print_history_filter_designer') -%}
          {%- set filter_layer_height = states('input_select.print_history_filter_layer_height') -%}
          {%- set search_text = states('input_text.print_history_search') | lower | trim -%}
          {%- set now_ts = as_timestamp(now()) | float(0) -%}
          {%- set ns = namespace(matches=[]) -%}
          {%- for a in archives -%}
            {%- set status = a.get('status', '') | lower -%}
            {%- set material = a.get('filament_type', '') -%}
            {%- set colors = a.get('filament_color', '') -%}
            {%- set printer = a.get('printer_id', '') | string -%}
            {%- set name = a.get('print_name', '') | lower -%}
            {%- set designer = a.get('designer', '') -%}
            {%- set lh = a.get('layer_height') -%}
            {%- set is_fav = a.get('is_favorite', false) -%}
            {%- set tags = a.get('tags', '') | lower -%}
            {%- set started_raw = a.get('started_at', '') -%}
            {%- set started_ts = as_timestamp(started_raw, 0) | float(0) if started_raw else 0 -%}
            {%- set days_ago = ((now_ts - started_ts) / 86400) | float(0) if started_ts > 0 else 99999 -%}
            {%- set m_status = filter_status == 'All' or status == filter_status | lower -%}
            {%- set m_material = filter_material == 'All' or material | lower == filter_material | lower -%}
            {%- set m_color = filter_color == 'All' or filter_color in colors -%}
            {%- set m_printer = filter_printer == 'All' or printer == filter_printer -%}
            {%- set m_favorites = filter_favorites == 'All' or (filter_favorites == 'Favorites Only' and is_fav) -%}
            {%- set m_designer = filter_designer == 'All' or designer | lower == filter_designer | lower -%}
            {%- set m_layer_height = filter_layer_height == 'All' or (lh | string == filter_layer_height) -%}
            {%- set search_blob = (name ~ ' ' ~ designer ~ ' ' ~ tags) | lower -%}
            {%- set m_search = search_text == '' or search_text in search_blob -%}
            {%- if filter_date == 'Today' -%}
              {%- set m_date = days_ago < 1 -%}
            {%- elif filter_date == 'This Week' -%}
              {%- set m_date = days_ago < 7 -%}
            {%- elif filter_date == 'This Month' -%}
              {%- set m_date = days_ago < 30 -%}
            {%- elif filter_date == 'Last 30 Days' -%}
              {%- set m_date = days_ago < 30 -%}
            {%- elif filter_date == 'Last 90 Days' -%}
              {%- set m_date = days_ago < 90 -%}
            {%- else -%}
              {%- set m_date = true -%}
            {%- endif -%}
            {%- if m_status and m_material and m_color and m_printer and m_search and m_date and m_favorites and m_designer and m_layer_height -%}
              {%- set ns.matches = ns.matches + [a] -%}
            {%- endif -%}
          {%- endfor -%}
          {{ ns.matches | length }}
        # ... (full sort + page logic shown in detailed template below)
        page_json: >-
          {# Full implementation in the detailed section below #}
          ...
        total_pages: >-
          ...
        page_info: >-
          ...
        active_filters: >-
          ...
```

> The full Jinja2 template is lengthy. See [Detailed Template Sensor Logic](#detailed-template-sensor-logic) below for the complete implementation.

### Dynamic Filter Option Sync

Like the Filament Catalog, filter dropdown options should be dynamically populated from the actual data.

**Automation: `print_history_sync_filter_options`**

Triggers:
1. `sensor.print_history_archives` state change — fires when new data is fetched
2. `homeassistant.start` — with 3-minute delay (after trigger-based sensor has fetched)

Behavior:
- Reads `archives_json` attribute from `sensor.print_history_archives`
- Collects unique `filament_type` values → updates `input_select.print_history_filter_material`
- Collects unique hex colors from `filament_color` (splits comma-separated strings) → exposes them as the always-visible multi-select color-chip row
- Collects unique `printer_id` values (mapped to names if available) → updates `input_select.print_history_filter_printer`
- Collects unique `designer` values (non-empty) → updates `input_select.print_history_filter_designer`
- Collects unique `project_name` values (non-empty) → updates `input_select.print_history_filter_project`
- Collects unique `layer_height` values (formatted as strings) → updates `input_select.print_history_filter_layer_height`
- Collects unique comma-separated archive `tags` values, excluding system-managed enrichment tags such as `s:*` and `f:*` → updates `input_select.print_history_filter_tag`
- Prepends `All` to each list, and keeps `None` permanently available for the project filter so unassigned prints remain selectable
- If current selection not in new list → HA resets the relevant helper to its default value

This mirrors the Filament Catalog's `sync_filter_options.yaml` pattern exactly.

### Page Reset Automation

**Automation: `print_history_reset_page_on_filter_change`**

Triggers:
- State change on any browser filter helper, search text, selected colors, selected activity day, page size, or layout mode

Action:
- Set `input_number.print_history_current_page` to 1

---

## Layer 3: Dashboard UI

### Browser Header

The Print History view now uses an always-visible header modeled after the Filament Catalog control pattern.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [ Search Prints........................ ] [Matches] [Open Bambuddy] [⚙]     │
│ [Status] [Archive Issue] [Material] [Printer] [Date]                       │
│ [Designer] [Project] [Layer Height] [Tag] [Favorites Only] [Sort]          │
│ [Items Per Page Slider] [Compact] [Media] [List] [Refresh]                 │
│ [Clear Active Filter Chips] [Clear Filters] [Refresh]                      │
│ Color Filters: All Colors or #FFFFFF • #000000                             │
│ [●] [●] [●] [●] [●] ... multi-select color chips                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### Header Responsibilities

| Control | Purpose | Notes |
|---------|---------|-------|
| `Search Prints` | Free-text search over name, designer, tags | Styled the same way as the catalog search field |
| `Matches` | Show the current filtered result count | Always visible near the search box |
| `Open Bambuddy` | Jump directly to Bambuddy's archive UI | Replaces the old large `Recent Prints` header card |
| `Settings` | Open only capture/history settings | Kept top-right; browsing controls stay on-page |
| Filter pills | Status/archive-issue/material/printer/date/designer/project/layer-height/tag | Rounded cards with current value and active-state indicator |
| `Archive Issue` | Scope the browser to archive health states that need correction | Current options: `Any Error`, `Missing Core 3MF`, `Source 3MF Only`, `Missing Thumbnail` |
| Tag filter | Planned compact multi-select tag picker | Tags should not use a persistent always-visible choice row like color; the active recommendation is a typeahead picker with `Any`/`All` tag logic |
| `Favorites Only` | Toggle favorites-only filtering | Boolean button rather than a dropdown |
| Layout toggles | Switch between `Compact`, `Media`, and `List` | Only one is active at a time |
| Items-per-page slider | Adjust page density without opening a popup | Mirrors the Filament Catalog threshold-slider pattern |
| `Clear` / `Refresh` | Reset active filters or refresh the cache | `Clear` is visually accented whenever any filter is active |
| Tag clear chip | Reset only the selected tag filter | Appears beside the other clear-action chips when a tag is active |
| Color chips | Multi-select filament-color filter | Clicking a swatch toggles it in the active filter set |

#### Settings Popup Scope

Only the capture/history settings remain in a popup:

1. Capture-stage toggles
2. Mid-print capture percentage
3. Capture camera list plus camera-selector action
4. History fetch enablement / cache size
5. Photo review timeout

### Archive Record Card Variants

The same filtered dataset is renderable in three presentation modes, but all three now share the same responsive full-width card grid.

| Variant | Best Use | Visual Characteristics |
|---------|----------|------------------------|
| `Compact` | Fast scanning, desktop/mobile browsing | Smaller hero image with compact KPI blocks and chips |
| `Media` | Visual browsing, choosing best print/photo | Large photo-first card with emphasis on image and result |
| `List` | Desktop inspection, troubleshooting, comparing runs | Richer metadata, tags, and failure details surfaced inline |

#### Variant Field Inventory

##### Compact Card

Current Home Assistant display:

- Thumbnail image
- `3D Viewer` icon button
- Favorite icon button
- Print title
- Date/time
- Status chip with color
- Archive ID chip
- Printer chip
- Enrichment status chip with color
- Duration KPI
- Filament weight KPI
- Cost KPI
- Filament color dots with hover state
- Tag chips with color
- Project chip with project color
- Photo-count action that opens directly into the fullscreen photo view
- Notes icon with hover text when notes exist

Possible future consideration fields from Bambuddy parity or adjacent UX ideas:

- File stored/source indicator such as `G-code` vs `3MF source`
- Actual-vs-estimated duration delta or percentage
- File size
- Additional quick actions such as `Print`, `Schedule`, `Open Slicer`, `Open MakerWorld`, `Download`, and `Delete`
- Explicit add/remove favorite affordance parity with Bambuddy action menus
- Overflow action menu for secondary archive operations

Implementation guidance:

- Keep compact focused on fast scan value. Any future additions should preserve the current density target and avoid pushing view-specific labels or tooltip wording down into Layer 1.
- Prefer adding new display-only metadata through Layer 2 enrichment/projection and final wording through Layer 3 card rendering.

##### Media Card

Current Home Assistant display:

- Larger thumbnail/cover image
- `3D Viewer` icon button
- Favorite icon button
- Status chip with color
- Print title
- Date/time
- Archive ID chip
- Printer chip
- Enrichment status chip with color
- Duration KPI
- Filament KPI
- Cost KPI
- Filament color dots with hover state
- Tag chips with color

Possible future consideration fields:

- Project chip when we want media view to carry more organizational context without sacrificing the photo-first layout
- Photo-count affordance when multi-image browsing needs to be more explicit from the card surface
- File stored/source indicator
- Actual-vs-estimated duration delta or percentage
- File size
- Secondary action row or overflow menu for `Print`, `Schedule`, `Open Slicer`, `Open MakerWorld`, `Download`, and `Delete`

Implementation guidance:

- Media should remain the most visually biased variant. Extra metadata should only be added if it does not materially compete with the larger image region.

##### List Card

Current Home Assistant display:

- Thumbnail image
- `3D Viewer` icon button
- Favorite icon button
- Print title
- Status chip with color
- Date/time
- Archive ID chip
- Printer chip
- Enrichment status chip with color
- Combined material/layer-height/designer summary chip using dot separators
- Printer chip with label and name
- Material chip
- Layer-height chip
- Nozzle-size chip
- Object-count chip
- Designer chip with label
- Duration KPI block
- Filament KPI block
- Cost KPI block
- Object-count KPI block
- Filament color circles with hover state
- Tag chips with color

Possible future consideration fields from Bambuddy list-view parity:

- Printer type such as `P1S`
- File size
- Additional action set such as `Print`, `Open Slicer`, `Download`, `Edit`, `Delete`, plus an overflow action menu

Implementation guidance:

- This is the best candidate for higher-density archive metadata because users choose it for inspection rather than rapid scan.
- If future list-card fields require new joins or display labels, keep the underlying archive projection lean and do the UX shaping in Layer 2 or Layer 3.

#### Variant Rules

- Prefer archive cover photo when available; fall back to the Bambuddy thumbnail endpoint.
- Keep action affordances consistent across variants so changing layout does not change behavior.
- The `Media` card should be allowed to use a noticeably larger image region than the compact row.
- Every variant should render inside the same two-column desktop grid and collapse to one column on narrow/mobile screens.
- Cards should use the full page width of a `panel: true` Lovelace view rather than a constrained section column.
- When `has_archive_error` is true, add a compact issue chip plus a severity-colored left rail so archive-health problems remain obvious even in dense browsing modes.
- Future parity work should favor cross-variant concepts first, such as file-source indicators, file size, duration delta, and action-menu patterns, before introducing one-off variant-only metadata.

### Archive Detail Popup

Archive cards now open a live archive-detail popup. The popup should continue to include:

1. Header with print name, result badge, date, printer, favorite state, and archive-issue chip when present
2. Operator-facing archive issue summary block for missing core 3MF / source-only / missing thumbnail cases
3. Timeline, filament/cost breakdown, and enrichment state
4. Editable `print_name`, `tags`, `notes`, `status`, and `failure_reason`
5. Manual `Re-Enrich`, favorite toggle, save, and close actions
2. Large cover image / thumbnail with quick links back to Bambuddy
	1. Ability to switch to view other images stored on the print archive
	2. Ability to view multiple images at once / expanded view
3. Print stats: planned vs actual duration, grams used, cost, quantity, layer height, nozzle size
4. Filament breakdown with color swatches and per-color usage when available
5. Designer / MakerWorld metadata and tags
6. Failure reason or stop context when the archive did not complete successfully
7. Future actions area for compare, favorite toggle, reprint, and archive diagnostics

### History Table Card

The live `print_history.yaml` renderer reads from `sensor.bambuddy_print_history_browser_page_archives` and renders responsive archive cards rather than a single-column table. The integration page entity provides the already-filtered, already-sorted current slice, so the frontend only handles layout.

### Pagination Controls

```
┌──────────────────────────────────────────────────────────────────┐
│ [⏮] [◀] [Page 1 of 5] [▶] [⏭]                                   │
└──────────────────────────────────────────────────────────────────┘
```

| Control | Implementation |
|---------|----------------|
| First / Prev / Next / Last | `script.navigate_history` with `direction=first|prev|next|last` |
| Page info | `sensor.print_history_page_info` |
| Page size slider | Lives in the browser header, always visible |
| Refresh | `script.refresh_print_history_archives` |

**Pagination is instant** — changing the page helper triggers the template sensor to re-evaluate, slicing a different window of the already-filtered+sorted data. No API call needed. The pager appears both above and below the archive grid.

---

## Performance Analysis

### The "Pull All Data" Question

> *"Does this only work if we somehow pull ALL data (not paged)? Is that a concern?"*

**Short answer**: You don't need ALL data. A reasonable cap (default 500) works well. The projection step makes the full endpoint viable.

### Data Size Estimates (After Projection)

| Archive Count | API Response | Projected JSON | Template Eval (L1) | Template Eval (L2) | Practical? |
|---------------|-------------|---------------|---------------------|---------------------|------------|
| 50 | ~500 KB | ~22 KB | ~0.2s | <0.1s | ✅ Trivial |
| 200 | ~2 MB | ~90 KB | ~0.5s | ~0.2s | ✅ Comfortable |
| 500 | ~5 MB | ~225 KB | ~1s | ~0.5s | ✅ Good default |
| 1,000 | ~10 MB | ~450 KB | ~2-3s | ~1s | ⚠️ Noticeable on fetch |
| 2,000 | ~20 MB | ~900 KB | ~5-8s | ~2-3s | ⚠️ Sluggish |

*L1 = projection loop (runs on fetch events, ~every 5 min). L2 = filter/sort/page (runs on every helper change, but operates on already-projected data).*

**Key insight**: L1 projection is the heavier step but runs infrequently (fetch events). L2 filtering operates on the trimmed data and is fast even at 500 items. Filter/sort/page changes feel instant because they don't re-fetch.

### Why 500 Is the Right Default

- **2 prints/day × 250 days = 500** — covers ~8 months for active users
- **API response at 500**: ~5 MB (full JSON with `extra_data`). Fetched once, projected to ~225 KB, and stored. The 5 MB is transient (in Jinja2 variable during render), not persisted.
- **Projected data size**: ~225 KB is well within HA's state machine capacity
- **L2 template speed**: Iterating 500 flat dicts with ~5 filter checks each ≈ Filament Catalog's 165 entities with ~15 attribute lookups
- **Recorder optimization**: Exclude `archives_json` attribute from the recorder:
  ```yaml
  recorder:
    exclude:
      entity_globs:
        - sensor.print_history_archives
  ```

### How the Architecture Mitigates Scale

| Concern | Mitigation |
|---------|------------|
| **Large API response** | Transient — held in Jinja2 variable during projection, then discarded. Only the trimmed ~225 KB is stored as an attribute. |
| **Too much API data** | `input_number.print_history_max_archives` caps the `?limit=` param (default 500, max 2000) |
| **Slow L1 projection** | Runs only on trigger events (~5-min interval + webhooks), NOT on filter changes |
| **Slow L2 filtering** | Operates on projected data (~450 bytes/item). Date Range filter applied early to reduce working set. |
| **Large attribute in recorder** | Exclude `sensor.print_history_archives` from recorder |
| **5-minute polling for stale data** | Webhook triggers (`print_complete`, `print_failed`) refresh immediately on events that matter |
| **Very large histories** | Users with 2000+ archives should use date range filters or the Bambuddy web UI for deep history |

### Alternative: API-Side Pre-Filtering (Considered & Deferred)

The Bambuddy API supports `?status=X&printer_id=Y&search=Q` server-side. We COULD push filters to the API level:

```
GET /archives/?limit=500&status=completed&printer_id=1&search=benchy
```

**Pros**: Much smaller response, faster template evaluation.
**Cons**:
- Every filter change requires a new API call (latency + rate limits)
- Can't do instant client-side sort or page navigation
- Filter UX feels sluggish (API round-trip on each dropdown change)
- More complex implementation (REST command params change dynamically)

**Verdict**: Start with the client-side approach (pull 500, project, filter in template). If users report scale issues at 1000+ archives, add an optional "server-side mode" that pushes status + date range filters to the API as query params. This is an optimization, not a requirement.

### Alternative: Hybrid API Pre-Filter + Client Sort (Future Optimization)

If scale becomes an issue, the architecture supports a middle ground:

1. API pre-filters by **date range** (reduces dataset the most, e.g., "Last 30 Days" → ~60 archives)
2. Client-side handles **status**, **material**, **color**, **search**, **sort**, **page**

This would require switching from trigger-based template to a script + REST command flow where filter changes trigger an API re-fetch. The downside is that filter changes are no longer instant. This can be added later without changing the dashboard or filter helpers — only the data fetch layer changes.

### Activity Heatmap Metric Semantics

The shipped activity heatmap uses these metric definitions:

- **Print Count**: one per archive row after filters are applied
- **Number of Printed Objects**: sum of projected `object_count` values from the Bambuddy archive payload
- **Filaments Used**: sum of distinct populated `filament_slots` per archive, intended as a usage/activity signal rather than a unique-filament-in-history count

This keeps the browser and heatmap aligned on the same projected Layer 1 data contract and avoids deriving object totals from fallback printable-object blobs.

### Total Time Printing Normalization

Issue #1156 raised a correctness problem in the `Total Time Printing` heatmap mode: when the card buckets duration entirely by `started_at` day, a single long print or several same-day starts can push one calendar cell above 24 hours and distort the whole color scale.

The current implementation keeps the existing start-date bucketing but normalizes the visual metric in the card layer:

- The heatmap still aggregates raw archive duration onto the archive start day.
- The cell intensity value for `Total Time Printing` is capped at 24 hours per day.
- Tooltips retain the raw started-on-that-day total so the cap is explicit instead of silently hiding duration.
- This normalization stays in the browser/card aggregation path, not Layer 1 projection, because it is a heatmap-display rule rather than a shared archive-data contract.

This is an intentional approximation, not a true occupancy calculation. A capped 24-hour cell means the started-print total for that date met or exceeded the daily display limit; it does not prove the printer was actually busy for all 24 wall-clock hours of that calendar day.

### Deferred: Cross-Day Duration Allocation

A more accurate model would split each archive's duration across every calendar day it overlaps, using `started_at` plus the best available effective duration to allocate hours per day before rendering the heatmap.

That approach is feasible, but it is deferred for now:

- It adds more per-archive date math to the hottest client-side aggregation path.
- It needs careful fallback rules for incomplete timestamps and duration fields.
- The immediate user problem is scale distortion, which the 24-hour cap solves with negligible performance cost.
- If deeper duration analytics are added to the print statistics surface, that view is a better place to introduce true cross-midnight allocation as a first-class metric instead of quietly changing the browser heatmap semantics.

### Deferred: Backend-Only Heatmap Filtering / Single Source of Truth

The idea of moving all heatmap filtering out of the browser card and into Layer 2 was analyzed and intentionally deferred.

**Why it was deferred:**

- The activity heatmap currently consumes the full projected archive cache from `sensor.print_history_archives`
- The existing Layer 2 payload is page-oriented and optimized for the archive browser, not full-scope activity aggregation
- Reusing the paged Layer 2 payload for the heatmap would either truncate activity totals or force Layer 2 to mix two different concerns into one payload

**Future-safe direction:**

- Keep the current browser-first heatmap implementation for now
- If a stricter backend single source of truth is needed later, add a dedicated full-scope activity payload such as `activity_scope_json` or `activity_days_json`
- Have the heatmap read that dedicated activity payload instead of reconstructing its own filtered working set from page-oriented data

That future refactor is an architectural cleanup and consistency improvement, not a correctness blocker for the current implementation.

---

## Updated Package Structure

New and modified files (additions to existing `print_history/` package):

```
homeassistant/packages/3d_printing/print_history/
├── rest_commands/
│   ├── (existing files...)
│   └── bambuddy_fetch_archives.yaml             # NEW — GET /archives for bulk fetch
├── template_sensors/
│   ├── (existing files...)
│   ├── print_history_archives.yaml               # NEW — trigger-based, fetch + project + store
│   └── print_history_filtered.yaml               # NEW — filter/sort/page sensor
├── helpers/
│   ├── input_select/
│   │   ├── (existing files...)
│   │   ├── input_select_print_history_filter_status.yaml        # NEW
│   │   ├── input_select_print_history_filter_material.yaml      # NEW
│   │   ├── input_select_print_history_filter_printer.yaml       # NEW
│   │   ├── input_select_print_history_filter_date_range.yaml    # NEW
│   │   ├── input_select_print_history_filter_designer.yaml      # NEW
│   │   ├── input_select_print_history_filter_project.yaml       # NEW
│   │   ├── input_select_print_history_filter_layer_height.yaml  # NEW
│   │   ├── input_select_print_history_filter_tag.yaml           # NEW
│   │   ├── input_select_print_history_sort.yaml                 # NEW
│   │   └── input_select_print_history_card_variant.yaml         # NEW
│   ├── input_boolean/
│   │   ├── (existing files...)
│   │   └── input_boolean_print_history_filter_favorites_only.yaml # NEW
│   ├── input_text/
│   │   ├── (existing files...)
│   │   ├── input_text_print_history_filter_colors.yaml          # NEW
│   │   └── input_text_print_history_search.yaml                 # NEW
│   └── input_number/
│       ├── (existing files...)
│       ├── input_number_print_history_page_size.yaml            # NEW
│       └── input_number_print_history_max_archives.yaml         # NEW
├── automations/
│   ├── (existing files...)
│   ├── print_history_sync_filter_options.yaml    # NEW — dynamic dropdown population
│   └── print_history_reset_page_on_filter.yaml   # NEW — reset to page 1 on filter change
├── scripts/
│   ├── (existing files...)
│   ├── print_history_clear_filters.yaml          # NEW — reset all filters to defaults
│   └── toggle_print_history_color_filter.yaml    # NEW — add/remove selected color chips
├── dashboard_cards/
│   ├── (existing files...)
│   ├── print_history_browser.yaml                # NEW — always-visible browser header
│   ├── print_history_pagination.yaml             # NEW — reusable top/bottom pager
│   └── print_history_archive_records.yaml        # NEW — variant-aware archive record renderer
└── dashboard_views/
  └── view_print_history.yaml                   # MODIFIED — switch to panel layout with top/bottom pagers
```

### Loader Updates

The existing `print_history_loader.yaml` already uses `!include_dir_merge_list` and `!include_dir_merge_named` for all domains. New files in existing directories are **auto-discovered** — no loader changes needed.

---

## Entity Reference (New Entities)

### Template Sensors

| Entity | Type | State | Key Attributes |
|--------|------|-------|----------------|
| `sensor.print_history_archives` | trigger template | Archive count (e.g., "487") | `archives_json` (full JSON array), `last_fetch` (ISO timestamp) |
| `sensor.print_history_filtered` | template | Filtered count (e.g., "47") | `page_json` (current page array), `total_pages`, `page_info`, `active_filters` |

### Helpers

| Entity | Type | Default |
|--------|------|---------|
| `input_select.print_history_filter_status` | input_select | `All` |
| `input_select.print_history_filter_material` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_printer` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_date_range` | input_select | `All Time` |
| `input_select.print_history_filter_designer` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_project` | input_select | `All` |
| `input_select.print_history_filter_layer_height` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_tag` | input_select | `All` (dynamic) |
| `input_select.print_history_sort` | input_select | `Date (Newest)` |
| `input_select.print_history_card_variant` | input_select | `Media` |
| `input_boolean.print_history_filter_favorites_only` | input_boolean | `off` |
| `input_text.print_history_search` | input_text | `""` |
| `input_text.print_history_filter_colors` | input_text | `""` |
| `input_number.print_history_page_size` | input_number | 15 |
| `input_number.print_history_max_archives` | input_number | 500 |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `print_history_sync_filter_options` | `sensor.print_history_archives` state change | Populate material + printer dropdown options from data |
| `print_history_reset_page_on_filter` | Any filter/sort/search helper state change | Set `print_history_current_page` → 1 |

### Scripts

| Script | Purpose |
|--------|---------|
| `script.print_history_clear_filters` | Reset all filter/sort/search helpers to defaults |

---

## Existing Entity Changes

### Potentially Removable (Post-Migration)

| Entity | Current Purpose | Replaced By |
|--------|----------------|-------------|
| `input_number.bambuddy_history_limit` | Historical REST sensor `?limit=` param (retired) | `input_number.print_history_max_archives` |
| `sensor.bambuddy_print_history_browser_page_archives` | Current visible page slice | Dashboard card entity |
| `script.load_history_page` | REST command pagination | Template sensor paging (no script needed) |
| `script.navigate_history` | Prev/next REST calls | Direct `input_number.set_value` on page helper |
| `sensor.print_history_page_info` | Page display string | `sensor.print_history_filtered` attr `page_info` |

These can be removed in a cleanup phase after the new filter system is validated.

### Kept As-Is

| Entity | Reason |
|--------|--------|
| `sensor.bambuddy_print_history` (REST, retired) | Formerly powered `sensor.bambuddy_last_print_*` quick-glance sensors |
| All `sensor.bambuddy_last_print_*` | Used by automations and other dashboard tiles |
| All photo capture / enrichment entities | Independent subsystems, unaffected |

---

## Detailed Template Sensor Logic

### `sensor.print_history_filtered` — Full Jinja2

The template sensor logic follows the same pattern as `sensor.filament_catalog_filtered_spools`:

1. Read raw data from Layer 1 sensor attribute
2. Read all filter helper states
3. Iterate archives, apply filters
4. Sort matching archives
5. Slice to current page
6. Output as JSON attributes

```jinja2
{# ── Read raw data ──────────────────────────────────────────── #}
{% set raw = state_attr('sensor.print_history_archives', 'archives_json')
     | default('[]', true) %}
{% if raw is string %}
  {% set archives = raw | from_json %}
{% elif raw is iterable %}
  {% set archives = raw | list %}
{% else %}
  {% set archives = [] %}
{% endif %}

{# ── Read filter helpers ────────────────────────────────────── #}
{% set filter_status = states('input_select.print_history_filter_status') %}
{% set filter_material = states('input_select.print_history_filter_material') %}
{% set filter_color = states('input_select.print_history_filter_color') %}
{% set filter_printer = states('input_select.print_history_filter_printer') %}
{% set filter_date = states('input_select.print_history_filter_date_range') %}
{% set filter_favorites = states('input_select.print_history_filter_favorites') %}
{% set filter_designer = states('input_select.print_history_filter_designer') %}
{% set filter_layer_height = states('input_select.print_history_filter_layer_height') %}
{% set search_text = states('input_text.print_history_search') | lower | trim %}
{% set sort_option = states('input_select.print_history_sort')
     | default('Date (Newest)', true) %}
{% set page_size = states('input_number.print_history_page_size') | int(15) %}
{% set current_page = states('input_number.print_history_current_page') | int(1) %}
{% set now_ts = as_timestamp(now()) | float(0) %}

{# ── Date range thresholds ──────────────────────────────────── #}
{% if filter_date == 'Today' %}
  {% set max_days = 1 %}
{% elif filter_date in ['This Week'] %}
  {% set max_days = 7 %}
{% elif filter_date in ['This Month', 'Last 30 Days'] %}
  {% set max_days = 30 %}
{% elif filter_date == 'Last 90 Days' %}
  {% set max_days = 90 %}
{% else %}
  {% set max_days = 999999 %}
{% endif %}

{# ── Filter pass ────────────────────────────────────────────── #}
{% set ns = namespace(matches=[]) %}
{% for a in archives %}
  {% set a_status = a.get('status', '') | lower %}
  {% set a_material = a.get('filament_type', '') %}
  {% set a_printer = a.get('printer_id', '') | string %}
  {% set a_name = a.get('print_name', '') | lower %}
  {% set a_started = a.get('started_at', '') %}
  {% set a_ts = as_timestamp(a_started, 0) | float(0) if a_started else 0 %}
  {% set a_days = ((now_ts - a_ts) / 86400) | float(0) if a_ts > 0 else 999999 %}

  {% set m_status = filter_status == 'All' or a_status == filter_status | lower %}
  {% set m_material = filter_material == 'All' or a_material | lower == filter_material | lower %}
  {% set m_printer = filter_printer == 'All' or a_printer == filter_printer %}
  {% set m_search = search_text == '' or search_text in a_name %}
  {% set m_date = a_days <= max_days %}

  {% if m_status and m_material and m_printer and m_search and m_date %}
    {# Build sort key based on sort_option #}
    {% if sort_option in ['Date (Newest)', 'Date (Oldest)'] %}
      {% set sk = a_ts %}
    {% elif sort_option in ['Duration (Longest)', 'Duration (Shortest)'] %}
      {% set sk = a.get('actual_time_seconds', 0) | float(0) %}
    {% elif sort_option in ['Cost (Highest)', 'Cost (Lowest)'] %}
      {% set sk = a.get('cost', 0) | float(0) %}
    {% elif sort_option in ['Filament (Most)', 'Filament (Least)'] %}
      {% set sk = a.get('filament_used_grams', 0) | float(0) %}
    {% elif sort_option in ['Name (A-Z)', 'Name (Z-A)'] %}
      {% set sk = a_name %}
    {% else %}
      {% set sk = a_ts %}
    {% endif %}
    {% set ns.matches = ns.matches + [dict(archive=a, sk=sk)] %}
  {% endif %}
{% endfor %}

{# ── Sort pass ──────────────────────────────────────────────── #}
{% set sort_desc = sort_option in [
  'Date (Newest)', 'Duration (Longest)', 'Cost (Highest)',
  'Filament (Most)', 'Name (Z-A)'] %}
{% set sorted_items = ns.matches | sort(attribute='sk', reverse=sort_desc) %}

{# ── Pagination ─────────────────────────────────────────────── #}
{% set total = sorted_items | length %}
{% set total_pages = ((total / page_size) | round(0, 'ceil')) | int %}
{% set total_pages = [total_pages, 1] | max %}
{% set safe_page = [[current_page, 1] | max, total_pages] | min %}
{% set offset = (safe_page - 1) * page_size %}
{% set page_items = sorted_items[offset:offset + page_size] %}

{# ── Output ─────────────────────────────────────────────────── #}
{# page_json: array of archive objects for current page #}
{% set page_archives = page_items | map(attribute='archive') | list %}
{{ page_archives | tojson }}
```

This pseudocode shows the structure. Each output attribute (`page_json`, `filtered_count`, `total_pages`, `page_info`, `active_filters`) follows this logic in separate attribute templates within the sensor definition.

---

## Browser Layout Wireframe

```
┌──────────────────────────────────────────────────────────────────────┐
│ ┌──────────── Browser Header ──────────────────────────────────────┐ │
│ │ Open Bambuddy  Settings                                          │ │
│ │ Status  Material  Printer  Date                                  │ │
│ │ Designer  Project  Layer Height  Favorites  Sort                 │ │
│ │ Search  47 matches  Clear actions                                │ │
│ │ Multi-select color chips                                         │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌──────────── Top Control Strip ───────────────────────────────────┐ │
│ │ ⏮ ◀  1 of 5  Prints / Page  Compact  Media  List  🔄  ▶ ⏭       │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─────────────────────── Print History Browser ───────────────────┐ │
│ │ [Media card] Hueforge BTTF                                     │ │
│ │ [larger image / cover photo]                                   │ │
│ │ Mar 28 · est 4.3h · 0.08mm · PLA · 44.8g · ★ printing         │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ [Compact row] Darth Vader Saber P2 · PLA · 69.3g · ✅         │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ [List card] Magnetic Frame P12                                 │ │
│ │ Mar 28 · 1.8h · 0.08mm · tags · designer · failure detail      │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ ...                                                             │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─────────── Repeated Bottom Control Strip ───────────────────────┐ │
│ │ ⏮ ◀  1 of 5  Prints / Page  Compact  Media  List  🔄  ▶ ⏭       │ │
│ └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Implementation Details

The browser entry surface now uses a permanently visible browser header plus a separate reusable control strip. Search, matches, settings, filter pills, clear actions, and the multi-select color chips live in the header; page navigation, page-size, layout selection, and refresh live in `print_history_top_controls.yaml` and are rendered above and below the archive grid.

The active top-controls contract intentionally splits pagination from utility controls so mobile behavior does not depend on `bubble-card` child indices. See `top-controls-contract.md`.

```yaml
# dashboard_cards/print_history_browser.yaml
type: vertical-stack
cards:
  - Open Bambuddy + settings
  - rounded filter pills
  - search + matches + clear actions
  - multi-select color chips

# dashboard_cards/print_history_top_controls.yaml
type: custom:config-template-card
card:
  - page navigation
  - page-size slider
  - Compact / Media / List toggles
  - refresh action
```

---

## Comparison: Filament Catalog vs Print History Filter

| Aspect | Filament Catalog | Print History |
|--------|-----------------|---------------|
| **Data source** | HA entity states (`sensor.spoolman_spool_*`) | External API → projected JSON attribute |
| **Data volume** | ~165 entities (fixed) | 50–2000 archives (growing) |
| **Data fetch** | Always in HA (Spoolman integration) | Trigger-based fetch with `rest_command` action + Jinja2 field projection |
| **Filter sensor** | `sensor.filament_catalog_filtered_spools` | `sensor.print_history_filtered` |
| **Filter inputs** | 12 input_selects + 1 input_text + 4 input_booleans + 3 input_numbers | 9 input_selects + 2 input_texts + 1 input_boolean + 2 input_numbers |
| **Grouping/tabs** | Yes (By Location, By Material, etc.) | No (flat list with sort) |
| **Sort** | 9 options (name, weight, cost, hue, etc.) | 10 options (date, duration, cost, filament, name) |
| **Pagination** | No (all shown, relies on auto-entities) | Yes (page_size + current_page) |
| **Primary browser controls** | `catalog_filter_bar.yaml` | `print_history_browser.yaml` |
| **Controls style** | expanded `bubble-card` sub-buttons | always-visible rounded control header with search, pills, and color chips |
| **Dynamic options** | `sync_filter_options` automation | `print_history_sync_filter_options` automation |
| **Clear filters** | `script.filament_catalog_clear_filters` | `script.clear_print_history_filters` resets the browser filters and the heatmap day drill-in (`input_text.print_history_activity_selected_date`) |
| **Scale concern** | 165 is comfortable, >300 would need paging | 500 default cap, configurable to 2000 |

---

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | Verify `GET /archives/` response shape matches projection expectations | Ensure `extra_data.filament_slots` path is correct, and all projected fields exist | Yes — test against Bambuddy API |
| 2 | Verify trigger-based template sensor `action` + `rest_command` response handling works as designed | Core architecture dependency (HA 2024.11+ feature) | Yes — test on live HA instance |
| 3 | Determine if `GET /archives/` supports `?status=X` or `?printer_id=Y` for future API-side pre-filtering | Could enable hybrid mode at scale | No — client-side filtering works regardless |
| 4 | Recorder exclusion for `sensor.print_history_archives` | Large `archives_json` attribute shouldn't bloat the database | No — add to recorder config during implementation |
| 5 | Printer ID → name mapping | `printer_id` is an integer; need friendly name for dropdown display. May require a separate API call or helper mapping. | No — can use printer_id as display initially |
| 6 | Search: current helper vs API-side FTS | `GET /search?q=...` adds `notes`/`filename` coverage, but it is not a drop-in replacement for the browser search helper because the active local search also supports ID, printer, project, and failure lookup. | No — keep the default browser search local; only add FTS later as an explicit secondary capability |
| 7 | Decide whether archive cards stay display-only or gain a detail popup | Governs how favorites/compare/actions land without overloading the card surface | No — current browser already works without it |

---

## Implementation Phases

This feature can be added incrementally within the existing print_history package:

### Phase A: Data Layer (REST command + trigger template sensor)
- Create `bambuddy_fetch_archives` REST command
- Create `print_history_archives` trigger-based template sensor
- Verify data fetch and attribute storage
- Add recorder exclusion

### Phase B: Filter Helpers + Template Sensor
- Create all `input_select`, `input_text`, `input_number` helpers
- Create `print_history_filtered` template sensor
- Create `sync_filter_options` automation
- Create `reset_page_on_filter` automation
- Create `clear_filters` script
- Add `input_select.print_history_card_variant` for persisted layout choice

### Phase C: Dashboard Integration
- Create `print_history_browser.yaml` as the always-visible header surface
- Create `print_history_top_controls.yaml` as the reusable top/bottom control strip
- Update `view_print_history.yaml` to use a full-width panel layout with the header, control strip, archive grid, and repeated bottom controls
- Update history record rendering to read from `sensor.bambuddy_print_history_browser_page_archives` and branch by card variant
- Add the multi-select color-chip row and layout toggle controls

Status: implemented baseline. Remaining dashboard work is mostly archive-detail drilldown and visual refinements rather than core browser plumbing.

### Phase D: Cleanup
- Remove dead compatibility artifacts only after confirming no external dashboards or scripts depend on them
- Consolidate `bambuddy_history_limit` → `print_history_max_archives`
- Update README.md entity reference
