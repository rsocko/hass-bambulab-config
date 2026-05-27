# Unified Production Queue Implementation Plan

> Status: Ready for execution planning
> Last updated: 2026-05-10
> Scope: End-to-end delivery plan for backend and frontend implementation of the Unified Production Queue and planner workflow.

## Purpose

Turn the approved queue design and mockups into a concrete implementation sequence that can be executed in GitHub issues and completed without ambiguity.

Design baseline:

- `unified-production-queue-design.md`
- `print-queue-assessment.md`
- `design/mockups/production-queue.html`
- `design/mockups/production-queue-add.html`
- `ux-concepts-and-mockups.md`

Issue links (prepopulated title/body):

- `unified-production-queue-github-issues.md`

## Current State Review

## What already exists

- Legacy catalog queue metadata (`to_print_status`, `to_print_priority`) exists only as historical compatibility data.
- Intake queue exists for model-catalog import/review flow.
- Bambuddy queue visibility exists in prototype form (`bambuddy/sensors.yaml`, `bambuddy/dashboards/queue.yaml`).
- Smart queueing primitives already exist in spoolman sync for deferred/pending tray assignment queues.

## Gaps to close for unified production queue

- No sidecar-owned unified queue entry model spanning `catalog_model`, `working_group`, `working_file`, and `idea` sources.
- No queue APIs for mixed-source queue CRUD/reorder/state transitions.
- No add flow contract for `quick add` vs `advanced add` with file/plate subsets.
- No archive linkage service that updates queue file/plate units by confidence tier.
- No planner API + apply/undo flow for strategy-driven reorder.
- No production HA frontend for the unified queue board and add modal.

## Architecture Decisions (Implementation)

## Ownership

- Sidecar owns unified queue persistence, planner, and linkage logic.
- Home Assistant frontend (custom JS cards) owns operator UX.
- Bambuddy remains execution queue/history-adjacent and should not be overloaded as the unified planning store.

Database guardrail:

- Unified queue storage must use the existing sidecar SQLite database (`model_catalog.db` via `MODEL_CATALOG_DB_PATH`) and existing migration system.
- Do not create a separate `queue.db` or any second queue-specific database file.

## Data model (minimum implementation slice)

- Queue Entry: source identity, state, rank, notes, copies, estimate, planner scores.
- File Unit: selected file scope and estimate.
- Plate Unit: selected plate scope, state, completion linkage, attempt tracking.
- Linkage Evidence: confidence tier and reason for suggested/automatic completion.

Estimate guardrail:

- treat `estimate` as provenance-aware metadata, not a single timeless field
- retain estimate source (`history`, `slicer`, `manual`) and freshness state so
	planner/ranking logic can prefer higher-confidence signals
- do not revive legacy curated-model `to_print_priority` as the persistence home
	for slicer-derived durations

## State model

- Entry states: `idea`, `todo`, `ready`, `started`, `blocked`, `done`.
- Plate states: `pending`, `started`, `blocked`, `done`.
- Failed archive attempts update attempts/outcome and do not auto-complete units.

## Delivery Plan

## Phase 1: Backend foundation

Deliverables:

- Persistent schema for queue entries + file/plate units in the existing `model_catalog.db` (migration-managed).
- API for queue CRUD + reorder + valid state transitions.
- Add-to-queue service contract for quick/advanced selection.

Suggested code areas:

- `sidecars/model_catalog/app/routers/`
- `sidecars/model_catalog/app/`
- `tests/`

Acceptance gate:

- API contract stable and covered by unit/integration tests.

## Phase 2: Linkage + smart planning backend

Deliverables:

- Archive linkage worker with confidence tiers (`high`, `medium`, `low`).
- Planner scoring endpoint with strategy presets.
- Apply/undo reorder endpoint and audit metadata.
- Ranking contract for estimate sources: prefer linked print-history duration,
	then fresh slicer-derived estimate, then manual estimate, then no-duration fallback.

Acceptance gate:

- Deterministic planner output and reversible rank rewrites.

Planning rule for first implementation:

- slicer-derived estimates should primarily improve ordering for entries that do
	not yet have print-history data
- queue consumers must be able to surface why a duration is shown (`history`,
	`slicer`, `manual`) and whether it is stale

## Phase 3: Frontend queue board and add flow

Deliverables:

- Launch-pad queue widget.
- Unified queue board with filters and mixed-source cards.
- Add-to-queue modal implementing quick and advanced modes.
- Queue detail expansion for file/plate states and suggestion actions.

Suggested code areas:

- `homeassistant/www/3d_printing/model_catalog/`
- `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`

Acceptance gate:

- Operator can add, reorder, inspect, and update queue items end-to-end.

## Phase 4: Integration hardening and rollout

Deliverables:

- Full e2e test coverage for add -> plan -> update -> completion flow.
- Migration checklist for existing queue-like fields.
- Rollout checklist and fallback plan.

Acceptance gate:

- All gates pass in CI and dashboard resources are version-bumped for frontend assets.

## Implementation Notes for This Repository

- Keep Layer 1/Layer 2/Layer 3 boundaries intact for print history data contracts.
- If JS assets are added/changed under `homeassistant/www/**`, bump matching resource URL versions in `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`.
- Do not introduce new queue behavior through model-catalog legacy queue fields; unified queue storage is the single queue contract.
- Extend existing `db_migrations.py` and `db_unified_queue.py` patterns; do not introduce a second SQLite file for queue data.
- If queue ranking consumes slicer-derived estimates, keep the estimate cache and
	invalidation keys in sidecar-owned persistence rather than recomputing on every
	board load.

## Test Plan (Minimum)

Backend:

- Queue schema migration tests.
- Queue CRUD/reorder/state transition tests.
- Add-flow selection validation tests.
- Archive-linkage confidence and completion behavior tests.
- Planner scoring/apply/undo tests.
- Estimate-source precedence tests (`history` over `slicer`, `slicer` over `manual`, stale handling).

Frontend:

- Add modal quick/advanced mode behavior tests.
- Queue board rendering and mutation-refresh tests.
- Planner drawer apply/undo behavior tests.
- Responsive layout and empty/error states.
- Duration badge/source-state rendering tests for fresh, stale, and missing estimates.

Integration:

- Mixed-source queue item lifecycle test.
- Failed archive attempt does not complete plate test.
- Medium-confidence suggestion accept/reject test.
- No-history queue entry receives slicer estimate and planner output changes accordingly.

## Work Tracking

Create tracking issues from:

- `unified-production-queue-github-issues.md`

Recommended sequence:

1. UQ-01 through UQ-03 (schema/API/add flow)
2. UQ-04 and UQ-05 (linkage/planner backend)
3. UQ-06 through UQ-09 (frontend)
4. UQ-10 (integration hardening and release checklist)
