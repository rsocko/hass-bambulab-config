# 3MF Embedded Thumbnail Display Design (Cards + Popup)

> Status: Proposed
> Last updated: 2026-05-03
> Scope: Sidecar local-authority model catalog thumbnail behavior for `.3mf` assets in card and popup surfaces.

## Goal

Automatically show a thumbnail for stored `.3mf` files on:

- Model browser cards
- Model detail popup media gallery/lightbox

without requiring manual image upload.

## Review Of Prior Analysis

The prior Copilot analysis is directionally correct and matches how we should implement this feature in this repo:

- Correct: `.3mf` should be treated as a ZIP container.
- Correct: embedded thumbnail discovery should check known locations first, then manifest-declared image parts.
- Correct: if no embedded thumbnail exists, fallback behavior should remain deterministic (existing preview image or placeholder).
- Correct: on-demand extraction is viable and avoids unnecessary duplicate storage.

Clarification for repo design:

- We should not depend on Windows Explorer behavior as a product contract.
- Our contract is sidecar-owned thumbnail detection + delivery over explicit API routes.

## Current State (Repo)

Local import currently creates `model_catalog_assets` rows with `preview_url=None` (including `.3mf` assets). As a result:

- local cards only show images when a preview image URL already exists
- local popup `photos[]` relies on uploaded photos and does not currently derive media from local assets for authority `local`

Relevant implementation points:

- `sidecars/model_catalog/app/routers/intake.py`
- `sidecars/model_catalog/app/routers/models.py`
- `sidecars/model_catalog/app/services/model_detail_service.py`
- `homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js`
- `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`

## Design Principles

- Deterministic: same `.3mf` bytes always produce the same selected thumbnail.
- Non-destructive: do not mutate source model files.
- Minimal duplication by default: do not persist duplicate thumbnail binaries unless explicitly needed.
- Backward-compatible: existing preview/photo behaviors continue to work.
- Fast enough for dashboard use via caching headers and lightweight thumbnail extraction.

## Chosen Approach

Use on-demand extraction with deterministic URL contracts, plus optional lightweight runtime caching.

### Why This Option

- Avoids creating and managing extra thumbnail files for each model revision.
- Fits current sidecar local-authority architecture.
- Enables immediate support for existing models already in the DB.

## Thumbnail Selection Contract

For a given `.3mf` asset, choose thumbnail candidate in this order:

1. Known high-confidence paths (case-insensitive):
   - `Metadata/thumbnail.png`
   - `Thumbnails/thumbnail.png`
   - `3D/Thumbnail.png`
2. Existing known preview families already used in repo tooling:
   - `Metadata/plate_*.png`
   - `Metadata/top_*.png`
   - `Metadata/pick_*.png`
   - `Auxiliaries/Model Pictures/*`
3. Manifest-declared image resources from `[Content_Types].xml` with image content types (`image/png`, `image/jpeg`, `image/jpg`, `image/webp`) sorted lexicographically by normalized path.

If multiple candidates remain in the same tier, sort by normalized path ascending and pick first.

If no valid image candidate exists, return `not_found` and continue with existing fallback preview behavior.

## API Contract Changes

### New endpoint

`GET /api/models/{model_ref}/files/{file_id}/thumbnail`

Behavior:

- Resolve local or manyfold model file as in existing download path.
- For local `.3mf` assets:
  - open ZIP safely
  - resolve candidate thumbnail path using contract above
  - stream image bytes with detected media type
- For manyfold path:
  - not required for initial scope; return `501` or `404` with `unsupported_authority` until explicitly implemented

Response headers:

- `Cache-Control: public, max-age=300`
- `ETag: <asset_hash_or_mtime_key>`

Errors:

- `404` `thumbnail_not_found`
- `400` `invalid_3mf`
- `413` `thumbnail_too_large`
- `415` `thumbnail_unsupported_type`

### Serialization updates

When serializing local model assets and summaries:

- If asset has explicit `preview_url`, keep it.
- If asset is `.3mf` and no explicit `preview_url`, synthesize derived URL:
  - `/api/models/{model_ref}/files/{asset_id}/thumbnail`
- For local summary preview selection, allow derived `.3mf` thumbnail URL as fallback when no image preview exists.

This keeps existing API payload shapes unchanged while making thumbnail URLs available automatically.

## Popup Media Contract

For local authority detail responses (`build_model_detail_response`):

- Continue returning uploaded photos as today.
- Add derived media entries from local assets when `preview_url` is available (explicit or synthesized), using the same photo shape (`id`, `image_url`, `thumbnail_url`, `is_preview`, `filename`, `source`).
- Preserve existing preview precedence:
  1. explicit preview photo selection
  2. asset role `preview`
  3. first deterministic media candidate

This ensures popup gallery and lightbox can display embedded `.3mf` thumbnail without user upload.

## Safety And Limits

ZIP parsing protections:

- Reject path traversal and non-normalized member escapes.
- Enforce max uncompressed candidate size (recommended 8 MB).
- Enforce max compressed entry ratio to reduce zip-bomb risk.
- Only allow image MIME/content signatures: PNG/JPEG/WebP.
- Never execute or parse arbitrary XML beyond manifest fields needed for path resolution.

## Performance Strategy

- First implementation: on-demand extraction per request.
- Optional optimization: in-memory LRU keyed by `(asset_id, file_hash)` for decoded thumbnail bytes/metadata.
- No persisted thumbnail file cache required in baseline.

## UX Behavior

### Browser cards

- If local model has uploaded/explicit preview image, use it.
- Else if primary/preview `.3mf` has embedded thumbnail, show it.
- Else fallback placeholder remains unchanged.

### Detail popup

- Media tab shows uploaded photos plus derived `.3mf` thumbnail media entries.
- Lightbox opens derived thumbnail like any other image entry.
- Optional follow-up: add small source badge (`Embedded 3MF`).

## Migration And Backfill

No DB migration required for baseline.

Existing models gain support automatically because URLs are synthesized at serialization time.

Optional future enhancement:

- Add `thumbnail_status` cache field in `model_catalog_assets` if operational telemetry needs it.

## Testing Plan

### Unit tests

- `geometry_3mf`/thumbnail helper tests:
  - known path hit
  - manifest fallback hit
  - no thumbnail
  - invalid zip
  - oversized thumbnail rejection

### API tests

- `GET /api/models/{model_ref}/files/{file_id}/thumbnail`:
  - 200 with image media type
  - 404 no thumbnail
  - 400 invalid 3mf
  - local non-3mf returns 415/404 per contract

### Integration/UI tests

- model list/search returns thumbnail URL for local model with `.3mf` and no manual image
- detail popup media includes derived `.3mf` thumbnail
- card and popup render remain stable when endpoint returns 404

## Rollout Plan

1. Add thumbnail extraction utility + endpoint.
2. Add synthesized preview URL fallback in model summary/asset serialization.
3. Add local detail media derivation from assets.
4. Add tests.
5. Deploy and validate with mixed sample set:
   - Bambu `.3mf` with embedded thumbnails
   - `.3mf` without thumbnail
   - existing models with explicit uploaded images

## Out Of Scope

- Full Manyfold `.3mf` thumbnail extraction for remote assets.
- Persisted thumbnail files and long-term artifact lifecycle policy.
- New UI controls for selecting among multiple embedded `.3mf` previews.

## Acceptance Criteria

- Local model cards automatically show embedded `.3mf` thumbnail when available and no explicit preview exists.
- Local detail popup media/lightbox can display the same derived thumbnail.
- Existing image-based preview workflows continue to behave unchanged.
- Behavior is deterministic and stable across restarts for unchanged files.
