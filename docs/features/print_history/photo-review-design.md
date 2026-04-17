# Post-Print Photo Review Design

> **Current status**: The archive popup and photo gallery are already shipped, and the gallery already supports the local `primary photo` override used by the print-history list and popup preview. What is still missing is the actual review workflow: delete, replace, dismiss, chip-to-popup handoff, and auto-dismiss lifecycle.
>
> **Authoritative runtime model**: Do not revive the old `input_text` JSON manifest idea for this feature. The active print-history implementation is Variant 3, so photo review should read from the Bambuddy-backed archive detail plus the local SQLite store in `custom_components/bambuddy`.

## Overview

After a print completes, Home Assistant may have captured multiple photos across several stages and cameras. The photo review feature is the operator pass that lets the user decide which photos to keep, which one should represent the print in Home Assistant, and when the review window is complete.

The intended review actions are:
- **Delete** — remove a photo from Bambuddy and from the local `www/printer_snapshots` copy when that local file is known.
- **Replace** — capture a new snapshot now, upload it, and optionally delete the superseded photo.
- **Use In List View** — select the preferred photo for print-history list and popup preview rendering using the existing local primary-photo override.
- **Dismiss** — mark the archive's photo review as complete without changing the current media set.

Optional later action:
- **Sync Bambuddy cover photo** — only if `cover_photo_id` is validated live and proves useful beyond the existing local primary-photo override.

## Design Direction

The earlier design assumed a standalone photo-review popup driven by a per-photo manifest in an `input_text` helper. That is no longer the right architecture.

The correct implementation path now is:
1. use the existing archive popup as the only review surface
2. keep Bambuddy archive detail plus local SQLite rows as the source of truth
3. expose review actions as Bambuddy integration services, not YAML-only scripts glued together around helpers
4. treat the review chip as a lightweight entry point into the existing popup, not as a separate UI system

That keeps the feature aligned with the current popup architecture and avoids introducing a second, parallel review state model.

## Existing Runtime Foundation

### Already shipped

- `custom:print-history-browser-card` opens an archive-specific popup
- the popup already includes the photo gallery card
- the gallery already supports local primary-photo selection via `bambuddy.set_print_history_primary_photo`
- `input_select.bambuddy_photo_review_state` is set to `pending` after terminal enrichment when photos were captured
- `input_number.photo_review_timeout_hours` already exists as the review timeout control

### Existing SQLite data that should be reused

The Variant 3 SQLite store already has the key media structures needed for review:

- `archive_photos` — authoritative archive photo filenames and ordering as mirrored from Bambuddy
- `archive_primary_photo_selection` — current local primary-photo override for list/popup rendering
- `archive_review_state` — existing generic review metadata used for mismatch/duplicate workflows

### Important constraint

Do **not** overload `archive_review_state` for photo review unless there is a compelling reason to merge those workflows. It already carries mismatch-oriented semantics such as `review_status`, `mismatch_flags`, and `review_note`.

Photo review is a distinct lifecycle with different actions, timeouts, and UI triggers. It should therefore use a dedicated media-review table rather than piggybacking on mismatch review fields.

## Proposed Store-Backed Review Model

### New table

Add a dedicated local table for per-archive photo-review lifecycle:

```sql
CREATE TABLE IF NOT EXISTS archive_media_review_state (
    archive_id INTEGER PRIMARY KEY,
    review_status TEXT NOT NULL DEFAULT 'idle',
    requested_at TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT '',
    dismissed_at TEXT NOT NULL DEFAULT '',
    photo_count INTEGER NOT NULL DEFAULT 0,
    last_action TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
);
```

Recommended `review_status` values:
- `idle` — no active review needed
- `pending` — archive needs review and has not been opened yet
- `reviewing` — popup was opened for review or an action is in progress
- `dismissed` — operator closed review without further media changes
- `completed` — operator completed one or more media actions and closed the loop

### Why a dedicated table is the right boundary

- photo review is per-archive and should survive HA restart
- the review chip should be able to reopen the right archive after refresh
- delete/replace actions should update a persistent row, not only a helper
- timelapse review can later extend the same `media review` concept without polluting mismatch review data

### Helper role after the redesign

