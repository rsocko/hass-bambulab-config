# Archive Recovery Remediation Queue 2026-04-12

## Purpose

Capture the current live Bambuddy archive state after the completed `189 -> 199` and `191 -> 200` recovery work, identify any remaining fallback or suspicious archive records, map them to the SD-card backup where possible, and define a practical step-wise remediation queue.

This document is intended to support:

- operator review of remaining recovery candidates
- one-at-a-time recovery execution with copy/paste PowerShell commands
- a clear distinction between what can be done safely today and what would require new bulk orchestration work

## Scope And Current State

Live Bambuddy inspection on 2026-04-12 shows:

- recovered replacement archive `199` is present and tagged `recovered_from:189`
- recovered replacement archive `200` is present and tagged `recovered_from:191`
- original fallback archives `189` and `191` have already been removed
- multiple older archive rows still have fallback characteristics:
  - empty `file_path`
  - missing `content_hash`
  - missing `thumbnail_path`
  - `extra_data.no_3mf_available = true`

Important nuance:

- `199` and `200` still carry `extra_data.no_3mf_available = true` after restore
- therefore `no_3mf_available` alone is no longer a reliable signal for "needs recovery"
- the better recovery-state test is:
  - already recovered if `tags` contain `recovered_from:<id>` and the archive has non-empty `file_path`, `content_hash`, and `thumbnail_path`
  - needs recovery if those file-backed signals are missing and the archive is not already tagged as recovered

## Live Findings

### Already Recovered

| Archive ID | Status | Recovery tag | File-backed signals present | Notes |
| --- | --- | --- | --- | --- |
| `199` | `completed` | `recovered_from:189` | Yes | Recovery succeeded. Historical source archive `189` has already been removed. |
| `200` | `completed` | `recovered_from:191` | Yes | Recovery succeeded. Historical source archive `191` has already been removed. |

### Current Incomplete Or Fallback-Like Archives

| Archive ID | Print name | Filename | Status | Exact SD-cache `.3mf` exists | Confidence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `19` | `2 AMS` | `2 AMS.3mf` | `completed` | Yes | High | Clean exact filename match in cache. Good pairwise recovery candidate. |
| `34` | `Spiderman Hueforge - B&W` | `Adaptive Layers .  100% Infill.3mf` | `completed` | Yes | Medium | Exact cache filename exists, but print name and filename are generic/mismatched. Inspect before restore. |
| `66` | `0.08mm layer, 2 walls, 100% infill` | `0.08mm layer, 2 walls, 100% infill.3mf` | `cancelled` | Yes | Low | Generic profile filename. High ambiguity. Not a safe bulk candidate. |
| `105` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | `cancelled` | Yes | Medium | Same source file as `106`. Decide whether cancelled archives should be recovered at all. |
| `106` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | `completed` | Yes | High | Strong exact filename match. Better recovery target than `105`. |
| `108` | `Laney Rivers 2026_Front_133x200` | `Laney Rivers 2026_Front_133x200.3mf` | `completed` | Yes | High | Strong exact filename match. Good pairwise recovery candidate. |
| `174` | `200mm x 200mm Deadpool & Wolverine Hueforge` | `200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | `completed` | Yes | Medium | Exact source file exists, but prior analysis shows collision with archive `181`. Recover only with explicit operator approval. |
| `206` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `failed` | Yes | Low | Generic profile filename, no obvious Batman-specific cache file. Not safe for automatic recovery. |
| `207` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `failed` | Yes | Low | Same ambiguity as `206`. |
| `208` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `completed` | Yes | Low | Same ambiguity as `206` and `207`. |

## SD-Card Source Matches

Confirmed exact cache matches under `bambuddy/Backup SD Card - 2026-04-03/cache/`:

- `2 AMS.3mf`
- `Adaptive Layers .  100% Infill.3mf`
- `0.08mm layer, 2 walls, 100% infill.3mf`
- `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf`
- `Laney Rivers 2026_Front_133x200.3mf`
- `200mm x 200mm Deadpool & Wolverine Hueforge.3mf`

Additional name-based sweep results:

- `Laney Rivers` has a clear exact match in cache
- `2 AMS` has a clear exact match in cache
- `Deadpool` has a clear exact match in cache plus related `.bbl` sidecars
- `Spiderman` has named cache files, but archive `34` points to a generic profile filename instead of the stronger model-named file
- `Batman` does not have an obvious Batman-specific cache `.3mf` in the backup folder

## Recommended Remediation Queue

### Tier 1: Ready For Pairwise Recovery

These are the best next one-at-a-time candidates.

| Queue order | Archive ID | Source path | Why it is ready |
| --- | --- | --- | --- |
| `1` | `19` | `bambuddy/Backup SD Card - 2026-04-03/cache/2 AMS.3mf` | Exact filename match, completed archive, low ambiguity |
| `2` | `106` | `bambuddy/Backup SD Card - 2026-04-03/cache/Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | Exact filename match, completed archive, stronger choice than cancelled `105` |
| `3` | `108` | `bambuddy/Backup SD Card - 2026-04-03/cache/Laney Rivers 2026_Front_133x200.3mf` | Exact filename match, completed archive, low ambiguity |

