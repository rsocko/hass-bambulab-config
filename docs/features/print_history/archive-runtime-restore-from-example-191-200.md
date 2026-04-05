# `restore_from` Example: Archive `191` To `200`

## Purpose

Show a concrete dry-run example for the proposed sidecar endpoint:

- source archive `191`
- target archive `200`

This example is based on the live Bambuddy archive comparison performed on 2026-04-04.

## Scenario Summary

Source archive `191` was an incomplete fallback archive.

It preserved:

- original run timestamps
- original `completed` status
- favorite state
- fallback lineage tags
- fallback-only printer snapshot data in `extra_data._print_data.*`

Target archive `200` was the recovered file-backed replacement.

It preserved:

- canonical `file_path`
- canonical `content_hash`
- canonical `thumbnail_path`
- parsed `.3mf` metadata such as filament usage, layer height, total layers, and model metadata
- recovery lineage tags and structured notes

## Recommended Request

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
  "overrides": {},
  "dry_run": true
}
```

## Expected Dry-Run Shape

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
    "skip_equal": 0,
    "skip_missing_source": 4,
    "skip_disallowed": 2,
    "override": 0
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
      "field": "completed_at",
      "group": "runtime",
      "action": "copy",
      "source_value": "2026-04-02T23:58:56.496148",
      "target_before": "2026-04-04T21:45:30.757481",
      "target_after": "2026-04-02T23:58:56.496148",
      "reason": "runtime_truth_present_on_source"
    },
    {
      "field": "created_at",
      "group": "runtime",
      "action": "copy",
      "source_value": "2026-04-02T16:37:22",
      "target_before": "2026-04-04T21:45:30",
      "target_after": "2026-04-02T16:37:22",
      "reason": "runtime_truth_present_on_source"
    },
    {
      "field": "status",
      "group": "runtime",
      "action": "copy",
      "source_value": "completed",
      "target_before": "archived",
      "target_after": "completed",
      "reason": "runtime_truth_present_on_source"
    },
    {
      "field": "is_favorite",
      "group": "user_metadata",
      "action": "copy",
      "source_value": true,
      "target_before": false,
      "target_after": true,
      "reason": "runtime_truth_present_on_source"
    },
    {
      "field": "tags",
      "group": "user_metadata",
      "action": "merge",
      "source_value": "Hueforge,exception:missing_3mf,replaced_by:200",
      "target_before": "repair:recovered,recovered_from:191,recovery_source:sd_cache_3mf,f:14,s:10,f:15,s:9",
      "target_after": "repair:recovered,recovered_from:191,recovery_source:sd_cache_3mf,f:14,s:10,f:15,s:9,Hueforge",
      "reason": "merged_tag_policy"
    },
    {
      "field": "notes",
      "group": "lineage",
      "action": "merge",
      "source_value": "[RECOVERY_AUDIT_V1] ... replaced_by_archive_id ...",
      "target_before": "[RECOVERY_AUDIT_V1] ... recovered_from_archive_id ...\n\n+>...",
      "target_after": "preserve target notes and append/update structured recovery audit without duplication",
      "reason": "merged_notes_policy"
    },
    {
      "field": "file_path",
      "group": "parser_target",
      "action": "keep_target",
      "source_value": "",
      "target_before": "archive/1/20260404_174530_200x200 - AMS Ready - Slice & Print/200x200 - AMS Ready - Slice & Print.3mf",
      "target_after": "archive/1/20260404_174530_200x200 - AMS Ready - Slice & Print/200x200 - AMS Ready - Slice & Print.3mf",
      "reason": "target_parser_field_has_priority"
    },
    {
      "field": "print_time_seconds",
      "group": "parser_target",
      "action": "keep_target",
      "source_value": null,
      "target_before": 22671,
      "target_after": 22671,
      "reason": "source_missing"
    },
    {
      "field": "extra_data.no_3mf_available",
      "group": "snapshot_subset",
      "action": "skip_disallowed",
      "source_value": true,
      "target_before": null,
      "target_after": null,
      "reason": "fallback_marker_must_not_be_copied"
    },
    {
      "field": "extra_data._print_data",
      "group": "snapshot_subset",
      "action": "skip_disallowed",
      "source_value": "<large transient printer snapshot>",
      "target_before": null,
      "target_after": null,
      "reason": "transient_snapshot_not_supported"
    }
  ],
  "warnings": [
    "source archive is incomplete and missing several parser-derived fields",
    "target archive parser-derived metadata will be preserved",
    "fallback-only source tags are excluded from target merge"
  ]
}
```

## Key Outcomes Encoded In This Example

### Copy From Source

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `is_favorite`

### Merge

- `tags`
- `notes`

### Keep Target

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

### Exclude Or Ignore

- `exception:missing_3mf`
- `replaced_by:200`
- `extra_data.no_3mf_available`
- `extra_data._print_data.*`

## Why Missing Source Fields Do Not Break The Merge

Archive `191` is sparse in exactly the way fallback archives tend to be sparse.

Examples:

- `print_time_seconds` is absent on source
- `filament_used_grams` is absent on source
- `thumbnail_path` is absent on source
- `content_hash` is absent on source

The merge policy therefore treats missing source data as `skip_missing_source`, not as a signal to null out target data.

## Why Equal Values Still Matter

The dry-run response should emit `skip_equal` for fields that already match after normalization.

That keeps the final write set small and makes operator review clearer.

Typical equal-value cases in future examples may include:

- `printer_id`
- already-repaired `status`
- lineage tags already present on target

## Post-Merge Verification Call

After merge, the caller can verify the pair and optionally remove the original fallback archive.

Recommended verification request:

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "remove_original": false,
  "dry_run": true
}
```

Expected behavior:

- report only actionable remaining differences
- ignore parser-target fields that are intentionally preserved on target
- ignore fallback-only source fields that are intentionally excluded
- mark the pair as removable only when there are no actionable remaining differences

Recommended cleanup request after successful verification:

```json
{
  "source_archive_id": 191,
  "target_archive_id": 200,
  "remove_original": true,
  "dry_run": false
}
```

Recommended operator policy:

- run verification first with `dry_run: true`
- only remove the original when `verified: true` and `remaining_difference_count: 0`

Recommended merge-then-verify sequence:

1. call `POST /admin/archive-restore-from` with `dry_run: false`
2. call `POST /admin/archive-restore-verify` with `dry_run: true`
3. if verification is clean, call `POST /admin/archive-restore-verify` again with `remove_original: true` and `dry_run: false`