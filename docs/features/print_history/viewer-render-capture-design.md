# Viewer Render Capture Design

Issue `#748` adds a user-driven way to capture the current archive viewer render and store it as a normal archive photo when the interactive viewer is a better visual summary than the parser-generated thumbnail. This matters most for Hueforge and other multi-color prints where the stock thumbnail can underrepresent the actual appearance.

## Current Design

The shipped design is now fully popup-owned.

- the 3D viewer popup card owns rendering, capture, crop, preview, and upload
- the viewer no longer opens a separate HTML page or tab for crop mode
- the capture result uploads through the existing `bambuddy/print_history_upload_photo` websocket command
- the viewer-capture flow no longer includes `Upload + Use In List View`

The popup now has a single interaction surface:

- `Capture View` exports the current full-frame render
- `Crop Capture` toggles inline crop mode and then captures the selected crop
- `Download PNG` and `Upload to Archive` operate on the current capture draft

## Goals

- let the user capture the exact render they are already looking at in the popup
- support both full-frame capture and operator-defined crop without leaving the popup
- store the result as a normal archive photo in Bambuddy
- keep the feature user-driven
- keep the capture path renderer-agnostic so it works for G-code preview now and future model rendering later

## Non-Goals

- automatically capturing every archive render
- changing Bambuddy's canonical `thumbnail_path`
- storing crop geometry in Layer 1
- reintroducing a second standalone viewer surface for capture authoring
- solving general cover-photo or timelapse management here

## Layering Boundary

This remains a popup/viewer workflow, not a Layer 1 projection concern.

- Layer 1 stays focused on normalized archive/detail payloads and reusable derived data
- crop rectangles, capture drafts, and button state stay in popup memory only
- wording and controls belong in the popup card and existing photo-gallery UI

Do not push crop metadata or popup-only UI state into Layer 1 just to simplify one viewer action.

## Why The Standalone Page Was Removed

The earlier implementation used a separate HA-served HTML page for advanced crop mode. That design was retired because it created avoidable complexity:

- duplicate rendering code in the popup and standalone page
- separate auth handling for direct HTTP requests from the page
- page/tab transitions that broke the operator's framing flow
- stale-cache and version skew risk across two viewer surfaces

Once the popup card absorbed crop state directly, the standalone HTML page, companion JS file, and page-only HTTP routes no longer justified their maintenance cost.

## UX

### Entry point

All viewer capture actions live in the popup card toolbar.

- `Capture View`
- `Crop Capture`
- `Refresh`
- `Download G-code`

The preview tray below the stage owns the capture-result actions:

- `Download PNG`
- `Upload to Archive`

### Crop interaction

Crop mode is an overlay on the existing popup stage.

- default crop box starts centered in the stage
- drag inside the box to move it
- drag corner handles to resize it
- dimmed masks show the excluded region
- presets control aspect behavior

Supported presets:

- `Square`
- `Freeform`
- `Landscape 4:3`
- `Landscape 16:9`

`Square` remains the default because it is the closest match to thumbnail-like replacement behavior. The landscape presets are better when the user wants framing that reads well in the wider list card.

### Preview tray

After capture, the popup shows:

- rendered PNG preview
- pixel dimensions
- current archive context
- whether the capture was full-frame or cropped

This preview is intentionally local and ephemeral until the user downloads or uploads it.

## Technical Design

### Frontend boundary

All capture and crop orchestration now lives in `print-history-3d-viewer-card.js`.

The popup card owns:

- archive context
- render-surface lifecycle
- crop overlay state
- preview-draft state
- upload state and status messaging

This keeps the feature on the same surface the user is already using.

### Capture model

Capture is a renderer-agnostic bitmap export from the active popup canvas.

Client-side flow:

1. identify the active viewer canvas
2. map the crop rectangle from popup stage coordinates into source-canvas coordinates when crop mode is active
3. copy the relevant pixels into an offscreen 2D canvas
4. encode as PNG
5. show the capture preview locally
6. upload through `bambuddy/print_history_upload_photo` when requested

This design works for the current `gcode-preview` canvas and remains compatible with a future Three.js canvas as long as the render surface stays same-origin and exportable.

### Upload contract

Viewer capture reuses the existing websocket upload contract.

- `archive_id`
- `file_name`
- `mime_type`
- `content_base64`

Suggested filename pattern remains:

`viewer-capture-{archive_id}-{renderer_mode}-{timestamp}.png`

Cropped captures reuse the same contract and do not need a separate backend endpoint.

## Data And State

Only the uploaded archive photo persists.

Popup-only in-memory state includes:

- `rendererMode`
- `cropMode`
- `cropAspectPreset`
- `cropRect`
- `captureDraft`
- `uploadInProgress`

None of this state should be persisted in store tables.

## Constraints

### Renderer availability

The current viewer still prioritizes the G-code preview path, so capture must remain tied to the active canvas rather than to any specific renderer implementation.

### WebGL export edge cases

Canvas export can still fail if the render surface is tainted or not yet painted. The popup therefore keeps full-frame capture as the primary action and treats crop as an enhancement on top of the same canvas-export primitive.

### Mobile ergonomics

Precise crop handles are inherently less comfortable on small screens. Full-frame capture remains the safest default, while crop mode stays available when tighter framing matters.

## Implementation State

Implemented:

- inline popup capture
- inline popup crop overlay with aspect presets
- popup preview tray
- popup upload through websocket photo upload
- removal of the standalone viewer page and companion script
- removal of the standalone-only viewer capture HTTP routes

Deferred:

- automatic capture
- canonical thumbnail mutation
- any viewer-driven primary-photo promotion shortcut

## Recommendation

Keep viewer capture popup-owned. It matches the user's framing context, minimizes auth and caching complexity, and avoids maintaining two separate viewer implementations for the same archive action.