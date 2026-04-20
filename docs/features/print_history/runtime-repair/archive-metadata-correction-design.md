# Archive Metadata Correction Design (Issue #953)

## Purpose

Define a design for correcting archive metadata that is more sensitive than the existing popup edit flow, but does not require the full replacement-archive restore workflow.

This issue is not a request to turn print history into a generic archive-admin console.

It is specifically about a safe operator path for correcting archive-core metadata when one or more of these are true:

- the field is not available through Bambuddy's normal `PATCH /archives/{id}` contract
- the field affects derived runtime or historical placement behavior
- the change needs stronger warnings, preview, and auditability than the normal popup edit slice

## Recommendation

### Final recommendation

Use a two-phase rollout.

Phase 1:

- ship `Correct Metadata` as its own button inside `Advanced Actions`
- keep it separate from `Repair Archive`

Phase 2:

- merge the same flow into the broader `Repair Archive` workflow as a first-class branch
- keep the sidecar contract and workflow semantics stable so the Phase 2 change is primarily a UX consolidation, not a backend rewrite

### Why this phased split is the right fit

- it gets the simpler, higher-confidence metadata-correction flow shipped sooner
- it avoids blocking issue `#953` on the larger repair-hub UX
- it preserves the cleaner long-term information architecture where high-risk correction workflows start from one repair-family entry point
- it prevents the first implementation from bloating the normal popup edit surface

### Phase 1 UX position

Phase 1 should expose:

- archive popup
- `Advanced Actions`
- `Correct Metadata`

This should sit alongside, not inside, `Repair Archive` for the first delivery.

### Phase 2 UX position

Phase 2 should expose:

- archive popup
- `Advanced Actions`
- `Repair Archive`
- chooser with:
  - `Correct Metadata`
  - `Repair From Replacement 3MF`

In Phase 2, the standalone `Correct Metadata` button should be retired once the shared repair entry point is in place.

## Current Boundary

The repository already has three different mutation classes.

### 1. Normal popup edit

Current popup edit is appropriate for low-risk, API-native fields such as:

- `print_name`
- `tags`
- `notes`
- `project_id`
- standalone `status`
- standalone `failure_reason`

This path should remain the default for simple operator edits.

### 2. Runtime repair

The runtime-repair sidecar already supports explicit correction of:

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`

This is already the right write boundary for canonical timing correction because those fields are not just descriptive metadata. They change archive ordering, stats placement, timing accuracy, and other downstream behavior.

### 3. Restore from replacement archive

The restore workflow is for cases where the archived file-backed record itself is incomplete, wrong, or must be merged with a replacement archive.

That workflow is too heavy for issue `#953` when the operator only needs to correct metadata on one existing archive row.

## Design Decision

Issue `#953` should introduce a new single-archive `metadata correction` workflow family that sits between normal popup edit and full restore.

Short version:

- keep normal popup edit for everyday API-native edits
- use a sidecar-backed advanced correction flow for canonical runtime and other high-risk archive-core fields
- keep replacement-restore for file-backed repair cases

Do not collapse all three into one vague editor.

## Scope Recommendation

### V1 in scope

The first phase should stay narrow and solve the highest-value problem: canonical runtime correction for an existing archive.

Recommended V1 editable fields:

- `created_at`
- `started_at`
- `completed_at`
- optional bundled `status`
- optional bundled `failure_reason`
- operator-required `reason` or `audit_note`

This directly addresses the current gap where the archive row exists but the historical timing is wrong or incomplete.

### V2 candidate scope

After the warning, preview, and audit model is proven, the same workflow can optionally expand to selected user-metadata fields that need stronger audit than the normal popup edit path.

Possible V2 fields:

- `quantity`
- `external_url`
- `cost`

These should be deferred until overwrite policy is clear, especially for `cost`, because manual re-enrich and other enrichment flows may also touch that field.

### Out of scope

These should not be edited through metadata correction:

- `file_path`
- `thumbnail_path`
- `source_3mf_path`
- `content_hash`
- `print_time_seconds`
- parser-derived slicer metadata such as `layer_height`, `total_layers`, `designer`, `filament_used_grams`, and similar file-backed fields

Those values either belong to the archived file payload or are parser-derived and should be corrected through replacement-restore, rescan, or re-enrich workflows instead.

