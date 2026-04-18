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
- materially broader than Bambuddy at the platform level because it spans mixed-fleet operations, local AI failure detection, order-to-ship workflow, and multi-user business controls

Why it matters:

- it validates that the repo's roadmap areas are legitimate product directions, especially compare, reprint, diagnostics, project grouping, and cost analytics
- it is the clearest example of a system that treats print history as one part of a larger operations stack rather than as the whole product

#### O.D.I.N. vs Bambuddy: What Is Essentially the Same

At a high level, both systems already cover the same core archive loop:

- automatic print-history capture
- searchable archive browser
- reprint from history
- archive comparison
- tags/notes editing
- timelapse support
- self-hosted Docker deployment
- no cloud requirement for the base local-control model

That is why O.D.I.N. should be treated as a competitor or replacement-scale platform, not as a small additive companion. The overlap is real.

#### O.D.I.N. vs Bambuddy: Where O.D.I.N. Is Stronger or Materially Different

O.D.I.N. is stronger when the problem is broader print-farm operations rather than archive stewardship alone.

- **Mixed-fleet scope**: O.D.I.N. natively targets Bambu, Klipper, PrusaLink, and Elegoo in one product. Bambuddy is intentionally Bambu-first.
- **Operations breadth**: O.D.I.N. includes queueing, order management, BOM/product workflow, per-order profitability, user roles, OIDC/SSO, audit-style controls, and organization scoping. Bambuddy has queue and maintenance, but it is not trying to be a full manufacturing-ops suite.
- **Model-library split**: O.D.I.N. separates archives from `print_files`, models, and jobs. That creates a cleaner upstream place for pricing, scheduling, printer compatibility, and source-file metadata. Bambuddy keeps more of the intelligence archive-centric.
- **Vision / failure detection**: O.D.I.N. ships a real local vision subsystem with ONNX inference, per-printer thresholds, detection review, frame retention, stats, and training-data export. Bambuddy does not currently have an equivalent local AI vision stack.
- **API philosophy**: O.D.I.N. exposes a whole-platform API, session-cookie auth for UI, bearer tokens for automation, websocket updates, and no built-in rate limiting. Bambuddy has a strong API too, but it is more product-domain specific and more explicitly segmented by feature groups and rate limits.

#### O.D.I.N. vs Bambuddy: Where Bambuddy Is Stronger or Materially Different

Bambuddy is stronger when the problem is specifically Bambu-native archive fidelity and archive-side media/file workflows.

- **Archive richness at the archive object itself**: Bambuddy's archive record exposes more directly on the archive row and archive response: `content_hash`, duplicate lineage, estimated and actual duration, time-accuracy, full `extra_data`, MakerWorld/designer fields, favorite flag, quantity, failure reason, photos, energy, source 3MF, and Fusion 360 `f3d` attachments.
- **Archive-domain API depth**: Bambuddy's archive API is much deeper than O.D.I.N.'s archive API specifically. It includes failure-analysis endpoints, similar-archive search, global tag rename/delete, richer timelapse manipulation, project-page extraction/editing, source-file attachment flows, gcode extraction, archive capabilities, per-plate metadata, filament requirements, photo upload/delete, and Bambu-oriented file/media handling.
- **Bambu-specific 3MF introspection**: Bambuddy goes further into Bambu-flavored `.3mf` structure and exposes that directly on archive endpoints. That matters for this repo because the print-history feature is already designed around Bambu-specific archive enrichment and media review.
- **Media-first archive workflows**: Bambuddy is better aligned with this repo's current photo-enrichment, popup editing, archive browser, and historical repair flows. O.D.I.N. can support history, but its print archive is only one subsystem among many.
- **Current repo fit**: this repo already has a Bambuddy-backed sidecar, Layer 1/2/3 contracts, enrichment payloads, repair tooling, and Home Assistant browser assumptions built around Bambuddy semantics. That is a substantial switching cost, even before evaluating product quality.

#### Archive Storage and Schema Findings

This was the main question behind the direct comparison: does O.D.I.N. have a materially richer archive schema than Bambuddy?

Short answer: **not in the archive record itself**.

More precise answer:

- **Bambuddy archive rows are richer and more self-contained**. The archive model and response carry a broad set of Bambu-specific metadata and file/media relationships directly on the archive resource.
- **O.D.I.N. splits richness across adjacent domains**. The archive row is lighter, while the surrounding `print_files`, models, jobs, spools, and orders domains carry the rest of the operational context.