### Tier 2: Recover Only After Explicit Review

| Archive ID | Source path | Why review is needed |
| --- | --- | --- |
| `174` | `bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | Prior analysis already classified this as medium confidence because the cache file also aligns with live archive `181` |
| `34` | `bambuddy/Backup SD Card - 2026-04-03/cache/Adaptive Layers .  100% Infill.3mf` | Exact file exists, but print name and filename mismatch make it weaker than Tier 1 candidates |

### Tier 3: Manual Review Only

| Archive ID | Why not queue now |
| --- | --- |
| `66` | Generic profile filename only; cancelled archive; ambiguous source |
| `105` | Same file as `106`, but cancelled; likely lower-value recovery target |
| `206` | Generic profile filename; no Batman-specific source found |
| `207` | Generic profile filename; no Batman-specific source found |
| `208` | Generic profile filename; no Batman-specific source found |

## Step-Wise Operator Plan

### Phase 1: Triage And Approval

1. Work Tier 1 candidates first: `19`, `106`, `108`.
2. Defer `174` and `34` until Tier 1 is complete.
3. Do not bulk-import the generic-profile candidates (`66`, `105`, `206`, `207`, `208`) without stronger evidence.

### Phase 2: Pairwise Recovery Execution

For each approved fallback archive:

1. Inspect the fallback archive and source file.
2. Upload or re-use the replacement archive from the chosen source `.3mf`.
3. Run `restore-from` merge from old archive to new archive.
4. Run `restore-verify`.
5. If photo migration fails because the old archive has stale photo references, retry apply and verify with `-SkipPhotos`.
6. After successful verify, decide whether to remove the original fallback archive.

### Phase 3: Cleanup And Documentation

1. Record the replacement archive ID.
2. Record whether photos were preserved, skipped, or missing at source.
3. Record whether the historical source archive was removed.
4. Update this queue document or a follow-up runbook with the final result.

## One-At-A-Time Command Flow

These commands assume your terminal already has:

- `$sidecarBaseUrl`
- `$env:REPAIR_API_TOKEN`
- `$env:BAMBUDDY_API_BASE_URL`
- `$env:BAMBUDDY_API_KEY`

### A. Inspect A Fallback Candidate

Example for archive `19`:

```powershell
$headers = @{ 'X-API-Key' = $env:BAMBUDDY_API_KEY }
Invoke-RestMethod -Method Get -Uri "$env:BAMBUDDY_API_BASE_URL/api/v1/archives/19" -Headers $headers |
  Select-Object id, print_name, filename, status, file_path, content_hash, thumbnail_path, tags
```

### B. Create The Replacement Archive From SD Cache

Use the existing helper in `Inspect`, `Upload`, or `Full` mode.

Example for archive `19`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl 'http://bambuddy.socko.us' \
  -PrinterId 1 \
  -FallbackArchiveId 19 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf' \
  -RecoverySource 'sd_cache_3mf'
```

If the inspect result looks correct, create the replacement archive:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Upload \
  -BaseUrl 'http://bambuddy.socko.us' \
  -PrinterId 1 \
  -FallbackArchiveId 19 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf' \
  -RecoverySource 'sd_cache_3mf'