## Why This Should Use The Sidecar

Even though some fields are already writable through the Bambuddy API, issue `#953` should still be designed around a sidecar-backed correction boundary for the advanced flow.

Reasons:

- one request can validate the full field set before anything mutates
- one dry-run can explain derived impact before apply
- one write boundary can append a portable audit note and return a structured diff
- one transaction avoids a split between direct `PATCH` edits and direct SQLite runtime writes

Recommended rule:

- simple popup edit stays on the existing Bambuddy API path
- advanced metadata correction uses the sidecar whenever any sidecar-only field is present
- if the advanced correction request includes both API-native and sidecar-only fields, the sidecar should own the whole mutation as one transaction

## Proposed Sidecar Extension

## Endpoint shape

Add a dedicated endpoint instead of overloading `POST /admin/archive-runtime-repair` with unrelated semantics.

Recommended endpoint:

- `POST /admin/archive-metadata-correction`

Keep the same `dry_run` pattern used by runtime repair and restore.

### Why not overload runtime repair

Runtime repair today is intentionally narrow and timing-focused.

Metadata correction needs extra concepts:

- field allow-list by correction mode
- derived-impact preview
- optimistic concurrency guard
- correction-category warnings
- richer audit payload

That is a different contract, even if V1 only exposes runtime fields.

### Recommended request shape

```json
{
  "archive_id": 263,
  "expected_archive_revision": "sha256:...",
  "fields": {
    "created_at": "2026-04-02T19:43:19-04:00",
    "started_at": "2026-04-02T19:43:19-04:00",
    "completed_at": "2026-04-02T22:11:42-04:00",
    "status": "completed",
    "failure_reason": null
  },
  "reason": "Historical SD evidence confirmed original print timing",
  "trigger_source": "home_assistant_advanced_action",
  "dry_run": true
}
```

### Required request fields

- `archive_id`
- `fields`
- `reason`
- `dry_run`

### Recommended optional request fields

- `expected_archive_revision`
- `trigger_source`
- `operator_id` or `actor_label` when available
- `request_id` for correlation with local audit rows

### Response shape

The sidecar response should not just echo before/after fields.

Recommended response sections:

- `before`
- `after`
- `updated_fields`
- `warnings`
- `derived_impacts`
- `audit_preview` or `audit_id`

Example `derived_impacts` summary:

```json
{
  "duration_source": "timestamps",
  "actual_time_seconds_before": 9533,
  "actual_time_seconds_after": 8923,
  "created_at_day_before": "2026-04-10",
  "created_at_day_after": "2026-04-02",
  "archive_ordering_impacted": true,
  "heatmap_day_impacted": true,
  "time_accuracy_impacted": true,
  "reenrich_recommended": false
}
```

## Sidecar behavior

The sidecar should:

- validate allowed fields for the requested correction mode
- load the current archive row
- reject stale edits when `expected_archive_revision` no longer matches
- compute a before/after diff
- compute derived-impact preview
- append a compact portable correction note block to Bambuddy `notes`
- return structured output for HA to cache and display

The sidecar should not:

- own popup wording or card layout
- re-enrich automatically by default
- modify parser-backed file metadata
- bypass the audit contract for direct SQLite updates

## Derived Field Policy

Issue `#953` needs an explicit contract for what should be edited directly, what should be recalculated, and what should stay preserved.

### Directly writable canonical fields

These are the fields the operator is intentionally correcting:

- `created_at`
- `started_at`
- `completed_at`
- `status`
- `failure_reason`

### Recalculated or re-evaluated from canonical fields

These should not be edited directly in the correction request. They should be allowed to follow from the corrected canonical fields or be recomputed on read.

- `actual_time_seconds`
- duration shown in popup and browser cards
- time-accuracy views based on runtime duration vs slicer estimate
- archive ordering and date-bucket placement that depend on `created_at`
- duplicate-sequence ordering that depends on `created_at`
- local heatmap and day drill-in placement that depend on archive date

### Preserved parser-backed or file-backed fields

These should remain unchanged in V1 metadata correction:

- `print_time_seconds`
- `file_path`
- `thumbnail_path`
- `source_3mf_path`
- `content_hash`
- parser-derived slicer/material metadata

Reason:

