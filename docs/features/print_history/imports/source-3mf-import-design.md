# Source 3MF Import Design

> **Status**: Popup-driven Home Assistant source-3MF image import is still design-only.
>
> **Current live state**: The repo already ships a separate forensics provenance path through [tools/bambuddy/gcode_forensics_viewer.py](../../../tools/bambuddy/gcode_forensics_viewer.py) and [tools/bambuddy/run_forensics_import_queue.py](../../../tools/bambuddy/run_forensics_import_queue.py) for local source selection, manifest writeback, and optional Bambuddy `POST /api/v1/archives/{id}/source` attachment. That existing path is not the popup/gallery feature designed in this document.
>
> **Scope boundary**: This feature is about importing useful images and limited metadata from a user-supplied source `.3mf` into an existing Bambuddy archive from the Home Assistant print-history popup. It is not a replacement for Bambuddy's canonical archive upload flow and it is not an in-place archive repair mechanism.

See also:

- `../../model_library/model-library-strategy.md`
- `../../model_library/integration/ha-model-library-integration.md`

## Overview

Home Assistant already exposes a shipped popup and gallery flow for archive photos:

- upload phone or desktop photos through the HA websocket bridge
- delete archive photos
- choose the preferred local primary photo for list and popup rendering
- dismiss local media review

This design adds a second, archive-scoped import source:

- user selects a `.3mf` file from the popup
- HA parses the uploaded `.3mf` server-side
- HA presents discovered candidate images and metadata
- user chooses `none`, `some`, or `all` candidate images to import into Bambuddy as archive photos
- optional limited metadata can be written back to the archive as notes, tags, or external link fields

The intended real-world source is the original Bambu Studio or MakerWorld project `.3mf`, not the already archived sliced `.gcode.3mf` payload.

## Relationship To Forensics Recovery

This document covers the popup-driven source `.3mf` attachment and image-import flow for an archive that already exists.

It is adjacent to, but distinct from, the local forensic recovery workflow built around:

- [tools/bambuddy/gcode_forensics_viewer.py](../../../tools/bambuddy/gcode_forensics_viewer.py)
- [tools/bambuddy/run_forensics_import_queue.py](../../../tools/bambuddy/run_forensics_import_queue.py)
- [archive-historical-backfill-from-sd-card.md](./archive-historical-backfill-from-sd-card.md)

That distinction matters because there are now three separate operator intents:

1. `create_archive_upload`
  - create a new canonical Bambuddy archive from a sliced `.3mf` or `.gcode.3mf`
2. `attach_source_only`
  - attach a source/project `.3mf` to an existing archive for provenance and later image extraction
3. `wrap_raw_gcode_experimental`
  - future experimental path that would try to synthesize a Bambu-style package from raw `.gcode`

Only the second item belongs to this document.

The repo's forensics runner can now execute that second path directly when the manifest writeback already identifies a target archive:

- `attach_source_only` with `archive_id` set
- upload through Bambuddy `POST /api/v1/archives/{id}/source`

That execution path is still provenance-only. It does not convert a raw `.gcode` into a canonical archive artifact and it does not replace `POST /archives/upload`.

## Goals

- let the operator attach richer model-facing imagery to an existing archive without leaving the HA popup
- reuse the existing archive photo pipeline rather than inventing a separate image store
- support `keep none`, `keep some`, and `keep all` selection
- preserve provenance so imported images remain distinguishable from printer-camera photos
- optionally surface extracted MakerWorld-related metadata in a controlled way

## Non-Goals

- replacing Bambuddy's `POST /archives/upload` canonical archive creation flow
- repairing a missing or wrong `file_path` on an existing Bambuddy archive
- replacing Bambuddy's `source_3mf_path` feature
- building a general-purpose 3MF file manager in HA
- synchronizing arbitrary parsed project-page fields back into Bambuddy's schema
- exercising or validating a future raw-gcode-to-`.gcode.3mf` synthesis path

## Why This Belongs In HA

Bambuddy already supports:

- archive photo uploads
- archive source-3MF attachment
- archive thumbnail and project-page reads from the main archived `.3mf`

