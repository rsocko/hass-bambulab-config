# Phase Delivery And Validation Tracker

> **Status**: Active execution tracker.
> **Last updated**: 2026-04-28
> **Purpose**: Turn the phased implementation plan into concrete, reviewable deliverables with validation gates.

## Authoritative Roadmap Update

The authoritative phase roadmap is now the sequential post-Manyfold plan in [Post-Manyfold Transition Plan (2026-04)](../post-manyfold-transition-plan-2026-04.md).

Use the following sequence for active execution:

1. Phase 1 - Authority Pivot Foundation
2. Phase 2 - Canonical Data Model Expansion
3. Phase 3 - API and Storage Cutover
4. Phase 4 - UI Continuity and In-Flight Preservation
5. Phase 5 - Intake, Bulk Discovery, and Working/Curated Unification
6. Phase 6 - Search, Ranking, and Enrichment Parity
7. Phase 7 - Data Migration and Compatibility Layer
8. Phase 8 - Docs and Issue Realignment
9. Phase 9 - Future Integrations and Advanced Work

Legacy phase sections below are retained for implementation history and crosswalk only.

## How To Use This Tracker

For each phase:

- define the specific deliverables that must exist in the repo or deployment
- define how to validate them before moving forward
- note what can be tested automatically versus what remains a manual or environment-dependent check

This tracker is intentionally stricter than the strategy docs. The goal is to keep implementation incremental and falsifiable.

## Phase 0: Delivery Baseline And Contracts

### Goal

Freeze the implementation baseline so Phase 1 can begin without reopening core architecture decisions.

### Required Deliverables

1. Architecture baseline doc approved:
   - `architecture-overview.md`
2. External-storage behavior and recovery rules published:
   - `external-storage-behavior.md`
3. Strategy decision matrix published:
   - `implementation-strategy-options.md`
4. Working-group model and HA-facing expectations published:
   - `working-groups-and-veneer.md`
5. Cross-feature contract boundary published:
   - `cross-feature-data-contracts.md`
6. Persistence decision frozen:
   - sidecar-owned SQLite for model-catalog state
7. First implementation milestone selected and written down:
   - **Chosen milestone**: Phase 1A sidecar scaffold with health/config endpoints, SQLite bootstrap, and Manyfold read smoke path

### Validation Gate

Phase 0 is complete when all of the following are true:

1. The required docs exist and are indexed from the model-catalog README.
2. The docs agree on these baseline decisions:
   - Manyfold is curated authority
   - Bambuddy/print_history is archive authority
   - model-catalog keeps its own SQLite store
   - cross-feature reads happen through service/DTO contracts, not shared DB reads
   - same-stack sidecar is the preferred baseline implementation strategy
3. The next executable milestone is explicit enough that implementation can start without reopening the storage or authority model.

### What Can Be Validated Automatically

- markdown file existence
- markdown diagnostics/errors
- targeted text checks for the frozen baseline decisions

### What Remains Manual

- final human approval that the design baseline is stable enough to begin Phase 1

## Phase 1A: First Executable Milestone

## Phase 5 Wave 4 Design Baseline

Before Wave 4 implementation begins, the UI design baseline should be treated as frozen enough to support card, popup, and helper work without reopening the operator-surface shape.

### Required Deliverables

1. Wave 4 implementation-facing UI design doc exists.
   - `phase-5-wave-4-ha-ui-design.md`
2. End-state and handoff companion exists.
   - `phase-5-end-state-ui-and-handoff-design.md`
3. The design set explicitly covers:
   - #1077 working groups and link management
   - #1082 batch selection and curation actions
   - #1145 source mode, queue, and cleanup policy UI
4. The design set explicitly threads forward dependencies from:
   - #1163 / #1137 preview promotion and supporting-asset import
   - #1132 / #1133 enhanced Working groups, publish workflow, revision lineage
   - #1149 deployment/runtime and remote-client intake
   - #1146 cleanup safety and retry visibility
   - #213 local-library / OneDrive import path

### Validation Gate

Wave 4 UI implementation is ready to start when all of the following are true:

