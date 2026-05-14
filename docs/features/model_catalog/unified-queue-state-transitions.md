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
