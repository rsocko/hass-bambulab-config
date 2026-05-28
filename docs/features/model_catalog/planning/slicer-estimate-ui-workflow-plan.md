# Slicer Estimate UI And Workflow Plan

> Status: Proposed and issue-ready
> Last updated: 2026-05-27
> Scope: Model Catalog + Unified Queue estimate-generation UX

## Purpose

Close the gap between the backend estimate-only slicer capability and the operator-facing UI surfaces that should create, refresh, and explain those estimates.

The current state is useful but incomplete:

- The backend can run `estimate_only` slicing and persist queue estimate metadata.
- Planner ranking can already prefer history over fresh slicer over manual estimates.
- The UI can display some estimate state, but there is no clear operator entrypoint that says "run the slicer now and save an estimate for this queue item."

This plan defines where estimate generation should live, where it should only be displayed, and which delivery slices should be tracked separately in GitHub.

## Product Decisions

1. Do not automatically slice every queue add in the first version.
2. Keep normal `Add to Queue` fast and low-friction.
3. Make the Unified Queue board the primary surface for estimate creation and re-estimation.
4. Reuse the existing slicer wizard, but add an explicit `estimate_only` mode.
5. Use the Model Detail popup as a secondary inspection and launch surface, not the primary planning workspace.
6. Treat `Add and Estimate` as an explicit opt-in path, not a hidden side effect.
7. Keep estimate-only jobs transient: no archive commit, no retained sliced output by default.

## UX Ownership By Surface

| Surface | Primary role | Create estimate here? | Notes |
| --- | --- | --- | --- |
| Unified Queue board | Main operator planning surface | Yes | Default place for `Estimate`, `Re-estimate`, and stale recovery |
| Add to Queue dialog | Lightweight entry | Not by default | Add optional `Add and Estimate` follow-up once queue-first flow is stable |
| Model Detail popup | Inspect queue context | Yes, secondary | Good for one-off recovery and detail-aware actions |
| Slicer wizard | Shared execution shell | Yes, reusable | Must support both `create_archive` and `estimate_only` intents |

## Recommended Operator Flow

### Flow A: Queue-first planning

1. Operator adds a model to the queue.
2. Queue row shows one of: `History`, `Slice`, `Slice stale`, `Manual`, or `Missing`.
3. If there is no fresh slicer estimate, the row exposes `Estimate`.
4. Clicking `Estimate` opens the slicer wizard in `estimate_only` mode with the queue entry's current file/plate selection preloaded.
5. On success, the queue row refreshes in place and shows the effective estimate minutes plus `Slice` as the source.

This is the mainline workflow and should be the first UI slice delivered.

### Flow B: Re-estimate after selection changes

1. Operator edits file or plate selection for an existing queue row.
2. Existing slicer estimate becomes `Slice stale`.
3. The queue row explains why the estimate is stale and exposes `Re-estimate`.
4. Running the estimate updates the same queue entry instead of creating a new planning object.

### Flow C: Detail-first recovery from popup

1. Operator opens the Model Detail popup.
2. Queued Prints shows estimate minutes, source, and freshness for each queued entry.
3. If the item has no fresh estimate, popup exposes `Estimate via Slicer`.
4. Action launches the same wizard/contract as the queue board.

This is useful for operators already working from detail view, but it should not replace the queue board as the primary planning surface.

### Flow D: Combined add-and-estimate

1. Operator opens Add to Queue.
2. Dialog still defaults to lightweight queue creation.
3. Operator may choose `Add and Estimate` when they want to immediately populate planning metadata.
4. Queue entry is created first; estimate follows using the exact submitted selection.

This should be a follow-on slice, not the first slice, because it mixes creation and background execution complexity.

## UI Contract

### Unified Queue board

Required row-level affordances:

- `Estimate` when there is no fresh slicer estimate.
- `Re-estimate` when source is slicer and freshness is stale or failed.
- `Estimating...` busy state while a job is active.
- Source badge and freshness badge next to effective minutes.
- Clear empty-state wording when only history or manual fallback exists.

Recommended row labels:

- `History 7h 42m`
- `Slice 6h 55m`
- `Slice stale 6h 55m`
- `Manual 7h 10m`
- `Estimate missing`

### Model Detail popup

Queued Prints should show:

- Effective estimate minutes.
- Source badge.
- Freshness/status badge.
- `Estimate via Slicer` or `Re-estimate` action when a queue entry exists.

The popup must not imply that adding to queue already triggered slicing unless that path was explicitly used.

### Add to Queue dialog

The first implementation should preserve the current lightweight default.

Follow-on behavior:

- `Add to Queue` remains primary.
- `Add and Estimate` is explicit.
- Success copy distinguishes `queue entry created` from `estimate running`.
- If estimate launch fails after queue creation, the queue entry remains intact.

### Slicer wizard

The wizard should be reusable for both archive creation and estimate-only runs.

It needs:

- Intent-aware header copy.
- Intent-aware success state.
- No archive commit step in `estimate_only` mode.
- Clear explanation that the result updates planning metadata for the selected queue entry.

## Backend/API Follow-On Contract

The backend estimate-only implementation exists, but the UI still needs a clean, queue-entry-targeted trigger contract.

That contract should:

- Accept queue entry identity plus current file/plate selection context.
- Carry printer/profile information needed to build a slicer estimate profile key.
- Return operator-usable failure states for missing printer mapping, missing profile, bad selection, or slicer execution failure.
- Refresh queue estimate metadata in-place rather than creating detached estimate records.

Avoid introducing a second planning persistence model for this feature. The queue entry remains the source of truth for estimate metadata.

## Delivery Sequence

### Phase 1: Trigger contract

- Add the queue-entry-targeted estimate trigger contract.
- Keep the result attached to existing queue estimate metadata.

### Phase 2: Reusable wizard mode

- Extend the slicer wizard to support `estimate_only` mode.
- Preserve current archive creation behavior.

### Phase 3: Queue board primary UX

- Add `Estimate` / `Re-estimate` actions.
- Render source + freshness clearly.
- Refresh row state after completion.

### Phase 4: Secondary surfaces

- Add popup estimate display + launch action.
- Add optional `Add and Estimate` path to queue-add flow.

### Phase 5: Validation and rollout

- Manual end-to-end validation.
- Documentation alignment.
- Resource-version and hard-refresh guidance for shipped JS changes.

## Non-Goals

- Automatic estimate generation for every queue add.
- Silent background slicing triggered by browsing alone.
- Retaining estimate-only sliced output as a durable model artifact.
- Treating estimate-only runs as archive creation.

## Validation Checklist

- Queue row can launch estimate-only slicing for an existing entry.
- Queue row refreshes to fresh slicer metadata after success.
- Editing file/plate selection marks a slicer estimate stale.
- Re-estimate clears stale state on success.
- Model Detail popup matches queue-board source and freshness wording.
- `Add and Estimate` preserves the queue entry even if estimate launch fails.
- Archive creation flow in slicer wizard does not regress.

## Related Artifacts

- `docs/features/model_catalog/planning/print-history-slicer-plan.md`
- `docs/features/model_catalog/planning/unified-queue-plan.md`
- `docs/features/model_catalog/planning/slicer-estimate-ui-issues.md`
- `docs/features/model_catalog/design/mockups/queue-estimate-planning.html`