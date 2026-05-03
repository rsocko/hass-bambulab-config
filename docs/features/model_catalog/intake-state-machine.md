# Intake Flow States And Transitions

> Status: Canonical state machine with wizard-first UX direction
> Issue: #1079
> Last updated: 2026-05-03
> Scope: Canonical state machine for Phase 5 intake-to-working workflow.

## Purpose

Define the state model that governs intake items from submission through validation and conversion to Working/Curated outcomes. This contract is used by sidecar API endpoints, queue processing, and HA operator surfaces.

For a visual walkthrough of the same flow, plus a state/action cheat sheet and a separate current-implementation flow, see [import-flow-diagrams.md](c:\dev\hass-bambulab-config\docs\features\model_catalog\import-flow-diagrams.md).

## Scope Boundary

This state machine covers intake and working handoff only.

Included:

- intake submission
- pre-commit validation and dedupe review
- conversion into new or existing Working/Curated targets
- terminal outcome recording in Job History

Excluded (later phases):

- publish-to-curated actions
- lineage/supersession decisions
- publish-time preview promotion

## Lifecycle Overview: Queue Lifecycle vs Job History

Intake items progress through two distinct phases:

### Queue Lifecycle (System Layer)
Queue states remain part of the system lifecycle and compatibility layer.

Inbox review is demoted from the primary operator path for now.

- `submitted` — item just arrived, not yet validated
- `validated_ready` — passed validation cleanly, ready for operator action
- `validated_warning` — passed validation with caveats, operator decision required
- `deferred` — optional parked state (non-primary UX)

### Terminal States (Job History)
Items in Job History are **complete workflows** where a terminal action has been taken.

- `grouped_new` — item created a new working group (terminal for intake)
- `grouped_existing` — item attached to existing working group (terminal for intake)
- `published_to_catalog` — item published directly to local curated catalog (terminal, bypass working)
- `rejected` — operator rejected as noise/invalid (terminal, discarded)

After an item reaches a terminal state, the intake workflow is **complete for that item**. Terminal records should be visible in Job History regardless of whether the execution was direct from wizard or processed through queued/background path.

### Primary States

**Active Queue states:**

`submitted`

- item accepted by sidecar intake endpoint
- canonical path normalization has run
- no validation result yet (unless auto-validate enabled)
- **status**: in queue, awaiting operator review

`validated_ready`

- supported type
- source is readable
- no blocking duplicate condition
- ready for grouping or direct publish actions
- **status**: in queue, actionable

`validated_warning`

- validation succeeded with warning conditions
- examples: duplicate candidates, name collisions, grouping ambiguity
- operator decision required before grouping
- **status**: in queue, requires deliberate operator choice before proceeding

`deferred`

- intentionally parked by operator for later review
- item remains visible in active queue
- can be reopened to `submitted` or `validated_ready` for revalidation
- **status**: in queue, parked

**Terminal states (Job History):**

`grouped_new`

- item converted to a newly created working group
- immutable linkage to resulting `working_group_id`
- workflow **complete** for this intake item
- further intake actions blocked; operator may view details or reopen via admin override

`grouped_existing`

- item attached to an existing working group
- immutable linkage to resulting `working_group_id`
- workflow **complete** for this intake item
- further intake actions blocked; operator may view details or reopen via admin override

`published_to_catalog`

- item published directly to local curated catalog (skips working group stage)
- immutable linkage to resulting `local_model_id`
- workflow **complete** for this intake item
- further intake actions blocked; operator may view details or reopen via admin override

`rejected`

- operator rejected item as noise/duplicate/invalid
- kept for audit history; not eligible for grouping
- workflow **complete** for this intake item
- operator may view details; explicit admin override required to reopen

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

### Queue Transitions (Before Terminal State)

