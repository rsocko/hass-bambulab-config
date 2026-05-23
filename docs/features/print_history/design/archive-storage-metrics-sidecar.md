# Archive Storage Metrics Sidecar Design

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/planning/archive-storage-metrics-sidecar-design.md
Replaced By: none

## Purpose

Define a narrow sidecar contract for calculating per-archive storage metrics from Bambuddy's mounted data volume and caching the results in the Home Assistant Variant 3 local store.

This feature exists because Bambuddy exposes archive file paths and the main `file_size`, but it does not expose a full per-archive asset-size breakdown through the archive API.

The design must stay aligned with the active print-history architecture:

- Bambuddy remains the archive-of-record
- Home Assistant Variant 3 remains the durable local query/cache boundary
- a sidecar may do heavy or environment-specific filesystem work when that work should not happen in HA templates or frontend cards

## Decision Summary

Recommended shape:

- add a read-oriented sidecar endpoint for archive storage scanning
- mount the Bambuddy data volume into that sidecar
- resolve archive asset paths from the Bambuddy DB plus archive-relative folder conventions
- cache scan results in the HA local SQLite store, not in the Bambuddy DB
- compute on demand and optionally in low-priority batches, not during every print-history refresh

Not recommended:

- widening the Layer 1 mirrored `archives` row with card-specific storage labels
- rescanning the full archive tree on each browser refresh
- writing derived storage metrics back into Bambuddy notes or tags
- requiring the frontend to infer asset sizes itself

## Why A Sidecar

The scan logic is environment-specific and filesystem-dependent.

It needs all of these:

- read access to the Bambuddy SQLite DB when Bambuddy runs on SQLite
- read access to the Bambuddy archive data directory
- awareness of Bambuddy's archive-relative path conventions
- safe handling of incomplete fallback archives where `file_path` may be empty

That is a better fit for a narrow sidecar than for:

- dashboard card code
- HA template sensors
- repeated ad hoc shell commands

## Deployment Assumption

With the current Docker layout, Bambuddy uses:

- `DATA_DIR=/app/data`
- `base_dir = DATA_DIR`
- `archive_dir = DATA_DIR/archive`
- SQLite DB at `DATA_DIR/bambuddy.db`

If the same named Docker volume is mounted into the sidecar as `/data`, the sidecar can read:

- `/data/bambuddy.db`
- `/data/archive/**`

That is sufficient for this feature.

The logs volume is not required.

## Storage Ownership

### Bambuddy-owned inputs

The sidecar treats these as authoritative inputs only:

- archive rows from Bambuddy
- Bambuddy archive-relative path fields such as `file_path`, `thumbnail_path`, `source_3mf_path`, `timelapse_path`, `f3d_path`
- Bambuddy's archive `photos` list
- files present under the mounted Bambuddy data directory

### HA-owned derived outputs

Home Assistant owns:

- per-archive storage summaries used by popup/detail/query workflows
- aggregate rollups for dashboard/statistics use
- staleness, scan status, and provenance fields for those summaries

These do not belong in Bambuddy's DB because they are derived analytics, not archive-core facts.

## Sidecar Responsibilities

The sidecar should own:

- request validation
- Bambuddy DB reads needed to resolve archive-relative paths
- filesystem stat and directory traversal work
- dry-run or uncached scan execution
- compact classification of known asset classes
- safe handling of missing files and incomplete archives

The sidecar should not own:

- dashboard wording
- popup formatting
- HA card-level grouping logic
- long-lived query state for the browser

Those remain in the Variant 3 integration and frontend.

## Scan Model

### Known per-archive asset classes

The sidecar should calculate these per archive when possible:

- `archive_3mf_bytes` — canonical archived file from `file_path`
- `thumbnail_bytes` — canonical thumbnail from `thumbnail_path`
- `source_3mf_bytes` — optional attached source project from `source_3mf_path`
- `timelapse_bytes` — optional timelapse from `timelapse_path`
- `f3d_bytes` — optional Fusion 360 file from `f3d_path`
- `photo_bytes` — total size of all known archive photos
- `photo_count` — number of existing photos found on disk
- `other_bytes` — other files found under the resolved archive directory that do not map to the known classes above
- `total_bytes` — sum of all archive-scoped bytes above

Optional extended fields:

- `photo_largest_bytes`
- `photo_average_bytes`
- `files_missing_count`
- `other_file_count`
- `by_extension_json`

### Resolution rules

