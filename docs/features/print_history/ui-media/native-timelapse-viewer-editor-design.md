# Native Timelapse Viewer And Editor Design

## Scope

This document covers the next timelapse phase for print-history in Home Assistant:

- keep playback inside the existing archive popup flow
- add richer native playback controls, including speed selection
- add an editor surface for trim, thumbnails, and Bambuddy-backed processing
- keep server-side transcoding and media mutation in Bambuddy instead of moving FFmpeg into Home Assistant

This is a follow-on to the shipped scan/upload/viewer slice documented in `timelapse-actions-and-viewer.md`.

## Current Status

The first implementation slices now exist in the repo:

- HA proxy routes for `timelapse/info`, `timelapse/thumbnails`, and `timelapse/process`
- a richer timelapse viewer card with playback speed controls and metadata fetches
- a dedicated native editor card shell that loads info and thumbnails on demand and submits processing requests through the HA proxy layer

The trim UI is still a phase-1 shell. It intentionally uses numeric trim inputs before introducing a heavier interactive timeline control.

## Goals

- preserve the current HA-native popup workflow instead of redirecting the user into Bambuddy
- reuse Bambuddy's existing timelapse backend endpoints for info, thumbnails, and processing
- avoid copying Bambuddy frontend code into this repo
- keep dashboard work lightweight and lazy so popup open cost stays low

## Non-Goals

- no iframe embedding of the Bambuddy archives page
- no direct reuse of Bambuddy React viewer/editor components
- no browser-side transcoding or trim/export pipeline in Home Assistant
- no change to the current single-timelapse-per-archive contract

## Architecture

### Playback

The existing viewer already streams Bambuddy's raw timelapse file through a native `<video>` element.

That remains the right media source for phase 1 of the richer viewer because the upstream playback endpoint is already designed for browser media tags and does not require auth headers on the request itself.

### Editor API Boundary

The editor depends on three upstream Bambuddy endpoints:

- `GET /api/v1/archives/{id}/timelapse/info`
- `GET /api/v1/archives/{id}/timelapse/thumbnails`
- `POST /api/v1/archives/{id}/timelapse/process`

Home Assistant should proxy those through authenticated integration views so the frontend keeps the same trust boundary as the existing upload proxy.

### Print-History Layering

Keep the current three-layer print-history contract intact.

- do not project timelapse editor metadata into Layer 1
- do not cache thumbnail strips inside the archive projection store
- fetch info and thumbnails on demand when the popup editor is opened
- keep popup wording and editor-only state in Layer 3 custom cards

The only archive mutation that should flow back into the local store is the refreshed archive detail after a successful replace-style process operation.

## UI Structure

### Popup Entry Point

Reuse the existing `View Timelapse` action and popup plumbing in `print-history-archive-actions-card.js`.

The popup should stay a print-history popup, not a separate page.

### Viewer Card

The current `print-history-timelapse-card.js` should become the richer viewer shell.

Planned viewer responsibilities:

- playback
- playback-rate selection
- quick skip controls
- open-in-new-tab fallback
- handoff into editor mode

### Editor Card

Add a dedicated editor card under the same popup stack.

Planned editor responsibilities:

- fetch timelapse info on demand
- fetch thumbnail frames on demand
- collect trim start and trim end
- collect speed and save mode
- optionally collect a replacement audio track
- submit process requests through the HA proxy route
- refresh archive detail after success

## Component Choices

### Viewer

Preferred: `Media Chrome`

Reasons:

- MIT licensed
- web-component oriented
- fits the repo's plain custom-card style well
- works with native media elements instead of forcing a framework migration

Fallback: `Plyr`

Use it only if Media Chrome turns out awkward in the current Home Assistant shadow-root setup.

### Trim Control

Preferred: `noUiSlider`

Reasons:

- MIT licensed
- dual-handle range support
- keyboard accessible
- lightweight and dependency free

### Deferred Audio UX

Optional later addition: `wavesurfer.js`

This is a future enhancement for richer audio overlay workflows. It is not required for the first editor slice.

## Data Flow

1. User opens `View Timelapse` from the popup.
2. HA renders the viewer card immediately using the direct timelapse media URL.
3. HA only fetches editor metadata when the editor surface is opened.
4. The editor requests info and thumbnails through HA proxy endpoints.
5. The editor submits trim and speed changes through the HA process proxy.
6. The integration refreshes archive detail in the local store after successful processing.
7. The popup rerenders from the refreshed local archive snapshot.

## Backend Work

### Integration Endpoints

Add Home Assistant proxy views for:

- timelapse info
- timelapse thumbnails
- timelapse process

Those views should live beside the existing source-3MF and timelapse upload views in the Bambuddy integration.

### API Client

Extend `BambuddyApiClient` with wrappers for the same three upstream endpoints.

### Refresh Behavior

For `save_mode = replace`, always refresh archive detail back into the local print-history store.

For `save_mode = new`, still return the process payload, but do not expand Layer 1 just to surface alternate output files.

## Frontend Work

### Phase 1

- richer playback controls in the existing timelapse card
- new HA proxy endpoints in place
- editor card shell with basic form controls and submit flow

### Phase 2

- thumbnail strip timeline
- dual-handle trim UI with `noUiSlider`
- popup-level view or edit toggle

### Phase 3

- optional audio overlay affordances
- stronger preview behavior for trim loops
- save-as-new affordances if a concrete archive/file-management story is needed

## Phase Plan

1. Implement HA proxy routes and client methods for `info`, `thumbnails`, and `process`.
2. Add smoke tests for those proxy views.
3. Upgrade the existing timelapse card into a richer viewer.
4. Add a dedicated editor card that uses the new proxy routes.
5. Add trim thumbnails and `noUiSlider` once the shell is stable.
6. Revisit optional audio waveform UX only after the trim and speed workflow is solid.

## Testing

- add integration smoke tests for the new proxy views
- keep structural tests asserting that the new routes and docs stay registered
- prefer popup-lazy loading for thumbnails so dashboard performance does not regress

## Rationale

This design keeps the UX native to Home Assistant, keeps the heavy media processing where it already belongs, and avoids the licensing and maintenance cost of copying Bambuddy frontend code.