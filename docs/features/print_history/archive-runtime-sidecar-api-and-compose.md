# Archive Runtime Sidecar API And Compose Draft

## Purpose

Define a concrete sidecar service shape for canonical Bambuddy archive runtime repair without modifying upstream Bambuddy.

This is the durable no-upstream option for print_history if direct DB repair becomes a recurring feature instead of a rare manual action.

Clarification:

The sidecar is not `n8n`-only. It exposes a normal HTTP endpoint that Home Assistant can call directly.

`n8n` is optional and is only useful when you want orchestration around the sidecar call or around broader recovery steps.

## Sidecar Responsibilities

The sidecar should own:

- request validation
- Bambuddy DB access
- repair transaction execution
- dry-run support
- audit logging
- narrow authentication

The sidecar should not own:

- print detection logic
- `.3mf` retrieval logic
- dashboard UX

Those remain with HA and optionally `n8n`.

## API Surface

## Supported Input Modes Today

Today the sidecar supports two repair modes:

- target archive ID plus explicit runtime metadata fields
- source archive ID plus target archive ID restore/verify flows for already-existing archive pairs

That means the caller can either provide explicit canonical runtime fields for one archive, or ask the sidecar to compare two existing Bambuddy archive rows and apply the current merge policy.

Current request model:

- `archive_id`
- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`
- `audit_note`
- `dry_run`

The sidecar then:

- loads the current target archive row
- validates the provided inputs
- updates only the provided runtime-repair fields
- appends an audit block to `notes` when `audit_note` is supplied

## Variations Supported Today

### 1. Direct explicit repair

Yes. This is the current implementation.

Example:

- archive ID `123`
- explicit `started_at`, `completed_at`, `created_at`
- optional `status`
- optional `failure_reason`

### 2. Partial repair

Yes.

You do not need to send every field. The service updates only the fields you provide.

Examples:

- only `created_at`
- only `status`
- only `started_at` and `completed_at`

### 3. Dry-run diff

Yes.

Set `dry_run: true` and the sidecar returns before and after values without applying the DB update.

### 4. Source archive ID plus target archive ID restore mode

Yes.

`POST /admin/archive-restore-from` is implemented today for an existing source/target pair.

Current behavior:

- loads both archive rows from the Bambuddy SQLite database
- applies the field-policy contract documented in [archive-runtime-restore-from-field-matrix.md](archive-runtime-restore-from-field-matrix.md)
- preserves parser-derived target fields such as `content_hash`, `thumbnail_path`, and `print_time_seconds`
- copies or merges selected runtime, user metadata, notes, tags, photos, and `extra_data`
- supports dry-run planning, apply mode, and optional post-merge re-enrich

Important limit:

- this mode only works when both records already exist in Bambuddy
- it does **not** inspect SD-card files, backfill manifests, `.bbl` sidecars, or other external evidence directly

### 5. Post-merge verification and optional original removal

Yes.

`POST /admin/archive-restore-verify` is implemented today.

Current behavior:

- re-runs the restore policy as a verification plan
- reports remaining actionable differences
- blocks source removal when actionable differences remain
- blocks source removal by default when enrichment is still incomplete
- can remove the original source row only after verification is clean

## Variations Not Implemented Yet

### 1. Duplicate preflight against external recovery/import evidence

Not implemented today.

Current restore behavior assumes the operator has already selected the correct source/target pair.

It does **not**:

- compare an SD-card candidate against existing Bambuddy archives before upload
- distinguish `already represented` from `same hash but suspiciously different archive metadata`
- maintain a sidecar-native duplicate review state for operator decisions

That logic belongs ahead of upload/restore and is currently only partially covered by the historical backfill tooling and docs.

### 2. Timing inference from SD-card or backup artifacts

Not implemented today.

Current restore behavior can:

- copy `started_at`, `completed_at`, and `created_at` from an existing source archive
- accept explicit operator-provided canonical runtime fields through runtime-repair mode

Current restore behavior cannot:

- derive print timing from `.3mf`, `.bbl`, filesystem, or backup evidence on its own
- score timing confidence
- apply `started_at` or `completed_at` from inferred evidence automatically

### 3. Provenance-aware canonical update from inferred timing

Not implemented today.

There is currently no first-class request model for:

- carrying a timing-evidence bundle into the sidecar
- recording the inference confidence that justified a canonical timestamp write
- distinguishing `recovered replacement`, `historical import`, and `manual inferred-timing correction` in one stable provenance contract

## Proposed Future Extension: Provenance-Aware Timing Mode

The live `191` to `200` comparison is a useful reference case for what this mode should and should not do.

Observed pattern:

- source archive `191` preserved the original runtime truth and some fallback-only printer snapshot data
- target archive `200` preserved the canonical file-backed metadata recreated from the recovered `.3mf`
- neither record alone contained the full desired historical result

That means `restore_from` should not behave like a blind row copy.

It should behave like a field-aware merge with explicit precedence rules.

That merge mode now exists in a first usable form.

The next extension should **not** be another blind copy option. It should be a provenance-aware timing and duplicate workflow layered on top of the existing merge path.

## Important Current-State Boundary

Today the sidecar covers this boundary well:

- repair canonical runtime fields on an existing archive
- merge a fallback/source archive into an existing recovered target archive
- verify the merge result and optionally remove the original source row

Today the sidecar does **not** cover this boundary:

- discover external SD-card candidates
- infer original print dates from file evidence
- decide whether a source file is already represented by a real-time archive or a previous restore/import
- persist rich provenance or timing-evidence history outside Bambuddy notes

That means duplicate prevention and timing inference must be designed as an intake/review layer ahead of sidecar apply, not bolted into the current merge call implicitly.

## Goal Of `restore_from`

Given:

- a source archive that represents the original print run, often incomplete or fallback-derived
- a target archive that represents the recovered file-backed replacement

produce:

- a target archive that keeps the replacement archive's canonical file metadata and parser-derived fields
- plus selected original runtime and user metadata copied forward from the source archive when appropriate

## Non-Goal Of `restore_from`

The mode should not:

- replace the recovered archive's parsed `.3mf` metadata with stale or lower-quality source values
- copy the source archive's entire `extra_data` blob verbatim
- propagate fallback markers onto the recovered archive as if they were still true
- assume every field exists on the source archive
- assume every differing field should be copied

## Proposed Request Shape

Example request:

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "copy_runtime_fields": true,
  "copy_user_metadata": true,
  "merge_tags": true,
  "merge_notes": true,
  "write_recovery_audit": true,
  "dry_run": false
}
```

