# Archive Restore Workflow Home Assistant UX Design

## Purpose

Define how Home Assistant should expose the sidecar-backed archive `restore_from` workflow to an operator.

This document covers:

- where restore actions should live in the existing print-history UX
- which restore steps should and should not be exposed in each phase
- the proposed Home Assistant-side contract for planning, applying, verifying, and optionally removing the original archive
- guardrails for a workflow that is materially higher risk than normal archive edits

This document is intentionally separate from the sidecar API draft and the runbook.

- [archive-runtime-sidecar-api-and-compose.md](archive-runtime-sidecar-api-and-compose.md) defines the sidecar HTTP surface
- [archive-runtime-restore-from-runbook.md](archive-runtime-restore-from-runbook.md) defines the current operator-run sequence
- this document defines the Home Assistant UX and workflow contract that can sit on top of those pieces

## Current Status

### Designed today

The repository already contemplates Home Assistant as the UX plane for archive mutation workflows.

Existing evidence:

- [archive-runtime-ha-contract.md](archive-runtime-ha-contract.md) defines a Home Assistant contract for direct runtime repair of one archive
- [archive-detail-popup-design.md](../ui-media/archive-detail-popup-design.md) reserves future archive-action slots in the popup instead of on the archive card face
- [advanced-features-design.md](../planning/advanced-features-design.md) already treats repair and archive-admin flows as advanced follow-on work rather than default browsing behavior

### Not designed or implemented today

The full source-to-target restore workflow is not currently designed as a Home Assistant UI feature.

Current state:

- the sidecar supports `POST /admin/archive-restore-from` and `POST /admin/archive-restore-verify`
- the repo includes a manual runbook and example pair analysis
- there is no Home Assistant package implementation yet for restore planning, apply, verification, or original removal
- there is no currently shipped Lovelace action, script, or service under `homeassistant/` for the restore workflow

That means the current restore flow is sidecar-first and operator-run, with Home Assistant still needing an explicit UX and service contract.

This document adds the missing HA-side design for two related gaps:

- browser-initiated replacement archive creation from an uploaded sliced `.gcode.3mf`
- finalization behavior when restore has merged metadata but re-enrich cannot be triggered automatically through the runtime-repair sidecar

## Why A Separate HA Workflow Is Worth Adding

Yes, it makes sense to add Home Assistant functionality for restore, but only as an advanced, explicitly guarded workflow.

Why it is worth adding:

- archive restore is an operator task that naturally starts from print history, not from a shell or raw HTTP client
- the print-history popup already provides a stable drilldown surface for per-archive actions
- the sequence is review-heavy and benefits from guided state, explicit warnings, and result summaries
- Home Assistant can refresh the browser state immediately after each step and keep the operator in context

Why it should not be a casual default action:

- restore mutates one archive using another archive as source
- later verification can authorize deletion of the original source archive
- the sidecar response payloads are richer and easier to misuse than simple `PATCH /archives/{id}` edits
- the workflow is fundamentally closer to archive administration than to normal browsing

## UX Goals

1. keep restore actions out of the default browsing flow
2. make dry-run review the normal first step, not an optional afterthought
3. keep the operator oriented around a specific source-target pair at all times
4. separate plan, apply, verify, and remove into visibly distinct states
5. prevent destructive cleanup until verification is clean
6. fit the workflow into the existing archive popup/action architecture rather than inventing a second navigation model

## Non-Goals

1. do not expose restore as a one-tap action on archive cards
2. do not rely on `input_text` helpers to store full restore diff payloads
3. do not make Home Assistant own merge policy logic; the sidecar remains the policy and write boundary
4. do not collapse restore and direct runtime repair into one vague operator button
5. do not permit source removal without a prior clean verification result

## Design Principles

### 1. Home Assistant is the trigger and review plane

Home Assistant should initiate the sidecar calls, render the workflow state, and refresh the print-history view.

Home Assistant should not reimplement:

- merge rules
- field policy decisions
- database writes
- source-removal safety rules

### 2. Restore belongs in advanced archive actions

This follows the guidance already established in [archive-runtime-ha-contract.md](archive-runtime-ha-contract.md): high-risk repair flows belong in advanced archive actions, not in the default browsing surface.

### 3. Review before mutation

The default happy path should be:

