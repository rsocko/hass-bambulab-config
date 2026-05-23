# Archive Runtime `restore_from` Field Matrix

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/runtime-repair/archive-runtime-restore-from-field-matrix.md
Replaced By: none

## Purpose

Define the default field-by-field policy for a future sidecar endpoint that merges a source archive into a recovered target archive.

Primary reference case:

- source fallback archive `191`
- target recovered archive `200`

## Policy Meanings

| Policy | Meaning |
| --- | --- |
| `copy_source` | Copy source value to target when source is present and differs |
| `keep_target` | Keep target value even when source differs |
| `merge_tags` | Merge normalized tag sets with exclusions |
| `merge_notes` | Merge notes with structured audit append behavior |
| `disallowed` | Do not copy this field from source to target |
|

## Missing-Source Rule

Unless a field explicitly says otherwise:

- if source is null, empty, or absent, do not clear target
- record `skip_missing_source`

## Equal-Value Rule

Unless a field explicitly says otherwise:

- if normalized source and target are equal, do not write
- record `skip_equal`

## Field Matrix

| Field Path | Group | Default Policy | Source Of Truth | Missing Source Behavior | Notes |
| --- | --- | --- | --- | --- | --- |
| `started_at` | runtime | `copy_source` | source | keep target | Original run start should copy forward when present |
| `completed_at` | runtime | `copy_source` | source | keep target | Original run completion should copy forward when present |
| `created_at` | runtime | `copy_source` | source | keep target | Prefer original historical record creation time |
| `status` | runtime | `copy_source` | source | keep target | Typically restore `completed` over recovery-time `archived` |
| `failure_reason` | runtime | `copy_source` | source | keep target | Only if source has a meaningful value |
| `actual_time_seconds` | runtime-derived | `disallowed` | derived | keep target | Recompute from repaired timestamps if supported; do not copy directly |
| `is_favorite` | user_metadata | `copy_source` | source | keep target | User intent should survive recovery |
| `cost` | user_metadata | `copy_source` | source | keep target | Copy only when source has a real value |
| `quantity` | user_metadata | `copy_source` | source | keep target | User-managed metadata |
| `external_url` | user_metadata | `copy_source` | source | keep target | User-managed metadata |
| `tags` | user_metadata | `merge_tags` | merged | preserve target | Carry forward user tags, exclude fallback markers |
| `notes` | lineage | `merge_notes` | merged | preserve target | Preserve target notes and append structured audit once |
| `file_path` | parser_target | `keep_target` | target | keep target | Recovered archive owns canonical file path |
| `file_size` | parser_target | `keep_target` | target | keep target | Recovered archive owns canonical file size |
| `content_hash` | parser_target | `keep_target` | target | keep target | Recovered archive owns canonical content hash |
| `thumbnail_path` | parser_target | `keep_target` | target | keep target | Recovered archive owns canonical thumbnail |
| `timelapse_path` | parser_target | `keep_target` | target | keep target | Preserve recovered archive asset references |
| `source_3mf_path` | parser_target | `keep_target` | target | keep target | Preserve target-side source attachment path if present |
| `f3d_path` | parser_target | `keep_target` | target | keep target | Preserve target-side generated viewer asset path |
| `print_name` | parser_target | `keep_target` | target | keep target | Prefer parser/model-derived replacement value |
| `print_time_seconds` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `filament_used_grams` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `filament_type` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `filament_color` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `layer_height` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `total_layers` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `nozzle_diameter` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `bed_temperature` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata if present |
| `nozzle_temperature` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `sliced_for_model` | parser_target | `keep_target` | target | keep target | Prefer parsed sliced metadata |
| `designer` | parser_target | `keep_target` | target | keep target | Prefer parser/MakerWorld metadata |
| `makerworld_url` | parser_target | `keep_target` | target | keep target | Prefer parser/MakerWorld metadata |
| `project_id` | target_identity | `keep_target` | target | keep target | Do not rewrite linkage identifiers in restore merge |
| `project_name` | target_identity | `keep_target` | target | keep target | Do not rewrite linkage identifiers in restore merge |
| `printer_id` | target_identity | `keep_target` | target | keep target | Recovered archive already belongs to correct printer |
| `duplicates` | target_identity | `disallowed` | system | keep target | System-maintained relationship data |
| `duplicate_count` | target_identity | `disallowed` | system | keep target | System-maintained relationship data |
| `duplicate_sequence` | target_identity | `disallowed` | system | keep target | System-maintained relationship data |
| `original_archive_id` | lineage | `keep_target` | target | keep target | Preserve existing target lineage semantics |
| `photos` | asset_state | `merge_photos` | merged | preserve target | Preserve target photos and upload only source-only photos to the target archive via Bambuddy API |
| `energy_kwh` | user_metadata | `copy_source` | source | keep target | Copy only if source has meaningful historical value |
| `energy_cost` | user_metadata | `copy_source` | source | keep target | Copy only if source has meaningful historical value |
| `created_by_id` | audit_identity | `keep_target` | target | keep target | Preserve actual creator of recovered record unless explicit override is ever required |
| `created_by_username` | audit_identity | `keep_target` | target | keep target | Preserve actual creator of recovered record unless explicit override is ever required |

