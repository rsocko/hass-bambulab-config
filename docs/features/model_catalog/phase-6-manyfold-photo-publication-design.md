# Phase 6 Design: Publish Uploaded Model Photos To Manyfold

Status: proposed

Owner surface:
- Model Catalog sidecar
- Home Assistant model-detail popup
- Manyfold curated model record

## Why this exists

Phase 3.1 photo upload currently solves the operator workflow inside Home Assistant, but the uploaded images are sidecar-local only. They appear in the model-detail popup because the sidecar stores the image bytes on disk and stores photo metadata in the sidecar SQLite custom-fields table. They do not appear in Manyfold because the current upload flow does not attach them to the Manyfold model.

This document defines a later-phase design to promote selected uploaded photos from sidecar-local storage into Manyfold-managed model media while preserving a safe fallback path when Manyfold publication fails.

## Current state

Current behavior:
- browser upload from the model-detail popup posts directly to the sidecar
- sidecar validates image type and size
- sidecar stores uploaded bytes under a sidecar-managed `model_catalog_photos` root
- sidecar stores photo metadata in `model_catalog_custom_fields` under `uploaded_photos`
- sidecar serves those images back through `/api/models/{model_ref}/photos/{photo_id}/content`
- delete and preview-selection operate only on the sidecar-local uploaded photo store

Current limitations:
- uploaded photos are not attached to the model in Manyfold
- Manyfold UI does not show these uploads
- Manyfold remains authoritative for curated preview selection, but the current sidecar preview flag is only local for sidecar-hosted photos
- sidecar-local photo state can diverge from Manyfold media state

## Goals

- allow operator-selected uploaded photos to be published into Manyfold so they appear on the Manyfold model page
- preserve the current sidecar-local upload flow as the first hop so browser upload remains reliable from Home Assistant
- make publication explicit and observable instead of silently pushing every uploaded image into Manyfold
- support preview promotion so one published image can become the Manyfold-visible preferred preview when safe
- keep the sidecar resilient: a Manyfold publication failure must not destroy the local uploaded photo

## Non-goals

- replacing the current Phase 3.1 local upload path with a direct browser-to-Manyfold upload flow
- automatically publishing every uploaded image to Manyfold without operator intent
- direct writes to Manyfold's database
- bulk asset-promotion workflows across many models in this phase

## Design principles

- Manyfold remains authoritative for curated model media that should be visible in Manyfold UI
- sidecar-local uploaded photos remain valid as staging artifacts and fallback copies
- publication to Manyfold is a second-stage action with explicit state transitions
- sidecar metadata tracks publication status, upstream Manyfold media identifiers, and retryable failures
- do not silently replace an upstream Manyfold preview without explicit operator action or a clearly scoped policy

## Proposed operator workflow

1. Operator uploads one or more photos in the HA model-detail Gallery tab.
2. Photos are stored sidecar-locally and appear immediately in the HA popup.
3. Each local uploaded photo exposes a `Publish to Manyfold` action.
4. Sidecar uploads the selected image to the Manyfold model media/file surface.
5. If publication succeeds:
   - sidecar stores the upstream Manyfold photo/file identifier and URL
   - sidecar marks the local photo as `published`
   - sidecar can optionally offer `Use as Manyfold preview`
6. If publication fails:
   - local photo remains available in HA
   - sidecar records a failure state and last error
   - operator can retry later

Optional later refinement:
- add a combined `Publish and set as preview` action when the upstream publication route is confirmed to support deterministic preview promotion

## Data model additions

Extend the current sidecar-local uploaded photo record with publication metadata.

Suggested per-photo fields:
- `id`
- `relative_path`
- `filename`
- `mime_type`
- `created_at`
- `publication_status`:
  - `local_only`
  - `publishing`
  - `published`
  - `publish_failed`
- `manyfold_photo_id` or `manyfold_file_id`
- `manyfold_photo_url`
- `published_at`
- `publish_error`
- `is_local_preview`
- `is_manyfold_preview`

These fields can remain in sidecar-managed metadata initially. A dedicated table is preferable if photo-management scope grows beyond the current `uploaded_photos` custom-field shape.

## Sidecar API contract

Add a publication endpoint distinct from the local upload endpoint.

### Publish one uploaded photo

`POST /api/models/{model_ref}/photos/{photo_id}/publish`

Response:

```json
{
  "success": true,
  "photo_id": "photo-abc123",
  "publication_status": "published",
  "manyfold_photo_id": "mf-photo-987",
  "manyfold_photo_url": "https://manyfold.example/models/foo/model_files/bar"
}
```

Failure response:

```json
{
  "success": false,
  "photo_id": "photo-abc123",
  "publication_status": "publish_failed",
  "error": "Upstream Manyfold upload failed"
}
```

### Promote published photo to Manyfold preview

`POST /api/models/{model_ref}/photos/{photo_id}/publish-preview`

This route should only operate on photos already published to Manyfold.

## Manyfold integration approach

Use documented Manyfold HTTP flows only.

Preferred contract:
- upload the staged image bytes through a supported Manyfold file/media upload route for the existing model
- persist the resulting upstream identifier in sidecar metadata
- refresh sidecar model detail from Manyfold after a successful upload so Manyfold-native photo state is visible in the next HA reload

If Manyfold lacks one clean documented route for “attach image to existing model as gallery media,” then this phase should explicitly document the chosen workaround and its tradeoffs rather than hiding the gap.

## UI changes in Home Assistant

Gallery tab additions for sidecar-local uploads:
- `Publish to Manyfold`
- `Retry publish` when `publish_failed`
- `Use as Manyfold preview` when `published`
- small badge states:
  - `Local only`
  - `Published`
  - `Publish failed`

Gallery display behavior:
- Manyfold-native images and sidecar-local staged images should remain distinguishable
- if a local photo is successfully published and later synced from Manyfold detail, the UI should avoid duplicate rendering of the same asset

## Failure handling

- keep local bytes and local metadata even if upstream publication fails
- never delete local bytes immediately after successful publication in the first version
- allow explicit operator cleanup later once publication is verified stable
- if Manyfold upload succeeds but preview promotion fails, record partial success instead of rolling back the uploaded media

## Limits and policy

- local upload validation stays as-is for the first hop: JPG, PNG, WebP, max 10MB per image
- publication should reuse the validated local artifact rather than re-reading browser input
- a later policy decision can allow larger staged files if Manyfold upload capabilities justify it, but the initial Manyfold publication phase should inherit the existing 10MB cap for simplicity

## Open questions

- Which Manyfold route is the supported contract for attaching image media to an existing model in the current deployed Manyfold version?
- Does Manyfold expose a distinct photo/gallery model, or should image uploads be modeled as image files attached to the existing model?
- What is the safest preview-promotion contract for existing models without accidentally replacing upstream preferred images?
- Should successful publication eventually prune the local artifact, or should the sidecar retain it as a cache/fallback copy?

## Acceptance criteria

- operator can publish a staged uploaded photo from HA to Manyfold
- published image appears on the Manyfold model page after refresh
- HA detail view reflects publication state without duplicating the image entry
- failed publications remain retryable and do not destroy local photo access
- preview promotion to Manyfold is explicit and observable

## Suggested issue split

Parent issue:
- Later phase: publish staged model photos from sidecar to Manyfold

Child issues:
- validate and document the exact Manyfold attach-media contract for existing models
- implement sidecar publish endpoint and publication-state tracking
- add HA Gallery actions and status badges for publish/retry/promote-preview