Optional future refinement:

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "field_groups": ["runtime", "user_metadata", "lineage"],
  "exclude_tags": ["exception:missing_3mf", "replaced_by:*"],
  "preserve_target_parser_fields": true,
  "copy_source_snapshot_subset": [],
  "dry_run": true
}
```

## Proposed Endpoint Contract

### `POST /admin/archive-restore-from`

This endpoint is a future extension for source-to-target recovery merge.

It should be separate from `POST /admin/archive-runtime-repair` because the semantics are different:

- runtime repair updates one archive from explicit caller-provided values
- restore-from merge compares two archives and applies policy-driven field decisions

### Request Model

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "field_groups": ["runtime", "user_metadata", "lineage"],
  "tag_merge_mode": "merge_preserve_target",
  "notes_merge_mode": "append_structured",
  "preserve_target_parser_fields": true,
  "copy_source_snapshot_subset": [],
  "exclude_tags": ["exception:missing_3mf", "replaced_by:*"],
  "include_tags": [],
  "overrides": {
    "status": "completed"
  },
  "dry_run": true
}
```

### Required Request Fields

- `source_archive_id`: integer
- `target_archive_id`: integer
- `dry_run`: boolean

### Optional Request Fields

- `field_groups`: array of enums
- `tag_merge_mode`: enum
- `notes_merge_mode`: enum
- `preserve_target_parser_fields`: boolean, default `true`
- `copy_source_snapshot_subset`: array of enums, default `[]`
- `exclude_tags`: array of strings or wildcard patterns
- `include_tags`: array of strings, optional allow-list override
- `overrides`: object of explicit field overrides applied after merge planning

