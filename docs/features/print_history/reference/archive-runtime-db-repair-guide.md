# Bambuddy Archive Runtime DB Repair Guide

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/runtime-repair/archive-runtime-db-repair-guide.md
Replaced By: none

## Purpose

Document the direct-database repair path for Bambuddy archive runtime fields that are not writable through the public archive API.

This is a reference guide for one-off or controlled repairs used by the print_history feature set. It is not a claim that direct DB mutation is a supported upstream Bambuddy feature.

## Confirmed Constraints

Based on Bambuddy source review:

- `PATCH /api/v1/archives/{id}` uses `ArchiveUpdate`
- `ArchiveUpdate` does not include `started_at`, `completed_at`, or `created_at`
- there is no `PUT /api/v1/archives/{id}` archive-record update endpoint
- `actual_time_seconds` is computed from `started_at` and `completed_at`, not stored directly
- Bambuddy already ships a maintenance script that directly updates `created_at`, which is evidence that DB-level repair is technically viable

## What Can Be Repaired Safely Enough

Direct updates to `print_archives` are the practical path for restoring:

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`

Potentially also:

- `notes`
- `tags`
- `cost`
- `quantity`
- `external_url`
- `project_id`
- `printer_id`

## What Needs Extra Caution

These are not just metadata concerns:

- `file_path`
- `thumbnail_path`
- `timelapse_path`
- `source_3mf_path`
- `f3d_path`
- `photos`

Changing those by SQL alone can desynchronize the DB from the filesystem.

## Secondary Effects

### Search index

Low risk.

Bambuddy's SQLite FTS table is maintained by triggers on `print_archives`, so normal `UPDATE print_archives ...` statements should keep search rows in sync.

### Stats and list ordering

High impact.

Several Bambuddy views and stats queries filter or sort by `created_at`, not `started_at`. If you want repaired records to appear on the original date in archive listings and date-scoped stats, `created_at` usually needs to be updated alongside runtime fields.

### Print log

Independent table, medium to high risk.

`print_log_entries` stores copied timestamp values and does not point back to `archive_id`. Updating `print_archives` will not retroactively repair historical print-log entries.

Implication:

- archive detail views can become correct
- archive stats can become correct if `created_at` is repaired
- print log can still show stale timing data unless repaired separately

## Recommended Repair Policy

### Minimum repair for recovered archives

Update:

- `started_at`
- `completed_at`
- `created_at`

Optionally update:

- `status`
- `failure_reason`

Add an audit note in `notes` describing:

- when the DB repair happened
- where the original times came from
- whether `print_log_entries` were also repaired

### Do not attempt by SQL alone

- filesystem-backed path fields
- photo arrays unless you are also managing disk contents
- derived metadata that should come from reparsing a real `.3mf`

## Operational Safety

### Preferred conditions

- run during low activity
- back up `bambuddy.db` first
- ideally pause Bambuddy writes during the repair window
- use a single transaction per archive or per repair batch

### SQLite notes

Bambuddy uses SQLite with WAL enabled. That helps concurrent access, but it does not remove the need for discipline. Treat repair as an administrative maintenance action, not a normal automation path.

## Suggested SQL Shape

Example repair for one archive:

```sql
BEGIN TRANSACTION;

UPDATE print_archives
SET
  started_at = '2026-03-31 18:04:12+00:00',
  completed_at = '2026-03-31 21:47:05+00:00',
  created_at = '2026-03-31 21:47:05+00:00',
  status = 'completed',
  failure_reason = NULL
WHERE id = 123;

COMMIT;
```

## Suggested Python Repair Shape

Use Python or SQLAlchemy only as a thin transaction wrapper, not as a second archive parser.

Responsibilities:

- validate target archive exists
- validate ISO datetimes before writing
- back up the DB or require backup confirmation outside the script
- update only the allowed columns
- optionally dry-run and print current versus proposed values

## Best Use Cases

- one-off repair of recovered fallback archives
- controlled batch repair driven by a curated CSV or JSON input file
- repair after external worker has reconstructed original runtime values

## Poor Use Cases

- every-print automation path
- high-frequency writes directly from Home Assistant templates or automations
- blind repair without operator review

## Recommendation

Use direct DB repair as the current practical path when canonical Bambuddy archive timestamps must be restored.

If this becomes a repeated workflow, do not keep it as ad hoc SQL forever. Move it behind either:

- an external worker that runs container-local repair logic
- or a sidecar/admin API with clear validation and audit logging