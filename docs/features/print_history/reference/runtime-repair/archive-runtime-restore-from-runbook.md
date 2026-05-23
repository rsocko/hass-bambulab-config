# Archive `restore_from` Runbook

## Purpose

Provide an operator-oriented runbook for the sidecar-based archive restore flow using a real archive pair.

Reference example:

- source archive: `191`
- target archive: `200`

This runbook assumes the sidecar is already running and reachable.

## Preconditions

- Bambuddy runtime repair sidecar is running
- you have a valid bearer token
- you have already identified the source archive and recovered target archive
- for this example:
  - source archive is `191`
  - target archive is `200`

## Recommended Sequence

1. Run restore-from in dry-run mode.
2. Review the proposed field actions.
3. Run restore-from in apply mode.
4. Run restore-verify in dry-run mode.
5. Only if verification is clean, run restore-verify again with source removal enabled.

## Step 1: Dry-Run Restore Plan

### HTTP

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-restore-from \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "source_archive_id": 191,
    "target_archive_id": 200,
    "dry_run": true
  }'
```

### PowerShell helper

```powershell
$restoreArgs = @{
  BaseUrl = 'http://127.0.0.1:8818'
  Token = 'replace-me'
  SourceArchiveId = 191
  TargetArchiveId = 200
}

pwsh -File tools/bambuddy/Test-RestoreFromSidecar.ps1 @restoreArgs
```

### What to review

- `field_actions`
- `updated = false`
- `applied = false`
- proposed `copy` actions for runtime fields
- proposed `merge` actions for tags and notes
- `keep_target` on parser-derived target fields

Expected highlights for `191 -> 200`:

- copy `started_at`
- copy `completed_at`
- copy `created_at`
- copy `status`
- copy `is_favorite`
- merge `tags`
- merge `notes`
- keep target `file_path`, `content_hash`, `thumbnail_path`, `print_time_seconds`, `filament_used_grams`

## Step 2: Apply Restore

### HTTP

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-restore-from \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "source_archive_id": 191,
    "target_archive_id": 200,
    "dry_run": false
  }'
```

### PowerShell helper

```powershell
$restoreArgs = @{
  BaseUrl = 'http://127.0.0.1:8818'
  Token = 'replace-me'
  SourceArchiveId = 191
  TargetArchiveId = 200
  Apply = $true
}

pwsh -File tools/bambuddy/Test-RestoreFromSidecar.ps1 @restoreArgs
```

### What to review

- `applied = true`
- `updated = true`
- `updated_fields`

Expected `updated_fields` for `191 -> 200` should include most or all of:

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `is_favorite`
- `tags`
- `notes`

## Step 3: Verify After Merge

### HTTP

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-restore-verify \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "source_archive_id": 191,
    "target_archive_id": 200,
    "remove_original": false,
    "dry_run": true
  }'
```

### PowerShell helper

```powershell
$restoreArgs = @{
  BaseUrl = 'http://127.0.0.1:8818'
  Token = 'replace-me'
  SourceArchiveId = 191
  TargetArchiveId = 200
  Verify = $true
}

pwsh -File tools/bambuddy/Test-RestoreFromSidecar.ps1 @restoreArgs
```

### What to review

- `verified`
- `blocking_difference_count`
- `non_blocking_difference_count`
- `remaining_difference_count`
- `removable`

Safe cleanup condition:

- `verified = true`
- `blocking_difference_count = 0`
- `remaining_difference_count = 0`
- `removable = true`

If those are not all true, do not remove the original archive.

## Step 4: Remove Original Archive

Only do this after verification is clean.

### HTTP

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-restore-verify \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "source_archive_id": 191,
    "target_archive_id": 200,
    "remove_original": true,
    "dry_run": false
  }'
```

### PowerShell helper

```powershell
$restoreArgs = @{
  BaseUrl = 'http://127.0.0.1:8818'
  Token = 'replace-me'
  SourceArchiveId = 191
  TargetArchiveId = 200
  Verify = $true
  RemoveOriginal = $true
  Apply = $true
}

pwsh -File tools/bambuddy/Test-RestoreFromSidecar.ps1 @restoreArgs
```

### What to review

- `verified = true`
- `source_removed = true`
- `applied = true`

## Expected Outcome For `191 -> 200`

After a successful full sequence:

- archive `200` keeps recovered `.3mf` metadata and original runtime/user fields copied forward
- archive `200` can be re-verified with no actionable remaining differences
- archive `191` may then be removed if desired

## When To Stop And Review Manually

Stop and review before removal if any of the following are true:

- `blocking_difference_count > 0`
- `remaining_difference_count > 0`
- `verified = false`
- the target archive still has `status = archived` when you expected `completed`
- the target archive is missing a copied runtime value you expected to move across

## Related Docs

- [archive-runtime-sidecar-api-and-compose.md](archive-runtime-sidecar-api-and-compose.md)
- [archive-runtime-restore-from-field-matrix.md](../archive-runtime-restore-from-field-matrix.md)
- [archive-runtime-restore-from-example-191-200.md](../archive-runtime-restore-from-example-191-200.md)