```

### C. Merge Runtime And User Metadata Into The Replacement Archive

Once you know the replacement archive ID, run the sidecar restore helper.

Dry run:

```powershell
& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 19 \
  -TargetArchiveId <new_archive_id> \
  -CompactOutput
```

Apply:

```powershell
& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 19 \
  -TargetArchiveId <new_archive_id> \
  -Apply \
  -CompactOutput
```

If the apply fails only because source photos are broken or missing, retry with:

```powershell
& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 19 \
  -TargetArchiveId <new_archive_id> \
  -Apply \
  -SkipPhotos \
  -CompactOutput
```

### D. Verify The Merge

Normal verify:

```powershell
& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 19 \
  -TargetArchiveId <new_archive_id> \
  -Verify \
  -CompactOutput
```

If the applied recovery intentionally excluded photos, verify with the same scope:

```powershell
& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 19 \
  -TargetArchiveId <new_archive_id> \
  -Verify \
  -SkipPhotos \
  -CompactOutput
```

### E. Remove The Old Fallback Archive After Successful Verify

```powershell
& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 19 \
  -TargetArchiveId <new_archive_id> \
  -Verify \
  -RemoveOriginal \
  -Apply \
  -CompactOutput
```

If the approved verification scope excluded photos, include `-SkipPhotos` here too.

## Queue-Specific Source Paths

Use these exact source files for the current Tier 1 queue.

### Queue 1: Archive 19

```text
bambuddy/Backup SD Card - 2026-04-03/cache/2 AMS.3mf
```

### Queue 2: Archive 106

```text
bambuddy/Backup SD Card - 2026-04-03/cache/Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf
```

### Queue 3: Archive 108

```text
bambuddy/Backup SD Card - 2026-04-03/cache/Laney Rivers 2026_Front_133x200.3mf
```

### Deferred Review: Archive 174

```text
bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf
```

### Deferred Review: Archive 34

```text
bambuddy/Backup SD Card - 2026-04-03/cache/Adaptive Layers .  100% Infill.3mf
```

## Does A Bulk Process Exist Today?

Partially.

What exists today:

- `tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1` has a `Backfill` mode
- `tmp/archive_backfill_manifest.json` already contains a large SD-card candidate set
- `tmp/archive_backfill_inspect.json` shows bulk inspect output
- `tmp/archive_backfill_full_one.json` shows that the backfill helper can create and annotate imported archives from a manifest entry

What that bulk process does well today:

- inspect many SD-card candidates
- skip files whose `content_hash` already exists in Bambuddy
- upload and annotate historical-import candidates from a manifest

What it does **not** do as a safe end-to-end bulk fallback-recovery system:

- choose the correct historical fallback archive automatically when filenames are ambiguous
- run the sidecar `restore-from` merge per old/new pair
- evaluate whether photo migration should be included or skipped per archive
- run post-merge verification and conditional source removal automatically per pair

Conclusion:

- a bulk historical-import pipeline exists today
- a bulk fallback-recovery pipeline with runtime merge and verify does **not** exist today in a safe operator-ready form
- that full bulk fallback-recovery flow would be new work

## Recommended Operating Model

Use a hybrid model:

1. keep using bulk inspect/backfill tooling for broad SD-card candidate analysis
2. maintain a curated queue of approved fallback archive IDs and exact source files
3. execute approved fallback recoveries one at a time with the existing pairwise scripts
4. only consider true bulk fallback recovery after adding queue-aware orchestration that tracks:
   - source fallback archive id
   - created replacement archive id
   - source confidence level
   - whether photo migration is allowed
   - verification scope
   - cleanup/removal approval

## Recommendation Summary

Recommended next queue:

1. recover archive `19`
2. recover archive `106`
3. recover archive `108`
4. review archive `174`
5. review archive `34`
6. leave `66`, `105`, `206`, `207`, and `208` in manual-review status

Do not treat `199` and `200` as unresolved just because `extra_data.no_3mf_available` still exists. Their file-backed recovery signals and recovery tags already show they are recovered.