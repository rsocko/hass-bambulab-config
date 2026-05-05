# Bambuddy Partial-Usage Contracts and Decision Tables

## Purpose

This document defines plan-level API and policy contracts for the partial-usage
hybrid workflow. It is implementation guidance and not a migration of
write-side authority away from Home Assistant.

## Authority Contract

- Home Assistant remains the only Spoolman writer.
- Sidecar provides estimate and consume orchestration data.
- Apply decisions are made by HA policy.

## Estimate Contract

Endpoint:

- `POST /admin/archive-partial-usage/estimate`

Request:

```json
{
  "archive_id": 123,
  "printer_id": "p1s-office",
  "outcome": "failed",
  "include_dedupe": true,
  "include_method_details": true
}
```

Response (target shape):

```json
{
  "archive_id": 123,
  "status": "ok",
  "estimate_total_g": 28.6,
  "slots": [
    {
      "slot_key": "ams_1_2",
      "spool_hint": {
        "tray_uuid": "...",
        "tray_index": 2
      },
      "estimated_g": 12.4,
      "method": "gcode_layer",
      "confidence": "high"
    }
  ],
  "method_summary": {
    "primary": "gcode_layer",
    "fallback_used": false
  },
  "signals": {
    "objects_skipped": true,
    "skip_signal_source": "timeline_event"
  },
  "dedupe": {
    "consume_key": "archive:123:partial",
    "already_consumed": false
  },
  "warnings": []
}
```

Required response fields:

- `archive_id`
- `status`
- `estimate_total_g`
- per-slot `estimated_g`, `method`, `confidence`
- `dedupe.consume_key`
- `dedupe.already_consumed`

## Consume Contract

Endpoint:

- `POST /admin/archive-partial-usage/consume`

Request:

```json
{
  "archive_id": 123,
  "consume_key": "archive:123:partial",
  "decision": "manual_apply",
  "expected_total_g": 28.6,
  "slots": [
    {
      "slot_key": "ams_1_2",
      "spool_id": 456,
      "grams": 12.4
    }
  ]
}
```

Response (target shape):

```json
{
  "archive_id": 123,
  "status": "applied",
  "idempotent_replay": false,
  "applied_total_g": 28.6,
  "spool_updates": [
    {
      "spool_id": 456,
      "delta_g": 12.4,
      "result": "ok"
    }
  ],
  "audit": {
    "consume_key": "archive:123:partial",
    "applied_at": "2026-05-03T00:00:00Z"
  }
}
```

Required behavior:

- repeated consume request with same key is idempotent
- no second decrement is performed on replay
- status clearly differentiates `applied` vs `already_applied`

## Decision Table

| Condition | Confidence | Policy Action | Notes |
|---|---|---|---|
| gcode layer usage + stable archive linkage | high | eligible for auto-apply (if enabled) | default preferred path |
| progress-derived estimate only | medium | review/manual apply | no default auto-apply |
| linear fallback only | low | review only | human validation required |
| spool mapping ambiguous | any | skip apply, notify | preserve safety |
| already consumed true | any | no-op, notify replay | idempotency guard |
| objects skipped with strong signal | high/medium | apply with downgrade to review if policy requires | explicit signal handling |
| objects skipped with weak/missing signal | any | review only | uncertainty hold |

## Confidence Policy Contract

Proposed normalized levels:

- `high`: layer-based estimate with consistent linkage
- `medium`: progress-derived estimate, partial linkage confidence
- `low`: linear fallback or missing linkage context

Policy helpers (HA-side) should support:

- minimum confidence for auto-apply
- method allowlist for auto-apply
- force-review when skip-object signal is weak

## Idempotency Contract

Consume key format (proposed):

- `archive:{archive_id}:partial`

Optional extension if multi-attempt semantics are required later:

- `archive:{archive_id}:partial:v{revision}`

Rules:

- one terminal decrement per archive per revision
- replay returns deterministic status
- HA stores consume result for operator traceability

## Error Contract

Standard error envelope (target shape):

```json
{
  "status": "error",
  "code": "ARCHIVE_NOT_FOUND",
  "message": "Archive 123 not found",
  "retryable": false
}
```

Minimum codes:

- `ARCHIVE_NOT_FOUND`
- `NO_ESTIMATE_AVAILABLE`
- `AMBIGUOUS_SPOOL_MAPPING`
- `ALREADY_CONSUMED`
- `INTERNAL_ERROR`

## Observability Contract

Every estimate/apply event should carry:

- archive ID
- outcome
- method and confidence
- grams total and per slot
- decision path (`review_only`, `manual_apply`, `auto_apply`, `skipped`)
- consume key and replay indicator (apply events)

These fields are required for rollout validation and incident triage.