That means O.D.I.N. is not obviously better if the main requirement is: "make the archive object itself the authoritative, deeply explorable print-history artifact." Bambuddy is better at that today.

O.D.I.N. does still add some useful archive-adjacent fields and concepts:

- archive capture includes user attribution, `print_file_id`, `plate_count`, cost estimate, duration, and spool-deduction linkage
- archive compare uses actual-duration and cost-estimate fields directly
- archive reprint is tied to job creation and printer scheduling rather than just file replay
- archive/project linkage fits a broader manufacturing workflow

But the tradeoff is clear: O.D.I.N. distributes history semantics across more tables and modules, while Bambuddy concentrates them in the archive domain.

#### API Surface Findings

At the API level, the comparison is mixed.

Where O.D.I.N. is better:

- broader whole-platform API, not just printer/archive endpoints
- native support for automation tokens plus browser session auth
- websocket event model for live UI updates
- direct routes for organizations, orders, products, BOMs, reporting, and vision
- archive APIs connect naturally into jobs, models, and scheduling

Where Bambuddy is better:

- deeper archive-specific endpoint catalog
- better archive/media mutation surface
- better Bambu-specific 3MF extraction endpoints
- richer archive comparison and failure-analysis behavior within the archive domain itself
- more direct support for archive-source attachments and per-archive media workflows

So the answer is not "O.D.I.N. has a better archive API". The more accurate statement is:

- **O.D.I.N. has a broader platform API**
- **Bambuddy has a deeper archive API**

For this repo's active print-history work, the second point matters more than the first.

#### Vigil AI / Vision: How It Works and How It Is Gated

The vision feature in O.D.I.N. is real local functionality, not a cloud black box.

What the source and docs show:

- O.D.I.N. runs **ONNX inference locally** on camera frames
- frames are stored locally under `/data/vision_frames/...`
- ONNX model files are stored locally under `/data/vision_models/`
- the backend includes routes for detections, per-printer settings, global settings, stats, and training-data labeling/export
- the docs and marketing explicitly state that camera frames do not leave the network

So the important answer is:

- **yes, it is usable in self-host mode**
- **no, it does not appear to require a cloud AI service**

The gating is instead a combination of **license tier** and **license terms**, not a cloud dependency.

- public pricing pages describe Community, Pro, Education, and Enterprise tiers
- the codebase contains a local license/tier system and frontend feature gating
- the project is **source-available under BSL 1.1**, not permissive open source in the conventional sense
- the license page states that non-commercial and personal use are allowed, while commercial use requires a paid license

One nuance worth documenting: the public pricing/marketing copy is not perfectly consistent about which tier lists Vigil AI, but the architecture is consistent. The vision subsystem itself is local and self-hostable. The constraint is commercial/tier licensing, not technical cloud lock-in.

#### Is O.D.I.N. Superior Enough to Justify a Transition?

Only if the problem statement changes.

O.D.I.N. is superior if the actual goal is:

- mixed-fleet management
- local AI monitoring
- business workflow around orders, BOMs, margin, and operators
- multi-user print-farm software with organizations and permissions

It is **not** clearly superior for this repo's current goal, which is more specific:

- keep Bambuddy as archive-of-record for Bambu-native history
- use Home Assistant as orchestration and UI
- enrich and query archive history locally with repo-owned logic
- preserve Bambu-specific archive/media semantics without replatforming the whole stack

For that goal, moving to O.D.I.N. would trade one set of strengths for another and would force a replacement-scale migration across:

- archive authority
- API contracts
- browser semantics
- enrichment assumptions
- photo/media flows
- existing local repair/provenance work

That churn is hard to justify unless the repo wants to become a farm-operations layer rather than a Bambuddy-backed HA history layer.

Why it is not the immediate answer:

- adopting it would mean choosing a new platform, not just borrowing a feature
- it overlaps heavily with work already underway in this repo and with Bambuddy's archive model
- it is too broad to add incrementally as a low-risk dependency
- it is source-available BSL software with tiered/commercial licensing, so depending on it is not the same category of decision as depending on a normal permissive OSS library

Recommendation:

- use O.D.I.N. as the clearest roadmap benchmark
- borrow platform ideas selectively: local AI detection posture, archive-to-job linkage, model-library separation, and project/order framing
- do not treat O.D.I.N. as an additive dependency next to Bambuddy
- do not transition from Bambuddy to O.D.I.N. unless the project intentionally pivots from "Bambu archive + HA sidecar" to "general print-farm operating system"

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