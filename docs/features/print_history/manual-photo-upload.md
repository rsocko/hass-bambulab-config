# Manual Photo Upload

## Scope

Issue #791 adds a lightweight path for attaching one or more photos from the user's phone directly to an existing Bambuddy print archive from the print-history photo gallery popup.

The shipped goal is narrow:

- open the existing photo gallery for an archive
- tap `Add Photo`
- let the mobile browser offer camera or photo-library selection
- upload the selected image(s) into Bambuddy
- refresh the local archive detail so the new photo appears immediately in the gallery and list-view primary-photo flow

This is intentionally not the full deferred photo-review workflow.

## Current UX

The `print-history-photo-gallery-card` now exposes an `Add Photo` action in both the inline card and the full-screen gallery.

On mobile browsers, the hidden file input uses `accept="image/*"` and `capture="environment"`, which gives the browser latitude to offer:

- take a new photo with the rear camera
- choose an existing photo from the library

The exact chooser UI is browser- and OS-dependent, but the feature is designed around the common iPhone and Android camera-roll flow.

Multiple images are allowed. The card uploads them sequentially and shows inline status for preparation, upload progress, success, or failure.

## Transport Design

The browser does not receive the Bambuddy API key directly.

Instead, the custom card sends the selected image through the existing Home Assistant websocket connection to the `bambuddy` custom integration, and the integration performs the authenticated multipart upload to Bambuddy.

Current implementation details:

- selected images are client-side resized before upload
- uploads are encoded as JPEG to keep websocket payload size reasonable
- the integration enforces an 8 MB decoded upload limit per file
- after each successful upload, the integration re-fetches that archive detail from Bambuddy and upserts it into the local print-history store

That last step matters because the browser card reads the same local store contract as the rest of print history. The upload flow should not bypass the local-store projection and leave the UI stale.

## Why This Lives Outside Layer 1

This feature is a mutation and media-management flow. It does not justify broadening Layer 1 with new UI-only fields.

The existing three-layer print-history contract still applies:

- Layer 1 keeps normalized archive/detail payloads and broadly useful derived data
- mutation-specific upload state lives in the card and the integration response path
- final gallery wording remains in the card

## Constraints

- this path depends on the browser being able to decode the chosen source image
- the card currently re-encodes uploads to JPEG, so transparency in original PNG/WebP images is not preserved
- very large original photos may still fail if the browser cannot decode or canvas-encode them reliably
- this is designed for archive attachment, not for local photo curation or replacement semantics

## Future Phase Options

### Desktop Upload

The current file-picker path is already usable on desktop browsers, but a future desktop-focused phase could improve it with:

- drag-and-drop onto the gallery
- paste-from-clipboard support
- clearer batching/progress UI for larger uploads
- optional preservation of original PNG/WebP format instead of always transcoding to JPEG

### Extract Images Embedded In `.3mf`

A useful later phase is to surface images embedded inside the archive's `.3mf` so the operator can choose one or more to attach to the archive.

The likely shape is:

1. parse the `.3mf` ZIP server-side from the archive's source file or stored `.3mf`
2. enumerate candidate image assets from standard package parts and Bambu/Studio-specific preview locations
3. generate a lightweight preview list in HA
4. let the user select one or more images to import into Bambuddy as archive photos

This should remain a separate phase because it introduces materially different concerns:

- ZIP/package parsing and file provenance
- source-asset discovery rules across sliced `.3mf` vs project `.3mf`
- duplicate detection between embedded previews and already-uploaded archive photos
- UX for selecting several images instead of a single immediate camera/library action

### Best Next Step For `.3mf` Images

If that phase is picked up, the first implementation should be read-only discovery:

- inspect real `.3mf` files already present in the archive/backfill corpus
- document where preview/model images actually live across the file variants in use here
- only then add import actions into the archive gallery

That keeps the current issue focused on the mobile upload path without overcommitting to assumptions about `.3mf` image layout.