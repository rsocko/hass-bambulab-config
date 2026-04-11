# Print History External Services Design Review (2026-04)

## Scope

This review compares the current Bambuddy-backed print history implementation against the external systems referenced by these issues:

- #211 - broader comparison against 3D Print Log and similar tools
- #235 - Node-RED history automation and Postgres pipeline
- #247 - OctoPrint, OctoPi, OctoEverywhere, Obico
- #248 - OpenSpoolman
- #249 - PrintStack

It also folds in additional relevant options found during research:

- O.D.I.N.
- SpoolSync
- SimplyPrint

The goal is not just feature parity. The primary decision criteria are:

- what metadata is captured
- which system is authoritative for that metadata
- how that metadata is maintained over time
- which ideas are worth adopting into this repo
- whether any external service should become part of the architecture

## Current Baseline

The active design in this repo is not a thin archive browser. It is already a layered history system:

- Bambuddy is the archive-of-record for print archives
- the `bambuddy` custom integration projects Bambuddy archives into a local SQLite store
- the local store adds repo-owned metadata that Bambuddy does not natively model well enough for dashboard/query needs
- Home Assistant remains the orchestration and presentation layer for browsing, enrichment, popup editing, photos, and diagnostics

Today the system already captures or persists these metadata classes:

| Domain | Current Bambuddy-backed coverage |
|---|---|
| Archive identity | archive id, printer id, timestamps, filename/print name/model name, status, favorite |
| Archive payload | full JSON payload retained in local store |
| Filament usage | normalized per-archive filament rows, multi-color support, color slots, enrichment data |
| Tags and notes | normalized tags plus hidden managed enrichment payload rows |
| Photos and media | archive photos, thumbnails, local upload flow, photo counts |
| Failure metadata | status, failure reason, archive comparison/failure-analysis endpoints available upstream |
| Review workflow | local review state table |
| Repair/provenance | repair lineage table, sync metadata, payload hashes, source-updated timestamps |
| Spool linkage | current enrichment-derived spool and filament tags plus hidden note payload linkage |

That matters because several external systems only cover one slice of this stack.

## Decision Frame

The cleanest way to evaluate the alternatives is by role.

