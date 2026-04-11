# Post-Print Photo Review Design

> **Current status**: Only the lightweight review-status chip is shipped today. The popup, review actions, and auto-dismiss automation remain design-only follow-on work.
>
> **Runtime note**: The shipped package no longer stores a per-photo JSON manifest in an `input_text` helper. Current runtime state is limited to a captured-photo counter plus a short last-upload-result summary. The manifest model below remains future design work and will need archive-backed or file-backed storage before implementation.

## Overview

After a print completes, HA may have captured 3–6+ photos across multiple stages and cameras. Not all photos are keepers — a first-layer capture might be blurry, an error photo might be redundant, or one of the extra camera angles might be uninteresting. The post-print review feature gives the user a quick way to curate the photos attached to a Bambuddy archive directly from the HA dashboard.

**Actions available in review**:
- **Remove** — delete a photo from both Bambuddy and local storage
- **Replace** — take a new snapshot now and swap it for an existing photo
- **Set as cover** — designate which photo appears as the archive thumbnail
- **Dismiss** — accept all photos as-is and close the review

## Trigger & Lifecycle

### When Does Review Appear?

The review is **opt-in** and surfaces as a conditional card after print completion:

1. Print completes (success, failed, or cancelled)
2. Enrichment automation runs (tags/notes PATCH)
3. Enrichment automation sets `input_select.bambuddy_photo_review_state` → `pending`
4. The review chip appears on the print history view (conditional on state = `pending`)

Current shipped behavior:
- **See status** — the chip advertises that reviewable photos exist
- **Open entity more-info** — tapping the chip opens the helper entity, not the planned popup yet

Planned advanced behavior:
- **Review now** — open the review popup and curate photos
- **Dismiss** — accept all, set state → `idle`, and close the review cycle
- **Ignore** — let the future auto-dismiss automation close the review window after timeout or next print start

### Auto-Dismiss

Status: not implemented yet.

