# Manyfold-Bambuddy Linkage Model

> Status: Proposed integration contract.
> Scope: Single-user or mostly single-user model catalog with Manyfold as the archival model store and a local companion store for structured Bambuddy linkage.

## Purpose

Define a concrete data model and ownership split for linking:

- Manyfold models and model files
- Bambuddy archives
- optional Bambuddy library records
- repo-specific enrichment and review state

This contract exists because Manyfold is a good store for model records and files, but it does not currently provide a clean built-in place to store structured cross-system linkage metadata.

## Recommended Operating Model

For this repo, the simplest useful operating mode is:

1. Use Manyfold as the authoritative store for model records, files, previews, tags, creators, collections, and human-facing notes.
2. Use Bambuddy as the authoritative store for print/archive/runtime facts.
3. Use a small local linkage database to connect the two.
4. Let Home Assistant surface the joined view.

This avoids trying to force Bambuddy runtime data into Manyfold fields or trying to force Manyfold catalog semantics into Bambuddy archive records.

## Identity Model

### Core Principle

Every joined record should anchor first on stable upstream IDs, not names.

Preferred identity order:

1. Manyfold model public ID or canonical Manyfold model URL
2. Manyfold model file ID when the linkage is file-specific
3. Bambuddy archive ID
4. Bambuddy library file ID if present
5. Content hash or source file hash when available
6. Human-facing name only as a snapshot or fallback aid

### Recommended Canonical Keys

Use these as first-class foreign-reference columns in the local linkage store:

- `manyfold_model_url`
- `manyfold_model_public_id`
- `manyfold_model_file_url`
- `manyfold_model_file_id`
- `bambuddy_archive_id`
- `bambuddy_library_file_id`

If Manyfold base URL may vary by environment, also store:

- `manyfold_instance_base_url`

## Proposed Storage Shape

Use a local SQLite database owned by the Home Assistant integration boundary.

Recommended location:

- `.storage/bambuddy_model_catalog.db`

Do not store this linkage state:

- in Manyfold itself
- in Bambuddy upstream tables
- in helper entities
- in entity attributes as the primary store

## Primary Tables

### 1. `model_catalog_links`

This is the current-state relationship table.

Recommended columns:

- `id`
- `manyfold_instance_base_url`
- `manyfold_model_url`
- `manyfold_model_public_id`
- `manyfold_model_name_snapshot`
- `manyfold_model_file_url`
- `manyfold_model_file_id`
- `manyfold_model_file_name_snapshot`
- `bambuddy_archive_id`
- `bambuddy_archive_name_snapshot`
- `bambuddy_archive_status_snapshot`
- `bambuddy_library_file_id`
- `relationship_type`
- `link_role`
- `source_hash`
- `match_method`
- `match_confidence`
- `review_state`
- `review_note`
- `is_active`
- `linked_by`
- `created_at`
- `updated_at`

### Suggested semantics

- `relationship_type`: what kind of relationship exists
- `link_role`: whether this row is the primary authoritative link or a secondary supporting link
- `source_hash`: optional hash of the source project file or source artifact used during matching

Recommended `relationship_type` values:

- `model_printed_in_archive`
- `model_file_printed_in_archive`
- `archive_references_model`
- `library_file_matches_model`

Recommended `link_role` values:

- `primary`
- `secondary`
- `candidate`

Recommended `match_method` values:

- `manual`
- `content_hash_exact`
- `file_hash_exact`
- `path_exact`
- `filename_plus_time_window`
- `normalized_filename_overlap`
- `time_proximity_plus_name`
- `linked_plate_family_neighbor`
- `name_only_fallback`

Recommended `match_confidence` values:

- `high`
- `medium`
- `low`

Recommended `review_state` values:

- `accepted`
- `unreviewed`
- `needs_review`
- `rejected`

### 2. `model_catalog_annotations`

This is the structured repo-owned metadata table.

Recommended columns:

- `id`
- `manyfold_model_url`
- `manyfold_model_public_id`
- `bambuddy_archive_id`
- `annotation_scope`
- `annotation_key`
- `annotation_value_json`
- `is_active`
- `created_at`
- `updated_at`