## Current Duplicate And Provenance Limits

The current `restore_from` implementation merges two existing archive rows. It does not perform duplicate discovery against external SD-card/import evidence.

Important implications:

- `duplicate_count`, `duplicate_sequence`, and `original_archive_id` remain computed Bambuddy outputs, not manually copied fields
- a same-hash relationship can mean either `already represented` or `suspicious duplicate/mismatch`; `restore_from` does not decide that today
- source-file fingerprints, timing-evidence confidence, and operator duplicate-review decisions need a separate provenance store rather than being inferred from archive-row fields alone

## `extra_data` Matrix

| Field Path | Group | Default Policy | Source Of Truth | Missing Source Behavior | Notes |
| --- | --- | --- | --- | --- | --- |
| `extra_data.no_3mf_available` | snapshot | `disallowed` | source fallback only | keep target | Marker must not be copied onto recovered archive |
| `extra_data._print_data.*` | snapshot | `disallowed` | source fallback only | keep target | Too large and transient for raw copy |
| `extra_data.original_subtask` | snapshot_subset | `disallowed` by default | source | keep target | May be copied only into curated audit payload later |
| `extra_data.designer` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.print_name` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.print_time_seconds` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.total_layers` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.filament_type` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.filament_color` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.filament_used_grams` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.filament_slots[*]` | parser_target | `keep_target` | target | keep target | Prefer parsed target per-slot usage data |
| `extra_data.makerworld_model_id` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| `extra_data.makerworld_url` | parser_target | `keep_target` | target | keep target | Prefer parsed target metadata |
| curated snapshot payload in notes | snapshot_subset | optional copy | source | skip if missing | Only for selected small provenance fields such as tray UUIDs |

## Proposed HA-Side Provenance Store Matrix

These fields are not natural top-level Bambuddy archive columns. Store them in the Home Assistant print-history SQLite store, then surface a compact summary in Bambuddy notes and popup detail.

| Field Path | Group | Default Policy | Source Of Truth | Missing Source Behavior | Notes |
| --- | --- | --- | --- | --- | --- |
| `provenance.origin_kind` | provenance | `copy_or_override` | workflow | keep existing | Example values: `native`, `recovered_replacement`, `historical_import`, `manual_file_import` |
| `provenance.source_sha256` | provenance | `copy_or_override` | intake runner | keep existing | Primary idempotency key for SD/import evidence |
| `provenance.source_path` | provenance | `copy_or_override` | intake runner | keep existing | Store normalized backup-relative path when available |
| `provenance.restored_from_archive_id` | lineage | `copy_or_override` | restore workflow | keep existing | Links replacement/import record back to the prior archive when one existed |
| `provenance.replaced_archive_id` | lineage | `copy_or_override` | restore workflow | keep existing | Reverse link for the replaced archive when retained |
| `provenance.duplicate_review_state` | provenance | `copy_or_override` | operator | keep existing | Example values: `unreviewed`, `already_represented`, `suspicious_duplicate`, `approved_distinct_history` |
| `provenance.inferred_started_at` | timing_evidence | `copy_or_override` | timing engine | keep existing | Evidence value only unless elevated into canonical `started_at` |
| `provenance.inferred_completed_at` | timing_evidence | `copy_or_override` | timing engine | keep existing | Evidence value only unless elevated into canonical `completed_at` |
| `provenance.inferred_created_at` | timing_evidence | `copy_or_override` | timing engine | keep existing | Evidence value only unless elevated into canonical `created_at` |
| `provenance.inferred_actual_time_seconds` | timing_evidence | `copy_or_override` | timing engine | keep existing | Useful for review when start/end are estimated |
| `provenance.timing_confidence` | timing_evidence | `copy_or_override` | timing engine | keep existing | `high`, `medium`, or `low` |
| `provenance.timing_sources[]` | timing_evidence | `merge_list` | timing engine | keep existing | Example values: `ha_recorder_transition`, `filesystem_last_modified`, `bbl_timestamp`, `zip_member_timestamp` |
| `provenance.timing_applied_to_canonical` | timing_evidence | `override` | sidecar apply | keep existing | Records whether inferred values were actually written into canonical archive columns |

## Canonical Runtime Write Rule For Inferred Timing

Use these rules when the source of truth is inferred timing rather than an already-existing Bambuddy source archive:

- `high` confidence: sidecar may update `started_at`, `completed_at`, and `created_at` automatically in apply mode
- `medium` confidence: require explicit operator approval or an explicit request flag before canonical writes
- `low` confidence: do not update canonical runtime fields; keep the evidence only in the HA-side provenance store and compact notes metadata

If only `completed_at` is strong and the start is estimated from `print_time_seconds`, mark that derivation explicitly in provenance and do not present it as a directly observed timestamp.

## Tag Policy Details

### Copy Forward By Default

- freeform user tags such as `Hueforge`
- enrichment tags already present on target should remain
- recovery lineage tags may exist on the target while a restore workflow is in flight, but they are not permanent after completion

### Exclude By Default

- `exception:missing_3mf`
- `replaced_by:*`

### Keep On Target

- `f:<id>`
- `s:<id>`

### Remove On Completion

When `verify + remove_original` succeeds, collapse recovery state into notes-only provenance on the surviving target.

- `repair:pending`
- `repair:failed`
- `repair:recovered`
- `recovered_from:<id>`
- `recovery_source:<value>`
- `exception:missing_3mf`
- `replaced_by:*`

## Notes Policy Details

### Keep

- existing target notes content
- existing `+>` block on target
- existing `[RECOVERY_AUDIT_V1]` block on target if already correct

### Append Or Update

- one structured recovery audit block containing original runtime truth from source
- update that recovery audit block at completion with finalization metadata such as target archive id, completion timestamp, original removal flag, and removed transient tags
- optional structured source-snapshot provenance block if snapshot subset copying is enabled later
- compact provenance summary for import/restore origin and inferred timing confidence when that summary is not already present elsewhere

### Do Not Copy Blindly

- raw fallback notes if they duplicate target lineage information
- raw machine snapshot blobs

## Example Outcome For `191` To `200`

| Field | Outcome |
| --- | --- |
| `started_at` | copy from `191` |
| `completed_at` | copy from `191` |
| `created_at` | copy from `191` |
| `status` | copy from `191` |
| `is_favorite` | copy from `191` |
| `print_name` | keep `200` |
| `print_time_seconds` | keep `200` |
| `filament_used_grams` | keep `200` |
| `file_path` | keep `200` |
| `content_hash` | keep `200` |
| `tags` | merge, carrying forward `Hueforge` but excluding fallback-only tags |
| `notes` | merge, preserving target audit and enrichment blocks |
| `extra_data.no_3mf_available` | do not copy |
| `extra_data._print_data.raw_data.*` | do not copy |