But current Bambuddy behavior does not provide the workflow this feature needs:

- `POST /archives/{id}/source` stores the uploaded `.3mf` as `source_3mf_path` only
- it does not automatically import embedded source images into archive photos
- it does not prompt the user to choose which embedded images to keep
- it does not automatically write selective project metadata back into archive fields

It also does not turn a raw `.gcode` into a canonical `.gcode.3mf`, and it should not be treated as a fallback for the experimental raw-wrap path.

HA already owns the popup UX and already has the authenticated photo-upload bridge, so HA is the correct place for the operator selection workflow.

## User Stories

### Story 1: Import one cover image

1. User opens an archive popup.
2. User taps `Import From 3MF`.
3. User selects a source project `.3mf` from phone or desktop.
4. HA parses the file and shows discovered images.
5. User selects only the best model image.
6. HA uploads that image to Bambuddy as an archive photo.
7. User optionally sets it as the local primary photo.

### Story 2: Import all useful images

1. User selects a multi-image MakerWorld project `.3mf`.
2. HA shows model pictures, profile pictures, and embedded thumbnails in separate groups.
3. User chooses `Import All Model Pictures` and skips profile pictures and thumbnails.
4. HA uploads the selected images sequentially and refreshes archive detail.

### Story 3: Metadata-only import

1. User uploads a source `.3mf` but decides not to import any images.
2. HA still shows extracted metadata such as title, designer, and MakerWorld URL.
3. User chooses to write only a source URL and a structured notes block.

## High-Level Architecture

The feature should use a two-step server-side flow.

### Step 1: Discovery

Browser sends uploaded `.3mf` to HA.

HA:

- validates size and extension
- parses the ZIP/package server-side
- extracts candidate images and metadata
- returns a lightweight discovery manifest to the popup

### Step 2: Import

Browser sends the selected candidate IDs back to HA.

HA:

- reuses the already parsed in-memory or temporary-file representation
- uploads selected images to Bambuddy via the existing authenticated multipart bridge
- optionally patches limited metadata to Bambuddy
- refreshes local archive detail and local SQLite state

## Transport Decision

Do not reuse the current base64-over-websocket image upload path for raw `.3mf` files as the primary transport.

Reason:

- source `.3mf` files can be much larger than the current manual-photo workflow
- base64 expansion is wasteful for ZIP archives
- browser resizing/transcoding benefits used for photos do not apply to 3MF files

### Recommended transport

Add a dedicated HA HTTP upload view for temporary source-3MF intake.

Recommended shape:

- `POST /api/bambuddy/print-history/source-3mf/discover`
- request: multipart form with `archive_id` and `file`
- response: JSON discovery manifest

The browser card can still trigger the flow from the existing popup, but the file upload itself should be plain multipart HTTP to HA.

### Why an HTTP view is preferred here

- avoids base64 overhead
- works better for larger desktop and mobile file uploads
- aligns with the fact that the payload is a file, not a lightweight command
- keeps the Bambuddy API key on the HA side, just like the current photo upload bridge

## Parsing Scope

The parser should support both sliced `.3mf` files and source/project `.3mf` files, but the selection UX should classify outputs differently.

### Candidate image groups

The discovery manifest should classify candidate images into:

- `model_pictures`
  - expected from source/project `.3mf`
  - often the most useful user-facing import targets
- `profile_pictures`
  - expected from MakerWorld-style project payloads
  - may be useful but lower priority than model pictures
- `project_thumbnails`
  - expected from `Auxiliaries/.thumbnails/`
  - usually lower-value fallback images
- `plate_previews`
  - expected from sliced `.3mf` under `Metadata/plate_*.png`
  - useful fallback when no richer source imagery exists
- `top_previews`
  - expected from `Metadata/top_*.png`
  - useful as alternates, but lower priority than plate renders
- `pick_previews`
  - expected from `Metadata/pick_*.png`
  - default hidden or disabled in import UI because they are usually not user-facing cover art

### Candidate metadata fields

The discovery response should normalize these fields when present:

- `title`
- `description`
- `designer`
- `designer_user_id`
- `license`
- `creation_date`
- `modification_date`
- `makerworld_url`
- `makerworld_model_id`
- `profile_title`
- `profile_description`
- `profile_user_name`
- `design_profile_id`
- `design_region`

