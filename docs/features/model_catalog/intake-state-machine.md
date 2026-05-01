# Intake Flow States And Transitions

> Status: Wave 1 specification
> Issue: #1079
> Last updated: 2026-04-30
> Scope: Canonical state machine for Phase 5 intake-to-working workflow.

## Purpose

Define the state model that governs intake items from submission through triage and conversion to working groups. This contract is used by sidecar API endpoints, queue processing, and HA operator surfaces.

For a visual walkthrough of the same flow, plus a state/action cheat sheet and a separate current-implementation flow, see [import-flow-diagrams.md](c:\dev\hass-bambulab-config\docs\features\model_catalog\import-flow-diagrams.md).

## Scope Boundary

This state machine covers intake and working handoff only.

Included:

- intake submission
- validation and dedupe review
- defer/reject decisions
- conversion into new or existing working groups

Excluded (later phases):

- publish-to-curated actions
- lineage/supersession decisions
- publish-time preview promotion

## Primary States

`submitted`

- item accepted by sidecar intake endpoint
- canonical path normalization has run
- no validation result yet (unless auto-validate enabled)

`validated_ready`

- supported type
- source is readable
- no blocking duplicate condition
- ready for grouping actions

`validated_warning`

- validation succeeded with warning conditions
- examples: duplicate candidates, name collisions, grouping ambiguity
- operator decision required before grouping

`deferred`

- intentionally parked for later review
- item remains visible in inbox queue

`rejected`

- operator rejected item as noise/duplicate/invalid
- kept for audit history; not eligible for grouping unless explicitly reopened

`grouped_new`

- item converted to a newly created working group
- immutable linkage to resulting `working_group_id`

`grouped_existing`

- item attached to an existing working group
- immutable linkage to resulting `working_group_id`

## Validation Outcome Substates

Validation outcomes are stored as `validation_state` and inform transitions.

- `ready`
- `duplicate_candidate`
- `unsupported_type`
- `missing_source`
- `needs_manual_grouping`

Mapping:

- `ready` -> `validated_ready`
- `duplicate_candidate`, `needs_manual_grouping` -> `validated_warning`
- `unsupported_type`, `missing_source` -> `validated_warning` with blocking flags

## Transition Table

| From | Event | To | Notes |
|---|---|---|---|
| `submitted` | `validate` success/no warnings | `validated_ready` | Automatic when `auto_validate=true` |
| `submitted` | `validate` success/with warnings | `validated_warning` | Warning payload required |
| `submitted` | `defer` | `deferred` | Operator action |
| `submitted` | `reject` | `rejected` | Operator action |
| `validated_ready` | `group:create_new` | `grouped_new` | Creates working group |
| `validated_ready` | `group:attach_existing` | `grouped_existing` | Attaches to existing group |
| `validated_ready` | `defer` | `deferred` | Operator action |
| `validated_ready` | `reject` | `rejected` | Operator action |
| `validated_warning` | `revalidate` clears warnings | `validated_ready` | Revalidation path |
| `validated_warning` | `group:create_new` override | `grouped_new` | Requires explicit override flag |
| `validated_warning` | `group:attach_existing` override | `grouped_existing` | Requires explicit override flag |
| `validated_warning` | `defer` | `deferred` | Operator action |
| `validated_warning` | `reject` | `rejected` | Operator action |
| `deferred` | `reopen` | `submitted` | Returns to intake processing |
| `deferred` | `validate` | `validated_ready` or `validated_warning` | Optional direct revalidation |
| `rejected` | `reopen` | `submitted` | Explicit operator-only recovery |

Terminal behavior:

- `grouped_new` and `grouped_existing` are terminal for intake flow.
- any post-grouping operations are delegated to working-group workflows.

## Required Metadata By State

All states:

- `item_id`
- `source_type`
- `source_path_canonical`
- `created_at`
- `updated_at`

Validation states:

- `validation_state`
- `warnings_json`
- `validated_at`

Grouped states:

- `working_group_id`
- `grouped_at`
- `group_action` (`create_new` or `attach_existing`)

Rejected/deferred states:

- `decision_reason`
- `decision_actor`
- `decision_at`

## API Behavior Requirements

Required endpoint behavior consistency:

- transition attempts must be idempotent where practical
- invalid transitions must return explicit `invalid_transition` errors
- warning overrides must require explicit payload fields
- grouped states must reject further grouping attempts

Suggested error codes:

- `invalid_transition`
- `invalid_override`
- `item_not_found`
- `working_group_not_found`
- `validation_required`

## Operator UX Requirements

HA/UI surfaces must show:

- current state chip
- warning count and warning details for `validated_warning`
- clear action set by state
- explicit confirmation on override grouping from warning state

Action availability by state:

- `submitted`: validate, defer, reject
- `validated_ready`: create group, attach existing, defer, reject
- `validated_warning`: revalidate, override create/attach, defer, reject
- `deferred`: reopen, validate
- `rejected`: reopen
- grouped states: open working group

## Acceptance Checklist (Issue #1079)

- states are fully enumerated and scoped to Phase 5 intake
- transition rules and invalid transition behavior are explicit
- required metadata by state is explicit
- sidecar/API and HA/UI behavior expectations are explicit

## Related Docs

- `docs/features/model_catalog/intake-inbox-design.md`
- `docs/features/model_catalog/import-flow-diagrams.md`
- `docs/features/model_catalog/phase-1.5-intake-implementation-breakdown.md`
- `docs/features/model_catalog/working-file-spec.md`
- `docs/features/model_catalog/phase-delivery-and-validation.md`
