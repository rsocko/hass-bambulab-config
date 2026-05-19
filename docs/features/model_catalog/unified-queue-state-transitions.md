# Unified Queue State Transitions

Issue: #1407 (UQ-01c)

## Transition Matrix

Allowed queue-entry transitions:

**Forward path (main workflow):**
- `backlog → up_next`
- `up_next → preparing`
- `preparing → ready`
- `ready → in_progress`
- `in_progress → done`

**Backwards/deprioritization moves:**
- `up_next → backlog` (defer to parking)
- `ready → up_next` (deprioritize but keep committed)
- `ready → backlog` (move back to parking)
- `preparing → up_next` (abort prep, return to queue)
- `done → in_progress` (reprint same entry)

**Blocking/recovery:**
- `up_next → blocked`
- `preparing → blocked`
- `ready → blocked`
- `in_progress → blocked` (issue encountered)
- `blocked → preparing` (recovery attempt)
- `blocked → ready` (recovery — skip prep)
- `blocked → in_progress` (recovery — continue)
- `blocked → done` (operator skip)

No other transitions are valid.

## Validation Behavior

When a transition is invalid, API returns `400` with:

- `error: "invalid_transition"`
- `from_state`
- `to_state`
- `allowed_targets`

## Audit Logging

Each valid state transition writes an immutable event row to `model_catalog_events`:

- `event_type: unified_queue_state_transition`
- `entity_type: unified_queue_entry`
- `entity_id: <queue_entry_id>`
- `payload_json`: includes `from_state`, `to_state`, `actor`, `reason`, `transitioned_at`

## Revert Operations

Supported recovery paths:

- `blocked → ready` (skip issue, proceed)
- `blocked → preparing` (restart prep)
- `blocked → in_progress` (continue if issue resolved)
- `ready → up_next` (deprioritize)
- `ready → backlog` (park it)
- `preparing → up_next` (abort prep)
- `done → in_progress` (reprint)

---

## Done-Entry Retention & Cleanup

### Problem

`done` entries accumulate indefinitely. They contain planning metadata
(rank, scores, blocked reasons, selection mode) that has zero value after
completion, and execution-level data (timings, filament, temperatures) is
already captured in the Bambuddy archive linked via `last_archive_id` /
`completed_by_archive_id`. Unbounded growth slows active-queue queries and
wastes storage.

### Retention Policy (proposed)

| Rule | Value |
|------|-------|
| Default retention window | **30 days** after `completed_at` |
| Configurable via | Sidecar env var `QUEUE_DONE_RETENTION_DAYS` (int, default `30`) |
| Sweep cadence | Daily background task (or on-demand `POST /api/unified-queue/purge-done`) |

### Pre-Purge Stamp-Out

Before deleting a `done` entry, stamp durable facts onto the linked catalog
model (or archive tags) so they survive:

| Fact | Destination | Notes |
|------|-------------|-------|
| `copies_requested` vs `copies_completed` | Catalog model `print_stats` JSON | "Planned 6, printed 4" — not recorded elsewhere |
| `queue_notes` (if non-empty) | Archive tags or catalog model notes | Operator intent captured at planning time |

All other queue-only fields (`rank`, `ams_ready_score`, `overnight_fit_score`,
`duration_bucket`, `selection_mode`, `blocked_reason`) are discarded — they
are stale planning artifacts.

### What Already Survives Without Stamping

- **State-transition history** — Every transition (including `→ done`) is
  already written to `model_catalog_events` with timestamps, actor, and
  reason. The audit trail persists independently of the queue row.
- **Archive linkage** — `last_archive_id` and plate-level
  `completed_by_archive_id` values are recorded in events and in the archive
  itself, so the print-history ↔ queue-entry relationship is not lost.

### Cascade Behavior

Deleting a queue entry must also delete its child rows:

1. `unified_queue_file_units` (by `queue_entry_id`)
2. `unified_queue_plate_units` (by `queue_entry_id`)
3. `unified_queue_match_suggestions` where `queue_entry_id` or
   `remapped_queue_entry_id` matches (set null or delete per FK policy)

### API Surface

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/unified-queue/purge-done` | POST | On-demand purge; accepts optional `?older_than_days=N` override |
| Background task | — | Runs daily at sidecar startup + every 24 h; respects `QUEUE_DONE_RETENTION_DAYS` |

Response: `{ "purged_count": <int>, "stamped_count": <int> }`