### Parsing precedence

Prefer richer project-page data over sliced-preview fallbacks.

Recommended priority for proposed `default import` suggestions:

1. `model_pictures`
2. `profile_pictures`
3. `project_thumbnails`
4. `plate_previews`
5. `top_previews`
6. `pick_previews`

## Discovery Manifest Contract

The discovery response should be explicit enough that the frontend does not need to infer image classes.

Recommended shape:

```json
{
  "archive_id": 123,
  "session_id": "b2d11d3f...",
  "source_file": {
    "filename": "My Model.3mf",
    "size_bytes": 4821931,
    "kind": "source_3mf",
    "has_gcode": false,
    "has_model_mesh": true
  },
  "metadata": {
    "title": "Hueforge Back to the Future",
    "designer": "StefBull85",
    "makerworld_url": "https://makerworld.com/en/models/775698",
    "makerworld_model_id": "775698"
  },
  "candidates": [
    {
      "candidate_id": "model-1",
      "group": "model_pictures",
      "label": "Model Picture 1",
      "path": "Auxiliaries/Model Pictures/cover.png",
      "content_type": "image/png",
      "width": 1024,
      "height": 1024,
      "size_bytes": 188233,
      "suggested": true,
      "default_selected": true,
      "preview_url": "/api/bambuddy/print-history/source-3mf/session/b2d11d3f/candidate/model-1"
    }
  ],
  "selection_presets": {
    "recommended": ["model-1"],
    "all_images": ["model-1", "thumb-1", "plate-1"]
  },
  "warnings": [
    "Embedded pick previews are excluded from default import."
  ]
}
```

## Temporary Storage Model

The HA side needs a short-lived import session between discovery and import.

### Recommended model

- store uploaded `.3mf` in a short-lived temp directory under HA config or system temp
- create a `session_id`
- persist parsed candidate metadata in memory with expiry, or in a lightweight temp manifest file
- expire unused sessions automatically after a short TTL such as 30 to 60 minutes

### Why a session is needed

- avoids sending the `.3mf` twice
- lets the popup preview candidates before committing imports
- keeps import operations deterministic against the exact parsed file

## Import Actions

The popup should support three explicit action families.

### 1. Import Images

Uploads selected candidates to Bambuddy as archive photos.

Recommended behavior:

- upload sequentially for simpler progress reporting and error handling
- preserve original PNG/JPEG/WebP format when possible
- assign a deterministic imported-photo role label in HA-local state, for example `imported_3mf`
- refresh archive detail once after the batch, not after every single image, unless Bambuddy response shape forces per-image refresh

### 2. Import and Use As Primary

After image import completes, optionally set one imported image as the local primary photo using the existing local selection path.

This should remain HA-local by default, because current behavior already prefers a local primary-photo override rather than a Bambuddy cover-photo write.

### 3. Import Metadata

Metadata import should be optional and granular.

Recommended write targets:

- `external_url`
  - set from `makerworld_url` only when archive has no existing external URL or user explicitly allows overwrite
- `notes`
  - append a structured `[HA_3MF_IMPORT_V1]` block rather than replacing existing notes
- `tags`
  - optional system-style tags such as `makerworld:775698` or `designer:StefBull85` only if consistent with existing enrichment policy

Do not attempt to write arbitrary project-page fields directly into Bambuddy unless Bambuddy gains a supported API contract for them.

## Notes Block Recommendation

If metadata write-back is enabled, use a versioned hidden notes block.

Example:

```text
[HA_3MF_IMPORT_V1]
{"source_filename":"My Model.3mf","makerworld_url":"https://makerworld.com/en/models/775698","makerworld_model_id":"775698","designer":"StefBull85","imported_candidate_ids":["model-1","thumb-1"],"imported_at":"2026-04-16T18:45:00Z"}
```

This keeps provenance machine-readable without widening Layer 1 for a feature-specific mutation history.

## Duplicate Handling

This feature needs duplicate rules at the image level, not the archive level.

### Recommended first-pass duplicate rules

