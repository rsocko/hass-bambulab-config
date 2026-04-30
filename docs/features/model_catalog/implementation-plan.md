# Model Catalog Implementation Plan

> **Status**: Legacy pre-transition implementation plan retained for historical context.
> **Last updated**: 2026-04-25
> **Current roadmap**: Use [post-manyfold-transition-plan-2026-04.md](post-manyfold-transition-plan-2026-04.md) for authoritative phase sequencing and [phase-delivery-and-validation.md](phase-delivery-and-validation.md) for active execution tracking.
> **Scope below**: Historical Manyfold-first baseline and legacy phase names.

## Post-Manyfold Status Note

This file is no longer the authoritative sequencing document.

- The active model-catalog direction is sidecar-owned authority.
- The phase numbers below are preserved as historical implementation context.
- When this file references legacy phases such as `Phase 1.25`, `Phase 1.5`, `Phase 3.5`, or `Phase 10`, use the crosswalk in [post-manyfold-transition-plan-2026-04.md](post-manyfold-transition-plan-2026-04.md#legacy-to-new-phase-crosswalk) to map them into the current post-Manyfold sequence.

## Goal

Deliver a model-catalog system that:

- surfaces stable curated models through Manyfold
- links those models to Bambuddy print archives
- provides a Working-file veneer outside Manyfold
- supports quick reprint, recent/common/frequent discovery, and a simple backlog/queue
- adds provenance capture, enrichment, and controlled write-back where that is safe

## Execution Snapshot

Already complete or materially implemented:

- **Phase 0** baseline docs are closed
- **Phase 1A** sidecar scaffold and Manyfold read baseline are implemented
- **Phase 2** archive-linkage slice is implemented and validated end to end

Open next or later work:

- **Phase 1.25** persistence-and-backup execution
- **Phase 1.5** intake and bulk-discovery flow
- **Phase 3+** browse, Working, publish, enrichment, provenance, backfill, and upstream/project follow-on work

Use this document as the baseline implementation plan. Use [phase-delivery-and-validation.md](phase-delivery-and-validation.md) for the stricter current execution state and validation gates.

## Implementation Principles

- favor Manyfold's documented REST API over direct DB integration
- treat Working and curated catalog as separate operating zones
- avoid assuming native storage-mode conversion or automatic relink of moved external paths
- use sidecar-owned metadata for anything that does not naturally belong in Manyfold
- prefer same-stack sidecar deployment without direct Manyfold DB writes
- keep model-catalog persistence in a separate sidecar-owned SQLite database rather than reusing Manyfold Postgres or the print-history Variant 3 local store
- consume print-history/archive intelligence through stable archive-facing contracts, not direct reads of print-history internal tables

## Issue Tracking Note

At the time this document was written, the GitHub phase track had not yet been renumbered to the post-Manyfold sequence. The `.3mf` extraction and online provenance work from issue `#173` was therefore described here under legacy sub-phases:

- `Phase 3.5` for reusable parser, cache, and async analysis foundations
- `Phase 5` for publish-time preview and supporting-asset application
- `Phase 7` for public-source provenance capture and online metadata refresh

Current issue titles have since been realigned. See [3mf-resource-extraction-and-online-provenance-design.md](3mf-resource-extraction-and-online-provenance-design.md) plus the post-Manyfold transition plan for the active mapping.
See [3mf-resource-extraction-and-online-provenance-design.md](3mf-resource-extraction-and-online-provenance-design.md) for the detailed capability review and extraction contract.

## Phase Plan

### Phase 0: Delivery Baseline And Contracts

Status:

- complete in docs

Outcome:

- the architectural baseline is frozen before code starts
- the sidecar boundary, Working-group concept, and external-storage recovery rules are explicit

Work items:

- lock the Manyfold capability matrix and corrected assumptions from the design review
- publish the external-storage truth table and recovery matrix
- publish the implementation-strategy decision matrix
- freeze the Working-group model and its HA-facing surface
- freeze the cross-feature data-contract boundary between model-catalog, print_history, Bambuddy, and HA
- freeze the persistence decision: sidecar-owned SQLite for model-catalog local state

Deliverables:

- architecture docs and strategy appendix approved
- cross-feature contract doc approved
- first implementation milestone chosen from the updated phases below


Design handoff for preview promotion and supporting-asset behavior: [phase-5-publish-preview-and-supporting-assets-design.md](phase-5-publish-preview-and-supporting-assets-design.md)
### Phase 1: Sidecar Scaffold And Manyfold Read Baseline

Status:

- implemented for the current scaffold/read baseline

Outcome:

- catalog sidecar exists as a runnable service in the same Docker stack
- sidecar can read Manyfold and expose a normalized summary cache

Core delivered slice:

- scaffold a FastAPI sidecar service
- add health, configuration, and diagnostics endpoints
- bootstrap SQLite schema for:
  - archive/model links
  - custom fields
  - Manyfold model summary cache
  - Working groups and Working items
  - review/audit events
- define the first archive-facing dependency contract from HA/print_history into model-catalog as DTO/service consumption rather than shared DB reads
- add Manyfold REST client for:
  - list models
  - get model detail
  - get model file detail when needed
  - list collections and creators as needed for browse and summary
- expose sidecar read endpoints for cached model summaries

Follow-on prep still associated with this phase:

- keep schema room for intake, Working, and project extensions used by later phases
- keep archive-facing dependency contracts DTO/service-based rather than DB-coupled

Deliverables:

- sidecar runs in Docker
- HA can reach the sidecar
- Manyfold summaries can be fetched without direct browser-to-Manyfold dependency

### Phase 1.25: Sidecar Persistence And Backup Automation

Status:

- open

Outcome:

- sidecar durable state is protected before broader operator data accumulation
- backup/restore expectations are explicit before intake, Working, and enrichment phases create harder-to-reconstruct state

Work items:

- freeze `/data` as the durable sidecar-state boundary
- keep the default live-storage recommendation as a dedicated Docker named volume
- define a consistent SQLite export/snapshot step rather than naive raw-copy backup
- document restore flow and validation expectations
- keep HA as an optional status/trigger surface rather than the primary backup executor

Deliverables:

- persistence boundary and backup strategy are documented
- first backup automation path is chosen
- restore drill is defined and executed

### Phase 1.5: Intake Inbox, Bulk Discovery, And Import

Status:

- open

Outcome:

- files can enter a sidecar-owned Intake Inbox for validation and triage before broader Working or curated workflows
- bulk discovery and ad hoc intake share one review queue

Work items:

- add Intake Inbox persistence and validation state
- accept ad hoc file submissions into the Inbox
- support bulk discovery feeding the same review model
- dedupe against Inbox and existing Working groups before conversion
- allow the narrow handoff actions: create a new Working group or attach to an existing one
- add the first HA Inbox review surface and services for intake actions

Deliverables:

- Intake Inbox endpoints and review state exist
- bulk discovery can stage proposals into the same Inbox flow
- operators can convert Inbox items into Working groups without invoking publish workflows

Boundary note:

- this phase owns intake and triage only
- it does not replace the broader Working CRUD/UX of Phase 4 or the publish workflow of Phase 5

### Phase 2: Archive Linkage And Popup Integration

Status:

- implemented for the first archive-popup linkage slice
- follow-on heuristic/search enhancements remain open

Outcome:

- archive popup becomes the first strong operator surface for model linkage

Work items:

- implement archive-link CRUD and candidate-review endpoints
- expose HA services for:
  - fetch link summary
  - refresh candidates
  - create manual link
  - accept/reject candidate
  - deactivate link
- update archive popup contract and HA card surfaces
- show Manyfold model summary in popup
- allow queue/backlog state updates from confirmed archive linkage when appropriate

Deliverables:

- end-to-end archive-to-model linking from HA
- accepted/rejected review flow

### Phase 3: Queue, Ranking, And Curated Browse

Status:

- open

Outcome:

- curated catalog becomes useful for day-to-day rediscovery and quick reprint

Work items:

- add sidecar-owned queue/backlog fields:
  - `to_print_status`
  - `to_print_priority`
- add sidecar-owned model taxonomy/browse fields for the first curated-catalog slice:
  - `model_favorite` kept sidecar-owned because Manyfold does not currently expose a dependable documented favorite/like REST surface for this workflow
  - `model_rating` as integer `1` through `5`
  - `taxonomy_origin_class` for `reprint`, `remix_or_tweak`, and `custom_unique`
  - `taxonomy_change_axes` for `color`, `model`, and `other`
  - `colors_used` as a hex-first model-level taxonomy field in the Phase 3 baseline
- derive archive-backed ranking fields such as recent/common/frequent views
- add HA browse card for curated catalog with:
  - preview
  - tags
  - collection
  - linked archive count
  - recent/common/frequent indicators
  - queue state
  - taxonomy/favorite/rating indicators where they help browse and filtering without bloating the first shipped card
- leave richer provenance and publish-destination metadata out of this phase so the shipped Phase 3 browse/ranking slice stays narrow
- add filtered backlog/queue view in HA
- add curated browse filtering support for the first taxonomy slice:
  - taxonomy-origin filtering
  - change-axis filtering
  - `model_favorite` filtering
  - hex-based `colors_used` filtering

Deliverables:

- curated catalog card optimized for quick rediscovery
- simple backlog/queue view in HA
- first taxonomy-aware curated browse slice exists without requiring Spoolman identity linkage yet

### Phase 3.5: Bulk Metadata Enrichment

Status:

- open

Outcome:

- working groups can be analyzed and enriched in bulk after the Phase 3 browse and taxonomy baseline exists

Work items:

- add reusable parser/analysis support for batch workflows
- analyze working groups in bulk for color and tag proposals
- apply operator-reviewed enrichments in batch
- add a focused HA review surface for bulk-enrichment approval

Deliverables:

- bulk-analyze and bulk-enrich flows exist
- operator-reviewed color/tag enrichment can be applied to many Working groups efficiently

Boundary note:

- this phase owns bulk analyze/enrich workflows only
- individual curated asset upload and richer per-model enrichment remain Phase 6 concerns

### Phase 4: Working Groups And Working Veneer

Status:

- open

Outcome:

- Working files gain a first-class operator surface without forcing them into Manyfold
- repeated acquisition of the same external source can be reconciled safely before curated publish

Work items:

- implement Working-group data model in the sidecar
- support logical grouping of one or more files plus supporting assets
- allow grouping independent of the exact filesystem folder shape
- add Working-side duplicate detection for reacquired source files, especially common Makerworld or Printables re-download cases such as filename suffixes like `(2)`
- support operator-safe reacquisition choices such as attach to existing Working group, keep both as variants, or replace an earlier Working copy deliberately
- add sidecar endpoints for:
  - list Working groups
  - create/update group metadata
  - attach/detach files
  - set stage/status
  - mark a primary file
- add curated-model provenance metadata fields and operator editing surface for:
  - `origin_type` with explicit `custom_unique` vs `remix`/`derivative`
  - `remix_source` for "remix of what" capture
  - `published_to` as a multi-destination picker/list
  - optional `published_urls` map for later direct-link support per destination
- expose these fields in HA and sidecar APIs as sidecar-owned metadata, not as Manyfold-native fields
- add HA Working-group board and detail view
- support quick-open actions for group folder or primary file

Boundary note:

- this phase owns the full Working experience
- earlier intake phases may create or attach a Working group, but they do not replace the broader Working CRUD and UX defined here

Deliverables:

- Working files become visible and manageable from HA
- group-oriented workflow exists without Manyfold ownership of active edits
- Working reacquisition and duplicate-handling rules exist before publish-to-curated flows become common
- custom/remix provenance and external publish-destination tracking are available as operator-managed model metadata without pulling this work earlier than Phase 3

### Phase 5: Publish Workflow And Revision Lineage

Status:

- open

Outcome:

- the boundary between Working and curated catalog becomes explicit and operator-safe
- duplicate or repeat-acquired source files can be reconciled against existing curated records intentionally

Work items:

- implement publish flow from Working group to curated catalog
- define lineage semantics:
  - canonical revision
  - supersedes / superseded_by
  - optional metadata carry-forward rules
- add curated duplicate and reconciliation checks before publish, including warnings when a reacquired file appears to overlap an existing Manyfold model
- support deliberate publish-time choices such as publish as new revision, add as additional file, keep separate, or cancel for cleanup
- support two publish targets:
  - Manyfold-managed/internal-style curated storage (preferred baseline)
  - external scanned curated storage when deliberately chosen
- define recovery behavior when a curated external path changes and a recreate/relink flow is needed
- apply extracted `.3mf` resources during publish when requested:
  - select one extracted preview as the curated preview candidate
  - optionally attach a narrow allowlisted set of sidecar-managed support artifacts
  - preserve the analysis revision and resource inventory link used for the publish decision

Deliverables:

- clear Working-to-curated publish action
- revision lineage captured outside Manyfold where needed
- duplicate warning and reconciliation behavior exists for Working-to-curated publish decisions
- publish-time preview promotion and supporting-asset decisions are explicit rather than implicit side effects

Boundary note:

- publish, lineage, curated duplicate reconciliation, and preview promotion remain Phase 5 concerns
- earlier phases should hand off into this flow rather than partially reimplement it

### Phase 6: Photo Upload And 3MF Enrichment

Status:

- open

Outcome:

- curated records become richer without manual re-entry of obvious assets

Work items:

- add photo-upload proxy to Manyfold
- implement sidecar-driven 3MF parsing and extracted asset upload
- add a reusable `.3mf` analysis cache keyed by file hash so bulk enrichment, Working-group detail, and publish-time flows share the same parse results
- inventory preview candidates, embedded companion resources, and embedded provenance hints without surfacing raw model payload members as user-facing support files
- allow preview selection assistance when safe
- expose photo and enrichment actions in archive popup and curated browse surfaces
- add later-phase enrichment hooks for model color taxonomy improvement:
  - optional operator picker to assign Spoolman `filament_id` to a model-catalog `colors_used` entry
  - optional automatic `filament_id` inference from parsed `.3mf` metadata when the source data is strong enough
  - keep spool identity out of model-level taxonomy because it is print-specific rather than model-specific

Deliverables:

- curated model records can be enriched from HA and sidecar flows
- model color taxonomy has a defined upgrade path from Phase 3 hex-only values to later Filament-ID linkage
- `.3mf` analysis results are reusable across bulk analyze, Working review, publish, and later backfill flows

### Phase 7: Provenance Capture And Online Ingestion

Status:

- open

Outcome:

- online-source provenance is captured early and richer ingestion can follow later

Work items:

- add source recording for Printables/Makerworld URLs
- surface pending source records in HA
- preserve enough source identity to assist repeat-download review where practical
- store embedded provenance hints discovered during `.3mf` analysis separately from fetched public metadata
- add an opt-in source-resolution step that can normalize MakerWorld or other public source URLs into durable source records
- add metadata-scrape draft flow later when justified

Deliverables:

- provenance capture works before or after cataloging
- source provenance can assist duplicate/re-download review but is not required for the first Working-side duplicate checks
- `.3mf`-embedded provenance hints and online-source metadata use separate lifecycles and refresh timestamps

### Phase 8: Historical Print-History Backfill From Model Catalog

Status:

- open

Outcome:

- the model-catalog UI can assist operator-driven backfill of older or incomplete print-history records by reusing existing forensics and folder-catalog workflows

Work items:

- add a catalog-driven review flow for historical backfill candidates from curated or Working model records
- surface nearby or candidate archive matches using archive identity, filename similarity, source provenance, existing manifests, or related analyzed artifacts when available
- support operator choices such as:
  - link to an existing archive
  - create a new canonical archive from an archive-ready sliced artifact
  - attach source-only provenance to an existing archive
  - defer when the candidate remains ambiguous
- reuse existing runner and manifest concepts from:
  - folder 3MF catalog workflow
  - forensics import queue
  - source-3MF provenance attachment flow
- keep the first slice operator-driven and review-heavy rather than attempting a fully automatic archive recreation path

Deliverables:

- a model-catalog-driven backfill workflow exists for older records
- existing forensics/backfill tooling is integrated as an execution engine rather than stranded as a separate operator-only path
- created or attached archives can be linked back into the catalog flow immediately

### Phase 9: Storage Monitoring, Preview Quality, And Recovery

Status:

- open

Outcome:

- the system can identify stale previews, storage drift, and recovery cases while giving operators safe cleanup actions

Tracking:

- issue [#222](https://github.com/rsocko/hass-bambulab-config/issues/222) (storage size monitoring and preview cleanup)

Work items:

- surface stale-preview detection
- add storage sensors and maintenance actions, including trend-aware storage growth checks
- add preview-retention and trim actions with explicit dry-run and apply modes
- define preview-quality guardrails so cleanup does not remove canonical primary preview coverage
- add explicit recovery guidance and optional helper actions where safe

Deliverables:

- operators can identify when rescan is enough and when recreate/relink is required
- operators can identify when preview cleanup is safe, and can run bounded trim actions with audit-friendly output

### Phase 10: Upstream Improvement Track

Status:

- open

Outcome:

- the sidecar boundary remains stable while upstream opportunities are evaluated deliberately

Work items:

- maintain a short list of upstream-worthy Manyfold gaps
- submit upstream PRs where features are broadly useful
- avoid a long-lived fork unless a feature is urgent, Manyfold-native, and not cleanly achievable via the sidecar

Deliverables:

- clear distinction between short-term sidecar delivery and longer-term Manyfold enhancement

## Validation Spikes

Before implementation begins in earnest, validate the riskiest assumptions:

1. Manyfold REST upload and add-file flows for curated catalog operations
2. Manyfold file/model PATCH behavior for safe write-back fields
3. Rescan behavior for curated external library changes
4. Recovery after restoring a missing external file or folder to the same path
5. Sidecar feasibility for Working-file indexing and logical grouping
6. Archive-derived ranking signals from Bambuddy and print-history data
7. Same-stack sidecar deployment and auth/config ergonomics

## Decision Matrix Requirement

Implementation documentation must carry a strategy appendix comparing:

1. pure REST sidecar
2. same-stack sidecar with shared volumes/network and no direct DB writes
3. direct Manyfold enhancement via fork/upstream PRs

Required comparison dimensions:

- delivery speed
- upgrade risk
- operational complexity
- access to internal capabilities
- data-authority clarity
- suitability for Working veneer
- suitability for curated catalog enhancements
- long-term maintainability

Current baseline recommendation:

- same-stack sidecar where operationally convenient
- no direct Manyfold DB writes as the primary product contract

## Out Of Scope For The Baseline

- managing `Downloads/` as a first-class system
- turning HA into a full Manyfold admin replacement
- forcing Working into Manyfold as the default operating model
- depending on unsupported GraphQL or native storage-mode conversion features