1. The Wave 4 doc names the concrete surfaces, reusable components, and key interaction states needed for implementation.
2. The end-state doc shows how those surfaces expand later without requiring a parallel UI system.
3. The new docs align with the post-Manyfold authority model and the existing intake/Working docs.
4. The docs are linked from the model-catalog overview/index and the Phase 5 execution sequence.

### What Can Be Validated Automatically

- markdown file existence
- markdown diagnostics/errors
- targeted checks that the new docs are linked from the overview/index and execution-sequence docs

### What Remains Manual

- final human review that the surface hierarchy, componentization, and interaction density are correct before card implementation starts

### Selected Scope

This is the first implementation milestone chosen at the end of Phase 0.

Build a minimal model-catalog sidecar that can:

1. run as a local service
2. expose health/config/diagnostics endpoints
3. create or open its SQLite database
4. read Manyfold model summaries through the documented REST API
5. expose a normalized read endpoint for those summaries

### Required Deliverables

1. Sidecar scaffold exists in the repo.
2. Sidecar configuration supports Manyfold base URL and local SQLite path.
3. SQLite bootstrap creates the first schema needed for:
   - Manyfold summary cache
   - archive/model links
   - Working groups/items
   - audit/review events
4. Manyfold client supports a minimal read path:
   - list models
   - get model detail if needed for normalization
5. At least one local validation path exists that does not require Home Assistant UI wiring.

### Validation Gate

Phase 1A is complete when all of the following are true:

1. The service starts locally.
2. Health endpoint responds successfully.
3. SQLite file is created and schema bootstrap succeeds.
4. A Manyfold read smoke test succeeds against a configured instance or a mocked/test fixture.
5. A normalized sidecar endpoint returns model summaries from fetched or cached data.

### Preferred Validation Order

1. focused unit tests for schema/bootstrap and normalization logic
2. local service smoke test for startup and health endpoint
3. Manyfold API smoke test with fixture or live configured endpoint
4. only then move to HA-facing integration wiring

## Phase 1.25: Sidecar Persistence And Backup Automation

### Goal

Freeze and validate the persistence boundary for model-catalog durable state before later phases accumulate working-group, linkage, and enrichment data that would be expensive to recreate.

### Required Deliverables

1. Persistence strategy doc exists and is indexed from the model-catalog README.
   - `persistence-and-backup-strategy.md`
2. Durable-state boundary is frozen.
   - `/data` is the documented durable root
   - `MODEL_CATALOG_DB_PATH=/data/model_catalog.db` remains the baseline
3. Default storage mode is frozen.
   - dedicated Docker named volume is the default
   - Linux/WSL bind mount is documented as an opt-in mode
   - Windows-host bind mount is explicitly not the default recommendation for the live DB
4. Backup artifact shape is documented.
   - DB snapshot
   - metadata sidecar bundle
   - restore provenance fields
5. At least one concrete backup automation path is chosen for first implementation.
   - repo-local scheduled export job or equivalent
   - optional downstream retention via `restic` or `kopia`
6. Restore drill is documented and executed at least once against a fresh target instance or equivalent isolated restore path.
7. HA role is frozen.
   - HA may expose status and optional manual trigger later
   - HA is not the primary filesystem backup executor

### Validation Gate

Phase 1.25 is complete when all of the following are true:

1. The persistence strategy doc exists and matches the roadmap decision.
2. The current compose/deployment guidance still aligns with the default named-volume recommendation.
3. A consistent backup bundle can be produced from live sidecar state.
4. A restore drill has been executed and validated with `/healthz` plus at least one representative sidecar endpoint.
5. The team has chosen the first live retention path.
   - scheduled local export only as bootstrap, or
   - export plus `restic`, or
   - export plus `kopia`

### Preferred Validation Order

1. doc review for persistence boundary and deployment-mode tradeoffs
2. backup bundle creation test against a disposable sidecar instance
3. restore drill against a fresh target path or isolated test instance
4. only then allow later phases to rely on sidecar-only durable state

### What Can Be Validated Automatically

- markdown file existence
- markdown diagnostics/errors
- targeted checks for the frozen default storage mode and HA-role language
- backup-bundle file existence, naming, and metadata presence if automation is scripted in repo later

### What Remains Manual

- live restore confidence on the real deployment host
- final selection between `restic` and `kopia` if both are viable in the homelab
- operational approval of retention policy and backup destination

