# Custom Fields Schema

> **Status**: Proposed schema.
> **Last updated**: 2026-05-09
> **Scope**: Fields stored in the local sidecar SQLite DB to extend what Manyfold natively supports.

## Why Custom Fields Are Needed

Manyfold does not provide a native custom-field system. The REST API and native UI expose a fixed set of built-in fields only. Fields that are useful for personal catalog management but are not native Manyfold fields must be stored in the sidecar database, keyed by Manyfold model URL or public ID.

For the full API gap analysis that confirms this, see [Manyfold API Gap Analysis](manyfold-api-gap-analysis-2026-04-21.md).

## Manyfold Native Fields — Reference, Do Not Replicate

These fields exist natively in Manyfold and must NOT be replicated in the local DB as the primary store:

| Manyfold API field | Purpose |
|---|---|
| `name` | Model display name |
| `caption` | Short tagline |
| `description` | Full public-facing notes |
| `keywords` | Tags and catalog traits |
| `creator` | Creator assignment |
| `collection` | Collection assignment |
| `links` | External human-facing URLs |
| `spdx:license` | License |
| `preview_file` | Preview image reference |
| `sensitive` | Content sensitivity flag |

The sidecar caches summaries of these fields for performance, but Manyfold is canonical for all of them.

## Custom Field Storage

### Table: `model_catalog_model_fields`

All custom fields for a Manyfold model are stored as typed rows keyed by `manyfold_model_url`.

```sql
CREATE TABLE model_catalog_model_fields (
  id INTEGER PRIMARY KEY,
  manyfold_model_url TEXT NOT NULL,
  manyfold_model_public_id TEXT,
  field_key TEXT NOT NULL,
  field_value_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_model_fields_model_key
  ON model_catalog_model_fields (manyfold_model_url, field_key);

CREATE INDEX idx_model_fields_key_value
  ON model_catalog_model_fields (field_key, field_value_json);
```

Using a key/value row model rather than wide columns makes it straightforward to add new field types without schema migrations for every addition.

## Supported Custom Fields

| Field key | JSON type | Allowed values | Issue |
|---|---|---|---|
| `origin_type` | string | `custom_unique`, `remix`, `derivative` | #171 |
| `remix_source` | object | `{\"label\": \"Original model name\", \"platform\": \"makerworld\", \"url\": \"https://...\"}` when not unique | #171 |
| `source_download_url` | string | Original download URL | #183 |
| `source_platform` | string | `makerworld`, `printables`, `thingiverse`, `cults3d`, `manyfold`, `other`, `original_local` | #183 |
| `published_to` | array | `["makerworld", "printables"]` | #171 |
| `published_urls` | object | `{"makerworld": "https://..."}` | #171 |
| `catalog_quality_state` | string | `needs_preview`, `needs_tags`, `needs_photos`, `complete` | Internal |
| `internal_notes` | string | Free-text private operator notes | #171 |
| `to_print_status` | string | Legacy-only values (`none`, `queued`, `done`) retained for historical compatibility | #190 |
| `to_print_priority` | number | Legacy-only numeric priority retained for historical compatibility | #190 |
| `taxonomy_origin_class` | string | `reprint`, `remix_or_tweak`, `custom_unique` | #187 |
| `taxonomy_change_axes` | array | `[]`, `[
"color"]`, `["model"]`, `["color", "model"]`, `["other"]` | #187 |
| `model_favorite` | boolean | `true`, `false` | #187 |
| `model_rating` | number | Integer 1–5 | #187 |
| `colors_used` | array<object> | Phase 3 baseline is hex-first; later phases may add optional `filament_id` linkage | #187 |
| `3mf_parsed_at` | string | ISO 8601 datetime of last 3MF parse | #173 |
| `preview_last_refreshed_at` | string | ISO 8601 datetime of last preview refresh | #175 |

## Field Notes

### `origin_type` and `remix_source` (#171)

