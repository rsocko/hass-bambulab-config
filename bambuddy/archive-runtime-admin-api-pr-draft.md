# Bambuddy PR Draft: Admin Runtime Repair Endpoint For Archives

## Purpose

Describe the upstream-friendly API change that would eliminate the need for direct DB writes when repairing archive runtime fields.

This draft is intentionally kept in the legacy `bambuddy/` folder because it is the upstream-facing artifact, not the Home Assistant feature design.

## Problem

Fallback or recovery-created archives can end up with canonical runtime fields that do not reflect the real print execution timeline.

Today:

- normal archive `PATCH` does not accept `started_at`, `completed_at`, or `created_at`
- there is no `PUT /api/v1/archives/{id}` archive-record update endpoint
- repairing canonical timing values requires direct database intervention

## Proposal

Add a dedicated admin-only endpoint rather than widening the normal archive `PATCH` schema.

### Proposed endpoint

`POST /api/v1/archives/{archive_id}/admin/runtime-repair`

## Why A Dedicated Endpoint

- runtime timestamp repair is administrative, not normal metadata editing
- validation rules are stricter than for notes or tags
- auditability matters more
- future related-repair behavior may include additional records such as print log entries

## Proposed Request Body

```json
{
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "failure_reason": null,
  "repair_print_log": false,
  "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
  "source": "external_recovery"
}
```

## Recommended Validation

- archive must exist
- datetimes must be valid ISO 8601
- `completed_at >= started_at` if both are supplied
- `status` must be a known archive status
- reject unrelated filesystem path fields entirely

## Recommended Behavior

In one transaction:

- update `print_archives.started_at`
- update `print_archives.completed_at`
- update `print_archives.created_at`
- update `print_archives.status`
- update `print_archives.failure_reason`
- append or replace a structured audit block in `notes`

Optional future behavior:

- if `repair_print_log = true`, attempt repair of related print-log records when that can be done safely

## Suggested Response

```json
{
  "archive_id": 123,
  "updated": true,
  "print_log_repaired": false,
  "print_log_status": "skipped",
  "before": {
    "started_at": null,
    "completed_at": null,
    "created_at": "2026-04-01T02:10:00+00:00",
    "status": "archived",
    "failure_reason": null
  },
  "after": {
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "status": "completed",
    "failure_reason": null
  }
}
```

## Auth Recommendation

Use a stronger permission than ordinary archive editing.

Suggested new permission semantics:

- `ARCHIVES_RUNTIME_REPAIR`
- or `ARCHIVES_ADMIN_REPAIR`

## Why This Helps

- avoids direct DB writes from external tooling
- preserves validation near the data model
- gives external systems a stable contract
- makes runtime repair auditable and testable

## Compatibility Note

This endpoint can be added without changing current archive `PATCH` semantics.

That makes it a lower-risk upstream enhancement than expanding the normal archive metadata schema.