Recommended `annotation_scope` values:

- `model`
- `model_file`
- `archive`
- `link`

This table is where repo-specific structured metadata should live.

Examples:

- archive linkage provenance
- operator review flags
- confidence overrides
- catalog completeness state
- custom enrichment results

### 3. `model_catalog_link_events`

Optional but recommended if you expect manual review and correction over time.

Recommended columns:

- `id`
- `link_id`
- `event_type`
- `actor`
- `payload_json`
- `created_at`

Recommended `event_type` values:

- `link_created`
- `link_confirmed`
- `link_rejected`
- `link_reassigned`
- `annotation_updated`

## Minimal Practical SQL Shape

```sql
CREATE TABLE model_catalog_links (
  id INTEGER PRIMARY KEY,
  manyfold_instance_base_url TEXT,
  manyfold_model_url TEXT NOT NULL,
  manyfold_model_public_id TEXT,
  manyfold_model_name_snapshot TEXT,
  manyfold_model_file_url TEXT,
  manyfold_model_file_id TEXT,
  manyfold_model_file_name_snapshot TEXT,
  bambuddy_archive_id INTEGER,
  bambuddy_archive_name_snapshot TEXT,
  bambuddy_archive_status_snapshot TEXT,
  bambuddy_library_file_id INTEGER,
  relationship_type TEXT NOT NULL,
  link_role TEXT NOT NULL DEFAULT 'primary',
  source_hash TEXT,
  match_method TEXT NOT NULL,
  match_confidence TEXT NOT NULL,
  review_state TEXT NOT NULL DEFAULT 'unreviewed',
  review_note TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  linked_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_model_catalog_links_active_primary
  ON model_catalog_links (manyfold_model_url, bambuddy_archive_id, relationship_type, is_active);

CREATE INDEX idx_model_catalog_links_manyfold_model_url
  ON model_catalog_links (manyfold_model_url);

CREATE INDEX idx_model_catalog_links_archive_id
  ON model_catalog_links (bambuddy_archive_id);

CREATE INDEX idx_model_catalog_links_review_state
  ON model_catalog_links (review_state, is_active);

CREATE TABLE model_catalog_annotations (
  id INTEGER PRIMARY KEY,
  manyfold_model_url TEXT,
  manyfold_model_public_id TEXT,
  bambuddy_archive_id INTEGER,
  annotation_scope TEXT NOT NULL,
  annotation_key TEXT NOT NULL,
  annotation_value_json TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_model_catalog_annotations_model
  ON model_catalog_annotations (manyfold_model_url, annotation_scope, annotation_key, is_active);
```

## Authoritative Field Ownership

### Manyfold-owned fields

These should be treated as canonical in Manyfold and synced outward rather than overwritten elsewhere.

Recommended Manyfold authority:

- model name
- model caption
- model description or notes
- model tags via `keywords`
- creator assignment
- collection assignment
- preview file selection
- file-level caption or description
- file-level orientation and previewability fields
- human-facing links that belong on the model page

### Bambuddy-owned fields

These should remain canonical in Bambuddy.

Recommended Bambuddy authority:

- archive ID
- archive status and completion outcome
- archive timestamps
- printer identity used for the print
- runtime print metrics
- archive-local thumbnails and print-local media
- queue and printer workflow state

### Linkage-store-owned fields

These should not be forced into either Manyfold or Bambuddy unless an upstream feature is added later.

Recommended local authority:

- manyfold-to-archive relationship rows
- linkage confidence
- linkage review state
- linkage provenance
- operator decisions
- repo-specific annotations
- cross-system IDs that are not natural Manyfold or Bambuddy fields
- enrichment state
- deduping or reconciliation notes

## Recommended Field Split