Given `base_dir = /data` in the sidecar:

- `file_path` resolves to `/data/<file_path>`
- `thumbnail_path` resolves to `/data/<thumbnail_path>`
- `source_3mf_path` resolves to `/data/<source_3mf_path>`
- `timelapse_path` resolves to `/data/<timelapse_path>`
- `f3d_path` resolves to `/data/<f3d_path>`

Archive photo files are not stored as full DB paths.

Photo rule:

- if `file_path` resolves to a file, define `archive_dir = parent(file_path)`
- photo files live under `archive_dir / "photos" / <filename>`
- use the archive's `photos` list as the authoritative candidate file list

### Fallback and incomplete archives

Some fallback archives have empty `file_path`.

Rules:

- never derive `archive_dir` from an empty `file_path`
- only derive folder-scoped photo and residual scans when `file_path` is non-empty and resolves to a file
- explicit asset fields such as `thumbnail_path` or `source_3mf_path` may still be scanned individually even when `file_path` is empty
- mark scan status as partial when folder-based traversal could not be performed

## Sidecar API Contract

The sidecar should expose a narrow read API.

### 1. Scan one archive

`POST /admin/archive-storage/scan`

Request body:

```json
{
  "archive_id": 171,
  "force": false,
  "include_other_files": true,
  "include_extension_breakdown": false,
  "max_other_entries": 2000
}
```

Behavior:

- load the archive row from Bambuddy
- resolve all known asset paths
- stat known assets
- if possible, scan the archive directory for residual files
- return a normalized metric payload

Suggested response:

```json
{
  "archive_id": 171,
  "scan_status": "complete",
  "scan_basis": "sqlite+filesystem",
  "base_dir": "/data",
  "resolved_archive_dir": "/data/archive/1/20260328_095504_0.08mm layer, 1 walls, 100% infill",
  "metrics": {
    "total_bytes": 8123456,
    "archive_3mf_bytes": 7569585,
    "thumbnail_bytes": 48321,
    "source_3mf_bytes": 0,
    "timelapse_bytes": 0,
    "f3d_bytes": 0,
    "photo_bytes": 505550,
    "photo_count": 4,
    "other_bytes": 0,
    "other_file_count": 0,
    "files_missing_count": 0
  },
  "artifacts": {
    "file_path": {
      "relative_path": "archive/1/.../print.3mf",
      "exists": true,
      "bytes": 7569585
    },
    "thumbnail_path": {
      "relative_path": "archive/1/.../thumbnail.png",
      "exists": true,
      "bytes": 48321
    },
    "source_3mf_path": {
      "relative_path": "",
      "exists": false,
      "bytes": 0
    },
    "photos": [
      {"filename": "a1b2c3d4.jpg", "exists": true, "bytes": 143210},
      {"filename": "b2c3d4e5.jpg", "exists": true, "bytes": 121000}
    ]
  },
  "computed_at": "2026-04-20T20:10:00Z"
}
```

### 2. Scan many archives

`POST /admin/archive-storage/scan-batch`

Request body:

```json
{
  "archive_ids": [171, 172, 173],
  "force": false,
  "include_other_files": true,
  "max_archives": 100
}
```

Suggested response:

```json
{
  "requested_count": 3,
  "completed_count": 3,
  "failed_count": 0,
  "results": [
    {"archive_id": 171, "scan_status": "complete", "total_bytes": 8123456},
    {"archive_id": 172, "scan_status": "partial", "total_bytes": 2100455},
    {"archive_id": 173, "scan_status": "missing", "total_bytes": 0}
  ],
  "computed_at": "2026-04-20T20:11:00Z"
}
```

### 3. Aggregate volume summary

`GET /admin/archive-storage/summary`

Purpose:

- support a quick sidecar-native summary when needed
- useful for validating scan logic before HA caching is in place

Suggested response:

```json
{
  "totals": {
    "archive_total_bytes": 4567890123,
    "archive_3mf_bytes": 3212345678,
    "thumbnail_bytes": 12345678,
    "source_3mf_bytes": 456789012,
    "timelapse_bytes": 654321000,
    "f3d_bytes": 0,
    "photo_bytes": 231234567,
    "other_bytes": 123456188
  },
  "archive_count": 812,
  "computed_at": "2026-04-20T20:12:00Z"
}
```

Important boundary:

- HA should treat this summary as optional convenience output
- the durable aggregate view should come from summing the local cached table, not from depending on a live sidecar summary for every dashboard render