- `print_time_seconds` is the slicer estimate and should stay tied to the archived file
- the advanced correction flow is not a file-repair workflow

### Re-enrich policy

Default rule for V1:

- timing-only corrections do not auto-run re-enrich

Reason:

- re-enrich is not required to make the canonical runtime correction valid
- automatic re-enrich risks surprising the operator with extra mutations unrelated to the requested timing fix

Recommended follow-up behavior:

- always refresh archive detail and browser cache after apply
- if a correction changes fields that affect local summaries or popup timeline placement, refresh those local read models immediately
- show `Run Re-Enrich` only as an explicit optional follow-up when the archive is already known to have incomplete enrichment

## Warning And Review UX

This flow should be designed around dry-run preview first.

### Entry point

Phase 1 entry point:

- archive popup
- `Advanced Actions`
- `Correct Metadata`

Phase 2 entry point:

- archive popup
- `Advanced Actions`
- `Repair Archive`
- `Correct Metadata`

### Review stages

1. select or confirm the target archive
2. show field editor only for the supported correction set
3. require a reason
4. run dry-run preview
5. show impacted surfaces and warnings
6. require explicit apply confirmation

### Required warning content

Before apply, the UI should tell the operator:

- this changes canonical archive history, not just popup display text
- changing `created_at` can move the archive to a different day in list views and stats
- changing `started_at` or `completed_at` changes derived duration and time-accuracy behavior
- parser-derived file metadata will not be updated by this action

### Confirmation model

Use a stronger confirmation than the standard popup save button.

Recommended apply guard:

- dry-run required first
- then a dedicated confirmation step such as `Apply Metadata Correction`
- if `created_at` changes day or month boundaries, show an extra impact warning row in the preview

## Audit Trail Recommendation

Yes, issue `#953` should have a durable audit trail in the local Variant 3 store.

It should not rely only on a note appended to Bambuddy.

### Why local audit is needed

- correction history needs to be queryable in HA even if Bambuddy notes become noisy
- popup and timeline views need structured event history, not just free-text notes
- local workflow records can store full before/after diff payloads without bloating archive-core fields

### Recommended persistence model

Use two layers:

#### 1. Portable Bambuddy note block

Append a compact structured note block for archive portability.

Suggested marker:

- `[ARCHIVE_METADATA_CORRECTION_V1]`

Contents should stay compact:

- correction timestamp
- actor or trigger source
- reason
- corrected field names
- request ID or audit ID

#### 2. Full local audit table in Variant 3 store

Add a dedicated local table, for example:

- `archive_metadata_correction_audit`

Recommended columns:

- `correction_id`
- `archive_id`
- `request_id`
- `requested_at`
- `applied_at`
- `status`
- `actor_label`
- `trigger_source`
- `reason`
- `before_json`
- `after_json`
- `derived_impacts_json`
- `warnings_json`
- `sidecar_response_json`

This follows the same general philosophy as the existing local timeline and review-state model: detailed workflow history belongs in Variant 3, not in Layer 1 archive projection.

## HA Visibility For Audit Trail

Yes, the audit trail should be accessible from HA.

Recommended surfaces:

- compact summary inside the advanced correction flow after apply
- `View Correction History` action from `Advanced Actions`
- popup timeline event entry for applied corrections

Recommended timeline extension:

- add a new local timeline event type such as `metadata_corrected`

This should render like other local workflow events:

- one concise event in the popup timeline
- full detail only when the operator opens correction history or metadata inspection

That keeps the popup readable while preserving traceability.

## Relationship To The Existing Repair Workflow

The best long-term design is a repair-family fork, but Phase 1 should not wait for that larger consolidation.

### Phase 1 relationship

In Phase 1, `Correct Metadata` stays separate from `Repair Archive`.

Why this is the right temporary split:

- metadata correction is the simpler and more constrained workflow
- it does not require source/target pairing, upload state, verify/remove-original logic, or replacement lineage handling
- the UI can ship faster without first inventing a shared repair launcher

### Phase 2 relationship

In Phase 2, `Correct Metadata` becomes a branch inside `Repair Archive`.

Recommended operator fork:

- `Correct Metadata` when the archive row is correct but metadata needs repair
- `Repair From Replacement 3MF` when the archived file or parser-backed metadata is wrong or incomplete

