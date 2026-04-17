# Viewer Render Capture Design

Issue `#748` explores a user-driven way to capture the archive viewer rendering and store that result with the Bambuddy archive when the rendered model is a better visual summary than the parser-generated thumbnail. This is especially relevant for Hueforge and other multi-color prints where the stock thumbnail can underrepresent the final appearance.

## Problem Statement

The current print-history media model already supports:

- Bambuddy's canonical archive thumbnail
- archive photo attachments uploaded through the Home Assistant integration
- a local primary-photo override used for list/popup preview rendering
- a dedicated 3D viewer popup for issue `#747`

What is missing is a way for the operator to promote the viewer rendering itself into the archive media set.

The title of issue `#748` says "replace the thumbnail," but for Phase 1 that is the wrong boundary. The canonical Bambuddy `thumbnail_path` should remain parser-derived. The lower-risk path is:

1. capture a user-approved viewer render
2. upload it as a normal archive photo through the existing HA-mediated upload path
3. optionally set it as the local primary photo for print-history list/popup rendering

That gives the user the practical outcome they want without inventing a new thumbnail-mutation contract.

## Goals

- let the user manually capture the current viewer output from the existing HA-served viewer page
- support either full-frame capture or an operator-defined crop
- store the result as a normal archive photo in Bambuddy
- optionally promote the captured image to the local primary-photo override immediately
- keep the feature user-driven in Phase 1
- keep the design renderer-agnostic so it works for G-code preview now and Three.js model rendering later

## Non-Goals

- automatically capturing every archive render
- changing Bambuddy's canonical `thumbnail_path` in Phase 1
- storing viewer-only crop metadata in Layer 1
- building a second standalone media-review system outside the existing archive popup/gallery flow
- solving full timelapse or cover-photo management as part of this issue

## Layering Boundary

This feature is a popup/viewer mutation workflow, not a Layer 1 projection concern.

- Layer 1 remains the normalized archive/detail payload plus broadly reusable derived fields
- local workflow state belongs in the viewer page, popup state, and existing Variant 3 store tables where needed
- final wording and operator controls belong in the viewer page and photo gallery UI

Do not add viewer-crop rectangles, crosshair labels, or capture-button state into Layer 1 archive rows just to simplify one popup action.

## Existing Foundations

The repository already has the core building blocks needed for a Phase 1 implementation:

- `print-history-3d-viewer.html` is a standalone HA-served page, so capture UI can live there without destabilizing the main history card
- `bambuddy/print_history_upload_photo` already accepts browser-provided base64 image content and uploads it to Bambuddy without exposing the API key client-side
- `bambuddy.set_print_history_primary_photo` already lets the UI promote any archive photo path to the list/popup preview image
- the Variant 3 local store already refreshes archive detail after upload and already tracks media-review state

That means issue `#748` should reuse the existing upload and primary-photo paths rather than inventing a sidecar or separate asset pipeline for Phase 1.

## Options Explored

### Option A: Full Viewer Capture Only

Add a single `Capture View` button that saves the active render surface exactly as shown.

Pros:

- smallest implementation slice
- easy to explain
- no extra selection UI

Cons:

- does not let the user exclude dead space, legends, or future controls
- may produce poor framing for tall or off-center models

### Option B: Full Capture Plus Crop Box

Let the user toggle a crop mode, drag a crop rectangle over the viewer stage, preview the result, then upload.

Pros:

- matches the issue request most closely
- avoids saving large amounts of empty build-volume area
- keeps the operator in control for special cases like Hueforge or plate subsets

Cons:

- more UI state to manage
- needs careful mobile interaction design

### Option C: Browser-Native Screenshot Instructions

Do not build capture at all. Instead, tell the user to take an OS/browser screenshot and use the existing `Add Photo` flow.

Pros:

- nearly zero engineering work

Cons:

- poor UX
- inconsistent cropping and file naming
- loses the opportunity to bind directly to the active archive/viewer context

