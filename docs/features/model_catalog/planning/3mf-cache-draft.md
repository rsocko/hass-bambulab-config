# 3MF Analysis Cache Schema And API Draft

> **Status**: Draft for issue #1135.
> **Last updated**: 2026-04-25
> **Scope**: Concrete sidecar schema and REST contract for `.3mf` analysis cache, preview/resource inventory, and refresh behavior.

## Purpose

Turn the design direction from [../3mf-resource-extraction-and-online-provenance-design.md](../3mf-resource-extraction-and-online-provenance-design.md) into a sidecar-ready schema and API draft that fits the current implementation style.

This draft is intentionally limited to the `#1135` scope:

- file-hash-keyed analysis cache
- preview/resource inventory
- analysis status and refresh behavior
- sidecar read/write API shape

It does **not** fully specify Phase 7 public-source resolution or Phase 5 publish UX. Those phases may consume this cache but should not distort the cache schema itself.

## Current Baseline

The current sidecar already has these patterns:

- SQLite schema migrations are versioned in `sidecars/model_catalog/app/db.py`
- API routes are exposed from `sidecars/model_catalog/app/main.py`
- domain endpoints already use `/api/...` families such as archive-link and model-summary routes
- existing tables store JSON payloads as `*_json TEXT` rather than introducing wide relational breakdowns too early

That means the first 3MF cache should follow the same style:

- additive migration(s)
- compact relational core
- JSON payloads where the shape is still evolving
- explicit timestamps and status fields

## Design Goals

- reuse one analysis result across bulk analyze, Working detail, publish, and backfill workflows
- avoid reparsing unchanged files unless forced
- support multiple analysis revisions over time when file content changes
- preserve a deterministic inventory of previews and extracted companion resources
- keep raw model payload members out of the user-facing artifact surface
- support async execution and partial failure without losing diagnostics

## Proposed Tables

### `three_mf_analysis_runs`

One row per analyzed source artifact revision.

Suggested schema:

```sql
CREATE TABLE IF NOT EXISTS three_mf_analysis_runs (
    id INTEGER PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_file_name TEXT,
    source_path TEXT,
    source_path_key TEXT,
    parser_family TEXT NOT NULL DEFAULT 'unknown',
    parser_version TEXT,
    analysis_status TEXT NOT NULL,
    refresh_mode TEXT NOT NULL DEFAULT 'skip_if_current',
    is_current INTEGER NOT NULL DEFAULT 1,
    file_kind TEXT,
    sliced_state TEXT,
    resource_inventory_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    embedded_provenance_hints_json TEXT NOT NULL DEFAULT '[]',
    analysis_errors_json TEXT NOT NULL DEFAULT '[]',
    analyzed_at TEXT NOT NULL,
    superseded_at TEXT,
    UNIQUE(source_sha256, is_current) WHERE is_current = 1
)
```

Notes:

- `source_sha256` is the primary reuse key
- `source_path` is useful for diagnostics and local re-analysis, but not a stable identity anchor
- `is_current` supports retaining older revisions after file content changes
- `analysis_status` should be a small enum-like string set, not a freeform blob

Recommended `analysis_status` values:

- `queued`
- `running`
- `completed`
- `completed_with_warnings`
- `failed_invalid_zip`
- `failed_unsupported`
- `failed_parser_error`

Recommended `file_kind` values:

- `source_3mf`
- `sliced_3mf`
- `gcode_3mf`
- `unknown`

### `three_mf_analysis_previews`

One row per preview candidate discovered for an analysis run.

Suggested schema:

```sql
CREATE TABLE IF NOT EXISTS three_mf_analysis_previews (
    id INTEGER PRIMARY KEY,
    analysis_run_id INTEGER NOT NULL,
    preview_key TEXT NOT NULL,
    member_name TEXT NOT NULL,
    preview_group TEXT NOT NULL,
    label TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    width_px INTEGER,
    height_px INTEGER,
    storage_mode TEXT NOT NULL DEFAULT 'sidecar_cache',
    cache_relative_path TEXT,
    is_primary_candidate INTEGER NOT NULL DEFAULT 0,
    promoted_state TEXT NOT NULL DEFAULT 'not_promoted',
    promoted_target TEXT,
    promoted_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (analysis_run_id) REFERENCES three_mf_analysis_runs(id),
    UNIQUE(analysis_run_id, preview_key)
)
```

Recommended `preview_group` values:

- `plate_preview`
- `top_preview`
- `pick_preview`
- `thumbnail`
- `model_picture`
- `project_thumbnail`

Recommended `promoted_state` values:

- `not_promoted`
- `promoted_sidecar`
- `promoted_manyfold_preview`
- `superseded`

### `three_mf_analysis_resources`

One row per extracted companion resource that is not part of the raw model payload.

Suggested schema:

```sql
CREATE TABLE IF NOT EXISTS three_mf_analysis_resources (
    id INTEGER PRIMARY KEY,
    analysis_run_id INTEGER NOT NULL,
    resource_key TEXT NOT NULL,
    resource_origin TEXT NOT NULL,
    member_name TEXT,
    source_path TEXT,
    resource_class TEXT NOT NULL,
    mime_type TEXT,
    extension TEXT,
    size_bytes INTEGER,
    storage_mode TEXT NOT NULL DEFAULT 'sidecar_cache',
    cache_relative_path TEXT,
    publish_eligibility TEXT NOT NULL DEFAULT 'review_only',
    notes_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (analysis_run_id) REFERENCES three_mf_analysis_runs(id),
    UNIQUE(analysis_run_id, resource_key)
)
```

Recommended `resource_origin` values:

- `embedded_zip_member`
- `external_sibling`

Recommended `resource_class` values:

- `preview_image`
- `companion_image`
- `document`
- `metadata_dump`
- `machine_profile_artifact`
- `other_allowlisted`

Recommended `publish_eligibility` values:

- `not_publishable`
- `review_only`
- `eligible_supporting_asset`

### Optional: `three_mf_analysis_jobs`

Only add this if async execution needs a first-class persisted job tracker separate from `three_mf_analysis_runs`.

For the initial draft, it is acceptable to keep async job metadata in the run row or in the existing `model_catalog_events` log until concurrency needs justify a dedicated table.

## Why This Split

`three_mf_analysis_runs` keeps the reusable structured cache.

`three_mf_analysis_previews` and `three_mf_analysis_resources` make list/filter/promotion operations simpler than burying everything in one giant JSON payload.

At the same time, the shape stays compact enough to fit the current sidecar style without over-normalizing every internal detail.

## Proposed Migration Strategy

Recommended next migration sequence in `db.py`:

- migration `6`: add `three_mf_analysis_runs`
- migration `7`: add `three_mf_analysis_previews`
- migration `8`: add `three_mf_analysis_resources`

This keeps future changes easier to reason about if the resource table shape needs adjustment after the first implementation slice.

## API Family

Use `/api/3mf-analysis/...` to stay explicit and consistent with current route naming.

### Analyze A File Or Working Item

`POST /api/3mf-analysis/analyze`

Suggested request body:

```json
{
  "working_item_id": 17,
  "source_path": null,
  "force": false,
  "refresh_mode": "skip_if_current",
  "extract_previews": true,
  "extract_companion_resources": true
}
```

Rules:

- require exactly one of `working_item_id` or `source_path`
- if the source hash already has a current completed run and `force=false`, return that run
- if `force=true`, enqueue or execute a fresh run even when the hash matches

Suggested response:

```json
{
  "success": true,
  "reused_existing": true,
  "analysis": {
    "id": 42,
    "source_sha256": "ABC123...",
    "analysis_status": "completed",
    "parser_family": "bambu",
    "file_kind": "source_3mf",
    "analyzed_at": "2026-04-25T15:45:00Z"
  }
}
```

### Get Analysis By Run ID

`GET /api/3mf-analysis/runs/{analysis_run_id}`

Suggested response shape:

```json
{
  "id": 42,
  "source_sha256": "ABC123...",
  "source_size_bytes": 12488930,
  "source_file_name": "widget.3mf",
  "parser_family": "bambu",
  "analysis_status": "completed",
  "file_kind": "source_3mf",
  "metadata": {
    "printer_name": "P1S 0.4 nozzle",
    "estimated_print_time_seconds": 12450
  },
  "embedded_provenance_hints": [],
  "errors": [],
  "previews": [],
  "resources": []
}
```

### Get Current Analysis By Hash

`GET /api/3mf-analysis/by-hash/{source_sha256}`

Use this to reuse analysis across bulk and publish workflows.

### List Preview Candidates

`GET /api/3mf-analysis/runs/{analysis_run_id}/previews`

Support query params later if needed:

- `group`
- `promoted_state`

### Promote Preview Candidate

`POST /api/3mf-analysis/previews/{preview_id}/promote`

Suggested request body:

```json
{
  "target": "manyfold_preview",
  "replace_existing": false
}
```

This endpoint should update cache state only in the Phase 3.5 draft. The actual publish-time Manyfold side effect can remain a later implementation concern if needed.

### List Companion Resources

`GET /api/3mf-analysis/runs/{analysis_run_id}/resources`

Suggested filter params:

- `resource_class`
- `publish_eligibility`

### Mark Resource Eligibility Or Selection

`POST /api/3mf-analysis/resources/{resource_id}/selection`

Suggested request body:

```json
{
  "publish_eligibility": "eligible_supporting_asset",
  "note": "Keep as optional supporting PDF"
}
```

This lets later publish flows consume a reviewed selection set instead of recomputing intent.

## Refresh Behavior

### `skip_if_current`

- if a current completed run exists for the same hash, reuse it
- if a current failed run exists, return it unless `force=true`

### `rebuild_cache_only`

- rerun extraction and refresh sidecar cache records
- do not automatically mark previews/resources as promoted

### `replace_derived_artifacts`

- rerun extraction
- supersede earlier cache-backed preview/resource rows
- preserve auditability for previously promoted rows

### `full_refresh`

- rerun extraction regardless of prior state
- clear current-row status from older runs for the same logical source
- use only when the operator explicitly wants a new baseline

## Relationship To Working And Publish Flows

Phase 3.5 should only promise:

- analysis cache exists
- preview/resource inventory exists
- reviewed eligibility can be stored

Phase 5 should consume this cache for:

- preview promotion
- supporting-asset import decisions

That keeps the analysis cache reusable and avoids turning it into a publish-only schema.

## Diagnostics And Events

The existing `model_catalog_events` table is sufficient for the first draft.

Recommended event types:

- `three_mf.analysis_queued`
- `three_mf.analysis_completed`
- `three_mf.analysis_failed`
- `three_mf.preview_promoted`
- `three_mf.resource_selection_updated`

Event payloads should include:

- `analysis_run_id`
- `source_sha256`
- `parser_family`
- `analysis_status`
- `error_codes` when relevant

## Out Of Scope For This Draft

- remote source metadata fetch and persistence beyond embedded provenance hints
- full Manyfold upload side effects for preview/resource promotion
- background scheduler/job-runner architecture beyond the minimum API contract
- geometry-level introspection of raw model payload members

## Recommended Immediate Follow-Ons

1. Add a short schema note or appendix in `docs/features/model_catalog/api-reference.md` once endpoints stabilize.
2. Update issue `#1135` to point at this draft.
3. Use this doc as the contract for `#1136` implementation slicing.