### Why this is better than forcing full repair

- avoids unnecessary upload and new-archive creation
- avoids creating synthetic lineage when the file itself is already correct
- keeps the operator in the right mental model for single-row correction vs source-target merge

### Why this is better than keeping metadata correction separate forever

- both are high-risk admin flows
- both need warnings, dry-run, and audit history
- one repair-family surface is easier to explain than several unrelated advanced mutation buttons

## Phased Delivery Recommendation

## Phase 1: Standalone `Correct Metadata` In Advanced Actions

### Outcome

Operator can launch a single-archive metadata-correction workflow directly from `Advanced Actions` without entering the broader repair workflow.

### UX shape

- add `Correct Metadata` to `custom:print-history-archive-actions-card`
- keep existing `Repair Archive` behavior unchanged
- open a dedicated metadata-correction popup or child popup
- do not add any metadata-correction controls to the normal popup edit section

### Backend scope

- add the sidecar request and response contract for `POST /admin/archive-metadata-correction`
- add HA service handlers for preview and apply
- add allowed V1 field validation
- add derived-impact preview model
- add local audit-table schema or at minimum reserve the storage contract if persistence is deferred by one slice

### Frontend scope

- editor for the V1 field set
- required reason field
- dry-run preview summary
- guarded apply action
- post-apply refresh of archive detail and browser cache

### Rules

- no source/target pairing concepts
- no upload concepts
- no verify/remove-original concepts
- no automatic migration into the restore workflow yet

### Acceptance criteria

- operator can open `Correct Metadata` directly from `Advanced Actions`
- operator can preview timing corrections before apply
- operator sees warnings for archive-history and derived-duration impacts
- apply returns a structured result and refreshes visible archive state
- the workflow contract is shaped so it can later be launched from inside `Repair Archive` without breaking the backend API

## Phase 2: Merge Into `Repair Archive`

### Outcome

`Correct Metadata` becomes a branch within the shared repair-family workflow, and the standalone Phase 1 button is removed.

### UX shape

- `Repair Archive` becomes the shared entry point
- opening `Repair Archive` shows a chooser between:
  - `Correct Metadata`
  - `Repair From Replacement 3MF`
- selecting `Correct Metadata` launches the same correction editor and preview flow from Phase 1

### Migration principle

Phase 2 should be mostly a launcher consolidation.

Do not change without clear need:

- sidecar request shape
- correction field policy
- warning model
- audit model
- apply semantics

### Backend scope

- add a repair-family workflow shell or chooser state in HA
- reuse the existing Phase 1 metadata-correction service handlers behind the new repair launcher
- keep restore and metadata-correction state distinct even if they share the same entry point

### Frontend scope

- replace the standalone `Correct Metadata` action with the shared `Repair Archive` chooser
- ensure the metadata branch stays visually simpler than the replacement-repair branch
- preserve deep-linking or internal flow state so the selected branch remains obvious throughout the session

### Acceptance criteria

- `Repair Archive` is the only repair-family launcher in `Advanced Actions`
- metadata correction still works without any source/target or upload requirements
- replacement repair still works without inheriting metadata-only assumptions
- moving from the standalone button to the repair chooser does not require any sidecar API rewrite

## Phase 3: Local Audit History And Timeline Integration

Deliver:

- local audit persistence
- `metadata_corrected` popup timeline event
- `View Correction History` detail surface

Goal:

- traceability and operator confidence after corrections become routine

## Phase 4: Optional V2 field expansion

Deliver only after the Phase 1 and Phase 2 structure proves stable:

- selected non-runtime advanced metadata fields such as `quantity`, `external_url`, or `cost`
- explicit overwrite policy for fields that may also be touched by enrichment

Goal:

- expand scope without weakening the safety model

## Summary

Issue `#953` should be treated as a sidecar-backed advanced correction workflow for one existing archive, not as a wider popup edit form and not as a forced replacement-restore flow.

Recommended final shape:

- Phase 1 ships a sidecar-backed standalone `Correct Metadata` advanced action with dry-run, warnings, and audit
- Phase 2 folds that same flow into `Repair Archive` as a repair-family branch
- simple edits remain in the existing popup edit area
- full correction history lives in the local Variant 3 SQLite store
- HA exposes that history through advanced actions and popup timeline integration