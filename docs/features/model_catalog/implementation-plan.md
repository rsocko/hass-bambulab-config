# Model Catalog Implementation Plan

> **Status**: Revised implementation plan.
> **Last updated**: 2026-04-22
> **Scope**: Single-user personal model catalog using Manyfold for curated cataloging, Bambuddy for archives, a same-stack sidecar for cross-system logic, and HA as the operator-facing control plane.

## Goal

Deliver a model-catalog system that:

- surfaces stable curated models through Manyfold
- links those models to Bambuddy print archives
- provides a Working-file veneer outside Manyfold
- supports quick reprint, recent/common/frequent discovery, and a simple backlog/queue
- adds provenance capture, enrichment, and controlled write-back where that is safe

## Implementation Principles

- favor Manyfold's documented REST API over direct DB integration
- treat Working and curated catalog as separate operating zones
- avoid assuming native storage-mode conversion or automatic relink of moved external paths
- use sidecar-owned metadata for anything that does not naturally belong in Manyfold
- prefer same-stack sidecar deployment without direct Manyfold DB writes

## Phase Plan

### Phase 0: Delivery Baseline And Contracts

Outcome:

- the architectural baseline is frozen before code starts
- the sidecar boundary, Working-group concept, and external-storage recovery rules are explicit

Work items:

- lock the Manyfold capability matrix and corrected assumptions from the design review
- publish the external-storage truth table and recovery matrix
- publish the implementation-strategy decision matrix
- freeze the Working-group model and its HA-facing surface

Deliverables:

- architecture docs and strategy appendix approved
- first implementation milestone chosen from the updated phases below

### Phase 1: Sidecar Scaffold And Manyfold Read Baseline

Outcome:

- catalog sidecar exists as a runnable service in the same Docker stack
- sidecar can read Manyfold and expose a normalized summary cache

Work items:

- scaffold a FastAPI sidecar service
- add health, configuration, and diagnostics endpoints
- bootstrap SQLite schema for:
  - archive/model links
  - custom fields
  - Manyfold model summary cache
  - Working groups and Working items
  - review/audit events
- add Manyfold REST client for:
  - list models
  - get model detail
  - get model file detail when needed
  - list collections and creators as needed for browse and summary
- expose sidecar read endpoints for cached model summaries

Deliverables:

- sidecar runs in Docker
- HA can reach the sidecar
- Manyfold summaries can be fetched without direct browser-to-Manyfold dependency

### Phase 2: Archive Linkage And Popup Integration

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

Outcome:

- curated catalog becomes useful for day-to-day rediscovery and quick reprint

Work items:

- add sidecar-owned queue/backlog fields:
  - `to_print_status`
  - `to_print_priority`
  - optional manual favorite/frequent overrides if needed
- derive archive-backed ranking fields such as recent/common/frequent views
- add HA browse card for curated catalog with:
  - preview
  - tags
  - collection
  - linked archive count
  - recent/common/frequent indicators
  - queue state
- add filtered backlog/queue view in HA

Deliverables:

- curated catalog card optimized for quick rediscovery
- simple backlog/queue view in HA

### Phase 4: Working Groups And Working Veneer

Outcome:

- Working files gain a first-class operator surface without forcing them into Manyfold

Work items:

- implement Working-group data model in the sidecar
- support logical grouping of one or more files plus supporting assets
- allow grouping independent of the exact filesystem folder shape
- add sidecar endpoints for:
  - list Working groups
  - create/update group metadata
  - attach/detach files
  - set stage/status
  - mark a primary file
- add HA Working-group board and detail view
- support quick-open actions for group folder or primary file

Deliverables:

- Working files become visible and manageable from HA
- group-oriented workflow exists without Manyfold ownership of active edits

### Phase 5: Publish Workflow And Revision Lineage

Outcome:

- the boundary between Working and curated catalog becomes explicit and operator-safe

Work items:

- implement publish flow from Working group to curated catalog
- define lineage semantics:
  - canonical revision
  - supersedes / superseded_by
  - optional metadata carry-forward rules
- support two publish targets:
  - Manyfold-managed/internal-style curated storage (preferred baseline)
  - external scanned curated storage when deliberately chosen
- define recovery behavior when a curated external path changes and a recreate/relink flow is needed

Deliverables:

- clear Working-to-curated publish action
- revision lineage captured outside Manyfold where needed

### Phase 6: Photo Upload And 3MF Enrichment

Outcome:

- curated records become richer without manual re-entry of obvious assets

Work items:

- add photo-upload proxy to Manyfold
- implement sidecar-driven 3MF parsing and extracted asset upload
- allow preview selection assistance when safe
- expose photo and enrichment actions in archive popup and curated browse surfaces

Deliverables:

- curated model records can be enriched from HA and sidecar flows

### Phase 7: Provenance Capture And Online Ingestion

Outcome:

- online-source provenance is captured early and richer ingestion can follow later

Work items:

- add source recording for Printables/Makerworld URLs
- surface pending source records in HA
- add metadata-scrape draft flow later when justified

Deliverables:

- provenance capture works before or after cataloging

### Phase 8: Storage Monitoring, Preview Quality, And External Recovery Support

Outcome:

- the system can identify stale previews, storage drift, and external-storage recovery cases

Work items:

- surface stale-preview detection
- add storage sensors and maintenance actions
- add explicit external-storage recovery guidance and optional helper actions where safe

Deliverables:

- operators can identify when rescan is enough and when recreate/relink is required

### Phase 9: Upstream Improvement Track

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