### Option D: Server-Side or Sidecar Render Capture

Re-render the model elsewhere and write back a replacement thumbnail or generated photo.

Pros:

- future path for automation

Cons:

- overbuilt for the current ask
- introduces renderer parity problems and extra moving parts
- not necessary while the requirement is explicitly user-driven

## Recommended Direction

Phase 1 should implement **Option B** with a deliberately narrow scope:

- `Capture View` for full-frame save
- `Crop Capture` for user-defined crop on the viewer stage
- upload result as a normal archive photo
- optional checkbox or second action to `Use In List View`

If implementation pressure is high, Phase 1 can ship as **Option A first** and keep the crop overlay as Phase 1.1. The backend contract should not care which one produced the final image blob.

## UX Proposal

### Entry point

Add capture actions inside the existing viewer page toolbar, not the main browser card.

Recommended toolbar actions:

- `Capture View`
- `Crop Capture`
- `Upload to Archive`
- `Upload + Use In List View`

Refinement:

- `Capture View` immediately snapshots the current render surface and opens a lightweight preview tray
- `Crop Capture` enters selection mode with a resizable crop rectangle over the stage
- `Upload...` actions are disabled until a capture exists

### Preview tray

After capture, show a compact preview tray below the stage with:

- rendered preview image
- pixel dimensions
- current archive name/id context
- `Retake`
- `Upload to Archive`
- `Upload + Use In List View`

### Crop interaction

Use a simple overlay on the viewer stage:

- default crop box centered in the stage
- drag to move
- corner handles to resize
- dimmed outside region
- optional crosshair lines for alignment

Keep the interaction intentionally basic. No rotation, perspective correction, or annotation tools.

### Aspect-ratio guidance

Phase 1.1 should not hard-enforce one output ratio for all captures.

- the existing archive photo pipeline already supports arbitrary image sizes
- Bambuddy's parser-generated thumbnail artifacts appear to be square-like in current sample/archive naming (`200x200`)
- the shipped print-history list card renders preview images in a wide landscape slot with `object-fit: cover`

That means the right UX is **preset-guided cropping**, not a mandatory ratio lock:

- `Square` is the best default when the user is trying to create a thumbnail-like replacement
- `Landscape 4:3` and `Landscape 16:9` are better fits for wide card presentation and camera-style framing
- `Freeform` remains useful for unusual prints such as tall plates or narrow Hueforge compositions

The Phase 1.1 implementation should therefore offer aspect presets and make `Square` the initial default, while still allowing the operator to switch to wider framing when the model composition calls for it.

### Mobile behavior

On narrow screens:

- crop mode should use a single drag target and larger handles
- preview tray collapses below the stage
- full-frame capture remains the default recommendation because precise cropping will be harder on phones/tablets

## Technical Design

### Frontend boundary

All capture orchestration should live in `print-history-3d-viewer-page.js` and the viewer HTML page.

The viewer page already owns:

- archive context from query params
- render-surface lifecycle
- toolbar controls
- status messaging

That makes it the right place to add ephemeral capture state.

### Capture model

Treat capture as a renderer-agnostic bitmap export from the active stage.

Proposed client-side flow:

1. identify the active render surface canvas inside the viewer stage
2. copy the current canvas pixels into an offscreen 2D canvas
3. if crop mode is active, draw only the selected stage rectangle
4. encode the result as PNG for Phase 1 to preserve crisp edges and avoid JPEG artifacts on linework and Hueforge gradients
5. preview the encoded result locally
6. send it through the existing `bambuddy/print_history_upload_photo` websocket command

This should work for the current G-code preview canvas and should also work for a future Three.js canvas as long as the render surface is same-origin and not tainted.

### Why canvas export first

Trying to screenshot the entire DOM stage would likely require an extra dependency such as `html-to-image` and could become brittle.

For Phase 1, the valuable part is the rendered model itself. Capturing the actual render canvas is:

- simpler
- more deterministic
- independent of decorative DOM around the stage