Captures how this model came to exist:

- `custom_unique` — designed from scratch by the operator
- `remix` — derived from another model, attribution expected
- `derivative` — significantly changed from a source model; attribution situation may be ambiguous

When `origin_type` is `remix` or `derivative`, `remix_source` should also be set so the operator can capture what it came from, not just whether it was remixed.

Recommended `remix_source` shape:

```json
{
  "label": "Gridfinity spool holder base",
  "platform": "makerworld",
  "url": "https://makerworld.com/..."
}
```

This keeps the model flexible enough for a plain-text attribution now while leaving room for richer linked-source handling later.

`remix_source.platform` should use the canonical platform IDs defined below so remix attribution, source provenance, and published-destination filters stay aligned.

**Relationship to Manyfold `keywords`:** it is useful to also add a corresponding Manyfold tag (e.g., `remix`) for visual context in the Manyfold UI. The structured `origin_type` field in the sidecar DB is the machine-readable authority; the Manyfold tag is for human browse context.

### `source_download_url` and `source_platform` (#183)

Records where a model was originally found before entering the local library. Supports:

- re-downloading if the local copy is lost
- cross-referencing with the original for updates
- the Phase 1 ingestion workflow where the operator pastes a URL into the sidecar UI

These fields are set at ingestion time and are rarely changed.

For full channel and adapter behavior (URL paste, browser extension, Stream Deck, and collection migration), see [External Source Intake Design](external-source-intake-design.md).

UI contract:

- `source_platform` is the primary model-level "SOURCE" attribute shown in cards and popup metadata.
- `source_download_url` is optional detail for click-through to the original source page.
- SOURCE is distinct from `published_to`: source answers where the model was acquired, while published-to answers where it was later published.
- for locally created models, set `source_platform` to `original_local`; this should render as `Source: Local original`.
- SOURCE may be empty for legacy/custom records; UI should render a muted `Source: Not set` state rather than inferring from `published_to`.

### Canonical Platform IDs

Use these lowercase IDs anywhere a platform/destination needs to be stored in sidecar-owned model metadata:

| ID | Intended meaning |
|---|---|
| `makerworld` | Published to or sourced from MakerWorld |
| `printables` | Published to or sourced from Printables |
| `thingiverse` | Published to or sourced from Thingiverse |
| `cults3d` | Published to or sourced from Cults3D |
| `manyfold` | Published to the operator's Manyfold instance or sourced from another Manyfold library |
| `other` | Known external destination that does not have a dedicated enum value yet |
| `original_local` | Locally created model with no external source platform |

Usage rules:

- `source_platform` may use any of the IDs above, including `original_local`
- `published_to` must NOT use `original_local`; it should contain only actual publication destinations
- `published_urls` keys should match the same canonical IDs used in `published_to`
- UI can display friendly labels such as `MakerWorld` while storing canonical lowercase IDs
- UI should render SOURCE and PUBLISHED TO in separate rows/chip groups
- SOURCE should be singular in UI even if future internal lineage supports multiple source records

### Third-Party Intake Addendum (#1266, #232, #1372, #189)

The following fields are recommended as **intake-record metadata** in sidecar-owned intake tables, not as durable curated-model taxonomy fields:

| Field key | JSON type | Allowed values | Purpose |
|---|---|---|---|
| `capture_channel` | string | `url_paste`, `browser_extension`, `streamdeck`, `karakeep_sync` | Where intake originated |
| `capture_mode` | string | `link_only`, `metadata_only`, `full_import` | Operator-selected import depth |
| `source_model_id` | string | Provider-native model ID when available | Stable provider identity |
| `source_collection_id` | string | Provider-native collection/list ID | Collection migration tracking |
| `source_confidence` | string | `high`, `medium`, `low`, `none` | Confidence gate for automated actions |
| `source_warnings` | array<string> | Adapter-defined warnings | Review-time risk visibility |
| `source_snapshot_json` | object | Raw normalized provider payload | Audit + reparse support |
| `provider_access_mode` | string | `api`, `scrape`, `hybrid`, `manual` | Adapter execution mode used for capture/import |
| `import_execution_policy` | string | `immediate_full_import`, `metadata_first_deferred_files`, `link_only` | Effective commit policy used |