### `field_groups` Enum

Allowed values:

- `runtime`
- `user_metadata`
- `lineage`
- `snapshot_subset`

Recommended default:

```json
["runtime", "user_metadata", "lineage"]
```

### `tag_merge_mode` Enum

Allowed values:

- `merge_preserve_target`
- `source_only`
- `target_only`

Recommended default:

- `merge_preserve_target`

### `notes_merge_mode` Enum

Allowed values:

- `append_structured`
- `target_only`
- `source_then_target`

Recommended default:

- `append_structured`

### `copy_source_snapshot_subset` Enum

Allowed values:

- `tray_uuids`
- `source_subtask_name`
- `ams_slot_summary`

Recommended default:

- `[]`

### `overrides` Allowed Keys

Allowed keys should stay narrow:

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`
- `is_favorite`
- `cost`
- `quantity`
- `external_url`

Unknown override keys should be rejected.

## Proposed Next Extension: Timing-Inference Payload

If the sidecar is extended for inferred-timing workflows, the next contract should stay explicit and operator-auditable.

Recommended additions:

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "timing_inference": {
    "origin_kind": "historical_import",
    "timing_confidence": "medium",
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "actual_time_seconds": 13373,
    "sources": [
      "ha_recorder_transition",
      "sd_cache_3mf.print_time_seconds",
      "filesystem_last_modified"
    ],
    "operator_approved": false
  },
  "apply_inferred_runtime": false,
  "dry_run": true
}
```

Recommended semantics:

- `timing_inference` is evidence, not an automatic write instruction by itself
- `apply_inferred_runtime = true` should only be accepted when confidence is high or the operator explicitly approves medium-confidence evidence
- low-confidence evidence should remain provenance-only and should not update canonical Bambuddy timestamps
- the apply response should record whether canonical runtime fields came from an existing source archive, explicit override values, or inferred timing evidence

## Response Contract

### Dry-Run Response

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "updated": false,
  "applied": false,
  "field_action_summary": {
    "copy": 5,
    "merge": 2,
    "keep_target": 12,
    "skip_equal": 3,
    "skip_missing_source": 8,
    "skip_disallowed": 41,
    "override": 1
  },
  "field_actions": [
    {
      "field": "started_at",
      "group": "runtime",
      "action": "copy",
      "source_value": "2026-04-02T16:37:22.828591",
      "target_before": null,
      "target_after": "2026-04-02T16:37:22.828591",
      "reason": "runtime_truth_present_on_source"
    },
    {
      "field": "file_path",
      "group": "parser_target",
      "action": "keep_target",
      "source_value": "",
      "target_before": "archive/.../200x200 - AMS Ready - Slice & Print.3mf",
      "target_after": "archive/.../200x200 - AMS Ready - Slice & Print.3mf",
      "reason": "target_parser_field_has_priority"
    },
    {
      "field": "extra_data.no_3mf_available",
      "group": "snapshot_subset",
      "action": "skip_disallowed",
      "source_value": true,
      "target_before": null,
      "target_after": null,
      "reason": "fallback_marker_must_not_be_copied"
    }
  ],
  "warnings": [
    "source archive is incomplete and several requested fields are missing",
    "target archive parser-derived metadata will be preserved"
  ]
}
```

### Apply Response

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "updated": true,
  "applied": true,
  "field_action_summary": {
    "copy": 5,
    "merge": 2,
    "keep_target": 12,
    "skip_equal": 3,
    "skip_missing_source": 8,
    "skip_disallowed": 41,
    "override": 1
  },
  "updated_fields": ["started_at", "completed_at", "created_at", "status", "is_favorite", "tags", "notes"],
  "writes": {
    "archive_fields": ["started_at", "completed_at", "created_at", "status", "is_favorite"],
    "tags_updated": true,
    "notes_updated": true
  }
}
```

## Post-Merge Verification Endpoint

