# Manyfold-Bambuddy API, Cache, And Sync Flow

> Status: Proposed runtime flow.
> Scope: How Home Assistant should fetch, cache, join, and selectively update Manyfold and Bambuddy data for the model catalog.

## Purpose

Define the runtime behavior for three data planes:

- Manyfold catalog API reads and selective writes
- Bambuddy archive/runtime reads
- local linkage DB reads and writes

The goal is to avoid both extremes:

- no giant always-hot mirror of both systems in HA state
- no expensive live joins on every popup render

## Systems Involved

### Manyfold

Used for:

- model summaries
- model detail
- preview URL or preview file reference
- user-facing metadata such as tags, links, description, creator, and collection

### Bambuddy

Used for:

- archive detail
- archive status and runtime facts
- archive-local media and operator context
- print-history entrypoints

### Local linkage DB

Used for:

- accepted links
- candidate links
- review state
- confidence and provenance
- repo-specific annotations

## Runtime Principles

### Principle 1: local linkage state is authoritative for relationships

HA should not infer current accepted links on every render from names or tags.

The active linkage row is the source of truth.

### Principle 2: Manyfold is authoritative for user-facing model metadata

If a linked model name changes in Manyfold, HA should eventually reflect that after refresh.

### Principle 3: Bambuddy is authoritative for archive truth

Archive status, timestamps, and runtime metrics should never be shadow-owned by Manyfold or the linkage DB.

### Principle 4: cache only what is needed for the operator surface

Prefer compact summary caches over full upstream payload persistence unless the full payload is explicitly needed.

### Principle 5: cross-system links point one way only — Catalog/Queue → Archive

All persisted relationships between the model catalog (including the unified print queue, which lives in the model-catalog DB) and Bambuddy print history are stored **only** on the catalog/queue side, keyed by Bambuddy-global identifiers (`bambuddy_archive_id`, `library_file_id`).

Bambuddy and the print-history sidecar/DB **must never** store back-pointers to catalog or queue surrogate keys (`queue_entry_id`, `model_catalog_links.id`, `manyfold_model_url`, catalog working-file IDs, etc.). No archive payload, enrichment write-back, or print-history materialization may embed a catalog/queue ID.

Rationale and asymmetry:

- The model-catalog sidecar supports a prod/test DB profile split (`MODEL_CATALOG_DB_PROFILE`). Catalog data, the unified print queue, and the archive linkage table all live in that DB and switch together.
- Bambuddy and the bambuddy-runtime-repair sidecar are intentionally **single-DB, single-namespace** with no prod/test split, and that is a permanent design choice — there will not be a `BAMBUDDY_DB_PROFILE`.
- `bambuddy_archive_id` is therefore globally unique. A catalog-side row referencing `archive_id=42` means the same physical archive regardless of which catalog profile is active.
- Catalog/queue surrogate keys (`queue_entry_id`, link row IDs, etc.) are **profile-local** and meaningless outside the DB that minted them. Writing them into Bambuddy would couple the global archive store to whichever profile happened to be active at write time and silently break under a profile switch.
- One-way linkage keeps Bambuddy free of profile concerns and keeps the test profile a true throwaway sandbox. Test mode is allowed to diverge freely from prod; there is no promote/merge path and no UI guard against divergence — that divergence is the point of having a test profile. PROD is the canonical operator surface.

Consequences for consumers:

- Anything that needs to associate Bambuddy data with a catalog/queue concept must do so by looking up `bambuddy_archive_id` (or another Bambuddy-global key) **from the catalog/queue side**.
- HA automations, scripts, and webhooks that need a stable cross-profile reference must use `bambuddy_archive_id` (or a content hash), not `queue_entry_id` or link row IDs.
- It is expected and acceptable that the same archive can show different linked-model state depending on which catalog profile is active.

## Recommended Data Shapes

### Cached Manyfold model summary

Recommended fields:

- `manyfold_model_url`
- `manyfold_model_public_id`
- `name`
- `caption`
- `description`
- `keywords`
- `links`
- `creator_name`
- `creator_url`
- `collection_name`
- `collection_url`
- `preview_file_url`
- `preview_content_url`
- `updated_at_hint` if derivable
- `fetched_at`

### Cached Bambuddy archive summary

Recommended fields:

- `archive_id`
- `archive_name`
- `status`
- `completed_at`
- `printer_name`
- `thumbnail_url`
- `source_3mf_hint`
- `fetched_at`

### Joined popup projection

Recommended fields:

- `archive_id`
- `archive_name`
- `archive_status`
- `linked_model_name`
- `linked_model_url`
- `linked_model_preview_url`
- `link_review_state`
- `link_confidence`
- `candidate_count`

## Read Flow

### Flow A: archive popup render

When an archive popup opens:

1. Fetch archive detail from the existing Bambuddy archive path or cache.
2. Query local linkage DB for active and candidate links by `archive_id`.
3. If no active or candidate link exists, render `no link` state.
4. If an active link exists, try to resolve cached Manyfold model summary.
5. If summary cache is stale or missing, fetch Manyfold model detail and update cache.
6. Return flattened popup payload.

Recommended staleness rule for popup reads:

- linked Manyfold model summary cache older than 15 minutes may be refreshed lazily
- linkage DB should always be read live

### Flow B: model catalog card or panel render

When the user opens the model-catalog surface:

1. Load paged Manyfold model summaries from local cache.
2. Join linked archive counts and latest archive references from the linkage DB.
3. Hydrate missing or expired Manyfold summaries in the background.
4. Render current cached results first, then patch updated results in.

This keeps the UI responsive and avoids blocking on a full Manyfold fetch.

## Candidate Generation Flow

When `refresh_archive_model_link_candidates` runs:

1. Fetch Bambuddy archive detail.
2. Extract matching hints:
   - source file hash if available
   - source path if available
   - archive name
   - timestamps
3. Query Manyfold cache first for likely models.
4. If cache coverage is insufficient, query Manyfold list/detail endpoints as needed.
5. Score results by match method.
6. Write or update candidate rows in the linkage DB.
7. Auto-accept only if the match is unique and deterministic.
8. Otherwise leave `needs_review` or `unreviewed` candidates.

## Write-back Flow

### Link acceptance

When operator accepts a candidate:

1. Mark chosen link row as `accepted` and `is_active=1`.
2. Mark competing candidate rows for the same archive as inactive or rejected.
3. Emit link event if audit table exists.
4. Refresh popup projection.

### Manual link creation

When operator creates a manual link:

1. Validate archive ID.
2. Validate Manyfold model URL or ID if provided.
3. Upsert a `manual` link row.
4. Set `match_confidence=high` and `review_state=accepted`.
5. Refresh popup projection.

### Selective Manyfold metadata sync

Only for later phases.

When a deterministic HA edit is sent to Manyfold:

1. Read current Manyfold model detail.
2. Merge only the intended built-in fields.
3. PATCH the Manyfold model.
4. Update local Manyfold summary cache.
5. Never store repo-specific structured linkage state in the Manyfold payload as the primary truth.

## Cache Strategy

### Linkage DB cache policy

- no secondary cache required for current-state linkage rows
- read directly from SQLite for popup and action flows

### Manyfold cache policy

Recommended caches:

- in-memory short-lived summary cache inside coordinator or runtime service layer
- persisted compact summary cache in SQLite only if needed for startup speed or offline tolerance

Recommended TTLs:

- model summary for popup: 15 minutes
- model summary for browse panel: 30 minutes
- creator/collection display names: 60 minutes

Force refresh when:

- link is newly created
- operator opens linked model details after a write-back
- Manyfold config entry changes

### Bambuddy cache policy

Reuse existing archive/print-history patterns where possible.

Do not create a second competing archive cache if the integration already has suitable archive access abstractions.

## Failure Handling

### Manyfold unavailable

Behavior:

- keep linkage DB usable
- keep Bambuddy archive popup usable
- render linked model using last cached summary when available
- show stale-state indicator instead of failing popup entirely

### Bambuddy unavailable

Behavior:

- model catalog panel may still render Manyfold data
- archive-centric popup actions should fail gracefully

### Linkage DB unavailable

Behavior:

- archive popup should fall back to `linkage unavailable`
- no candidate generation or accept/reject actions should run

## Recommended Background Jobs

### Job 1: Manyfold summary refresh

Triggered by:

- periodic interval
- explicit manual refresh
- link creation or acceptance

### Job 2: orphan link reconciliation

Checks for:

- Manyfold model URLs that no longer resolve
- archive IDs that no longer resolve
- stale candidate rows

### Job 3: archive linkage candidate refresh

Triggered by:

- archive completion events if appropriate
- operator action from popup
- optional periodic backfill for unlinked archives

## Suggested Sequence Diagram

```text
Archive popup opens
  -> HA reads Bambuddy archive detail
  -> HA reads local linkage DB by archive_id
  -> if active link exists:
       -> HA resolves Manyfold summary from cache
       -> if stale/missing: fetch Manyfold model detail
       -> update cache
  -> HA returns flattened popup payload

Operator accepts candidate
  -> HA updates local linkage DB
  -> HA deactivates competing candidates
  -> HA refreshes Manyfold summary if needed
  -> popup re-renders with accepted link
```

## Concrete Recommendation

The first version should be read-mostly and link-centric:

- live read Bambuddy for archive truth
- live read SQLite for accepted and candidate links
- lazily read and cache Manyfold summaries
- defer broad Manyfold write-back until the read-and-link path is stable

That gives you a responsive HA operator flow without over-committing to a full synchronization engine too early.