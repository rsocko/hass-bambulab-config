# Custom Fields Schema

> **Status**: Proposed schema.
> **Last updated**: 2026-04-21
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
| `origin_type` | string | `original`, `remix`, `derivative` | #171 |
| `remix_source_url` | string | URL of original model if remix | #171 |
| `source_download_url` | string | Original download URL | #183 |
| `source_platform` | string | `printables`, `makerworld`, `thingiverse`, `cults3d`, `other`, `original` | #183 |
| `published_to` | array | `["Printables", "Makerworld"]` | #171 |
| `published_urls` | object | `{"Printables": "https://..."}` | #171 |
| `catalog_quality_state` | string | `needs_preview`, `needs_tags`, `needs_photos`, `complete` | Internal |
| `internal_notes` | string | Free-text private operator notes | #171 |
| `to_print_status` | string | `none`, `queued`, `done` | #190 |
| `to_print_priority` | number | Integer 1–10, higher = higher priority | #190 |
| `3mf_parsed_at` | string | ISO 8601 datetime of last 3MF parse | #173 |
| `preview_last_refreshed_at` | string | ISO 8601 datetime of last preview refresh | #175 |

## Field Notes

### `origin_type` (#171)

Captures how this model came to exist:

- `original` — designed from scratch by the operator
- `remix` — derived from another model, attribution expected
- `derivative` — significantly changed from a source model; attribution situation may be ambiguous

When `origin_type` is `remix` or `derivative`, `remix_source_url` should also be set.

**Relationship to Manyfold `keywords`:** it is useful to also add a corresponding Manyfold tag (e.g., `remix`) for visual context in the Manyfold UI. The structured `origin_type` field in the sidecar DB is the machine-readable authority; the Manyfold tag is for human browse context.

### `source_download_url` and `source_platform` (#183)

Records where a model was originally found before entering the local library. Supports:

- re-downloading if the local copy is lost
- cross-referencing with the original for updates
- the Phase 1 ingestion workflow where the operator pastes a URL into the sidecar UI

These fields are set at ingestion time and are rarely changed.

### `published_to` and `published_urls` (#171)

Tracks platforms where the operator has published an original or remixed model externally. These are operator-maintained fields and are not automatically populated.

Example:

```json
{
  "published_to": ["Printables"],
  "published_urls": {
    "Printables": "https://www.printables.com/model/12345"
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

### `to_print_status` and `to_print_priority` (#190)

A minimal print queue capability directly in the catalog. See [Print Queue Assessment](print-queue-assessment.md) for the full analysis of why this approach was chosen over alternatives.

Status: planned for a later phase. These fields are not part of the shipped Phase 2 archive-linkage slice.

- `to_print_status: queued` marks a cataloged model as intended to be printed
- `to_print_priority` allows manual ordering (1 = lowest, 10 = highest priority)
- Later-phase behavior may update status to `done` when an archive is accepted as linked to this model, but that automatic state transition is not implemented today

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

GET    /models?to_print_status=queued      — filter models by field value
GET    /models?catalog_quality_state=needs_preview — filter by quality state
```

HA services wrap these endpoints for use in dashboard cards and automations.

## Relationship To Manyfold Tags

Some custom fields could be approximated with Manyfold `keywords` tags. Both may be used:

- **Manyfold tags**: coarse catalog traits visible in the Manyfold browse UI (`remix`, `printed`, `needs-review`, `favorite`)
- **Custom fields**: structured, queryable, integration-specific values used by HA dashboards and automations

**Rule**: use Manyfold tags for human-visible catalog traits; use custom fields in the sidecar DB for machine-readable, queryable, or integration-specific data.