### `POST /admin/archive-restore-verify`

This endpoint is intended to be called after merge application or after a manual operator review.

Its job is to:

- compare source and target again using the same restore policy rules
- report any actionable remaining differences
- optionally remove the original source archive when verification is clean

### Request Model

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "field_groups": ["runtime", "user_metadata", "lineage"],
  "exclude_tags": ["exception:missing_3mf", "replaced_by:*"],
  "remove_original": false,
  "dry_run": true
}
```

### Verification Semantics

- `verified = true` means there are no actionable remaining differences under the current policy
- `remaining_differences` should include only unresolved `copy`, `merge`, or `override` actions that would still change the target
- `keep_target`, `skip_missing_source`, `skip_equal`, and `skip_disallowed` are not considered blocking verification failures

### Optional Original Removal

If all of the following are true:

- `verified = true`
- `remove_original = true`
- `dry_run = false`

then the sidecar may delete the source archive row.

Recommended guardrail:

- refuse deletion when actionable remaining differences still exist

### Verification Response Example

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "verified": true,
  "applied": false,
  "removable": true,
  "source_removed": false,
  "blocking_difference_count": 0,
  "non_blocking_difference_count": 19,
  "remaining_difference_count": 0,
  "remaining_difference_summary": {
    "copy": 0,
    "merge": 0,
    "keep_target": 0,
    "skip_equal": 0,
    "skip_missing_source": 0,
    "skip_disallowed": 0,
    "override": 0
  },
  "remaining_differences": [],
  "blocking_differences": [],
  "non_blocking_differences": [],
  "warnings": []
}
```

## Action Enum

Allowed `field_actions[].action` values:

- `copy`
- `merge`
- `keep_target`
- `skip_equal`
- `skip_missing_source`
- `skip_disallowed`
- `override`

## Reason Enum

Suggested reasons:

- `runtime_truth_present_on_source`
- `source_missing`
- `normalized_values_equal`
- `target_parser_field_has_priority`
- `fallback_marker_must_not_be_copied`
- `transient_snapshot_not_supported`
- `merged_tag_policy`
- `merged_notes_policy`
- `explicit_override`

## Validation Rules For `restore_from`

- source archive must exist
- target archive must exist
- source and target archive IDs must differ
- requested enums must be valid
- override keys must be in the allow-list
- target archive should have at least one file-backed signal unless an explicit force flag is added later

Recommended target validation signals:

- non-empty `file_path`, or
- non-null `content_hash`, or
- non-null `thumbnail_path`

Recommended warning conditions, not hard failures:

- source archive has `extra_data.no_3mf_available = true`
- source archive is missing all runtime fields requested by `field_groups`
- source archive and target archive print names differ materially
- source archive and target archive filenames differ materially

## Merge Engine Pseudocode

```text
function restore_from(request):
  source = load_archive(request.source_archive_id)
  target = load_archive(request.target_archive_id)

  validate_request(request, source, target)

  matrix = load_field_matrix()
  plan = []

  for field_rule in matrix:
    if field_rule.group not in request.field_groups and field_rule.group not in ["parser_target"]:
      continue

    source_value = get_field(source, field_rule.path)
    target_value = get_field(target, field_rule.path)

    if field_rule.path in request.overrides:
      plan.add(action="override", field=field_rule.path, target_after=request.overrides[field_rule.path])
      continue

    if field_rule.policy == "disallowed":
      plan.add(action="skip_disallowed", field=field_rule.path)
      continue

    normalized_source = normalize(field_rule.path, source_value)
    normalized_target = normalize(field_rule.path, target_value)

    if is_missing(normalized_source):
      plan.add(action="skip_missing_source", field=field_rule.path)
      continue

    if normalized_source == normalized_target:
      plan.add(action="skip_equal", field=field_rule.path)
      continue

    if field_rule.policy == "keep_target":
      plan.add(action="keep_target", field=field_rule.path)
      continue

    if field_rule.policy == "copy_source":
      plan.add(action="copy", field=field_rule.path, target_after=source_value)
      continue

    if field_rule.policy == "merge_tags":
      merged_tags = merge_tags(source_value, target_value, request.exclude_tags, request.include_tags)
      plan.add(action="merge", field=field_rule.path, target_after=merged_tags)
      continue

    if field_rule.policy == "merge_notes":
      merged_notes = merge_notes(source_value, target_value, source, target, request)
      plan.add(action="merge", field=field_rule.path, target_after=merged_notes)
      continue

  if request.dry_run:
    return build_dry_run_response(plan)

  apply_archive_field_updates(target.id, plan.scalar_writes)
  apply_tag_update(target.id, plan.tags)
  apply_notes_update(target.id, plan.notes)

  return build_apply_response(plan)
```

