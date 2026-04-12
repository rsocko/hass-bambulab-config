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
| `174` | `200mm x 200mm Deadpool & Wolverine Hueforge` | `200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | `completed` | Yes | Medium-High | Original cache candidate collided with archive `181`, but exported sliced file `Deadpool___Wolverine_Deadpool.gcode.3mf` provided a distinct recoverable source. |
| `206` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `failed` | Yes | Medium | Exported sliced file `bat4 - 200x200.gcode.3mf` now exists and appears to be the shared Batman source, but this row is still a failed attempt. |
| `207` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `failed` | Yes | Medium | Same shared exported sliced candidate as `206`, but this row is still a failed attempt. |
| `208` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `completed` | Yes | Medium-High | Exported sliced file `bat4 - 200x200.gcode.3mf` appears to be a Batman-specific shared source and `208` is the highest-value completed row in that cluster. |

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
- `Batman` does not have an obvious Batman-specific cache `.3mf` in the original backup cache, but an exported sliced file `bat4 - 200x200.gcode.3mf` is now available and embeds Batman-specific metadata

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
2. Defer `34` until Tier 1 is complete.
3. Do not bulk-import the remaining generic-profile candidates (`66`, `105`) without stronger evidence.

### Phase 2: Pairwise Recovery Execution

For each approved fallback archive:

1. Inspect the fallback archive and source file.
2. Upload or re-use the replacement archive from the chosen source `.3mf`.
3. Run `restore-from` merge from old archive to new archive.
4. Run `restore-verify`.
5. If photo migration fails because the old archive has stale photo references, retry apply and verify with `-SkipPhotos`.
6. After successful verify, decide whether to remove the original fallback archive.

If you remove the original, treat that step as workflow finalization: the surviving replacement archive should keep its recovery audit note but no longer keep transient recovery tags such as `repair:recovered`, `recovered_from:*`, or `recovery_source:*`.

### Phase 3: Cleanup And Documentation

1. Record the replacement archive ID.
2. Record whether photos were preserved, skipped, or missing at source.
3. Record whether the historical source archive was removed.
4. Update this queue document or a follow-up runbook with the final result.

## Live Execution Status

Current operator run status on 2026-04-12:

| Archive ID | Current state | Replacement archive | Current result | Remaining action |
| --- | --- | --- | --- | --- |
| `19` | restore applied and verified | `225` | pairwise recovery succeeded; verify reports `verified = true` and `remaining_difference_count = 0` | original archive `19` not removed because target enrichment is still missing and normal removal is therefore blocked |
| `106` | restore applied and verified with photo-skip scope | `226` | upload and restore apply succeeded; one source photo returned `404 Not Found` during apply; `-SkipPhotos` verify then reported `verified = true` and `remaining_difference_count = 0` | original archive `106` not removed because target enrichment is still missing and normal removal is therefore blocked |
| `108` | restore applied and verified with photo-skip scope | `227` | upload and restore apply succeeded; one source photo returned `404 Not Found` during apply; `-SkipPhotos` verify then reported `verified = true` and `remaining_difference_count = 0` | original archive `108` not removed because target enrichment is still missing and normal removal is therefore blocked |
| `174` | finalized after re-enrich and verified removal | `232` | recovered from exported sliced source `Deadpool___Wolverine_Deadpool.gcode.3mf`; original cache candidate remained deferred because it collides with archive `181`; restore apply succeeded, one source photo returned `404 Not Found`, `-SkipPhotos` verify reported `verified = true` and `remaining_difference_count = 0`, re-enrich completed, and normal remove-original then succeeded | original archive `174` has been removed; replacement archive `232` remains as the finalized surviving record |
| `34` | restore applied and verified | `228` | promoted from deferred review after deeper provenance check; upload, restore apply, and verify all succeeded with `remaining_difference_count = 0` | original archive `34` not removed because target enrichment is still missing and normal removal is therefore blocked |
| `208` | restore applied and verified | `229` | recovered from shared exported sliced source `bat4 - 200x200.gcode.3mf`; upload, restore apply, and verify all succeeded with `remaining_difference_count = 0` | original archive `208` not removed because target enrichment is still missing and normal removal is therefore blocked |
| `207` | restore applied and verified | `230` | failed-history row preserved from shared exported sliced source `bat4 - 200x200.gcode.3mf`; restore apply and verify both succeeded with `remaining_difference_count = 0` | original archive `207` not removed because target enrichment is still missing and normal removal is therefore blocked |
| `206` | restore applied and verified | `231` | failed-history row preserved from shared exported sliced source `bat4 - 200x200.gcode.3mf`; restore apply and verify both succeeded with `remaining_difference_count = 0` | original archive `206` not removed because target enrichment is still missing and normal removal is therefore blocked |

Re-enrich follow-up attempted on replacement archives `225`, `226`, `227`, and `228` via the runtime-repair sidecar.

- result: blocked by sidecar environment
- sidecar warning: `run_reenrich requested but HOME_ASSISTANT_BASE_URL/HOME_ASSISTANT_TOKEN are not configured`
- consequence: removal remains blocked through the normal path because verify still reports `enrichment_status = missing`

Archive `232` is now the first post-blocker finalized example:

- user reran re-enrich for replacement archive `232` and reported success
- follow-up verify reported `enrichment_status = complete` and `removable = true`
- normal `remove_original` then succeeded for source archive `174`
- final surviving archive `232` no longer carries transient recovery tags; only the recovery audit note remains in `notes`

## Tier 2 Review Notes

### Archive `174`

- original inspect against `cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf` looked mechanically valid but stayed deferred because its SHA256 `1AEDFF714998C7F18B179028B13F378683A2BB6D31A3C02BBB6CCF4790A87856` already matched live archive `181`
- new source provided on 2026-04-12: `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine_Deadpool.gcode.3mf`
- new source SHA256 is `FEC212637B4A24C1B4A4427B7DE7CF9FCDB2D9AAC5D522FD18ADBA836792201E`
- that hash did not already exist as a file-backed Bambuddy archive before recovery, so the prior collision concern no longer applied
- operator decision on 2026-04-12: recover `174` from the new exported sliced source rather than the colliding cache file
- execution result: replacement archive `232` created from `Deadpool___Wolverine_Deadpool.gcode.3mf`; restore apply succeeded; one source photo returned `404 Not Found` during apply; `-SkipPhotos` verify then reported `verified = true` and `remaining_difference_count = 0`
- follow-up finalization result: after re-enrich completed, normal `remove_original` succeeded for archive `174`; archive `232` is now the surviving finalized record and archive `174` has been deleted

### Archive `34`

- inspect against `cache/Adaptive Layers .  100% Infill.3mf` is mechanically valid but still weak from a provenance standpoint
- the backup cache also contains stronger Spider-Man-related candidates:
  - `200mm x 200mm Spiderman 4-color Hueforge.3mf`
  - `Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf`
- deeper comparison on 2026-04-12 shows those stronger-looking alternatives already map to other file-backed archives:
  - `200mm x 200mm Spiderman 4-color Hueforge.3mf` has SHA256 `76973985F87350420F8272E888DCAE3186774B9EE67F68FF53A85CB2299F7388` and already exists as archive `23`
  - `Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf` has SHA256 `B4CF4E2F03A9E6B288A12E1B17FC2C6DC9F2C416ACA6B67251D23C05FABD8FDE` and already exists as recovered archive `199`
  - the generic `Adaptive Layers .  100% Infill.3mf` candidate has SHA256 `1DD30ECF299CBE150733711A875AD0D7A28130FB2B2B67CA32C28BD27C225AF7` and did not surface as an existing file-backed Spider-Man archive during this review
- supporting evidence inside the generic `.3mf` improves the case enough for manual promotion:
  - the embedded `3D/3dmodel.model` metadata describes `Spiderman Symbiote Suit Hueforge`
  - the generic file has the full expected Bambu metadata set (`plate_1.gcode`, thumbnails, project settings, filament sequence), so it is not a truncated cache artifact
  - unlike the Hulk-related adaptive-height file, it does not have a matching `.bbl` sidecar in the backup cache, which weakens confidence relative to Tier 1-grade candidates
- operator decision on 2026-04-12: promote and recover `34` using the generic unmatched candidate
- execution result: replacement archive `228` created from `Adaptive Layers .  100% Infill.3mf`; restore apply and verify both succeeded; original archive `34` remains in place because target enrichment is still missing

## Remaining Manual-Review Set

### Archive `66`

- still cancelled
- still uses the fully generic filename `0.08mm layer, 2 walls, 100% infill.3mf`
- unlike the themed Hueforge rows that share that filename, this row has no user tags, no photos, and no stronger print-name identity to anchor it
- conclusion: keep `66` parked; it is weaker than the already-reviewed themed rows and there is no new provenance evidence to justify promotion

### Archive `105`

- still cancelled
- shares the exact same filename and fallback profile identity as archive `106`
- archive `106` has already been recovered successfully into replacement archive `226`
- conclusion: keep `105` parked; recovering the cancelled twin of an already-recovered completed row is still low-value unless you explicitly decide cancelled jobs should be preserved the same way

### Archives `206`, `207`, and `208`

- all three point to the same generic fallback filename `0.08mm layer, 2 walls, 100% infill.3mf`
- the generic cache file originally considered for this cluster was rejected because it embedded `Star Wars Darth Vader Hueforge` metadata rather than Batman metadata
- new evidence on 2026-04-12 established a better shared source:
  - exported sliced file `bambuddy/Backup SD Card - 2026-04-03/bat4 - 200x200.gcode.3mf`
  - embedded `3D/3dmodel.model` metadata has `Title = Batman Hueforge`
  - embedded metadata `CreationDate = 2026-04-12` reflects the reconstructed export date, not the original print date, so this is reconstructed rather than original-sliced evidence
  - SHA256 is `BCFCDBD1E2091838A858D596BE4D2F33FCFE74DB766A569238F1C07472AA3A8E`
  - that hash did not already exist as a file-backed Bambuddy archive before recovery
- operator decision on 2026-04-12: use the shared exported sliced file to recover the full Batman attempt cluster
- execution result:
  - archive `208` recovered to replacement archive `229`
  - archive `207` recovered to replacement archive `230`
  - archive `206` recovered to replacement archive `231`
  - restore apply and verify succeeded for all three
  - originals `206`, `207`, and `208` remain in place because target enrichment is still missing, so normal removal is blocked

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
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = 'http://bambuddy.socko.us'
  PrinterId = 1
  FallbackArchiveId = 19
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf'
  RecoverySource = 'sd_cache_3mf'
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

If the inspect result looks correct, create the replacement archive:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
$recoveryArgs = @{
  Mode = 'Upload'
  BaseUrl = 'http://bambuddy.socko.us'
  PrinterId = 1
  FallbackArchiveId = 19
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf'
  RecoverySource = 'sd_cache_3mf'
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

### C. Merge Runtime And User Metadata Into The Replacement Archive

Once you know the replacement archive ID, run the sidecar restore helper.

Dry run:

```powershell
$restoreArgs = @{
  BaseUrl = $sidecarBaseUrl
  Token = $env:REPAIR_API_TOKEN
  SourceArchiveId = 19
  TargetArchiveId = <new_archive_id>
  CompactOutput = $true
}

& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 @restoreArgs
```

Apply:

```powershell
$restoreArgs = @{
  BaseUrl = $sidecarBaseUrl
  Token = $env:REPAIR_API_TOKEN
  SourceArchiveId = 19
  TargetArchiveId = <new_archive_id>
  Apply = $true
  CompactOutput = $true
}

& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 @restoreArgs
```

If the apply fails only because source photos are broken or missing, retry with:

```powershell
$restoreArgs = @{
  BaseUrl = $sidecarBaseUrl
  Token = $env:REPAIR_API_TOKEN
  SourceArchiveId = 19
  TargetArchiveId = <new_archive_id>
  Apply = $true
  SkipPhotos = $true
  CompactOutput = $true
}

& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 @restoreArgs
```

### D. Verify The Merge

Normal verify:

```powershell
$restoreArgs = @{
  BaseUrl = $sidecarBaseUrl
  Token = $env:REPAIR_API_TOKEN
  SourceArchiveId = 19
  TargetArchiveId = <new_archive_id>
  Verify = $true
  CompactOutput = $true
}

& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 @restoreArgs
```

If the applied recovery intentionally excluded photos, verify with the same scope:

```powershell
$restoreArgs = @{
  BaseUrl = $sidecarBaseUrl
  Token = $env:REPAIR_API_TOKEN
  SourceArchiveId = 19
  TargetArchiveId = <new_archive_id>
  Verify = $true
  SkipPhotos = $true
  CompactOutput = $true
}

& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 @restoreArgs
```

### E. Remove The Old Fallback Archive After Successful Verify

```powershell
$restoreArgs = @{
  BaseUrl = $sidecarBaseUrl
  Token = $env:REPAIR_API_TOKEN
  SourceArchiveId = 19
  TargetArchiveId = <new_archive_id>
  Verify = $true
  RemoveOriginal = $true
  Apply = $true
  CompactOutput = $true
}

& .\tools\bambuddy\Test-RestoreFromSidecar.ps1 @restoreArgs
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

### Recovered Review: Archive 174

```text
bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine_Deadpool.gcode.3mf
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

1. configure `HOME_ASSISTANT_BASE_URL` and `HOME_ASSISTANT_TOKEN` for the runtime-repair sidecar, then rerun re-enrich for replacement archives `225`, `226`, `227`, `228`, `229`, `230`, and `231`
2. after re-enrich completes, rerun removal verification for original archives `19`, `106`, `108`, `34`, `208`, `207`, and `206`
3. archive `174` has now been recovered; keep `Deadpool___Wolverine_Deadpool.gcode.3mf` as the provenance note for that repair and keep the older cache file excluded because it matches archive `181`
4. archive `34` has now been recovered; keep the generic `Adaptive Layers .  100% Infill.3mf` file as the provenance note for that repair and avoid the two alternatives already represented by archives `23` and `199`
5. leave `66` parked because it is a cancelled fully generic row with no stronger identity markers
6. leave `105` parked because `106` already covers the same source profile and was the higher-value completed recovery
7. Batman cluster recovery is complete; keep `bat4 - 200x200.gcode.3mf` as the shared reconstructed provenance source for `206`, `207`, and `208`

Do not treat `199` and `200` as unresolved just because `extra_data.no_3mf_available` still exists. Their file-backed recovery signals and recovery tags already show they are recovered.

## Queue-Specific Inspect Commands

These are the copy/paste inspect commands for the current queue.

Use PowerShell splatting for multiline commands. Do not use `\` as a line continuation character in PowerShell.

### Queue item 1: archive `19`

```powershell
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = $baseUrl
  PrinterId = $printerId
  FallbackArchiveId = 19
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf'
  RecoverySource = 'sd_cache_3mf'
  ApiKey = $env:BAMBUDDY_API_KEY
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