1. inspect candidate pair
2. run dry-run restore plan
3. inspect field actions and warnings
4. apply restore
5. verify
6. only then reveal remove-original

### 4. Use the popup as the stable entry point

The popup is already the repository's per-archive action surface. Restore should attach there rather than creating a parallel dashboard interaction model.

### 5. Prefer integration-backed transient state over helper abuse

The active print-history browser already keeps heavy payloads in the custom integration and frontend query path rather than in Home Assistant state attributes. Restore-plan results should follow the same philosophy.

Short version:

- small operator selections may live in helpers
- large restore response payloads should live in an integration-owned transient store or dedicated workflow entity model

## Recommended Placement In The Existing UI

## Entry point

Restore should be launched from the archive detail popup only.

Recommended affordance:

- an admin-only `Restore` or `Advanced Restore` action in the popup action area

Not recommended:

- inline buttons on every archive card
- restore actions in the main control strip
- restore actions in the default row click behavior

## Candidate model

Restore is a pair-based workflow, not a single-archive edit.

The popup action should therefore open a focused restore subflow with both:

- source archive
- target archive

The most common starting point is expected to be one of these:

- user opens the original fallback archive and chooses a replacement target
- user opens the recovered target archive and chooses the original source archive
- Home Assistant pre-populates the likely counterpart when lineage tags or notes already identify the pair

## Browser-Initiated Replacement Upload

The restore workflow needs an HA-native intake path for the case where the operator already has the correct replacement file on their desktop or phone.

This path is specifically for a replacement sliced `.gcode.3mf` or other file intended to become the canonical Bambuddy archive payload.

It is not the same as the source-project `.3mf` import flow documented in [source-3mf-import-design.md](../imports/source-3mf-import-design.md), which is intentionally scoped to image and limited metadata import.

### Recommended entry point

From the archive popup for the broken or superseded archive, expose an admin-only action:

- `Repair From Replacement 3MF`

That action should open a repair subflow with three stages before restore planning begins:

1. upload the replacement file to HA
2. inspect the staged file summary and confirm that it should become a new Bambuddy archive
3. create the replacement archive in Bambuddy and capture the returned `target_archive_id`

### Recommended upload flow

1. User opens the popup for the source archive.
2. User chooses `Repair From Replacement 3MF`.
3. Browser uploads the file to HA through a dedicated multipart endpoint.
4. HA validates the upload and creates a short-lived repair-upload session.
5. HA returns a summary showing filename, size, likely file kind, and any validation warnings.
6. User confirms `Create Replacement Archive`.
7. HA uploads the staged file to Bambuddy with `POST /api/v1/archives/upload?printer_id=...`.
8. HA records the newly created archive ID as the target archive and immediately seeds the restore pair.
9. The workflow transitions into the normal `plan -> apply -> verify -> finalize` flow.

### Why HA should own this handoff

- the operator is already in the archive popup
- the browser can upload directly to HA without exposing Bambuddy credentials
- HA can keep the staged upload session, created target archive ID, and restore pair selection in one place
- the sidecar should stay focused on merge and verification policy, not raw browser file intake

## Recommended UI Surfaces By Phase

### Phase 1

- popup action opens read-only restore review
- shows selected pair, lineage markers, and warnings
- no write action yet

### Phase 2

- popup action can request dry-run restore plan
- results render in a dedicated review section or child popup

### Phase 3

- apply action becomes available from the reviewed plan state

### Phase 4

- verify action becomes available after apply
- remove-original becomes visible only when verification is clean

### Phase 5

- optional admin maintenance view shows recent restore operations and unresolved pairs

## Proposed Home Assistant Contract

The contract below is the recommended Home Assistant-side layer on top of the existing sidecar endpoints.

## Architectural shape

### Near-term contract

Near term, the simplest viable implementation is:

- Home Assistant script layer
- dedicated HTTP multipart upload view for replacement-file intake
- `rest_command` calls to the sidecar
- custom integration or event-backed workflow state for transient results
- popup UI that reads workflow state and presents the next legal action

### Long-term contract

Long term, the cleaner final shape is:

- `bambuddy` custom integration owns the restore-workflow state machine
- Lovelace calls integration services instead of raw `rest_command`s
- the integration calls the sidecar and stores transient workflow results for the active pair

