# Source 3MF Import Implementation Plan

> Companion to [source-3mf-import-design.md](source-3mf-import-design.md).

## Purpose

Turn the source-3MF import concept into a phased, implementable plan for the active Variant 3 print-history stack.

This plan assumes:

- the popup and photo gallery remain the only media-management surface
- the active backend is the `bambuddy` custom integration in `homeassistant/custom_components/bambuddy/`
- imported images become normal Bambuddy archive photos

## Phase Breakdown

## Phase 1: Discovery Only

### Outcome

User can upload a `.3mf` to HA from the archive popup and inspect extracted candidate images and metadata before any archive mutation occurs.

### Backend work

Add HA-side temporary import-session support in the Bambuddy custom integration.

Recommended new pieces:

- temp session manager in the custom integration
- `3mf` parser utility module for discovery
- authenticated archive existence check using the existing manager/store hydration pattern
- HTTP upload view for discovery
- HTTP preview endpoint for extracted candidate images tied to the session

### Frontend work

Extend the popup or photo gallery card with:

- hidden file input accepting `.3mf`
- `Import From 3MF` action
- discovery modal or inline panel for parsed results

### Suggested backend contracts

#### `POST /api/bambuddy/print-history/source-3mf/discover`

Request:

- multipart form
- fields: `archive_id`, `entry_id`, `file`

Response:

- discovery manifest described in the main design doc

#### `GET /api/bambuddy/print-history/source-3mf/session/{session_id}/candidate/{candidate_id}`

Response:

- image bytes for popup preview

### Phase 1 acceptance criteria

- archive popup can open source-3MF chooser
- HA accepts valid `.3mf` uploads and rejects invalid files cleanly
- user sees grouped candidate images and normalized metadata
- no Bambuddy photos or archive fields change during discovery

## Phase 2: Image Import

### Outcome

User can select candidate images and import them into Bambuddy as archive photos.

### Backend work

Add an import action that consumes a discovery session and selected candidate IDs.

Recommended contract:

#### `POST /api/bambuddy/print-history/source-3mf/import`

Request body:

```json
{
  "entry_id": "...",
  "archive_id": 123,
  "session_id": "...",
  "candidate_ids": ["model-1", "thumb-1"],
  "set_primary_candidate_id": "model-1"
}
```

Response body:

```json
{
  "archive_id": 123,
  "imported_count": 2,
  "skipped_count": 0,
  "failed_count": 0,
  "primary_photo_path": "photo_123.png",
  "detail": {"...": "refreshed archive detail payload"}
}
```

### Implementation notes

- use the existing `BambuddyApiClient.async_upload_archive_photo()` path for the actual photo upload
- avoid a second upload pipeline just for imported images
- upload sequentially in phase 2
- refresh the archive detail once after the import batch if possible
- if one candidate fails, continue with the rest and return partial success details

### Frontend work

Add selection controls:

- checkbox or selected state per candidate
- group-level select/deselect
- buttons: `Import Selected`, `Import Recommended`, `Cancel`

### Phase 2 acceptance criteria

- selected images appear in Bambuddy and the popup gallery after import
- imported images participate in existing delete and local-primary-photo flows
- popup stays consistent after refresh and does not require full page reload

## Phase 3: Metadata Import

### Outcome

User can selectively write limited extracted metadata back to the archive.

### Recommended write targets

- `external_url`
- `notes`
- optional managed tags if consistent with print-history enrichment policy

### Contract extension

Extend the import request with a metadata section.

```json
{
  "entry_id": "...",
  "archive_id": 123,
  "session_id": "...",
  "candidate_ids": ["model-1"],
  "metadata_import": {
    "write_external_url": true,
    "overwrite_external_url": false,
    "append_notes_block": true,
    "write_tags": false
  }
}
```

### Guardrails

- never overwrite operator notes; only append versioned hidden block
- never overwrite external URL without explicit user permission
- do not introduce new Layer 1 fields for feature-local metadata import state

### Phase 3 acceptance criteria