## HA Local Store Schema

Add a dedicated local table rather than widening `archives`.

### `archive_storage_metrics`

Suggested schema:

| Column | Type | Ownership | Notes |
|---|---|---|---|
| `archive_id` | integer PK/FK | local | one row per archive |
| `scan_status` | text | local | `complete`, `partial`, `missing`, `error`, `stale` |
| `scan_basis` | text | local | `sqlite+filesystem`, `filesystem_only`, `unknown` |
| `resolved_archive_dir` | text | local | absolute or normalized path seen by sidecar |
| `archive_3mf_bytes` | integer | derived | from `file_path` |
| `thumbnail_bytes` | integer | derived | from `thumbnail_path` |
| `source_3mf_bytes` | integer | derived | from `source_3mf_path` |
| `timelapse_bytes` | integer | derived | from `timelapse_path` |
| `f3d_bytes` | integer | derived | from `f3d_path` |
| `photo_bytes` | integer | derived | total bytes across known photos |
| `photo_count` | integer | derived | existing photos found |
| `other_bytes` | integer | derived | residual files under archive dir |
| `other_file_count` | integer | derived | residual file count |
| `files_missing_count` | integer | derived | referenced asset files missing on disk |
| `total_bytes` | integer | derived | sum of all archive-scoped bytes |
| `extension_breakdown_json` | text | derived | optional compact JSON map |
| `artifact_details_json` | text | derived | optional compact per-asset existence/size detail |
| `last_scanned_at` | text | local | UTC timestamp |
| `scan_duration_ms` | real | local | diagnostics |
| `scan_error` | text | local | last error summary |
| `source_snapshot_hash` | text | local | hash of relevant path/value inputs |
| `updated_at` | text | local | row update audit |

Suggested indexes:

- primary key on `archive_id`
- index on `last_scanned_at`
- index on `scan_status`
- index on `total_bytes`

## Input Snapshot Hash

To avoid rescanning when nothing relevant changed, compute a compact input hash from the archive fields that affect storage resolution:

- `file_path`
- `thumbnail_path`
- `source_3mf_path`
- `timelapse_path`
- `f3d_path`
- normalized `photos[]`
- optionally `updated_at` or `content_hash` if available and useful

If the hash matches and the row is not stale by policy, HA may reuse the cached metrics.

## Suggested HA Service Contract

These are integration services, not sidecar endpoints.

### `bambuddy.get_print_history_archive_storage_metrics`

Input:

- `archive_id`
- optional `entry_id`
- optional `refresh`

Behavior:

- return cached metrics when present and fresh
- if `refresh = true` or cached row is stale/missing, call the sidecar scan endpoint, persist the result locally, then return the refreshed row

### `bambuddy.refresh_print_history_archive_storage_metrics`

Input:

- `archive_id`
- optional `entry_id`

Behavior:

- always call sidecar scan
- persist local row
- return refreshed result

### `bambuddy.refresh_print_history_archive_storage_metrics_batch`

Input:

- `archive_ids`
- optional `entry_id`

Behavior:

- call sidecar batch scan
- persist updated rows
- schedule browser recompute only after the batch finishes

Current implementation status:

- implemented as an explicit archive-ID batch refresh service
- suitable for multi-select UI actions, manual operator backfills, and scripted maintenance jobs
- not yet wired to discover stale or recently changed archives automatically

## Query-Surface Guidance

The active browser should not load this data for every row by default.

Recommended use:

- popup detail hydration for a single archive
- optional browser sort/filter on size only after the local table exists and is indexed
- separate summary cards or diagnostics panels

Not recommended as a first step:

- injecting per-archive size chips into all browser cards by default
- adding heavy size breakdown payloads into summary entity attributes

## Statistics View Ideas

If aggregate display graduates beyond popup diagnostics, the Print History Statistics view is the best fit.

Why Statistics is the right surface:

- it already carries aggregate and trend-oriented expectations
- it avoids making the main browser heavier by default
- it gives storage analytics a place to evolve without forcing per-row card clutter

Useful first Statistics slices:

- total tracked archive storage across all cached rows
- stacked breakdown by asset class: archive 3MF, source 3MF, thumbnails, photos, timelapses, F3D, other
- top archives by `total_bytes`
- largest photo-heavy archives versus largest timelapse-heavy archives
- scan coverage summary: complete, partial, missing, error, stale

Useful grouped rollups after the first aggregate pass:

- storage by printer
- storage by project
- storage by print status
- storage by month or week of completion
- average bytes per archive for selected date ranges

Useful derived diagnostics:

- orphan-heavy archives where `other_bytes` is unexpectedly large
- archives with high `files_missing_count`
- archives where photos dominate total footprint
- archives where source 3MF attachment footprint is materially larger than the archived print file

Possible presentation patterns for Statistics:

- a headline totals card for overall tracked bytes and archive count
- a stacked bar or donut for asset-class composition
- a sortable table for largest archives
- trend charts by completion month once enough cached rows exist

Important guardrail:

- Statistics cards should aggregate from the HA local `archive_storage_metrics` table, not call the sidecar summary endpoint on every render

## Refresh Policy

Default recommendation:

- fetch on demand for the popup when missing or stale
- keep a freshness TTL such as 24 hours for complete rows
- use a shorter TTL such as 1 hour for partial or error rows
- invalidate immediately when archive detail changes a relevant asset-path field

Current implementation status:

- popup reads from cache and can refresh a single archive on demand
- explicit multi-select batch refresh exists for operator-driven refreshes
- archive delete cleanup removes the local storage-metrics row
- mutation-triggered invalidation or recompute is not yet wired for photo add/delete, source 3MF upload/replace, or timelapse attach/replace/scan-attach

Recommended mutation policy:

- primary-photo selection changes should not affect storage metrics
- photo add/delete should mark the row stale or refresh it immediately
- source 3MF attach/replace should mark the row stale or refresh it immediately
- timelapse attach/replace/scan-attach should mark the row stale or refresh it immediately
- delete should continue removing the row entirely

Optional background behavior:

- low-priority nightly backfill for missing/stale rows
- manual operator-triggered full refresh

If scheduled maintenance is added later, prefer:

- nightly refresh of `missing`, `partial`, `error`, or `stale` rows
- or nightly refresh of recently touched archives

Avoid using a nightly full-library rescan as the default steady-state path unless archive count remains small.

## Scan Classification Rules

Known file classes should win before residual classification.

Suggested precedence:

1. main archive 3MF from `file_path`
2. thumbnail from `thumbnail_path`
3. source 3MF from `source_3mf_path`
4. timelapse from `timelapse_path`
5. F3D from `f3d_path`
6. photos from `archive_dir/photos/<filename>` matching DB photo list
7. everything else under `archive_dir` becomes `other`

Important guardrail:

- do not count the same file twice if an explicit asset field and a residual folder walk both see it

## Failure Semantics

`scan_status` should mean:

- `complete` — all applicable asset paths resolved and folder scan performed where possible
- `partial` — some explicit assets scanned, but folder-level scan or one or more known assets could not be fully resolved
- `missing` — no resolvable files found for the archive
- `error` — operational failure during DB read or filesystem scan
- `stale` — cached row retained but known to need refresh

## Security And Mount Guidance

Recommended mount posture for a storage-scan sidecar:

- mount the Bambuddy data volume read-only when the sidecar is only used for storage metrics

If the same sidecar image also performs runtime repair:

- either keep separate read-only and read-write deployment modes
- or split runtime repair and storage scanning into separate services if least privilege matters operationally

The feature does not require:

- Bambuddy log volume access
- Home Assistant config volume access
- network access to Bambuddy media URLs for file-size measurement

## Initial Implementation Slice

The smallest useful implementation is:

1. sidecar endpoint for one-archive scan
2. local `archive_storage_metrics` table in the Variant 3 store
3. HA service to refresh one archive and persist the result
4. popup detail section showing the cached size breakdown

That is enough to validate:

- path resolution
- fallback archive handling
- scan cost
- whether the data is useful before adding aggregate dashboards or browser-wide sorting

## Future Extensions

Possible follow-on work after the first slice is proven:

- aggregate storage rollups by printer, project, date range, or status
- dedicated Statistics cards for storage composition and top-footprint archives
- browser sort/filter by `total_bytes`
- explicit photo-size distribution metrics
- richer per-photo diagnostics sourced from `artifacts.photos[].bytes`
- residual-file diagnostics for suspicious archives
- shared storage summary views that align with Bambuddy's broader system storage reporting

## Recommendation

Proceed with a narrow sidecar scan API plus a dedicated HA local table.

That keeps the architecture clean:

- Bambuddy continues to own archive records and paths
- the sidecar does the filesystem-heavy work
- HA owns derived caching and query surfacing
- Layer 1 archive projection stays lean