Rationale:

- these values are per-capture operational context, not permanent model taxonomy
- the same curated model may be captured multiple times from multiple channels over time
- collection migration and quick-capture channels need auditability separate from curated model metadata

Execution guidance:

- `source_confidence=high` may use `import_execution_policy=immediate_full_import`
- API-capable providers should generally prefer `metadata_first_deferred_files` unless operator explicitly requests full import
- non-API providers may prioritize `immediate_full_import` more often to avoid future source drift and unavailable file endpoints

### `published_to` and `published_urls` (#171)

Tracks platforms where the operator has published an original or remixed model externally. These are operator-maintained fields and are not automatically populated.

Design intent:

- `published_to` is the lightweight multi-value picker / list used by browse cards, filters, and quick status checks
- `published_urls` is optional detail for later phases when the operator wants direct links per destination

Example:

```json
{
  "published_to": ["makerworld", "printables"],
  "published_urls": {
    "makerworld": "https://makerworld.com/...",
    "printables": "https://www.printables.com/model/12345"
  }
}
```

### `catalog_quality_state` (internal)

A machine-readable flag for catalog completeness. Used to drive the "models needing attention" view in HA:

- `needs_preview` — no Manyfold preview image set yet
- `needs_tags` — no `keywords` tags set in Manyfold
- `needs_photos` — no real-world finished-print photo uploaded yet
- `complete` — all baseline quality criteria met

This field is set by the sidecar automatically based on inspection of Manyfold model state, and can be overridden by the operator.

### `internal_notes` (#171)

Private operator notes that should NOT appear in the Manyfold public-facing `description`. Examples of what belongs here:

- Slicing settings that worked well
- Known print failure modes or material recommendations
- Reminders about a model variant that needs finishing
- Personal context that should not be visible in a shared Manyfold instance

### `to_print_status` and `to_print_priority` (#190, legacy)

These fields are no longer the active queue system.

Current contract:

- Unified queue state and ordering now live in sidecar-owned unified queue entries.
- `to_print_status` and `to_print_priority` are retained only as historical metadata for compatibility and auditability.
- Queue behavior must be implemented through unified queue endpoints and HA unified queue rest commands.

Historical behavior note:

- Earlier phases used these fields for minimal catalog backlog semantics.
- That contract was retired during unified queue cutover and must not be used for new queue features.

Migration/deprecation references:

- [unified-queue-cutover-runbook.md](unified-queue-cutover-runbook.md)
- [unified-queue-deprecation-timeline.md](unified-queue-deprecation-timeline.md)

### Unified Production Queue fields (sidecar-owned, not Manyfold custom fields)

The following fields are recommended for queue entries, rather than for curated-model custom fields:

- `state`: `idea`, `todo`, `ready`, `started`, `done`, `blocked`
- `rank`: manual queue position
- `started_at`
- `completed_at`
- `copies_requested`
- `copies_completed`
- `selection_mode`: `all_files_all_plates`, `selected_files`, `selected_plates`
- `estimated_total_minutes`
- `duration_bucket`: `quick`, `medium`, `overnight`, `marathon`, `unknown`
- `ams_ready_score`
- `overnight_fit_score`

Per-file and per-plate progress also belongs in that queue projection, not in model custom fields.

Why:

- those values are per-entry operator state, not durable model taxonomy
- the same model may appear in the queue multiple times over time
- mixed-source queue entries need one consistent schema whether they came from Catalog, Working, or Ideas

### Taxonomy Extension For Issue #187 (Phase 3+)