- metadata write-back is explicit and optional
- provenance is visible and machine-readable in notes
- no unexpected overwrite of user-authored fields occurs

## Phase 4: Optional Source Attachment

### Outcome

User may optionally attach the uploaded `.3mf` to Bambuddy as `source_3mf_path` in addition to importing images.

### Why this is deferred

- attachment is useful provenance, but not required for image import
- it adds another mutation path and more operator choices
- it is not needed to prove the image-import workflow itself

### Suggested option

Add a checkbox in the import UI:

- `Also attach this file as Bambuddy source 3MF`

This should call Bambuddy's source-attachment endpoint only after image import succeeds.

## Parser Strategy

### Reuse guidance

Do not depend on Bambuddy upstream parser code at runtime.

Instead:

- implement a focused HA-side parser for discovery only
- copy only the minimum required discovery rules, not the full upstream archive-ingest behavior

### Minimum parser responsibilities

- validate ZIP archive
- detect image candidate paths
- detect mesh/gcode presence flags for UX labeling
- extract normalized project metadata when present
- read image dimensions and content types

### Candidate path families to support first

- `Auxiliaries/Model Pictures/`
- `Auxiliaries/Profile Pictures/`
- `Auxiliaries/.thumbnails/`
- `Metadata/plate_*.png`
- `Metadata/top_*.png`
- `Metadata/pick_*.png`
- `Metadata/thumbnail.png`

## Error Handling

### Discovery failures

Return structured errors for:

- invalid archive ID
- archive not loaded or not found
- invalid or oversized `.3mf`
- malformed ZIP
- no candidate images found

### Import failures

Return partial results when possible:

- imported count
- skipped count
- failed candidate list
- refreshed detail if at least one upload succeeded

### UX guidance

- discovery errors should keep the popup open and show an inline error
- import errors should preserve the existing selection state so the user can retry

## File Size and Session Limits

Recommended first-phase guardrails:

- conservative max `.3mf` size limit for discovery
- bounded number of preview candidates returned to the frontend at once
- session TTL expiration
- cleanup on HA startup for stale temp sessions if needed

Exact size limits can be tuned after real-file testing.

## Integration Touchpoints

### Backend files likely involved

- `homeassistant/custom_components/bambuddy/__init__.py`
- `homeassistant/custom_components/bambuddy/api.py`
- new parser/session helper under `homeassistant/custom_components/bambuddy/`
- `homeassistant/custom_components/bambuddy/manager.py` only if operation logging or store refresh plumbing needs extension

### Frontend files likely involved

- `homeassistant/www/3d_printing/print_history/print-history-photo-gallery-card.js`
- popup content card only if metadata-import controls should live outside the gallery itself

### Local store interaction

No new persistent SQLite tables are required for phase 1 or phase 2.

Reason:

- import sessions are temporary runtime state
- imported images become ordinary Bambuddy photos after upload
- local primary-photo selection already has a persisted table

## Acceptance Test Matrix

### Phase 1 test set

- source `.3mf` with MakerWorld model pictures
- sliced `.3mf` with only plate previews
- malformed `.3mf`
- valid `.3mf` with no useful image candidates

### Phase 2 test set

- import one image
- import multiple images from mixed groups
- import all recommended images
- import with one candidate intentionally failing
- set imported image as local primary photo

### Phase 3 test set

- append notes provenance only
- write external URL without overwrite
- explicit overwrite of existing external URL
- tag-write disabled versus enabled

## Recommended Delivery Order

1. Add design docs and README links.
2. Implement parser utility and temp-session manager.
3. Implement HA HTTP discovery endpoint.
4. Add frontend discovery UI.
5. Implement import endpoint using existing photo upload bridge.
6. Add optional local-primary-photo selection after import.
7. Add metadata write-back options.
8. Consider optional Bambuddy source attachment last.

## Explicit Deferrals

- global image dedupe across archives
- pixel-similarity matching against current Bambuddy thumbnail
- full project-page synchronization into Bambuddy
- automatic archive repair using uploaded source `.3mf`
- importing non-image embedded assets from `.3mf`
