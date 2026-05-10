# Unified Queue Legacy Compatibility Migration

Issue: #1409 (UQ-01d)

## Purpose

Provide a compatibility bridge from legacy model catalog queue metadata to unified queue entries.

Legacy fields:

- `to_print_status`
- `to_print_priority`

## Mapping

Source table: `model_catalog_custom_fields` (`entity_type = manyfold_model`, `field_namespace = model_catalog`)

Status mapping:

- `queued -> todo`
- `done -> done`
- `none` / empty -> skipped

Priority handling:

- `to_print_priority` is used to preserve relative ordering.
- Candidates are sorted by priority DESC and assigned queue `rank` starting at 1.

## API

Run migration:

- `POST /api/unified-queue/migrate-legacy`

Optional payload:

- `actor` string (for audit payload)

Operation characteristics:

- idempotent (existing `catalog_model` source refs are skipped)
- non-destructive (legacy fields are retained)
- writes audit events (`unified_queue_legacy_migration`)

## Rollback Path

If rollback is required:

1. Identify migrated entries by `source_kind = catalog_model` and `queue_notes = Migrated from legacy model_catalog queue fields`, or by matching migration audit events (`event_type = unified_queue_legacy_migration`).
2. Delete only the migrated unified queue rows from `unified_queue_entries`.
3. Do not delete legacy `model_catalog_custom_fields` rows (`to_print_status`, `to_print_priority`) unless performing a separate, explicit cleanup task.

Because legacy fields are preserved, rollback is safe and does not require reconstructing prior metadata.