| From | Event | To | Notes |
|---|---|---|---|
| `submitted` | `validate` success/no warnings | `validated_ready` | Automatic when `auto_validate=true` |
| `submitted` | `validate` success/with warnings | `validated_warning` | Warning payload required |
| `submitted` | `defer` | `deferred` | Optional backend/admin path |
| `submitted` | `reject` | `rejected` | Optional backend/admin path |
| `validated_ready` | `group:create_new` | `grouped_new` | **→ TERMINAL** Creates working group |
| `validated_ready` | `group:attach_existing` | `grouped_existing` | **→ TERMINAL** Attaches to existing group |
| `validated_ready` | `publish_to_catalog` | `published_to_catalog` | **→ TERMINAL** Direct publish bypass working |
| `validated_ready` | `defer` | `deferred` | Optional backend/admin path |
| `validated_ready` | `reject` | `rejected` | Optional backend/admin path |
| `validated_warning` | `validate_override` (revalidate) | `validated_ready` | Clears warnings after review |
| `validated_warning` | `group:create_new` override | `grouped_new` | **→ TERMINAL** Requires explicit override flag |
| `validated_warning` | `group:attach_existing` override | `grouped_existing` | **→ TERMINAL** Requires explicit override flag |
| `validated_warning` | `defer` | `deferred` | Optional backend/admin path |
| `validated_warning` | `reject` | `rejected` | Optional backend/admin path |
| `deferred` | `revalidate` | `validated_ready` or `validated_warning` | Returns to validation |
| `deferred` | `reject` | `rejected` | Optional backend/admin path |

### Terminal State Recovery (Admin Override Only)

| From | Event | To | Notes | Requires |
|---|---|---|---|---|
| `grouped_new` | `admin:reopen` | `validated_ready` | Reopen for reconsideration | Admin role + explicit confirmation |
| `grouped_existing` | `admin:reopen` | `validated_ready` | Reopen for reconsideration | Admin role + explicit confirmation |
| `published_to_catalog` | `admin:reopen` | `validated_ready` | Reopen for reconsideration | Admin role + explicit confirmation |
| `rejected` | `admin:reopen` | `submitted` | Discard previous rejection | Admin role + explicit confirmation |

### Terminal State Restrictions

Once an item reaches **any terminal state** (`grouped_new`, `grouped_existing`, `published_to_catalog`, `rejected`):

- ✓ **Allowed**: View item details, inspect results, query audit history
- ✓ **Allowed**: Admin-only reopen to Active Queue states (requires explicit confirmation)
- ✓ **Allowed**: Delete item from Job History log (soft archive or hard delete with confirmation)
- ✗ **Blocked**: Validate, group, publish, defer, or any other intake workflow action
- ✗ **Returns**: HTTP 409 Conflict with reason code if attempted

Reason codes for blocked actions:

- `item_terminal_published_to_catalog` — item already published
- `item_terminal_grouped_new` — item already created group
- `item_terminal_grouped_existing` — item already attached to group
- `item_terminal_rejected` — item rejected; reopen required

## Required Metadata By State

All states:

- `item_id`
- `source_type`
- `source_path_canonical`
- `created_at`
- `updated_at`
- `is_terminal` — boolean flag indicating whether item is in terminal state
- `allowed_actions` — array of action codes valid for this state

Validation states (Active Queue):

- `validation_state`
- `warnings_json`
- `validated_at`

Terminal states (Job History):

- `terminal_action` — code indicating what terminal action completed (e.g., `grouped_new`, `published_to_catalog`, `rejected`)
- `terminal_result_id` — ID of resulting entity (`working_group_id`, `local_model_id`, etc.)
- `terminal_at` — timestamp of completion
- `terminal_actor` — user/service that performed terminal action

## Action Eligibility By State

This table defines which operations are legal in each state and what the API should return if the operation is attempted from an invalid state.