| System | Primary role | Fit as authoritative print history | Fit as spool authority | Best use in this repo |
|---|---|---|---|---|
| Bambuddy + current sidecar | archive system + HA query sidecar | Strong | Partial | Keep as primary print-history architecture |
| OpenSpoolman | spool/AMS management with light history | Partial | Strong | borrow spool-linkage ideas |
| PrintStack | manual personal log | Weak | Weak | borrow lightweight analytics ideas only |
| 3D Print Log | richer manual print/material log | Partial | Partial | borrow explicit actual-vs-estimated fields and analytics ideas |
| Node-RED + Postgres flow (#235) | event pipeline + warehouse | Partial | Weak | borrow event-capture and derived-metrics ideas |
| OctoPrint / OctoPi | printer host and plugin platform | Weak for Bambu | Weak | not recommended as core path |
| OctoEverywhere / Obico | remote access, monitoring, AI, notifications | Weak | Weak | complementary only |
| SimplyPrint | cloud fleet platform | Partial | Partial | inspiration only unless architecture is intentionally cloud-managed |
| SpoolSync | spool inventory and live weight tracking | Weak | Strong | optional complement if live spool weight becomes a top priority |
| O.D.I.N. | broad ops/farm platform | Strong on paper | Strong on paper | source of roadmap ideas, not an additive dependency |

## Service-by-Service Review

### OpenSpoolman

What it does well:

- Strong spool and AMS/tray awareness
- Good notion of active spool assignment and spool change tracking
- Useful cost derivation from spool records
- Better native spool-state posture than Bambuddy

Where it is weaker than the current Bambuddy-backed stack:

- Print history is lighter and more spool-centric than archive-centric
- Less emphasis on per-archive provenance, review state, repair lineage, popup editing, and media-first archive browsing
- Not obviously stronger for archive-side photo workflows, hidden enrichment payloads, or local query/store layering

Recommended takeaways:

- strengthen spool linkage from archive rows to spool authority
- preserve spool snapshots at print start and terminal state
- keep spool-derived cost and material metadata explicitly separated from archive-native metadata

Recommendation:

- Do not replace Bambuddy with OpenSpoolman for print history
- Consider it only if spool authority needs to move beyond the current Spoolman-enrichment pattern

### PrintStack

What it does well:

- Very approachable personal print log
- Manual per-print notes and filament entries are easy to reason about
- Good lightweight statistics and manual variance tracking

Where it is weaker than the current stack:

- LocalStorage/manual-entry architecture is not suitable as an authoritative history backend here
- No meaningful advantage for archive media, webhook/event orchestration, or spool integration depth
- Much weaker provenance and lifecycle semantics than the current Bambuddy plus local-sidecar model

Recommended takeaways:

- keep personal-analytics UX lightweight where possible
- expose simple rollups without forcing users into an enterprise-style workflow

Recommendation:

- no architecture role
- only UI and analytics inspiration

### 3D Print Log

What it does well:

- Rich manual print metadata
- Explicit actual vs estimated time and material usage
- Better first-class modeling for materials, printers, purchase details, and consumable history than many hobby tools
- Images, comments, export, and analytics are all part of the core product

Where it is stronger than the current stack:

- explicit separation of estimated and actual usage
- more deliberate material inventory/accounting fields
- better out-of-the-box analytics/reporting framing

Where the current stack is stronger:

- Bambuddy already owns actual archive creation and Bambu-native metadata capture
- current repo already has richer automation and dashboard integration with HA
- current local store has review/provenance/repair structures that 3D Print Log is not obviously better at

Recommended takeaways:

- add explicit estimated-versus-actual semantics to Layer 2 or sidecar tables
- add clearer material accounting fields rather than overloading tags/notes
- expand archive analytics with export-friendly summaries

Recommendation:

- use as a schema and analytics reference, not as a replacement platform

### Node-RED Advanced History Flow (#235)

The Node-RED flow referenced by issue #235 is more important as a design pattern than as a target platform.

What it does well:

- launches two coordinated flows at print start
- fetches the active `.3mf` file and extracts preview image, weight, and material/type metadata
- writes per-print records into Postgres and updates them on pause, resume, fail, and finish
- joins power usage and electricity-rate data to derive per-print energy cost
- stores a single operational current-power row plus historical per-print rows
- adjusts failed/canceled material and cost using progress-based estimation

Where it is stronger than the current stack:

- clearer event ledger mentality
- clearer derived-metrics mentality for energy cost
- stronger separation between event capture and dashboarding
- stronger use of print-start artifact extraction for metadata recovery when runtime data is incomplete

Where the current stack is stronger:

- Bambuddy already creates the archive of record at print start
- the repo already has archive photos, archive editing, enrichment, browser UX, and local query architecture
- Home Assistant-native implementation is easier to keep aligned with the rest of this repo than a separate Node-RED plus Postgres dependency chain

Important caveat:

- the Node-RED flow stores several values as derived estimates rather than ground truth, especially on failed/canceled prints
- that pattern is useful only if the estimate is explicitly labeled and the derivation method is preserved

Recommended additions inspired by #235:

- add an explicit print event timeline table or note-row type for `started`, `paused`, `resumed`, `failed`, `stopped`, `finished`
- capture print-start artifact metadata when available, especially preview image, slicer-estimated weight, material profile names, and file-level cost hints
- add explicit `estimated_*` vs `actual_*` fields for weight, duration, and cost
- join printer energy data into per-print summaries, but keep it in repo-owned derived fields rather than pretending Bambuddy captured it natively
- preserve derivation provenance for all progress-adjusted values

Recommendation:

- do not add Node-RED as a required dependency
- do adopt several of its capture and warehousing ideas inside the current custom integration and local store

### OctoPrint / OctoPi

What they do well:

- very mature plugin ecosystem
- strong remote control and print-host model for printers they directly drive
- broad community knowledge base

Why they are a poor fit here:

- they are not natural archive authorities for Bambu printers in this architecture
- introducing OctoPrint for Bambu history would add indirection without improving the existing Bambuddy archive source
- core value is printer hosting/control, not archive stewardship

Recommendation:

- do not introduce OctoPrint/OctoPi into the Bambuddy-backed print-history architecture

### OctoEverywhere / Obico

What they do well:

- remote access
- notifications
- AI or computer-vision-assisted monitoring
- failure detection and user-facing remote workflows

Why they are not print-history replacements:

- they are complementary overlays, not authoritative stores for archive metadata
- they add monitoring value, not a better history data model

Recommendation:

- treat as optional complements only
- do not couple the print-history data model to them

### SimplyPrint

What it does well:

- broader cloud fleet management posture
- useful dashboards and operational summaries
- some overlap with queue, printer state, and consumable management

Why it is not a natural next step here:

- cloud-first operating model does not align with the repo's current local/HA/Bambuddy-first posture
- more replacement-scale than additive-scale
- would shift authority away from current local workflows without a commensurate benefit for archive provenance

Recommendation:

- treat as product inspiration only unless the project intentionally pivots toward a hosted fleet-management architecture

### SpoolSync

What it does well:

- authoritative spool inventory posture
- live weight history
- storage location, reorder thresholds, NFC, spool holders, printer-slot association
- better real-time spool state than the current print-history stack

Where it overlaps with this repo:

- several of its advantages already map conceptually to `spoolman_sync`
- it is strongest where the repo already treats spool state as a parallel concern, not where Bambuddy is strongest

Recommendation:

- only relevant if live spool weight, NFC workflows, or reorder/inventory operations become first-class goals
- not a reason to change print-history authority

### O.D.I.N.

What it does well:

- probably the most complete integrated competitor reviewed
- archive compare, reprint, project grouping, timelapses, analytics, inventory, cost/margin views, AMS preview, and broader ops workflows
- closer to a full print-operations platform than a point tool

Why it matters:

- it validates that the repo's roadmap areas are legitimate product directions, especially compare, reprint, diagnostics, project grouping, and cost analytics

Why it is not the immediate answer:

- adopting it would mean choosing a new platform, not just borrowing a feature
- it overlaps heavily with work already underway in this repo and with Bambuddy's archive model
- it is too broad to add incrementally as a low-risk dependency

Recommendation:

- use O.D.I.N. as the clearest roadmap benchmark
- borrow feature framing, not the platform itself

## Equivalent Features: Current State vs Gaps

### Already Strong or Already Better in the Current Stack

- Bambu-native archive creation through Bambuddy
- Home Assistant-first browsing and control integration
- archive photos and popup editing
- local sidecar metadata for review, repair lineage, and query annotations
- archive enrichment from spool context
- layered architecture that keeps Layer 1 lean and defers presentation logic to Layer 2/3

### Partial Gaps Worth Closing

- explicit estimated vs actual material, time, and cost fields
- clearer event timeline/history model per print
- first-class per-print energy cost join
- stronger spool snapshot semantics at print start and print end
- richer failure taxonomy and analysis summaries
- more deliberate project/model lineage and reprint metadata

### Areas That Should Remain Out of Scope

- making OctoPrint the archive path
- introducing Node-RED as a required runtime dependency
- replacing Bambuddy with a general-purpose external history app
- moving UI wording or view-specific labels into Layer 1 just to emulate another product

## Recommended Data Model Additions

These are the most valuable additions surfaced by the comparison work.

### 1. Explicit Derived Metrics Columns

Add sidecar-owned fields or tables for:

- `estimated_weight_g`
- `actual_weight_g`
- `estimated_duration_s`
- `actual_duration_s`
- `estimated_filament_cost`
- `actual_filament_cost`
- `estimated_energy_cost`
- `actual_energy_cost`
- `derivation_method`
- `derivation_confidence`

Why:

- this avoids hiding estimated values inside notes/tags
- it makes #235 and 3D Print Log style analytics possible without corrupting archive truth

### 2. Print Event Timeline

Add a sidecar event table keyed by archive id with rows like:

- `print_started`
- `print_paused`
- `print_resumed`
- `print_failed`
- `print_stopped`
- `print_finished`
- `photo_captured`
- `enrichment_applied`
- `repair_applied`

Why:

- it preserves lifecycle provenance cleanly
- it supports better diagnostics and auditability than relying only on final archive status

### 3. Stronger Spool Snapshot Contract

At minimum, persist per-print spool snapshot fields for each used slot:

- tray key / AMS slot
- spool id
- filament id
- tray UUID / RFID UUID when present
- color/profile/vendor at print start
- matching method used: direct UUID, tray-map snapshot, color fallback, manual override

Why:

- this makes spool attribution explainable and debuggable
- it adopts the strongest lessons from OpenSpoolman and SpoolSync without changing architecture

### 4. Artifact Extraction at Print Start

When a `.3mf` or equivalent print artifact is accessible, extract and retain:

- preview image
- slicer-estimated weight
- slicer-estimated cost if available
- material/profile names
- plate information
- model/project identifiers

Why:

- this is one of the best ideas from the Node-RED flow
- it improves resilience when runtime state is incomplete or delayed

### 5. Failure Analysis and Compare Readiness

Elevate these fields into explicit sidecar/query support:

- normalized failure category
- raw failure reason
- related comparison group key
- reprint source archive id
- duplicate/model lineage key

Why:

- this aligns the current advanced-features roadmap with the strongest ideas from O.D.I.N. and Bambuddy's own comparison endpoints

## Recommendation

### Architectural Recommendation

Keep the current direction:

- Bambuddy remains the authoritative archive source
- the `bambuddy` custom integration and local SQLite store remain the history-query sidecar
- Home Assistant remains the orchestration and UI layer

No reviewed external system is compelling enough to replace that architecture without introducing unnecessary churn or splitting authority.

### Integration Recommendation

Do not add any of the reviewed services as a required dependency for print history.

If anything external is adopted in the future, it should be because a parallel concern becomes primary:

- spool authority and live weight operations -> stronger Spoolman/SpoolSync-style sidecar work
- remote monitoring / AI -> optional OctoEverywhere or Obico integration
- fleet operations platform -> deliberate platform pivot, not an additive patch

### Feature Recommendation

The best additions to implement in this repo are not product swaps. They are targeted data-model and workflow upgrades:

1. explicit derived metrics for estimated vs actual material, duration, and cost
2. a per-print event timeline table
3. stronger spool snapshot provenance
4. print-start artifact extraction when source files are available
5. richer failure taxonomy and compare/reprint lineage
6. per-print energy-cost joins where power data exists

## Go-Forward Plan

### Phase A: Metadata Contract Hardening

- Define sidecar schema additions for derived metrics and event timeline rows
- Keep Layer 1 lean; place new analytics-friendly joins in Layer 2 or sidecar tables, not in UI-only archive projections
- Document which values are authoritative, derived, estimated, or user-edited

### Phase B: Capture Improvements

- Extend print-start handling to capture artifact-derived metadata when available
- Persist spool snapshot provenance at print start
- Add terminal event rows for finish/fail/stop and enrichment application

### Phase C: Analytics and UX

- Expose actual vs estimated usage in detail popup and analytics cards
- Add energy-cost per print when power monitoring is present
- Add event timeline and richer failure-analysis views

### Phase D: Advanced History Features

- implement compare-ready lineage fields
- implement reprint lineage fields
- group related archives by model/project/deduplicated source identity
- expand exports and rollups for long-term analysis

## Final Assessment

The external review reinforces the current strategy more than it challenges it.

The repo already has the right architectural split for a serious print-history system. The missing pieces are mostly schema maturity and provenance clarity, not a new platform. Issue #235 is valuable because it shows a strong event-capture and derived-metrics pattern. OpenSpoolman and SpoolSync are valuable because they show what stronger spool authority looks like. 3D Print Log is valuable because it models explicit actual-versus-estimated usage cleanly. O.D.I.N. is valuable because it shows what a fuller roadmap could become.

The correct move is to continue the Bambuddy-backed design and selectively absorb those ideas into the existing sidecar model.