An automation clears the review state:
- On next `print_started` webhook event (previous print's review window closes)
- After `input_number.photo_review_timeout_hours` (default: 24) elapses since `pending` was set

## Photo Manifest

During capture, the `capture_and_upload_snapshot` script builds a local manifest in `input_text.bambuddy_photo_manifest` — a JSON array tracking each captured photo:

```json
[
  {
    "stage": "start",
    "camera": "primary",
    "local_path": "/local/printer_snapshots/Benchy_start_20260328_143000.jpg",
    "file_path": "/config/www/printer_snapshots/Benchy_start_20260328_143000.jpg",
    "bambuddy_photo_id": "ph_abc123",
    "timestamp": "2026-03-28T14:30:00",
    "uploaded": true
  },
  {
    "stage": "midprint",
    "camera": "primary",
    "local_path": "/local/printer_snapshots/Benchy_midprint_20260328_150000.jpg",
    "file_path": "/config/www/printer_snapshots/Benchy_midprint_20260328_150000.jpg",
    "bambuddy_photo_id": "ph_def456",
    "timestamp": "2026-03-28T15:00:00",
    "uploaded": true
  },
  {
    "stage": "start",
    "camera": "secondary",
    "local_path": "/local/printer_snapshots/Benchy_start_20260328_143000_cam2.jpg",
    "file_path": "/config/www/printer_snapshots/Benchy_start_20260328_143000_cam2.jpg",
    "bambuddy_photo_id": "ph_ghi789",
    "timestamp": "2026-03-28T14:30:00",
    "uploaded": true
  }
]
```

Key fields:
- `local_path` — `/local/...` path for dashboard `<img>` rendering
- `file_path` — `/config/www/...` path for `shell_command` file operations
- `bambuddy_photo_id` — ID returned by Bambuddy's upload response (needed for DELETE/reorder)
- `uploaded` — false if upload failed (photo exists locally but not in Bambuddy)

### Manifest Population

The `capture_and_upload_snapshot` script is updated to:
1. After each capture + upload, read the upload response to extract the photo ID
2. Append a manifest entry to `input_text.bambuddy_photo_manifest`
3. If upload fails, still append with `uploaded: false` and `bambuddy_photo_id: null`

### Manifest Clearing

Cleared at two points:
- When `bambuddy_capture_archive_id` fires for a new print (fresh manifest for new print cycle)
- When review state transitions to `idle` and local cleanup runs (if configured)

## Required API Operations

### Confirmed Available
| Operation | Endpoint | Purpose |
|---|---|---|
| Upload photo | `POST /archives/{id}/photos` | Already in design |
| Update archive | `PATCH /archives/{id}` | Already in design |

### Needed for Review (to discover/confirm)
| Operation | Likely Endpoint | Purpose |
|---|---|---|
| List photos | `GET /archives/{id}/photos` | Get current photos with IDs for the review card |
| Delete photo | `DELETE /archives/{id}/photos/{photo_id}` or filename-based variant | Remove a photo from Bambuddy |
| Set cover photo | `PATCH /archives/{id}` with `cover_photo_id` | Designate cover thumbnail |
| Reorder photos | `PATCH /archives/{id}/photos/order` or similar | Change photo display order |

> **Open Item**: The shipped YAML currently uses `photo_id`, while earlier API review suggested delete may be filename-based. Reconcile that contract before enabling review delete actions. Reorder may not be available — if not, the "rearrange" goal is achieved by delete + re-upload in the desired order, or simply by setting the preferred photo as cover.

## New Entities

> **Implementation Status**: Helpers and placeholder REST commands below are **implemented** as part of Phase 2 core. Review scripts (delete, replace, set cover, dismiss), the review popup card, and auto-dismiss automation are **deferred to the advanced phase**. The `photo_review_chip.yaml` conditional card is implemented and wired into `view_print_history.yaml`.

### REST Commands (in `print_history/rest_commands/`)

| Service | Method | Endpoint | Fields |
|---|---|---|---|
| `rest_command.bambuddy_delete_archive_photo` | DELETE | `/api/v1/archives/{archive_id}/photos/{photo_id}` | `archive_id`, `photo_id` — contract still needs live verification |
| `rest_command.bambuddy_set_archive_cover` | PATCH | `/api/v1/archives/{archive_id}` | `archive_id`, `cover_photo_id` — cover contract still needs live verification |

### Scripts (in `print_history/scripts/` — **advanced phase, not yet implemented**)

| Script | Purpose |
|---|---|
| `script.review_delete_photo` | Delete from Bambuddy (if uploaded) + delete local file + update manifest |
| `script.review_replace_photo` | Capture new snapshot → upload → delete old → update manifest |
| `script.review_set_cover` | Call `bambuddy_set_archive_cover` with selected photo |
| `script.review_dismiss` | Set review state → `idle`, optionally clean up local files for removed photos |

### Helpers (in `print_history/helpers/` — **implemented in Phase 2 core**)

| Entity | Type | Purpose |
|---|---|---|
| `input_text.bambuddy_photo_manifest` | input_text (max 4096) | JSON manifest of captured photos for current/last print |
| `input_select.bambuddy_photo_review_state` | input_select | Review lifecycle: `idle`, `pending`, `reviewing` |
| `input_number.photo_review_timeout_hours` | input_number | Hours before auto-dismiss (default: 24, min: 1, max: 168) |

### Automations (in `print_history/automations/` — **advanced phase, not yet implemented**)

| ID | Trigger | Action |
|---|---|---|
| `bambuddy_photo_review_auto_dismiss` | Time elapsed since `pending` > timeout, OR next `print_started` event | Set review state → `idle` |

## Dashboard Card Design

### Review Chip (Print History View)

A conditional chip that appears in `view_print_history.yaml` when `input_select.bambuddy_photo_review_state` != `idle`.

**Implemented**: `dashboard_cards/photo_review_chip.yaml` — shows "📸 Photos to Review" with blue background. Tapping opens more-info for now; advanced phase will replace that with a browser_mod popup and review actions.

### Review Popup (**Advanced Phase**)

The popup renders from the manifest JSON:

```
┌─────────────────────────────────────────────┐
│  📷 Photo Review — Benchy                   │
│  Archive #42 · 4 photos captured            │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐       │
│  │ START   │ │ MID 50% │ │ NEAR    │       │
│  │ [photo] │ │ [photo] │ │ [photo] │       │
│  │ 14:30   │ │ 15:00   │ │ 15:45   │       │
│  │ primary │ │ primary │ │ primary │       │
│  │         │ │         │ │         │       │
│  │ ⭐ 🗑️ 🔄│ │ ⭐ 🗑️ 🔄│ │ ⭐ 🗑️ 🔄│       │
│  └─────────┘ └─────────┘ └─────────┘       │
│                                             │
│  ┌─────────┐                                │
│  │ FINISH  │                                │
│  │ [photo] │                                │
│  │ 16:00   │                                │
│  │ primary │                                │
│  │         │                                │
│  │ ⭐ 🗑️ 🔄│                                │
│  └─────────┘                                │
│                                             │
│  [ Accept All & Close ]                     │
└─────────────────────────────────────────────┘
```

Per-photo actions:
- ⭐ **Set as cover** — calls `script.review_set_cover`
- 🗑️ **Delete** — calls `script.review_delete_photo` (with confirmation)
- 🔄 **Replace** — calls `script.review_replace_photo` (captures new snapshot now, swaps in)

Footer action:
- **Accept All & Close** — calls `script.review_dismiss`

### Implementation Approach

The popup uses `custom:button-card` with JavaScript templates to:
1. Parse `input_text.bambuddy_photo_manifest` JSON
2. Render a grid of `<img>` tags pointing to `/local/printer_snapshots/...` paths
3. Each action button calls the appropriate script via `tap_action: call-service`
4. After each action, the manifest is updated and the card re-renders

### Fallback: No Photos Captured

If the manifest is empty (all capture stages were disabled, or print was too short), the review chip doesn't appear. The `pending` state is only set if the manifest contains at least one entry.

## Current Gap Summary

Implemented now:

- Review-state helper entities
- Manifest persistence helper
- Conditional review chip on the print history dashboard

Still deferred:

- Review popup UI
- Delete / replace / set-cover / dismiss scripts
- Auto-dismiss automation
- Confirmed delete and cover API contracts

## Local File Cleanup

Photos accumulate in `/config/www/printer_snapshots/`. Two cleanup strategies:

### Option A: Review-Driven Cleanup
When the user deletes a photo during review, both the Bambuddy copy and local file are removed. Accepted photos remain locally indefinitely (useful for HA dashboards, notifications history).

### Option B: Rolling Retention (Optional Enhancement)
A separate automation periodically cleans up local photos older than N days. Not part of the review feature itself — could be added later as a maintenance task. Configurable via an `input_number.snapshot_retention_days` helper.

The design starts with Option A. Option B can be layered on later without changing the review feature.

## Integration with Existing Capture Flow

The photo review feature requires minimal changes to the existing capture pipeline:

1. **`capture_and_upload_snapshot` script** — Add manifest entry after each capture/upload (new step at end)
2. **`bambuddy_enrich_archive_on_complete` automation** — After enrichment, set review state to `pending` if manifest is non-empty
3. **`bambuddy_capture_archive_id` automation** — Clear manifest at print start (fresh cycle)

No changes to trigger logic, camera configuration, or upload flow.

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | **Photo list/delete API** — Confirm `GET /archives/{id}/photos` and `DELETE .../photos/{photo_id}` exist | Cannot delete from Bambuddy without DELETE endpoint | Yes for delete action; review/dismiss still work without it |
| 2 | **Cover photo API** — Confirm `cover_photo_id` field on PATCH | Cannot set cover without this | No — nice-to-have; omit ⭐ button if unavailable |
| 3 | **Upload response schema** — Does `POST /archives/{id}/photos` return the `photo_id` in response? | Manifest needs photo_id to map local → Bambuddy photos | Yes for delete/replace; can fall back to listing photos if response doesn't include ID |
| 4 | **input_text max length** — 4096 chars may be tight for 6+ photos with full paths if task names is long | Manifest could be truncated | Low — can truncate paths or use shorter keys |
| 5 | **Photo reorder API** — Likely doesn't exist in Bambuddy | Rearrange limited to cover selection + delete/re-upload | No — cover selection covers the main use case |
