# Slicer Estimate UI GitHub Issues

> Status: Ready to create
> Last updated: 2026-05-27
> Repo target: `rsocko/hass-bambulab-config`

This file intentionally keeps the GitHub create-issue URLs out of the repo because the encoded query string is hard to read in Markdown.

Use the issue drafts below as the readable repo copy. Create-issue hyperlinks can be provided separately in chat when needed.

## Suggested Workflow

1. Create `SE-01` and `SE-02` first so the queue board has a stable trigger and reusable wizard mode.
2. Create `SE-03` next because the Unified Queue board is the primary operator surface.
3. Create `SE-04` and `SE-05` after the queue-board contract is stable.
4. Create `SE-06` last for end-to-end validation, docs alignment, and rollout hardening.

## Implementation References

- `docs/features/model_catalog/planning/slicer-estimate-ui-workflow-plan.md`
- `docs/features/model_catalog/planning/print-history-slicer-plan.md`
- `docs/features/model_catalog/planning/unified-queue-plan.md`
- `docs/features/model_catalog/design/mockups/queue-estimate-planning.html`

## Issue Drafts

## SE-01

Title: `Model Catalog: add queue-targeted estimate-only slicer trigger contract`

Summary: Add the backend/UI contract needed to run an estimate-only slicer job for an existing unified queue entry.

Scope:

- Define the queue-entry-targeted trigger path for estimate-only slicing.
- Carry source file, selected file/plate scope, printer/profile context, and queue entry identity.
- Persist/return execution states suitable for UI polling or completion refresh.
- Keep estimate-only jobs non-archive and non-retained by default.

Acceptance Criteria:

- An existing queue entry can request a slicer estimate without creating an archive.
- The request is scoped to the queue entry's current file/plate selection.
- Result updates the queue entry estimate metadata in sidecar persistence.
- Failure and missing-profile states are returned with operator-usable messages.

## SE-02

Title: `Model Catalog UI: add estimate-only mode to slicer wizard`

Summary: Extend the existing slicer wizard so it can run in explicit `estimate_only` mode as well as archive-creation mode.

Scope:

- Add a mode switch / intent contract for `create_archive` vs `estimate_only`.
- Reuse shared slicer setup UX where possible.
- In estimate-only mode, do not call commit-archive.
- Render progress, success, and error states appropriate for planning estimates.

Acceptance Criteria:

- Wizard can be opened in estimate-only mode from another UI surface.
- Execute completes without archive commit.
- Success state explains that the estimate was saved to the queue/planning metadata.
- Archive-creation mode behavior does not regress.

## SE-03

Title: `Unified Queue UI: add Estimate and Re-estimate actions with estimate state rendering`

Summary: Make the unified queue board the primary operator surface for generating and refreshing slicer-based print estimates.

Scope:

- Add `Estimate`, `Re-estimate`, and `Refresh estimate` row actions where appropriate.
- Render estimate source/state (`history`, `slicer`, `manual`, `missing`) and freshness (`fresh`, `stale`, `failed`, `estimating`).
- Refresh queue rows after estimate completion.
- Show stale reasons and re-estimate affordance after selection changes.

Acceptance Criteria:

- Operators can trigger estimate-only slicing from the queue board.
- Queue rows visibly show estimate source and freshness state.
- A stale slicer estimate can be re-estimated from the same row.
- Missing/failure states are understandable without opening dev tools.

## SE-04

Title: `Model Catalog Add-to-Queue: support Add and Estimate follow-up flow`

Summary: Update the Add to Queue dialog so operators can optionally request a slicer estimate as part of queue creation without making estimate generation mandatory.

Scope:

- Keep normal `Add to Queue` fast/lightweight.
- Add an explicit `Add and Estimate` or equivalent opt-in follow-up path.
- Carry selected file/plate scope into the estimate request.
- Return the operator to a clear success or progress state after queue creation.

Acceptance Criteria:

- Operators can still add to queue without triggering slicing.
- Operators can choose a combined add-and-estimate path from the same dialog.
- The combined path uses the exact queue selection that was submitted.
- Failures do not lose the queue entry that was successfully created.

## SE-05

Title: `Model Detail popup: show queue estimate source and allow Estimate via Slicer action`

Summary: Expose queue estimate status in the model detail popup and add an explicit `Estimate via Slicer` operator action.

Scope:

- Render effective estimate minutes, source, and freshness in the Queued Prints panel.
- Add `Estimate via Slicer` / `Re-estimate` action where a queue entry exists.
- For non-queued models, provide a clear path to queue-first or add-and-estimate.
- Keep popup wording aligned with unified queue terminology.

Acceptance Criteria:

- Queued Prints panel shows estimate source/status for queue entries.
- Operators can launch estimate-only slicing from model detail when appropriate.
- Popup does not imply that queue add automatically ran the slicer when it did not.
- Queue and popup states stay visually consistent after refresh.

## SE-06

Title: `Slicer estimate UX: integration validation, docs alignment, and rollout checklist`

Summary: Close the slicer-estimate UI/workflow loop with validation, mockup/doc alignment, and rollout guidance.

Scope:

- Validate queue-board, add-dialog, and model-detail estimate flows end to end.
- Confirm stale invalidation and re-estimate behavior with real selections.
- Align planning docs/mockups with shipped UI behavior.
- Record hard-refresh and dashboard resource validation steps.

Acceptance Criteria:

- End-to-end manual validation checklist is complete.
- Docs and mockups match shipped operator entrypoints.
- No unresolved ambiguity remains about where estimates are created vs only displayed.
- Resource cache-bust / deploy guidance is documented for touched JS assets.

## Dependency Order

1. `SE-01` -> `SE-02`
2. `SE-03`
3. `SE-04` and `SE-05`
4. `SE-06`