The following fields extend model-catalog capability for taxonomy-centric browse and filtering in Phase 3 or later.

#### `taxonomy_origin_class`

Represents the top-level taxonomy bucket for a model:

- `reprint` — recurring/common part where the same model is regularly reprinted
- `remix_or_tweak` — derived from a source model, with explicit change-axis metadata
- `custom_unique` — from-scratch/custom model

This is model-level catalog taxonomy, not a single-print archive status.

#### `taxonomy_change_axes`

Captures "what changed" for `remix_or_tweak` models:

- `color`
- `model`
- `other`

This field should usually be empty for `reprint` and `custom_unique`.

#### `model_favorite` and `model_rating`

- `model_favorite` is a catalog-level preference signal.
- `model_rating` is optional and intentionally separate from favorite so future scoring can distinguish "liked" from "top rated".
- `model_rating` uses integer values `1` through `5`.

Manyfold note:

- Manyfold has native UI concepts around likes/lists, but there is no first-class documented REST surface for those workflows in the current API contract.
- Because this sidecar feature is API-driven, `model_favorite` remains sidecar-owned unless/until a stable Manyfold API surface exists for favorites.

These fields are model-catalog owned and must not be conflated with Bambuddy archive-level `is_favorite`.

#### `colors_used` (Spoolman link contract)

`colors_used` is the model-level taxonomy bridge to filament identity.

Recommended item shape:

```json
{
  "hex": "#C12E1F",
  "display_name": "Bambu PLA Basic Red",
  "source": "linked_archives_provenance"
}
```

Rules:

- Phase 3 baseline is **hex-first** for storage and filtering
- spool identity is intentionally out of scope for model-level taxonomy
- later phases may add optional `filament_id` on each entry to support direct Spoolman filament linkage
- later phases may also support operator-selected `filament_id` assignment via picker UI
- automatic inference from parsed `.3mf` metadata is a candidate enhancement for that later phase

This keeps "Colors used" compatible with issue #187 now while preserving a clear migration path to Filament-ID linkage later.

### `3mf_parsed_at` (#173)

Timestamp of the last time the sidecar ran 3MF asset extraction for this model. Used to:

- avoid redundant re-parses
- detect when the source 3MF file has been updated and a re-parse is needed (compare against Manyfold `file.updated_at`)

### `preview_last_refreshed_at` (#175)

Timestamp of the last time the sidecar refreshed or uploaded a preview image for this model. Used alongside Manyfold `file.updated_at` to detect stale previews.

## Archive Linkage Fields

Archive linkage is NOT stored in `model_catalog_model_fields`. It uses the dedicated `model_catalog_links` table defined in [Manyfold-Bambuddy Linkage Model](manyfold-bambuddy-linkage-model.md).

This keeps the archive relationship in a proper relational structure with confidence, review state, match provenance, and audit history rather than as a flattened JSON field.

## Sidecar REST API

The sidecar exposes these endpoints for custom field management:

```
GET    /models/{model_id}/fields           — all custom fields for a model
GET    /models/{model_id}/fields/{key}     — get a specific field
PUT    /models/{model_id}/fields/{key}     — set a field value
DELETE /models/{model_id}/fields/{key}     — clear a field

GET    /models?taxonomy_origin_class=reprint — filter models by taxonomy
GET    /models?catalog_quality_state=needs_preview — filter by quality state
```

HA services wrap these endpoints for use in dashboard cards and automations.

## Relationship To Manyfold Tags

Some custom fields could be approximated with Manyfold `keywords` tags. Both may be used:

- **Manyfold tags**: coarse catalog traits visible in the Manyfold browse UI (`remix`, `printed`, `needs-review`, `favorite`)
- **Custom fields**: structured, queryable, integration-specific values used by HA dashboards and automations

**Rule**: use Manyfold tags for human-visible catalog traits; use custom fields in the sidecar DB for machine-readable, queryable, or integration-specific data.