### Queue item 2: archive `108`

```powershell
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = $baseUrl
  PrinterId = $printerId
  FallbackArchiveId = 108
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\Laney Rivers 2026_Front_133x200.3mf'
  RecoverySource = 'sd_cache_3mf'
  ApiKey = $env:BAMBUDDY_API_KEY
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

### Queue item 3: archive `106`

```powershell
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = $baseUrl
  PrinterId = $printerId
  FallbackArchiveId = 106
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf'
  RecoverySource = 'sd_cache_3mf'
  ApiKey = $env:BAMBUDDY_API_KEY
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

### Queue item 4: archive `174`

```powershell
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = $baseUrl
  PrinterId = $printerId
  FallbackArchiveId = 174
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\Deadpool___Wolverine_Deadpool.gcode.3mf'
  RecoverySource = 'bambu_studio_exported_sliced_3mf'
  ApiKey = $env:BAMBUDDY_API_KEY
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

### Queue item 5: archive `34`

```powershell
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = $baseUrl
  PrinterId = $printerId
  FallbackArchiveId = 34
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\Adaptive Layers .  100% Infill.3mf'
  RecoverySource = 'sd_cache_3mf'
  ApiKey = $env:BAMBUDDY_API_KEY
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

### Queue item 6: archive `105`

```powershell
$recoveryArgs = @{
  Mode = 'Inspect'
  BaseUrl = $baseUrl
  PrinterId = $printerId
  FallbackArchiveId = 105
  SourceFilePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf'
  RecoverySource = 'sd_cache_3mf'
  ApiKey = $env:BAMBUDDY_API_KEY
}

& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' @recoveryArgs
```

## Recommended Next Actions

1. Process Queue A first in the order `19`, `108`, `106`.
2. Queue item `174` is now resolved via the exported sliced Deadpool source; use that file instead of the colliding cache file if you need to re-run the inspect.
3. Keep `34` and `105` manual until the inspect output looks credible.
4. Leave `66` alone unless stronger matching evidence appears.
5. If you want true bulk fallback remediation, design a new orchestrator around the current pairwise steps rather than reusing `Backfill` mode directly.