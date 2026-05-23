# Unified Queue Deprecation Timeline

Issue: #1433 (UQ-Cutover-05)

## Purpose

Document migration and retirement milestones for historical model-catalog queue interfaces, and confirm unified queue as the sole active queue model.

## Historical Interfaces (Retired)

- `POST /api/models/{model_ref}/queue` (legacy model queue endpoint)
- `rest_command.model_catalog_update_model_queue`
- `model_catalog.queue_model_for_print`
- transitional bridge: `POST /api/unified-queue/migrate-legacy`

## Timeline

### Phase A: Unified Queue Introduction

- Added unified queue entry model and endpoints:
  - `POST /api/unified-queue/entries`
  - `GET /api/unified-queue/entries`
  - `PATCH /api/unified-queue/entries/{queue_entry_id}`
  - `DELETE /api/unified-queue/entries/{queue_entry_id}`
  - v1 compatibility list/add endpoints under `/api/v1/queues/{printer_id}`
- Browser queue actions and HA rest commands began migrating to unified queue operations.

### Phase B: Legacy Queue Contract Removal

- Removed legacy model queue endpoint and queue mutation side-effects.
- Removed HA legacy rest command/service surfaces.
- Removed queue filter passthrough based on `to_print_status`/`to_print_priority*`.

### Phase C: Migration Bridge Retirement

- Captured one-time migration and validation runbook:
  - `docs/features/model_catalog/unified-queue-cutover-runbook.md`
- Retired migration bridge API and helper implementation after cutover readiness.

### Phase D: Documentation Consolidation (This Issue)

- Updated queue docs to unified-only operator contract.
- Marked `to_print_status`/`to_print_priority` as legacy/historical metadata.
- Removed documentation that implied legacy queue APIs were active.

## Current Source of Truth

Unified queue is the single active queue system:

- state model: `idea`, `todo`, `ready`, `started`, `blocked`, `done`
- ordering model: explicit queue `rank`
- mixed-source entries: `catalog_model`, `working_group`, `working_file`, `idea`

Legacy `to_print_*` fields remain historical data only and must not be used for new queue behavior.

## Operator Guidance

- Use unified queue endpoints/commands for all queue operations.
- Use the cutover runbook for one-time migration execution/validation records.
- Treat legacy queue interfaces as removed and unsupported.
