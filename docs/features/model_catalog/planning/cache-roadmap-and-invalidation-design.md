# Cache Roadmap And Invalidation Design

> Status: Proposed
> Last updated: 2026-05-03
> Scope: Model Catalog sidecar cache strategy for local-authority APIs and UI-facing performance paths.

## Purpose

Define a concrete cache roadmap for the sidecar that improves p95 latency and lowers repeated expensive work while preserving deterministic behavior and low operational complexity.

This roadmap is intentionally incremental:

- Phase A: no Redis required
- Phase B: optional Redis adoption only after measurable triggers

## Current Baseline

The current service already has cache-like behavior:

- SQLite-backed Manyfold summary cache (`manyfold_model_summary_cache`)
- SQLite working inventory and derived state tables
- endpoint-level short cache headers on some binary responses
- single-process deployment in the independent stack by default

Observed gap:

- expensive binary-derived operations (3MF thumbnail extraction, geometry parsing/LOD prep) are not yet consistently memoized with explicit cache keys and invalidation contracts

## Non-Goals

- introduce distributed cache infrastructure by default
- add hidden stale-data behavior without observability
- replace SQLite durability with volatile cache

## Design Principles

- Deterministic keys: cache identity must be driven by content hash + relevant options.
- Explicit invalidation: clear events and boundaries, no implicit magic.
- Read-through with graceful fallback: cache miss always computes correct result.
- Safe staleness: bounded TTLs plus invalidation on authoritative writes.
- Observability-first: metrics before and after every cache slice.

## Target Hot Paths

1. 3MF embedded thumbnail delivery
2. 3MF geometry extraction and LOD response shaping
3. model list/search payload assembly
4. model detail enrichment payload assembly
5. refresh job coordination (single-flight lock semantics)

## Cache Layers

### Layer 0: Existing Durable State (SQLite)

Use existing tables as authoritative source of truth and persistent cache where already modeled.

Examples:

- Manyfold summary cache
- local model entries/assets
- working inventory metadata

### Layer 1: In-Process LRU (No New Infra)

Use process memory for repeated expensive computed payloads.

Characteristics:

- very low latency
- reset on restart (acceptable)
- no cross-instance sharing (acceptable in current topology)

### Layer 2: Optional Sidecar File Cache

Use `/data/cache/...` for large derived binary payloads where recomputation is expensive and deterministic.

Characteristics:

- survives process restart
- still no external dependency
- bounded by size and TTL-based cleanup

### Layer 3: Optional Redis (Deferred)

Only adopt after explicit trigger criteria are met.

## Key Contract By Endpoint Family

## 1) 3MF Thumbnail Endpoint Cache

Candidate endpoint:

- `GET /api/models/{model_ref}/files/{file_id}/thumbnail`

### Cache key

`thumbnail:v1:{authority}:{local_model_id_or_manyfold_ref}:{file_id}:{file_hash}`

where `file_hash` is preferred SHA256 from asset metadata; fallback to `(size,mtime)` fingerprint if hash unavailable.

### Value

- media type
- selected thumbnail member path
- image bytes (or file-cache pointer)
- extracted dimensions

### TTL

- in-process: 15 minutes
- file-cache: 24 hours (with lazy refresh)

### Invalidation

- asset write/update/delete for same `file_id`
- model publish/replace that mutates file hash
- explicit admin cache clear endpoint (future optional)

### Miss behavior

- safely parse ZIP, resolve candidate paths deterministically, return bytes
- if no candidate, store short negative cache (60 seconds) to prevent thundering herd

## 2) Geometry Endpoint Cache

Endpoint exists today:

- `GET /api/models/{model_ref}/geometry/{file_id}?plate_id=&lod=`

### Cache key

`geometry:v1:{authority}:{model_ref}:{file_id}:{file_hash}:{plate_id_or_all}:{requested_lod}:{include_debug_flag}`

### Value

- normalized geometry payload
- triangle counts + applied LOD metadata
- optional viewer notice flags

### TTL

- in-process: 10 minutes
- file-cache (optional): 12 hours for parsed intermediate representation (not final JSON)

### Invalidation

- same as thumbnail: asset hash change, file replacement, model deletion
- LOD algorithm version bump increments key prefix (`geometry:v2:...`)

### Miss behavior

- compute with current extraction path
- enforce complexity guardrails and return same error payload contract

## 3) Model List/Search Response Cache

Endpoints:

- `GET /api/models`
- `GET /api/models/search`

### Cache key

Canonicalized query-string key:

`models:list:v1:{authority_mode}:{normalized_query_hash}:{preview_proxy_base_hash}`

Normalization rules:

- sort query params by key
- normalize booleans/ints
- drop no-op/default params

### Value

- serialized response payload
- source metadata (`source`, `refresh_status`)

### TTL

- 30-90 seconds (short TTL, high churn surface)

### Invalidation

- any write to local model catalog entries/assets/custom fields relevant to list/search facets
- ranking updates
- manual cache bust on forced refresh path

## 4) Model Detail Cache

Endpoint:

- `GET /api/models/{model_ref}/detail`

### Cache key

`models:detail:v1:{authority}:{model_ref}:{detail_version_hint}:{include_debug}`

`detail_version_hint` can be derived from:

- local: max(updated_at across model row/assets/custom fields/photos)
- manyfold/hybrid: summary cache updated timestamp + local custom field/photo revision marker

### TTL

- 30-120 seconds

### Invalidation

- all model-scoped writes (fields, photos, assets, ranking)
- archive-link accept/reject impacting linked archives section

## 5) Refresh Lock / Single-Flight Cache

Problem:

- concurrent refresh calls can stampede upstream and duplicate expensive work.

### Without Redis

- process-local lock map keyed by refresh domain:
  - `refresh:manyfold_summaries`
  - `refresh:archive_candidates:{archive_id}`

Behavior:

- first request performs refresh
- concurrent requests await same future (single-flight)
- timeout fallback returns preserved cache with `refresh_in_progress=true`

### With Redis (deferred)

- distributed lock using `SET NX PX`
- bounded lock TTL
- owner token + safe release check

## Invalidation Event Matrix

- Local model create/update/delete: invalidate list/search + affected detail + affected thumbnail/geometry keys.
- Asset create/update/delete: invalidate detail + per-file thumbnail/geometry keys + list/search if preview candidate changes.
- Photo upload/delete/set-preview: invalidate detail + list/search preview projections.
- Ranking or queue fields update: invalidate list/search + detail.
- Archive link mutation: invalidate detail + archive-linked response fragments.
- Manyfold refresh completion: invalidate manyfold/hybrid list/search/detail caches.

## Capacity And Guardrails

In-process cache defaults (proposed):

- thumbnails: 128 entries, max 64 MB total
- geometry payloads: 32 entries, max 192 MB total
- list/search responses: 256 entries, max 32 MB total
- detail responses: 256 entries, max 32 MB total

Eviction policy:

- LRU with size-aware admission
- reject caching items beyond per-item max size (e.g., 8 MB thumbnails, 25 MB geometry payload)

## Observability Requirements

Expose per-cache metrics:

- hit count
- miss count
- fill count
- eviction count
- current entries and estimated bytes
- compute latency histogram for miss fills

Add to diagnostics endpoint summary:

- cache health snapshot by namespace
- top miss-heavy keys (sampled)

## Redis Decision Gates (Adoption Criteria)

Do not adopt Redis until at least two are true for sustained load windows:

1. Multi-replica deployment is active.
2. Cross-process stampede on same expensive keys is observed.
3. p95 latency target is missed after Layer 1/2 optimizations.
4. Need for distributed rate limits or job locks emerges.

## Rollout Plan

1. Add cache instrumentation scaffolding (metrics first).
2. Implement thumbnail cache (Layer 1; optional Layer 2 for bytes).
3. Implement geometry cache (Layer 1 + optional parsed intermediate Layer 2).
4. Add list/search short-TTL response cache with canonical query keys.
5. Add model detail short-TTL cache with version hints.
6. Add single-flight locks for refresh paths.
7. Evaluate metrics for 2-4 weeks before any Redis decision.

## Testing Plan

### Unit tests

- key normalization and stability
- version-hint invalidation behavior
- LRU eviction and size caps
- negative-cache TTL behavior for missing thumbnails

### Integration tests

- write -> read consistency after invalidation
- concurrent refresh request collapse (single-flight)
- geometry/thumbnail cache hit on repeated requests

### Performance tests

- baseline vs cached p50/p95 for thumbnail and geometry endpoints
- throughput impact under parallel model detail/list/search traffic

## Risks And Mitigations

- Risk: stale UI after writes
  - Mitigation: event-driven invalidation + short TTLs on response caches.

- Risk: memory pressure from large geometry payloads
  - Mitigation: strict item size caps, bounded entry counts, optional file-cache spillover.

- Risk: over-caching low-value keys
  - Mitigation: namespace metrics and pruning after measurement.

## Acceptance Criteria

- Documented key/TTL/invalidation contract exists for thumbnail, geometry, list/search, detail, and refresh locking.
- Layer 1 plan is deployable without Redis.
- Redis adoption criteria are explicit and measurable.
- Observability requirements are defined before implementation.
