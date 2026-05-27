# 3MF Thumbnail Caching And Collection Cover Derivation

> Status: Proposed
> Last updated: 2026-05-27
> Scope: Sidecar caching strategy for derived local `.3mf` thumbnails and collection cover usage in the model catalog browser.

## Tracking Issues

- Phase 1: surface derived local `.3mf` thumbnails into summaries and collection covers (#1603)
- Phase 2: add runtime caching and `ETag` revalidation for derived `.3mf` thumbnails (#1604)
- Phase 3: add telemetry and tuning for derived `.3mf` thumbnail caching (#1605)

## Problem Statement

The repo already supports on-demand extraction of embedded `.3mf` thumbnails through `GET /api/models/{model_ref}/files/{file_id}/thumbnail`.

That solves the functional problem of showing a preview without requiring manual image upload, but it leaves two gaps:

1. repeated requests can force repeated ZIP open + thumbnail extraction work on the sidecar
2. collection cover mosaics still depend on `preview_url` being present in the browse payload, so local models with only derived `.3mf` thumbnails may not contribute to collection covers

The immediate question is not whether collection covers should become first-class stored assets. The question is whether derived `.3mf` thumbnails should be cached, and at what layer.

## Goals

- avoid repeated server-side `.3mf` thumbnail extraction when the same model thumbnail is requested frequently
- let collection cover mosaics reuse the same cached per-model thumbnail path as cards and popup media
- preserve the current model-level preview precedence contract
- keep collection covers derived rather than operator-managed in the first phase
- keep cache invalidation deterministic and explainable

## Non-Goals

- generating and storing a separate composite image for each collection
- introducing manual `Create collection preview` or `Refresh collection preview` actions
- adding persistent thumbnail binaries to the database in the first phase
- extending embedded-thumbnail extraction to remote catalog or Manyfold assets in this phase

## Current State

### Current thumbnail behavior

- local `.3mf` thumbnails are extracted on demand from the thumbnail endpoint
- the endpoint currently returns `Cache-Control: public, max-age=300`
- the sidecar does not currently memoize extracted thumbnail bytes across requests
- the endpoint does not currently return `ETag` or `Last-Modified` validators

### Current browser behavior

- the browser card lazy-load path maintains an in-memory object URL cache for thumbnail endpoints during the active browser session
- normal non-derived image URLs rely on regular browser or upstream cache behavior
- collection mosaics reuse whatever image URLs appear in `cover_images`; there is no collection-specific image cache

### Current collection behavior

- collection browse derives `cover_images` from member models with non-empty `preview_url`
- collection browse does not store a collection cover artifact
- if a local model only has a latent `.3mf` thumbnail but no surfaced `preview_url`, that model may not contribute to collection cover selection

## Decision Summary

Cache derived `.3mf` thumbnails at the per-model thumbnail endpoint layer, not at the collection layer.

The first implementation should use:

1. synthesized derived thumbnail URLs for eligible local models in summary and browse payloads
2. an in-memory sidecar LRU cache keyed by thumbnail source identity
3. HTTP validators on the thumbnail endpoint so browsers can revalidate cheaply
4. existing browser-session object URL caching as an optimization, not as the primary contract

Collection covers should remain derived from model preview URLs. Once local model summaries expose the derived thumbnail URL, collection mosaics will pick them up automatically.

## Why Cache At The Model Thumbnail Layer

The same model preview may be used in multiple places:

- model grid cards
- model detail popup media
- collection cover mosaics
- future working-set or recent-items views

Caching a collection-specific composite would duplicate work and create a second invalidation problem. Caching the model thumbnail once lets every consumer benefit.

This also matches the existing architecture: collections do not own media, they summarize member media.

## Proposed Architecture

```mermaid
flowchart LR
    A[Collection browse/card render] --> B[Model preview_url]
    C[Model popup/media] --> B
    D[Model card] --> B
    B --> E[/api/models/{model_ref}/files/{file_id}/thumbnail]
    E --> F[In-memory thumbnail LRU]
    E --> G[3MF extraction]
    G --> H[Embedded thumbnail bytes]
    F --> E
```

### Layer 1: Summary and browse payload surfacing

For local models only:

- if an explicit preview image exists, preserve it as the model `preview_url`
- else if a deterministic local `.3mf` thumbnail candidate exists, surface the derived thumbnail endpoint as `preview_url`
- else continue to return no preview URL

This keeps collection browse unchanged conceptually. The browse endpoint should continue to derive collection covers from model preview URLs, but more local models will now qualify.

### Layer 2: Sidecar runtime thumbnail cache

Add an in-memory LRU cache for derived thumbnails.

Recommended cache key:

- `local_model_id`
- `asset_id`
- `file_hash` when available
- fallback fingerprint from `storage_path`, `mtime_ns`, and `size`

Recommended cache value:

- thumbnail bytes
- MIME type
- `etag`
- cache key metadata for debugging

Recommended cache policy:

- bounded entry count and/or total bytes
- evict least-recently-used entries first
- no persistent disk cache in the first phase

Recommended starting size:

- target 64 to 128 entries
- cap total cached bytes around 32 to 64 MB

This is enough to cover active dashboard browsing without creating a second asset store.

### Layer 3: HTTP caching and revalidation

Enhance the thumbnail endpoint response with:

- `Cache-Control: public, max-age=300`
- `ETag: <fingerprint>`
- optional `Last-Modified` if path metadata is already available cheaply

Behavior:

- if the request sends `If-None-Match` matching the current thumbnail fingerprint, return `304 Not Modified`
- if the runtime LRU already has the thumbnail for the current fingerprint, serve from memory without re-extraction
- if the fingerprint changed, extract again and replace the cached entry

This makes server work cheap both within and after the browser cache window.

## Collection Cover Contract

### What changes

- collection browse should treat surfaced derived local `.3mf` thumbnail URLs the same as any other model `preview_url`
- collection cards with 1 to 3 cover images should continue using the existing client-side repeat-fill behavior to render a full 2x2 mosaic

### What does not change

- no collection cover bitmap is stored
- no collection-level thumbnail cache is introduced in this phase
- no collection-level preview refresh action is added
- no special collection invalidation path is needed beyond the underlying model preview change

## Preview Precedence Contract

The existing precedence remains:

1. explicit operator-selected preview image or uploaded photo
2. explicit model thumbnail or primary photo already exposed by source authority
3. derived local `.3mf` thumbnail endpoint
4. placeholder / empty tile

The cache layer must not change ordering. It only accelerates resolution of level 3.

## Invalidation Strategy

Cache invalidation must be based on model asset identity, not time alone.

Invalidate or bypass the cached thumbnail when:

- the underlying local asset file changes
- the asset record changes to a different file hash or storage path
- the selected preview asset changes
- the model gains a higher-priority explicit preview, making the derived URL no longer the selected preview

No manual cache flush UI is required in the first phase.

Operationally, a sidecar restart may clear the runtime LRU. That is acceptable because:

- correctness is preserved
- browser HTTP caching still helps
- re-extraction remains deterministic

## Failure Handling

If derived thumbnail extraction fails:

- do not poison the cache indefinitely with a permanent failure record in the first phase
- return existing endpoint errors as today
- collection browse should simply treat the model as having no derived preview for that response cycle

Optional enhancement:

- short negative-cache TTL for `thumbnail_not_found` to avoid repeated extraction attempts on obviously empty `.3mf` assets during a single browsing session

This should be considered only if telemetry shows meaningful repeated misses.

## Observability

Add lightweight metrics or debug logging for:

- thumbnail cache hits
- thumbnail cache misses
- thumbnail extraction duration
- 304 revalidation count
- extraction failures by reason

The goal is to verify that the runtime cache is actually reducing ZIP extraction work.

## Security And Safety

The cache layer must preserve all existing extraction safety checks:

- path normalization
- ZIP entry size limits
- compression ratio guardrails
- supported MIME checks

Caching does not relax extraction rules. It only memoizes the result for a specific trusted asset fingerprint.

## Alternatives Considered

### Persist thumbnail binaries on disk

Pros:

- avoids re-extraction across sidecar restarts

Cons:

- introduces artifact lifecycle management
- requires invalidation and cleanup policy
- duplicates data already derivable from the `.3mf`

Decision:

- defer

### Cache collection composite images

Pros:

- potentially fewer browser requests for a collection card

Cons:

- duplicates source images
- introduces a second invalidation graph based on collection membership and ordering
- only helps collection cards, not other thumbnail consumers

Decision:

- reject for this phase

### Add a manual collection preview refresh action

Pros:

- explicit operator control

Cons:

- implies collection previews are authored state rather than derived state
- creates UX debt and support burden
- unnecessary once underlying model previews are surfaced and cached correctly

Decision:

- reject for this phase

## Implementation Plan

### Phase 1: surface derived local thumbnails into summaries and collection browse

- update local summary preview selection so eligible local `.3mf` assets can provide a derived thumbnail URL as `preview_url`
- verify `/api/collections/browse` starts returning `cover_images` for collections whose local members only have derived `.3mf` previews

### Phase 2: add sidecar runtime cache and HTTP validators

- add bounded in-memory LRU cache for derived thumbnail responses
- add `ETag` generation and `If-None-Match` handling on the thumbnail endpoint
- preserve existing `Cache-Control` behavior

### Phase 3: add telemetry and tune limits

- add hit or miss instrumentation
- validate memory footprint under real browsing load
- tune entry count or byte cap if needed

## Testing Plan

### Unit tests

- derived summary preview picks `.3mf` thumbnail URL when no explicit preview exists
- runtime cache hit avoids repeated extraction for the same fingerprint
- changed fingerprint invalidates cached thumbnail
- `If-None-Match` returns `304` for unchanged thumbnail

### API tests

- thumbnail endpoint returns `ETag` and `Cache-Control`
- thumbnail endpoint returns `304` when validator matches
- collection browse returns `cover_images` for local collections backed only by derived `.3mf` thumbnails

### UI tests

- collection card with one local derived preview renders repeated 2x2 mosaic
- collection card with two or three local derived previews renders repeated-fill mosaic without empty state
- collection card with zero previewable models still shows the existing empty state

## Acceptance Criteria

- local models with only embedded `.3mf` thumbnails can contribute to collection `cover_images`
- repeated requests for the same derived `.3mf` thumbnail do not require full extraction on every request during the sidecar process lifetime
- browser revalidation can return `304` for unchanged thumbnails
- collection covers remain derived, deterministic, and free of collection-specific preview management UI

## Repo Touch Points

- `sidecars/model_catalog/app/routers/models.py`
- `sidecars/model_catalog/app/services/model_media_service.py`
- `sidecars/model_catalog/app/geometry_3mf.py` if helper factoring is needed
- `tests/sidecars/model_catalog/test_thumbnail_endpoint.py`
- `tests/sidecars/model_catalog/test_facets_endpoint.py`
- `homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js` only if UI handling needs minor adjustments