If the user later wants the exact page chrome included, that can be a later enhancement.

### Upload contract

Do not create a new upload endpoint for this feature.

Reuse the current websocket contract used by `Add Photo`:

- `archive_id`
- generated `file_name`
- `mime_type`
- `content_base64`

Suggested filename pattern:

`viewer-capture-{archive_id}-{renderer_mode}-{timestamp}.png`

Examples:

- `viewer-capture-101-gcode-20260417T211530Z.png`
- `viewer-capture-101-model-20260417T211804Z.png`

### Post-upload actions

After a successful upload:

1. rely on the existing integration refresh path to upsert the new photo into the local store
2. if the user chose `Upload + Use In List View`, call `bambuddy.set_print_history_primary_photo` with the uploaded photo path returned by the refreshed archive detail
3. optionally mark media review `review_status=completed` with `last_action=viewer_capture_upload` when the archive was opened from a pending review workflow

## Data And State

### Do not persist crop geometry in store tables for Phase 1

Crop rectangles are temporary authoring state. Persisting them adds complexity without clear reuse value.

Only persist what already matters to the archive workflow:

- the uploaded image as an archive photo in Bambuddy
- optional local primary-photo override
- optional media-review state transition

### Optional ephemeral viewer state

The viewer page may maintain in-memory state such as:

- `rendererMode`
- `captureDraft`
- `cropRect`
- `captureStatus`
- `uploadInProgress`

None of that needs to leave the page.

## Risks And Constraints

### Renderer availability

Issue `#748` talks about Three.js rendering, but the current shipped viewer still prioritizes the G-code preview path. The capture design must therefore be tied to the active render surface, not to a specific renderer implementation.

### WebGL export edge cases

Canvas export from a WebGL surface can fail if the canvas becomes tainted or if preserve/draw timing is wrong. Phase 1 should explicitly test:

- current `gcode-preview` path
- future Three.js model path when added
- desktop Chrome/Edge
- mobile Safari / HA companion-app webview if used

### Mobile crop ergonomics

Precise crop handles may be awkward on smaller touch devices. This is another reason to keep full-frame capture as a first-class action rather than forcing crop mode.

### Not a real thumbnail replacement yet

Phase 1 should be described as `capture and promote a viewer render`, not as mutating Bambuddy's canonical thumbnail record. That avoids creating a misleading contract the backend does not currently support.

## Phased Plan

### Phase 1

- add viewer toolbar capture actions
- support full-frame canvas capture
- preview the captured image before upload
- upload via existing websocket photo-upload path
- optionally set uploaded photo as local primary photo

### Phase 1.1

- add crop overlay and crop preview
- add mobile-tuned crop handles and stage hit targets

### Phase 2

- add a one-tap `Use current render` action from the archive popup or viewer launcher
- optionally remember the user's last preference for `upload only` vs `upload + use in list view`
- evaluate whether a local `cover photo` abstraction is useful beyond primary-photo selection

### Phase 3

- evaluate automatic or semi-automatic render capture after archive import/render readiness
- only then revisit whether a sidecar or backend-supported thumbnail replacement is justified

## Implementation Checklist

- add capture controls to the existing viewer page
- expose the active render canvas through a small internal helper instead of coupling button handlers to one renderer path
- implement full-frame export to PNG blob/base64
- wire upload to the existing websocket command
- add optional `Upload + Use In List View` action
- add tests for viewer page markup/strings and the upload action wiring
- validate that the refreshed archive detail returns the new photo path needed for primary-photo promotion
- document the workflow in popup/media-review docs after the UI lands

## Recommendation

Build Phase 1 on top of the existing archive-photo pipeline and local primary-photo override. That gives the user the practical effect of replacing the visible thumbnail in Home Assistant, while avoiding premature mutation of Bambuddy's canonical thumbnail metadata.

If the Phase 1 canvas-export path proves reliable across browsers, it becomes the stable authoring primitive for later automatic capture work as well.