## Phase 2+ Tracking Rule

Before starting each later phase, extend this tracker with the same three sections:

1. required deliverables
2. validation gate
3. automatic vs manual validation split

That keeps each phase reviewable without relying on chat memory.

## Phase 1.5: Intake Inbox, Bulk Discovery And Import

### Goal

Deliver the first pre-curation intake surface so files can be staged, validated, deduped, and converted into Working groups before any broader publish workflow is attempted.

### Required Deliverables

1. Sidecar intake persistence exists for Inbox items and validation state.
2. Sidecar endpoints exist for:
   - submit intake items
   - list and fetch intake items
   - validate one or many intake items
   - defer or reject intake items
   - convert intake items into new or existing Working groups
3. Bulk-discovery path can feed the same Intake Inbox review model.
4. HA services exist for the first operator actions:
   - submit to Inbox
   - fetch items
   - validate item
   - create Working group from Inbox item
   - attach Inbox item to existing Working group
   - defer or reject item
5. First Intake review card or popup surface exists in HA with mixed-state rendering.
6. Duplicate warnings are visible before grouping decisions.

### Validation Gate

Phase 1.5 is complete when all of the following are true:

1. One-file submit to Inbox works end to end.
2. Validation produces stable operator-facing states for:
   - ready
   - duplicate candidate
   - unsupported type
   - missing source
3. An Inbox item can create a new Working group.
4. An Inbox item can attach to an existing Working group.
5. Reject and defer actions preserve review history and do not silently delete the item.
6. Bulk discovery can materialize reviewable proposals into the same Inbox model.

### Preferred Validation Order

1. focused unit tests for schema/bootstrap, validation rules, and dedupe logic
2. focused API tests for submit/list/detail/validate/group/reject/defer
3. bounded fixture test for folder discovery and proposal staging
4. HA service smoke tests against a running sidecar
5. manual review of the first Intake Inbox card with mixed statuses

### What Can Be Validated Automatically

- markdown/file existence for the implementation breakdown doc
- sidecar schema bootstrap for intake tables
- endpoint tests for submit, validate, and group flows
- duplicate-detection behavior with fixture files
- Working-group conversion behavior from Inbox items

### What Remains Manual

- final operator UX judgment on the first Inbox review card
- drag/drop or local path-entry ergonomics in the chosen HA/browser surface
- host-specific filesystem-path behavior for the deployment environment

## Current Status

- Phase 0 baseline: **closed in docs**
- First executable milestone selected: **Phase 1A sidecar scaffold and Manyfold read baseline**
- Phase 1A scaffold: **implemented and validated locally with focused pytest coverage**
- Phase 1.25 backup/persistence planning: **documented, not yet executed**
- Phase 1.25 default direction: **named Docker volume for `/data`, export-based snapshots, HA as status/trigger surface only**
- Phase 1 target (archive-facing DTO contract): **implemented** (`GET /api/archive-links/{archive_id}`)
- Phase 2 archive-linkage slice: **implemented and test-validated end to end**
- Implemented in this slice: archive-link CRUD and candidate review endpoints (`create`, `update`, `deactivate`, `candidates/refresh`, `accept`, `reject`), cache-refresh support for candidate refresh, manual-link URL canonicalization, duplicate prevention, confirmed-link preservation across candidate refresh, and popup card integration through HA rest-command wiring
- Manual and live validation completed for the popup linkage surface, including candidate acceptance, manual link create, and confirmed-link display with Manyfold model name
- Open follow-on endpoint in repo: duplicate cleanup for inactive historical link rows (`POST /api/archive-links/{archive_id}/cleanup-duplicates`)
- Deferred from Phase 2 into later phases: heuristic candidate broadening beyond the current name-overlap baseline, catalog picker/search, and queue/backlog field behavior
- Phase 6 authority docs now published:
   - `phase-6-search-ranking-and-discovery-design.md`
   - `phase-6-bulk-metadata-enrichment-design.md`
- Recommended next implementation target: **Phase 1.25 backup bundle automation and restore drill**
- After the current Phase 5 intake/bulk-unification execution: implement the published **Phase 6 search/discovery** and **Phase 6 bulk enrichment** contracts