| State | Validate | Group New | Group Existing | Publish Catalog | Defer | Reject | Reopen | Delete History |
|---|---|---|---|---|---|---|---|---|
| `submitted` | ✓ allowed | ✗ not ready | ✗ not ready | ✗ not ready | ✓ allowed | ✓ allowed | N/A | ✓ allowed |
| `validated_ready` | ✓ allowed | ✓ allowed | ✓ allowed | ✓ allowed | ✓ allowed | ✓ allowed | N/A | ✓ allowed |
| `validated_warning` | ✓ allowed | ✓ override | ✓ override | ✗ review warnings | ✓ allowed | ✓ allowed | N/A | ✓ allowed |
| `deferred` | ✓ allowed | ✗ not ready | ✗ not ready | ✗ not ready | N/A | ✓ allowed | N/A | ✓ allowed |
| `grouped_new` | ✗ terminal | ✗ terminal | ✗ terminal | ✗ terminal | N/A | N/A | ✓ admin only | ✓ allowed |
| `grouped_existing` | ✗ terminal | ✗ terminal | ✗ terminal | ✗ terminal | N/A | N/A | ✓ admin only | ✓ allowed |
| `published_to_catalog` | ✗ terminal | ✗ terminal | ✗ terminal | ✗ terminal | N/A | N/A | ✓ admin only | ✓ allowed |
| `rejected` | ✗ terminal | ✗ terminal | ✗ terminal | ✗ terminal | N/A | N/A | ✓ admin only | ✓ allowed |

Wizard-first UX policy:

- The primary operator flow should use Validate before Commit in wizard.
- Defer/Reject are not required actions in primary wizard UX for this iteration.
- Defer/Reject may remain available in backend/admin tooling and compatibility surfaces.

### Action Eligibility Rules

**Validate**
- Valid in: `submitted`, `validated_ready`, `validated_warning`, `deferred`
- Returns: 200 OK with new state (`validated_ready` or `validated_warning`)
- Invalid: Returns 400 with reason if source is not resolvable

**Group New (Create Working Group)**
- Valid in: `validated_ready` only
- Valid in: `validated_warning` with `override: true` flag
- Returns: 200 OK, sets state to `grouped_new`, records `working_group_id`
- Invalid in: `submitted`, `deferred`, or terminal states → 409 Conflict with reason code

**Group Existing (Attach to Existing Group)**
- Valid in: `validated_ready` only
- Valid in: `validated_warning` with `override: true` flag
- Returns: 200 OK, sets state to `grouped_existing`, records `working_group_id`
- Invalid in: `submitted`, `deferred`, or terminal states → 409 Conflict with reason code

**Publish to Catalog (Direct Publish, Skip Working)**
- Valid in: `validated_ready` only
- Returns: 200 OK, sets state to `published_to_catalog`, records `local_model_id`
- Invalid in: `validated_warning`, `submitted`, `deferred`, or terminal states → 409 Conflict with reason code

**Defer (Park for Later)**
- Valid in: `submitted`, `validated_ready`, `validated_warning`
- Returns: 200 OK, sets state to `deferred`
- Optional: `decision_reason` field for operator notes
- Invalid in: `deferred` (already deferred), `rejected`, or terminal states → 409 Conflict

**Reject (Discard)**
- Valid in: `submitted`, `validated_ready`, `validated_warning`, `deferred`
- Returns: 200 OK, sets state to `rejected` (terminal)
- Optional: `decision_reason` field for audit trail
- Invalid in: already `rejected` or terminal states → 409 Conflict

**Reopen (Admin Override)**
- Valid in: Terminal states (`grouped_new`, `grouped_existing`, `published_to_catalog`, `rejected`) **only**
- Requires: `admin_role` flag and `confirmation_token`
- Returns: 200 OK, returns item to `submitted` state
- Clears: Terminal result metadata; item reenters Active Queue workflow
- Invalid in: Active Queue states → 400 Bad Request (not applicable)

**Delete History (Soft Archive or Hard Delete)**
- Valid in: All states, but primarily for terminal items
- Soft archive mode (default): mark as archived, keep in database for audit
- Hard delete mode: requires `hard_delete: true` AND `confirmation_token`
- Returns: 200 OK or 202 Accepted for async hard delete
- Invalid in: Active processing (e.g., uploading) → 409 Conflict

## API Behavior Requirements

Required endpoint behavior consistency:

