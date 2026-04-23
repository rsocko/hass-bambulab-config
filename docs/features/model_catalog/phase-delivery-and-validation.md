# Phase Delivery And Validation Tracker

> **Status**: Active execution tracker.
> **Last updated**: 2026-04-22
> **Purpose**: Turn the phased implementation plan into concrete, reviewable deliverables with validation gates.

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

## Phase 2+ Tracking Rule

Before starting each later phase, extend this tracker with the same three sections:

1. required deliverables
2. validation gate
3. automatic vs manual validation split

That keeps each phase reviewable without relying on chat memory.

## Current Status

- Phase 0 baseline: **closed in docs**
- First executable milestone selected: **Phase 1A sidecar scaffold and Manyfold read baseline**
- Phase 1A scaffold: **implemented and validated locally with focused pytest coverage**
- Phase 1 next target (archive-facing DTO contract): **in progress**
- Implemented in this slice: `GET /api/archive-links/{archive_id}` with contract id `archive-link.v1alpha1` and focused test coverage
- Next implementation target after this slice: **add archive-link write/review operations (create, accept/reject, deactivate) behind the same contract boundary**