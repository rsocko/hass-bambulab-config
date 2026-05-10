# Unified Queue State Transitions

Issue: #1407 (UQ-01c)

## Transition Matrix

Allowed queue-entry transitions:

- `idea -> todo`
- `todo -> ready`
- `ready -> started`
- `started -> blocked`
- `started -> done`
- `blocked -> ready` (recovery/revert)
- `blocked -> done` (operator skip)

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

Supported recovery path:

- `blocked -> ready`

This is intended for operator-driven recovery after resolving blocker conditions.