## Reference Matrix

The concrete field-by-field policy table for this merge logic lives in:

- [archive-runtime-restore-from-field-matrix.md](archive-runtime-restore-from-field-matrix.md)

Operator-oriented request examples and the recommended merge/verify/remove sequence live in:

- [archive-runtime-restore-from-runbook.md](archive-runtime-restore-from-runbook.md)

## Proposed Execution Flow

1. Load source and target archive rows.
2. Validate that the target looks like a recovery/replacement candidate.
3. Build a field action plan rather than writing immediately.
4. For each supported field, decide one of:
   - `copy`
   - `keep_target`
   - `merge`
   - `skip_missing_source`
   - `skip_equal`
   - `skip_disallowed`
5. Return the action plan in dry-run mode.
6. Apply only the approved writes in non-dry-run mode.
7. Append lineage and audit notes.

## Field Classes

### Class 1: Parser-authoritative target fields

These should normally stay on the target archive because the recovered `.3mf` is the higher-quality source.

Examples:

- `file_path`
- `file_size`
- `content_hash`
- `thumbnail_path`
- `print_name`
- `print_time_seconds`
- `filament_used_grams`
- `filament_type`
- `filament_color`
- `layer_height`
- `total_layers`
- `nozzle_diameter`
- `nozzle_temperature`
- `sliced_for_model`
- `designer`
- `makerworld_url`

Default rule:

- keep target value
- do not overwrite from source, even if the source differs
- only allow override through an explicit force option if a future operator workflow proves the parser output wrong

### Class 2: Runtime-truth source fields

These should normally copy from the source archive when present because they represent the original run timeline.