Keep the existing helpers, but narrow their role:

- `input_select.bambuddy_photo_review_state` becomes a coarse UI signal for the view-level chip
- `input_number.photo_review_timeout_hours` remains the user-configurable timeout

The SQLite table becomes the authoritative per-archive state. The helper should be treated as a mirrored summary, not the source of truth.

## Trigger And Lifecycle

### When review becomes pending

The current completion behavior is close to correct and should stay:

1. print reaches a terminal state
2. archive enrichment runs
3. if captured-photo count is greater than zero, the archive is marked for photo review
4. the review chip appears on the print-history view

The missing piece is persistence. Instead of only setting the helper, terminal enrichment should also upsert `archive_media_review_state` for the completed archive with:
- `review_status = pending`
- `requested_at = now()`
- `photo_count = current archive photo count` when available
- `last_action = captured`

### When review starts

When the user taps the review chip or explicitly opens review from the popup, mark the row as `reviewing` with `started_at = now()`.

### When review ends

Review should end in one of two ways:
- **Dismissed** — no media change required; mark `dismissed_at`, `review_status = dismissed`, `last_action = dismissed`
- **Completed** — one or more delete/replace/primary-photo actions were taken and the operator closes the loop; mark `completed_at`, `review_status = completed`

### Auto-dismiss

Auto-dismiss remains desirable, but it should operate on store rows rather than only on the global helper.

Proposed behavior:
- on next `print_started`, dismiss any older archive still in `pending` or `reviewing`
- on timeout (`input_number.photo_review_timeout_hours`), transition stale `pending` or `reviewing` rows to `dismissed`
- recompute the helper state after every review-state mutation so the chip stays accurate

## Media Data Source

The popup does not need a dedicated `list photos` endpoint to render review actions.

The authoritative source for the visible photo set should be, in priority order:
1. archive detail already loaded for the popup
2. local SQLite `archive_photos` rows mirrored from that detail
3. existing thumbnail fallback when no photo exists

That means the review UI can be built on the existing popup/gallery path without reintroducing a separate manifest parser.

## Required API Operations

### Confirmed and usable now

| Operation | Endpoint | Role in review |
|---|---|---|
| Upload photo | `POST /archives/{id}/photos` | Needed for replace flow |
| Delete photo | `DELETE /archives/{id}/photos/{filename}` | Confirmed delete contract |
| Get photo file | `GET /archives/{id}/photos/{filename}` | Already used by gallery |
| Get archive detail | `GET /archives/{id}` | Provides current photo list/detail payload |

### Already shipped locally

| Operation | Current implementation | Role |
|---|---|---|
| Set preferred preview photo | `bambuddy.set_print_history_primary_photo` | Selects the photo used in list/popup preview rendering |

### Not required for first review slice

| Operation | Status | Notes |
|---|---|---|
| `cover_photo_id` PATCH support | Unverified | Treat as optional, not a blocker |
| Photo reorder endpoint | Unknown / unnecessary | Do not block review on reorder support |

## Service Architecture

The next build should add media-review services to the Bambuddy custom component rather than implementing the workflow only in YAML scripts.

### Recommended new services

| Service | Purpose |
|---|---|
| `bambuddy.delete_print_history_photo` | Delete a photo by filename, update local store rows, update media review state, recompute popup/query payloads |
| `bambuddy.dismiss_print_history_media_review` | Mark the current archive review as dismissed or completed |
| `bambuddy.replace_print_history_photo` | Orchestrate capture/upload/delete for one photo slot or one selected filename |
| `bambuddy.start_print_history_media_review` | Optional convenience service to mark `reviewing` and return the target archive context |

### Why integration services first

- they can mutate SQLite and query state in one place
- they can rehydrate missing archives on demand, matching the existing Variant 3 pattern
- they avoid scattering review logic across `rest_command`, helper writes, and frontend-only assumptions
- they make the popup/gallery simpler because the frontend only needs to call one service per action

## Popup UX

### Review entry point

The review chip should stop opening more-info for `input_select.bambuddy_photo_review_state`.

Instead, it should:
1. resolve the newest archive whose `archive_media_review_state.review_status` is `pending` or `reviewing`
2. set popup context for that archive
3. open the existing archive popup