| Concern | Authoritative system | Notes |
|---|---|---|
| Model display name | Manyfold | Human-facing catalog identity belongs here |
| Tags | Manyfold | Use `keywords`; sync to HA for browse/filter UX |
| Creator | Manyfold | Keep model taxonomy centralized |
| Collection | Manyfold | Same reason as creator |
| Description/notes | Manyfold | Human-facing prose only |
| External human links | Manyfold | For model pages and browsing |
| Archive ID linkage | Local linkage DB | Structured integration fact, not Manyfold prose |
| Archive match confidence | Local linkage DB | Repo-specific integration state |
| Review status | Local linkage DB | Operational control state |
| Archive runtime metrics | Bambuddy | Avoid shadow copies in Manyfold |
| Printer and queue status | Bambuddy | Runtime authority |
| Custom enrichment JSON | Local linkage DB | This is the missing native "custom fields" area |

## Practical Rules For Built-in Manyfold Fields

### Safe to use directly

These built-in Manyfold fields are a good fit for your custom catalog UI:

- `name`
- `caption`
- `description`
- `keywords`
- `links`
- `creator`
- `collection`
- `preview_file`

### Use sparingly for integration hints only

You can use these only if the value is also meaningful to a human operator, not just to the integration:

- `links` for a real archive URL or HA deep link
- `description` for small human-readable context about print availability
- `keywords` for broad catalog traits like `printed`, `prototype`, `favorite`, `needs-review`

### Do not overload for structured linkage

Do not use Manyfold built-ins as the primary store for:

- `bambuddy_archive_id`
- `archive_match_confidence`
- `sync_version`
- `enrichment_payload`
- raw provenance JSON
- operator-only review state

Those belong in the local linkage store.

## Matching Workflow

### Initial candidate creation

1. Prefer exact upstream IDs if the relationship was created by an explicit user action.
2. Otherwise match by file or content hash if available.
3. Otherwise fall back to path-based or filename-plus-time-window heuristics.
4. Any ambiguous result becomes `review_state=needs_review`.

### Manual confirmation

When an operator confirms a match:

- set `match_method=manual`
- set `match_confidence=high`
- set `review_state=accepted`
- preserve the previous candidate row as inactive or write an audit event

### Deactivation instead of deletion

Prefer `is_active=0` over hard deletion for superseded links.

This preserves history and makes reconciliation easier.

## Home Assistant Projection

Home Assistant should not read directly from Manyfold and Bambuddy on every view render if richer search or cross-system filters are needed.

Recommended projection model:

1. Pull Manyfold model metadata into a local cache or service layer.
2. Pull Bambuddy archive facts into a local cache or service layer.
3. Join through `model_catalog_links`.
4. Project a flattened view for Lovelace/custom-card use.

Recommended flattened view fields:

- `manyfold_model_url`
- `manyfold_model_public_id`
- `name`
- `caption`
- `keywords`
- `creator_name`
- `collection_name`
- `preview_url`
- `latest_archive_id`
- `latest_archive_name`
- `latest_archive_status`
- `latest_archive_completed_at`
- `archive_count`
- `link_review_state`
- `link_confidence`
- `custom_annotations`

For dashboard/browser consumers, expose `preview_url` as a sidecar-hosted proxy URL rather than a raw Manyfold `model_files` URL so Home Assistant does not hotlink cross-origin preview images directly.

## Recommended First Slice

For the first implementation, keep it narrow.

### Must-have

- One active link from a Manyfold model to zero or more Bambuddy archives
- Manual link creation and correction
- Review state and confidence
- Snapshot names for troubleshooting

### Nice-to-have later

- file-level linkage rows
- archive family grouping
- automatic candidate generation
- audit events
- richer custom annotations

## Concrete Recommendation

For your likely single-library workflow:

- let Manyfold own model taxonomy and user-facing catalog metadata
- let Bambuddy own print/archive runtime truth
- add a local SQLite linkage layer for structured associations
- use Home Assistant as the joined operator-facing UI

That gives you clean archive linking without needing Manyfold to support native custom fields.

## Related Docs

- [implementation-plan.md](c:\dev\hass-bambulab-config\docs\features\model_catalog\implementation-plan.md)
- [api-cache-sync-flow.md](c:\dev\hass-bambulab-config\docs\features\model_catalog\api-cache-sync-flow.md)