Examples:

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`

Derived implication:

- `actual_time_seconds` should not be written directly if it is computed by the DB or application layer from the repaired timestamps

Default rule:

- if source value is present and differs, copy it to target
- if source value is missing, leave target unchanged
- if source and target already match, record `skip_equal`

### Class 3: User-managed metadata fields

These are good candidates for copy or merge because they reflect operator intent rather than parser output.

Examples:

- `is_favorite`
- `cost`
- `quantity`
- `external_url`
- `failure_reason`
- user-authored tags
- user-authored notes

Default rule:

- scalar fields copy from source when source is non-null and target is null or meaningfully different
- tags merge by normalized token, not raw string replacement
- notes merge by preserving existing target notes and appending structured recovery audit blocks only once

### Class 4: Fallback-only or transient source fields

These should not be copied wholesale.

Examples:

- `extra_data.no_3mf_available`
- `extra_data._print_data.*`
- raw AMS state snapshots
- raw printer temperatures and humidity captured at fallback time
- ephemeral progress or remaining-time values

Default rule:

- skip as `disallowed`
- if a small subset proves useful later, extract it explicitly into a curated lineage block rather than copying the raw structure

## Proposed Decision Rules

For each supported field, evaluate in this order.

### Rule 1: Missing source value

If the source field is null, empty, or absent:

- do not clear the target field
- record `skip_missing_source`

This is critical for incomplete fallback archives, because missing source data is common and should not degrade the recovered archive.

### Rule 2: Equal values

If the normalized source and target values are equal:

- do nothing
- record `skip_equal`

This keeps the write set minimal and makes dry-run output easier to review.

### Rule 3: Disallowed field class

If the field belongs to the fallback-only or transient class:

- do not copy
- record `skip_disallowed`

### Rule 4: Parser-authoritative target field

If the field belongs to the parser-authoritative class:

- keep target value by default
- record `keep_target`

### Rule 5: Runtime-truth source field

If the field belongs to the runtime-truth class and the source value is present:

- copy source to target
- record `copy`

### Rule 6: Merge field

If the field is `tags` or `notes`:

- merge instead of replace
- record `merge`

## Tag Merge Rules

Tags need domain-specific handling.

Source tags may include fallback-state markers that should remain on the source archive only.

Recommended behavior:

- split tags into normalized tokens
- preserve target lineage tags such as `repair:recovered` and `recovered_from:<id>`
- carry forward user tags such as `Hueforge`
- exclude fallback-state tags such as `exception:missing_3mf`
- exclude old-linkage tags such as `replaced_by:<id>` from being copied to the target
- deduplicate case-insensitively after trimming

For the `191` to `200` example, the target should keep:

- `repair:recovered`
- `recovered_from:191`
- `recovery_source:sd_cache_3mf`
- enrichment tags already written on `200`
- `Hueforge` carried forward from `191`

The target should not inherit:

- `exception:missing_3mf`
- `replaced_by:200`

## Notes Merge Rules

Notes should not be overwritten blindly.

Recommended behavior:

- preserve existing target notes content
- append one structured recovery audit block if not already present
- optionally append a second structured block for copied source metadata decisions
- avoid duplicating the same `[RECOVERY_AUDIT_V1]` block on repeated runs
- preserve non-structured user text when present

## Optional Curated Snapshot Preservation

Most of `extra_data._print_data.raw_data.*` is too noisy to copy.

However, one future exception may be useful:

- selected tray UUID or AMS provenance fields needed for downstream filament lineage

If this is added later, it should be stored as a small curated audit payload such as:

```json
{
  "source_archive_id": 191,
  "selected_snapshot_fields": {
    "tray_uuids": ["..."],
    "source_subtask_name": "200x200 - AMS Ready - Slice & Print"
  }
}
```

This should live in a versioned audit block, not as a raw `extra_data` transplant.

## Dry-Run Response Shape

Dry-run should return an explicit decision per field.

Example:

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "applied": false,
  "field_actions": [
    {"field": "started_at", "action": "copy", "source": "2026-04-02T16:37:22.828591", "target_before": null},
    {"field": "status", "action": "copy", "source": "completed", "target_before": "archived"},
    {"field": "print_time_seconds", "action": "keep_target", "source": null, "target_before": 22671},
    {"field": "Hueforge", "action": "merge_tag", "source": true, "target_before": false},
    {"field": "exception:missing_3mf", "action": "skip_disallowed", "source": true, "target_before": false},
    {"field": "extra_data._print_data.raw_data", "action": "skip_disallowed"}
  ]
}
```

## Example: `191` To `200`

Recommended `restore_from` outcome for this specific pair:

- copy from source to target:
  - `started_at`
  - `completed_at`
  - `created_at`
  - `status`
  - `is_favorite`
- merge from source to target:
  - user tag `Hueforge`
  - structured recovery notes that preserve original runtime truth
- keep target values:
  - `file_path`
  - `file_size`
  - `content_hash`
  - `thumbnail_path`
  - `print_name`
  - `print_time_seconds`
  - `filament_used_grams`
  - `filament_type`
  - `filament_color`
  - `layer_height`
  - `total_layers`
  - `designer`
  - `makerworld_url`
- explicitly ignore:
  - `extra_data.no_3mf_available`
  - `extra_data._print_data.raw_data.*`
  - fallback tag `exception:missing_3mf`
  - old-linkage tag `replaced_by:200`

## Why This Design Handles Missing Or Non-Different Data Well

This mode is designed for incomplete source archives.

So the default posture must be conservative:

- missing source values never blank out good target values
- equal values generate no write
- parser-derived target fields are preserved even when the source differs
- merge fields preserve both history and recovered metadata without replacing one with the other

That makes `restore_from` safe for both:

- rich source archives that already contain some user metadata
- sparse fallback archives where only a few original runtime fields are worth copying

### 2. Bulk repair

Not implemented today.

No array-of-repairs or batch endpoint exists yet.

### 3. Arbitrary metadata copy

Not implemented today.

The service is intentionally limited to runtime-repair fields and related audit note handling. It does not currently copy tags, cost, external URL, photos, or other archive metadata.

## `POST /admin/archive-runtime-repair`

### Request

```json
{
  "archive_id": 123,
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "failure_reason": null,
  "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
  "dry_run": false
}
```

### Response

```json
{
  "archive_id": 123,
  "updated": true,
  "applied": true,
  "before": {
    "started_at": null,
    "completed_at": null,
    "created_at": "2026-04-01T02:10:00+00:00",
    "status": "archived"
  },
  "after": {
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "status": "completed"
  }
}
```

## `GET /health`

Return basic liveness information only.

## Validation Rules

- archive must exist
- only allow the approved repair fields
- reject malformed datetimes
- reject `completed_at < started_at`
- reject unknown statuses
- require admin token

## Authentication Model

Use one of:

- internal-only bind plus reverse-proxy auth
- static bearer token on internal Docker network
- mTLS if the environment already uses it

For this use case, internal Docker networking plus a dedicated bearer token is the practical default.

## Registry Image Deployment

If your deployment platform pulls from a registry but does not build from source, build the image locally and push it first.

Example local build and push:

```bash
docker build -f sidecars/bambuddy-runtime-repair/Dockerfile -t registry.local:5000/bambuddy-runtime-repair:0.1.0 .
docker push registry.local:5000/bambuddy-runtime-repair:0.1.0
```

The sidecar is therefore compatible with a Dockhand-style deployment model as long as the built image is available in the registry.

## Suggested Compose Pattern

```yaml
services:
  bambuddy:
    image: maziggy/bambuddy:latest
    container_name: bambuddy
    volumes:
      - bambuddy_data:/data

  bambuddy-runtime-repair:
    image: registry.local:5000/bambuddy-runtime-repair:0.1.0
    container_name: bambuddy-runtime-repair
    environment:
      BAMBUDDY_DB_PATH: /data/bambuddy.db
      REPAIR_API_TOKEN: ${REPAIR_API_TOKEN}
    volumes:
      - bambuddy_data:/data
    ports:
      - "127.0.0.1:8818:8080"
    depends_on:
      - bambuddy
    restart: unless-stopped

volumes:
  bambuddy_data:
```

Reference file:

- `../../../sidecars/bambuddy-runtime-repair/compose.example.yaml`

## Same-Host `n8n` Note

If `n8n` is already running in Docker on the same host as Bambuddy, prefer HTTP between containers over `docker exec`.

Recommended pattern:

1. attach `n8n` and `bambuddy-runtime-repair` to the same Docker network
2. let `n8n` call `http://bambuddy-runtime-repair:8080/admin/archive-runtime-repair`
3. mount the Bambuddy DB volume only into the sidecar

That keeps the sidecar as the only component with direct DB write access.

If no extra orchestration is needed, Home Assistant can call the same sidecar endpoint directly and skip `n8n` entirely.

## Suggested Container Internals

- lightweight FastAPI app
- one small service module that wraps the same repair logic as the CLI script
- JSON logging to stdout
- no direct dependency on Bambuddy runtime code unless needed for config discovery

## Suggested Internal Code Shape

- `app.py` or `main.py` for HTTP layer
- `repair.py` for validation and DB transaction logic
- `models.py` only if typed request and response models help clarity

## Relationship To The CLI Script

The sidecar should reuse the same repair core as the reference CLI where possible.

Desired layering:

- repair core library
- CLI wrapper
- HTTP wrapper

That avoids having two different implementations of the archive write logic.

## Recommendation

Do not build the sidecar first unless you already know this workflow will recur.

The right order is:

1. validate the repair logic with the CLI script
2. run it through `n8n` or operator tooling
3. promote it into a sidecar only if the workflow proves durable