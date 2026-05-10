# Unified Queue One-Time Cutover Runbook

Issue: #1432 (UQ-Cutover-04)

## Goal

Retire legacy queue migration bridge after one-time migration from model catalog legacy fields (`to_print_status`, `to_print_priority`) to unified queue entries.

## Preconditions

- Unified queue endpoints are deployed and healthy.
- HA package cutover is complete (legacy queue services/commands removed).
- A maintenance window is approved for cutover execution.

## Backup and Rollback Safety

1. Take a DB backup before migration:

```powershell
Copy-Item model_catalog.db model_catalog.pre-uq-cutover.backup.db
```

2. Record current schema version and queue counts.
3. Preserve backup until post-cutover validation and smoke tests complete.

## Pre-Cutover Validation

Run these checks against the target DB:

```sql
-- Legacy queue field inventory
SELECT field_key, COUNT(*) AS count
FROM model_catalog_custom_fields
WHERE entity_type = 'manyfold_model'
  AND field_namespace = 'model_catalog'
  AND field_key IN ('to_print_status', 'to_print_priority')
GROUP BY field_key;

-- Existing unified queue catalog-model entries
SELECT COUNT(*) AS catalog_model_entries
FROM unified_queue_entries
WHERE source_kind = 'catalog_model';
```

## One-Time Migration Procedure

Because the API bridge is retired, migration is executed as an explicit one-time DB operation in the cutover script/runbook environment.

1. Build candidate legacy model set where `to_print_status` is `queued` or `done`.
2. Skip any model already represented in `unified_queue_entries` (`source_kind='catalog_model'`).
3. Create queue entries with state mapping:
   - `queued -> todo`
   - `done -> done`
4. Assign deterministic rank order (priority-desc, then model id asc) for stable migration behavior.
5. Write audit records for each inserted row.

## Post-Cutover Validation

```sql
-- Verify no duplicate catalog_model source refs
SELECT source_ref, COUNT(*) AS count
FROM unified_queue_entries
WHERE source_kind = 'catalog_model'
GROUP BY source_ref
HAVING COUNT(*) > 1;

-- Check state distribution for migrated catalog-model entries
SELECT state, COUNT(*) AS count
FROM unified_queue_entries
WHERE source_kind = 'catalog_model'
GROUP BY state
ORDER BY state;
```

Spot-check at least 10 migrated models:

- Confirm source model id/ref mapping is correct.
- Confirm expected state (`todo`/`done`).
- Confirm rank ordering policy applied.

## Runtime Retirement (Completed in #1432)

- Removed `POST /api/unified-queue/migrate-legacy` endpoint.
- Removed `migrate_legacy_catalog_queue_fields` helper and associated helper functions.
- Removed migration-only tests and migration-only compatibility docs.

## Execution Record

- Environment(s): ____________________________
- Backup artifact(s): ________________________
- Legacy row counts before: _________________
- Unified queue counts before: ______________
- Migrated entries inserted: ________________
- Spot checks completed by: _________________
- Validation timestamp: ______________________
- Approved by: ______________________________

## Rollback Procedure

If post-cutover checks fail:

1. Stop write traffic to sidecar.
2. Restore DB from `model_catalog.pre-uq-cutover.backup.db`.
3. Re-run pre-cutover checks.
4. Fix migration script data issue and rerun in maintenance window.