If no pending row exists, the chip should not render.

### Review surface

Do not build a second dedicated review popup. Extend the existing archive popup and photo gallery.

The media actions should be available during ordinary archive viewing as well, not only when the archive is in a pending review state. In practice that means:
- the normal archive popup/gallery is the single place where photo actions live
- the review chip is only an entry point into that same popup when an archive still needs review
- a user browsing any past print can still delete, replace, or change the preferred preview photo from the gallery

This reuse is intentional. It avoids training the user on two different media surfaces and keeps photo management discoverable on every archive, while the pending-review state only adds workflow urgency.

Planned action set inside the current popup/gallery:
- `Use In List View` — already supported by the gallery's primary-photo path
- `Delete Photo` — new action, available from normal viewing and review entry, always protected by an explicit confirmation step
- `Dismiss Review` — popup-level action
- `Replace Photo` — later follow-on action, also available from normal viewing once implemented

### Delete confirmation

Deleting a photo is destructive and should always require confirmation before the service call is executed.

Recommended behavior:
1. user taps `Delete Photo` on the currently selected gallery image
2. a confirmation dialog or lightweight confirmation popup summarizes the archive name and selected filename
3. only after confirmation does the integration service run

The confirmation requirement applies regardless of whether the archive was opened from the review chip or from normal browsing.

### Initial implementation slice

The lowest-risk first slice is:
1. chip opens archive popup instead of more-info
2. popup/gallery adds `Delete Photo` for ordinary viewing and review-driven entry, with confirmation
3. popup adds `Dismiss Review`
4. primary-photo selection remains as-is

That is enough to ship a real review loop without waiting for replace orchestration.

## Local File Cleanup

Photos still accumulate under `/config/www/printer_snapshots/`, but cleanup should follow the action model rather than a manifest model.

### First-phase cleanup behavior

- if a reviewed photo is deleted and the local file path is known, remove the local file too
- if a photo is retained, keep the local file
- if a local file cannot be mapped safely, delete only from Bambuddy and record that the local copy was retained

### Deferred enhancement

A rolling retention automation for old local snapshots is still reasonable, but it is separate from the review feature.

## Current Gap Summary

Already shipped:
- archive popup
- photo gallery inside popup
- local primary-photo override
- coarse review helper and timeout helper
- review state becomes `pending` after terminal enrichment when photos exist

Still missing:
- store-backed per-archive media review state
- chip-to-popup handoff
- delete photo action
- dismiss review action
- replace photo action
- auto-dismiss automation over persistent review rows

Optional later work:
- Bambuddy cover-photo sync if live API validation proves it worthwhile

## Recommended Build Sequence

1. **Normalize contracts** — update docs and command comments so delete uses `filename`, not `photo_id`, and treat local primary-photo selection as the current shipped photo-promote behavior.
2. **Add store-backed media review state** — create `archive_media_review_state` and wire terminal enrichment plus lifecycle recompute into the custom integration.
3. **Ship the first real review loop** — make the chip open the existing archive popup and add `Dismiss Review` plus review-state transitions.
4. **Add delete photo** — integration service first, then popup/gallery button wired into the service.
5. **Add replace photo** — only after delete/dismiss are stable, because replace spans capture, upload, store refresh, and optional old-photo cleanup.
6. **Start timelapse review** — once basic photo review works, extend the same media-review model to timelapse scan, status, and preview.

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | Should `archive_media_review_state` stay separate from `archive_review_state`? | Affects schema clarity and future workflow coupling | Yes — decide before implementation |
| 2 | How should the chip resolve the target archive when several reviews are pending? | Affects popup entry behavior | Yes |
| 3 | Can replace safely map a newly captured local file back to one logical reviewed photo slot? | Affects replace UX and deletion safety | No for delete/dismiss first slice |
| 4 | Is Bambuddy `cover_photo_id` worth implementing if local primary-photo override already solves the HA UX? | Affects scope and whether `rest_command.bambuddy_set_archive_cover` is retained | No |
| 5 | Should timelapse share the same media-review table or add a sibling table later? | Affects long-term schema shape | No for first slice |