This design document defines the service and state contract so either implementation path can satisfy the same UX.

## Workflow identity

Each restore interaction should be keyed by a pair identity:

- `source_archive_id`
- `target_archive_id`

Recommended pair key format:

```text
restore:{source_archive_id}:{target_archive_id}
```

This gives the UI a stable way to refresh, compare, and clear transient results without confusing one candidate pair with another.

## Required Browser Upload Endpoint

The replacement-file intake cannot start as a normal script service because the browser needs to send a binary file.

Recommended endpoint:

```text
POST /api/bambuddy/print-history/archive-repair/replacement/discover
```

Recommended multipart fields:

- `source_archive_id`
- `printer_id`
- `file`

Recommended response summary:

- `upload_session_id`
- `source_archive_id`
- `filename`
- `size_bytes`
- `file_kind`
- `warnings`
- `ready_to_create_replacement`

The response does not need to fully parse the file like the source-project import design. It only needs to validate that the staged upload is plausible as a replacement archive input and hold it long enough for the operator to confirm creation.

## Proposed Home Assistant Services Or Scripts

These names define the recommended contract even if the first implementation uses scripts.

### 0. `bambuddy.create_archive_replacement_from_upload`

Purpose:

- take a previously staged browser upload session
- create a new Bambuddy archive through `POST /api/v1/archives/upload`
- capture the returned replacement archive ID
- initialize the restore workflow pair automatically

Inputs:

- `source_archive_id`
- `upload_session_id`
- `printer_id`
- optional `recovery_source`
- optional `run_reenrich`

Required behavior:

- reject expired or missing upload sessions
- reject creation if the staged upload failed validation
- call Bambuddy upload using HA-held credentials, not browser-held credentials
- store the returned `target_archive_id`
- set workflow state to `replacement_created`
- prefill the pair for subsequent plan/apply/verify actions
- refresh active archive detail and print-history browser state after success

### 1. `bambuddy.plan_archive_restore`

Purpose:

- request `POST /admin/archive-restore-from` with `dry_run: true`
- store the response as the current restore plan for the selected pair

Inputs:

- `source_archive_id`
- `target_archive_id`
- optional `field_groups`
- optional `exclude_tags`
- optional `include_tags`
- optional `overrides`
- optional `run_reenrich`

Required behavior:

- reject identical source and target IDs before calling the sidecar
- clear any stale apply/verify results for the pair
- store the dry-run response payload and timestamp
- refresh the active archive detail if the current popup is attached to one of the pair members

### 2. `bambuddy.apply_archive_restore`

Purpose:

- request `POST /admin/archive-restore-from` with `dry_run: false`
- record the apply result and transition the pair to `applied_pending_verify`

Inputs:

- same as `plan_archive_restore`
- optional `audit_note`

Required behavior:

- require a valid current pair selection
- strongly prefer that a dry-run plan already exists for the same pair before apply is allowed
- refresh print-history browser state after success
- persist `updated_fields`, warnings, and the apply timestamp

### 3. `bambuddy.verify_archive_restore`

Purpose:

- request `POST /admin/archive-restore-verify`
- evaluate whether the pair is removable

Inputs:

- `source_archive_id`
- `target_archive_id`
- optional `field_groups`
- optional `exclude_tags`
- optional `include_tags`
- `remove_original` forced to `false`

Required behavior:

- store the verification response
- surface `verified`, `remaining_difference_count`, `blocking_difference_count`, and `removable`
- refresh print-history browser state after success

### 4. `bambuddy.remove_restored_source_archive`

Purpose:

- request `POST /admin/archive-restore-verify` with `remove_original: true` and `dry_run: false`
- remove the original only when the pair has already verified cleanly

Inputs:

- `source_archive_id`
- `target_archive_id`

Required behavior:

- reject the call unless the most recent verification for the same pair reports:
  - `verified = true`
  - `remaining_difference_count = 0`
  - `removable = true`
- refresh print-history browser state after success
- finalize the surviving target archive by removing transient recovery tags and updating the structured recovery audit note
- clear or archive the transient workflow state for the pair after completion

### 5. `bambuddy.clear_archive_restore_workflow`

Purpose:

- dismiss the current transient restore state for the pair without mutating archives

Inputs:

- `source_archive_id`
- `target_archive_id`

Required behavior:

- clear the current workflow state
- keep historical audit notes on the archives untouched

## Proposed Sidecar Payload Usage

Home Assistant should pass through the sidecar contract rather than inventing a second policy language.

### Plan/apply payload

Based on [archive-runtime-sidecar-api-and-compose.md](archive-runtime-sidecar-api-and-compose.md):

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "field_groups": ["runtime", "user_metadata", "lineage", "asset_state", "snapshot_subset"],
  "exclude_tags": ["exception:missing_3mf", "replaced_by:*"],
  "include_tags": [],
  "overrides": {},
  "run_reenrich": false,
  "dry_run": true
}
```

### Verify payload

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "field_groups": ["runtime", "user_metadata", "lineage", "asset_state", "snapshot_subset"],
  "exclude_tags": ["exception:missing_3mf", "replaced_by:*"],
  "include_tags": [],
  "remove_original": false,
  "dry_run": true
}
```

### Remove-original payload

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "field_groups": ["runtime", "user_metadata", "lineage", "asset_state", "snapshot_subset"],
  "exclude_tags": ["exception:missing_3mf", "replaced_by:*"],
  "include_tags": [],
  "remove_original": true,
  "dry_run": false
}
```

## Proposed Workflow State Model

Home Assistant should track the restore workflow as an explicit state machine.

Recommended states:

- `idle`
- `replacement_upload_ready`
- `replacement_created`
- `pair_selected`
- `plan_ready`
- `apply_in_progress`
- `applied_pending_verify`
- `finalize_pending_reenrich`
- `verify_ready`
- `verified_clean`
- `verified_blocked`
- `remove_ready`
- `completed_original_retained`
- `removed`
- `failed`

Suggested state transitions:

1. replacement upload validated -> `replacement_upload_ready`
2. replacement archive created -> `replacement_created`
3. pair chosen or auto-seeded -> `pair_selected`
4. dry-run plan succeeds -> `plan_ready`
5. apply starts -> `apply_in_progress`
6. apply succeeds -> `applied_pending_verify`
7. target enrichment incomplete and no automatic re-enrich confirmation -> `finalize_pending_reenrich`
8. verify succeeds and clean -> `verified_clean`
9. verify succeeds but not clean -> `verified_blocked`
10. removal allowed -> `remove_ready`
11. operator keeps original after successful restore -> `completed_original_retained`
12. remove-original succeeds -> `removed`

## Recommended Data Exposed To The UI

The UI should be able to render these summaries without parsing the raw sidecar payload in card JavaScript.

Recommended derived fields:

- `source_archive_id`
- `target_archive_id`
- `workflow_state`
- `last_operation`
- `last_operation_at`
- `plan_warning_count`
- `plan_copy_count`
- `plan_merge_count`
- `plan_override_count`
- `plan_updated_field_count`
- `verify_blocking_difference_count`
- `verify_remaining_difference_count`
- `verified`
- `removable`
- `source_removed`
- `last_error`

The full raw plan and verify payloads should still remain available for a detail view, but the popup itself should primarily read summarized fields.

## Storage Recommendation

### Do not use helper state for the full payload

Do not store full `field_actions` arrays in:

- `input_text`
- ad hoc template attributes
- inline browser-mod variables

Reasons:

- payloads can be large
- helper limits are too small
- this would recreate the same state-bloat problems the active browser architecture already moved away from

### Recommended storage choices

Priority order:

1. `bambuddy` custom integration transient store and entity/service surface
2. event-backed workflow entity with summarized attributes plus side-channel detail lookup
3. temporary JSON file cache only if an integration-backed model is not feasible yet

## Proposed UI Contract

## Popup sections

The popup restore flow should render in four stacked sections.

### Section 1: Pair summary

Shows:

- source archive ID and print name
- target archive ID and print name
- origin badges such as `Incomplete`, `Recovered`, `Imported`, `Potential Duplicate`
- current workflow state

### Section 2: Plan summary

Shows:

- warning count
- copy/merge/override counts
- high-signal field decisions such as `started_at`, `completed_at`, `status`, `tags`, `notes`, and `is_favorite`
- whether parser-derived target fields will be preserved

### Section 3: Verification summary

Shows:

- `verified`
- `blocking_difference_count`
- `remaining_difference_count`
- `removable`
- `source_removed`

### Section 4: Action row

Actions vary by workflow state.

Recommended action set:

- `Upload Replacement 3MF`
- `Create Replacement Archive`
- `Review Pair`
- `Plan Restore`
- `Apply Restore`
- `Run Re-enrich`
- `Finish Repair`
- `Verify`
- `Remove Original`
- `Clear`

## Action visibility rules

### `Plan Restore`

Visible when:

- pair is selected
- workflow is not currently in progress

### `Create Replacement Archive`

Visible when:

- a valid staged upload session exists for the current source archive
- no replacement target has been created yet
- workflow is not currently in progress

### `Apply Restore`

Visible when:

- a dry-run plan exists for the current pair
- no operation is currently running

### `Verify`

Visible when:

- apply completed successfully

### `Run Re-enrich`

Visible when:

- apply completed successfully
- target archive enrichment is missing or partial
- the workflow is waiting on enrichment before cleanup

### `Finish Repair`

Visible when:

- apply completed successfully
- workflow is not currently in progress

Meaning:

- this is the HA orchestration step that decides whether the repair can be considered complete
- it may run re-enrich, run verify, stop with a pending-enrichment message, mark the repair complete while retaining the original, or proceed to guarded original removal depending on current state and operator choice

### `Remove Original`

Visible only when all of the following are true:

- latest verification is for the same pair
- `verified = true`
- `remaining_difference_count = 0`
- `removable = true`
- no operation is currently running

## Admin-only recommendation

Restore actions should be hidden from non-admin users.

If the dashboard framework cannot enforce that cleanly in the first implementation, the script or integration service layer must still reject non-admin or non-approved usage through configuration and visibility boundaries.

## Guardrails

### 1. No one-click restore on the archive card face

Keep the archive card tap dedicated to drilldown.

### 2. Require pair clarity

Never allow a restore action to run when the UI cannot show which archive is source and which is target.

### 3. Require plan-before-apply

The first shipped apply flow should require an existing dry-run plan for the same pair. This is both safer and easier to reason about operationally.

### 4. Require verify-before-remove

Do not surface `Remove Original` until verification is clean.

### 4a. Require enrichment clarity before cleanup

If the target archive is still missing or partial from an enrichment perspective, the HA flow should not silently delete the original just because restore-from apply succeeded.

Default policy:

- if `run_reenrich` was requested and the sidecar confirms it triggered HA successfully, wait for refresh and verify again
- if `run_reenrich` was requested but the sidecar reports that HA callback is not configured, move the workflow to `finalize_pending_reenrich`
- in `finalize_pending_reenrich`, expose explicit operator choices rather than implicit cleanup

Recommended operator choices in that state:

- `Run Re-enrich` now through the normal HA script path
- `Verify` again after enrichment completes
- `Finish Repair And Keep Original` if the operator wants the merge preserved but does not want cleanup yet
- `Remove Original Anyway` only as an explicit advanced override, and only if the lower-level sidecar call intentionally uses `force_remove_without_reenrich`

### 5. Always refresh the browser after mutation

After apply, verify, or remove, the UI should refresh the print-history browser and active archive detail surfaces.

### 5a. Finish-repair is an HA orchestration step, not a new merge mode

`Finish Repair` should not perform a second metadata merge.

Its job is to:

1. check whether enrichment is complete on the target archive
2. optionally invoke or re-invoke re-enrich
3. run verify for the current pair
4. if verification is clean, either:
  - mark the workflow complete with the original retained, or
  - call guarded original removal
5. clear transient workflow state only after the chosen completion path succeeds

### 6. Preserve the sidecar as the write boundary

Home Assistant should never directly mutate the Bambuddy database for restore behavior.

## Phased Delivery Plan

## Phase 1: Review-Only Restore Entry Point

### Scope

- add admin-only restore action to the archive popup
- allow source-target pair selection or pair prefill
- show read-only pair context, lineage markers, and restore warnings
- no write calls yet

### Deliverables

- popup subflow or child popup for restore review
- pair-state selection contract
- clear operator language distinguishing source vs target

### Why this first

- solves the workflow-entry problem
- proves the popup/action design without risk
- avoids immediate coupling to large response payload rendering

## Phase 2: Dry-Run Restore Planning

### Scope

- implement `bambuddy.plan_archive_restore`
- show plan summary and warnings from sidecar dry-run output
- keep large payloads out of helper state

### Deliverables

- sidecar plan call from HA
- summarized plan results in popup
- detail view for the most important field actions

### Exit criteria

- operator can choose a pair and see what would change before any mutation occurs

## Phase 3: Apply Restore

### Scope

- implement `bambuddy.apply_archive_restore`
- add explicit confirmation step
- refresh archive browser after success

### Deliverables

- apply button with confirmation copy
- apply result summary with `updated_fields`
- workflow state transitions to `applied_pending_verify`

### Exit criteria

- operator can apply the planned merge from the popup and immediately see post-apply state

## Phase 4: Verify And Cleanup Readiness

### Scope

- implement `bambuddy.verify_archive_restore`
- render verification summary and removable status
- do not remove original yet in this phase unless the UI/guardrail path is already stable

### Deliverables

- verify action
- verification summary section
- explicit clean vs blocked messaging

### Exit criteria

- operator can determine from HA whether the pair is safe to clean up

## Phase 5: Remove Original Archive

### Scope

- implement `bambuddy.remove_restored_source_archive`
- require a clean verification for the same pair
- clear or archive transient workflow state after removal

### Deliverables

- guarded remove-original button
- success state showing `source_removed = true`
- browser refresh that removes or downgrades the original exception state

### Exit criteria

- operator can complete the full sidecar-supported restore lifecycle from Home Assistant without leaving the popup flow

## Recommended Finalization Policy

For the browser-initiated replacement-file workflow, the default completion path should be:

1. upload replacement `.gcode.3mf` to HA
2. create replacement archive in Bambuddy
3. plan restore
4. apply restore
5. re-enrich target archive
6. verify the source-target pair
7. only then offer original removal

If automatic re-enrich is unavailable because the runtime-repair sidecar is not configured with HA callback credentials, the workflow should still remain manageable from HA:

- HA should expose a manual `Run Re-enrich` action against the target archive
- HA should keep the pair in `finalize_pending_reenrich` until enrichment becomes acceptable or the operator explicitly chooses to retain the original
- the default safe outcome in that condition is `completed_original_retained`, not silent deletion

This gives the workflow a clean two-step operator story when needed:

1. create and merge the replacement archive
2. finish repair after enrichment and verification are complete

## Phase 6: Admin Restore Operations View

### Scope

- add a protected maintenance surface for recent restore operations and unresolved candidate pairs
- surface failed verifications, stale plans, and removable pairs

### Deliverables

- admin dashboard section or subview
- recent restore results list
- filters for blocked vs clean vs removed

### Why this last

- it is useful, but not required to make the popup-based workflow safe and functional

## Recommended Implementation Order

The lowest-risk implementation sequence is:

1. Phase 1 review-only pair flow
2. Phase 2 dry-run plan
3. Phase 3 apply
4. Phase 4 verify
5. Phase 5 remove-original
6. Phase 6 maintenance view

This sequence intentionally delays destructive cleanup until the operator-review loop is already proven.

## Open Questions

1. Should pair detection and prefill rely only on lineage tags/notes, or should the custom integration also expose explicit candidate-pair discovery?
2. Should the replacement-upload intake do light file classification only, or also inspect enough metadata to warn when the upload appears to be a source-project `.3mf` instead of a sliced replacement?
3. Should the initial implementation live entirely in scripts plus `rest_command`, or should it wait for a proper `bambuddy` integration service layer?
4. Should the maintenance view eventually include a small restore-operation history store, or is the popup-oriented transient model sufficient?

## Recommendation

Proceed with the workflow, but start with review and dry-run only.

That approach matches the repository's existing architecture:

- popup-first advanced actions
- sidecar-owned write logic
- integration-owned heavy transient payloads
- guarded operator flows for high-risk archive operations

It also gives the project a clear contract that can be implemented incrementally without redesigning the print-history browser later.

## Documented Next Steps

The following follow-on work items should remain attached to this design:

1. turn this design into a concrete Phase 1 implementation plan with exact entities, helpers, scripts, and popup wiring
2. draft the initial Home Assistant YAML or custom-integration service surface for `plan`, `apply`, `verify`, and `remove`
3. add a companion candidate-pair discovery design so the popup can prefill likely source-target pairs instead of relying on manual selection