- **Idempotency**: Transition attempts must be idempotent where practical (e.g., defer twice returns 200 OK both times)
- **State Validation**: Invalid transitions must return explicit error codes (see below)
- **Warning Overrides**: Grouping from `validated_warning` must require explicit `override: true` flag
- **Terminal Blocks**: Terminal states must reject all intake workflow operations with 409 Conflict
- **Confirmation Tokens**: Admin override operations must require a signed/timestamped confirmation token

Error codes returned by API:

- `invalid_transition` — state transition not allowed for current state
- `item_terminal_*` — item is terminal (use reason code suffix: `_grouped_new`, `_grouped_existing`, `_published_to_catalog`, `_rejected`)
- `item_not_found` — upload_id or item_id not found
- `working_group_not_found` — referenced working_group_id does not exist
- `validation_required` — operation requires valid validation result first
- `override_required` — operation requires explicit override flag (e.g., grouping from warning state)
- `admin_required` — operation requires admin role
- `confirmation_token_invalid` — confirmation token missing, expired, or invalid

## Operator UX Requirements

HA/UI surfaces must distinguish between queue lifecycle data and Job History, while using wizard as the primary intake path.

### Wizard Surface (Primary)

Wizard must provide:

- Source step
- Organize step (for both browser and server modes)
- Validate step before commit
- Commit step
- destination-aware issue correction and override handling

### Queue Surface (Demoted)

Queue/inbox review UI is optional or hidden for routine operation in this phase.

UX requirements for Active Queue:

- Display current state chip with distinct colors for each state
- Show warning count and inline warning details for `validated_warning`
- Display clear, state-specific action set (render only valid actions from the eligibility table above)
- For `validated_warning`, show prominent "requires review" indicator on group actions
- Show state filter/tab (Submitted | Ready | Warning | Deferred)
- Show batch action support with eligibility precheck (e.g., "2 of 5 items eligible for group action")
- Support inline defer/reject with optional operator notes

### Job History Surface (Primary Post-Execution)
Shows items that have reached terminal states and are no longer active work (`grouped_new`, `grouped_existing`, `published_to_catalog`, `rejected`).

UX requirements for Job History:

- Display terminal action badge (e.g., "Published", "Grouped", "Rejected")
- Show result entity link (e.g., "working_group_id=42" or "local_model_id=gridfinity-bin--a1b2c3d4")
- Display immutable terminal state; no workflow action buttons
- Provide "View Details" link to resulting entity or result metadata
- Provide "Delete Log Row" button for operators to archive item (soft or hard delete)
- Provide terminal records for wizard-direct and queue-processed executions in one unified history list
- Show terminal completion timestamp
- Show actor (who performed terminal action) if available

### Action Availability by State (Eligibility Matrix)

Queue/Compatibility Actions:

- `submitted`: Validate | Defer | Reject | Delete
- `validated_ready`: Validate | Group New | Group Existing | Publish Catalog | Defer | Reject | Delete
- `validated_warning`: Validate | Group New (override) | Group Existing (override) | Defer | Reject | Delete
- `deferred`: Validate | Reject | Delete

Job History Actions:

- `grouped_new`: View Details | Delete Log | Admin Reopen
- `grouped_existing`: View Details | Delete Log | Admin Reopen
- `published_to_catalog`: View Details | Delete Log | Admin Reopen
- `rejected`: View Details | Delete Log | Admin Reopen

## Acceptance Checklist (Issue #1079)

- states are fully enumerated and scoped to Phase 5 intake
- transition rules and invalid transition behavior are explicit
- required metadata by state is explicit
- sidecar/API and HA/UI behavior expectations are explicit
- wizard-first validation-before-commit requirement is explicit
- Job History as unified outcome surface is explicit

## Related Docs

- `docs/features/model_catalog/intake-inbox-design.md`
- `docs/features/model_catalog/import-flow-diagrams.md`
- `docs/features/model_catalog/phase-1.5-intake-implementation-breakdown.md`
- `docs/features/model_catalog/working-file-spec.md`
- `docs/features/model_catalog/phase-delivery-and-validation.md`