- do not import the same candidate twice within one session
- if a candidate image hash matches an already imported image from the same session, skip duplicate upload
- do not attempt cross-archive global image dedupe in the first phase
- do not try to compare imported images against Bambuddy thumbnails by pixel similarity in the first phase

### Optional later enhancement

Add an HA-local heuristic that warns when an imported image appears to duplicate the archive thumbnail or an existing archive photo.

## UX Design

### Entry point

Add a popup action in the existing photo gallery or archive popup:

- `Import From 3MF`

This should sit near `Add Photo`, not near archive repair actions.

### Discovery state

After file selection, show:

- upload and parse progress
- parsed metadata summary
- grouped image gallery with checkboxes or selection chips
- `Select None`, `Select Recommended`, `Select All Visible`

### Selection behavior

The UI must support:

- deselect everything
- select one image only
- select an arbitrary subset
- select all within a group
- import nothing but keep metadata choices

### Suggested defaults

- if `model_pictures` exist, preselect recommended model pictures only
- if only sliced previews exist, preselect `plate_previews`
- never preselect `pick_previews`

### Post-import affordances

After import:

- show imported images immediately in the popup gallery
- offer `Use imported image in list view` if a single obvious candidate exists
- keep `Dismiss Review` separate from import completion

## Security and Validation

### File validation

- extension must be `.3mf`
- validate ZIP structure server-side
- reject encrypted or malformed archives
- enforce a conservative upload size limit for the first phase

### Image validation

- only expose import candidates with safe content types: PNG, JPEG, WebP, GIF if supported
- reject executable or non-image embedded payloads even if they live under image-like paths

### Auth boundary

- browser uploads the `.3mf` to HA only
- HA performs all Bambuddy-authenticated photo and archive mutations
- Bambuddy API key must never be exposed to the card or browser runtime

## Layering Guidance

This feature should follow the existing print-history layering contract.

- Layer 1 remains the normalized archive/detail projection coming from Bambuddy plus broadly useful derived fields
- import-session state remains in HA integration runtime, not in Layer 1
- local review and primary-photo override state remains in the Variant 3 local SQLite store
- card wording and selection UX remain in Layer 3

Do not widen Layer 1 simply to carry temporary import-session candidate lists.

## Relationship To Existing Features

### Manual photo upload

This feature should reuse the existing authenticated photo-upload bridge after extraction.

### Photo review

Imported images become normal archive photos once uploaded, so they automatically participate in:

- delete photo
- local primary-photo selection
- popup gallery browsing
- media review state

### Source 3MF attachment

This feature does not replace Bambuddy `source_3mf_path` attachment. A future enhancement could optionally offer:

- `Attach source 3MF to Bambuddy too`

But that should be a separate checkbox and not part of the first implementation slice.

For multi-plate prints where one source project may relate to several archive rows, see `source-3mf-storage-strategy.md`. The current design recommendation is to prefer a shared durable source copy plus selective archive attachment, rather than attaching the same source `.3mf` to every sibling archive by default.

## Recommended Phases

### Phase 1: Read-only discovery

- upload `.3mf` to HA
- parse and preview candidates
- no Bambuddy mutations yet

### Phase 2: Image import only

- import selected images into Bambuddy archive photos
- refresh popup and local store
- optional local primary-photo selection prompt

### Phase 3: Limited metadata import

- optional external URL write-back
- optional structured notes import block
- optional system-managed tags if aligned with enrichment policy

### Phase 4: Optional source attachment and richer dedupe

- optional `also attach as Bambuddy source 3MF`
- duplicate warnings against existing photos and thumbnail

## Open Questions Resolved For This Design

### Should this use websocket or HTTP upload to HA?

Use HTTP multipart upload to HA for the source `.3mf`, then use existing HA-side Bambuddy auth for downstream mutations.

### Should imported images go into a separate HA store?

No. Once selected, they should be uploaded into Bambuddy as normal archive photos.

### Should all parsed metadata be written back?

No. First implementation should limit write-back to external URL, notes provenance, and optional tags.

### Should sliced preview images be offered?

Yes, but as lower-priority fallback candidates behind project-level model and profile pictures.
