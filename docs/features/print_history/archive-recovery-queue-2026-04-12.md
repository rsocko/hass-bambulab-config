# Archive Recovery Queue 2026-04-12

## Purpose

Capture the current live Bambuddy fallback/incomplete archive set, identify which records are already recovered, map unresolved candidates to the SD-card backup under `bambuddy/Backup SD Card - 2026-04-03`, and provide a step-wise remediation queue.

This document is based on:

- live Bambuddy archive API data from `http://bambuddy.socko.us/api/v1/archives/`
- SD-card backup cache contents under `bambuddy/Backup SD Card - 2026-04-03/cache/`
- the existing bulk backfill manifest in `tmp/archive_backfill_manifest.json`
- live recovery results already completed for `189 -> 199` and `191 -> 200`

## Current Detection Rule

Do not treat `extra_data.no_3mf_available == true` as a standalone signal that an archive still needs recovery.

Recovered archives `199` and `200` still retain that source fallback marker in `extra_data`, but they are valid recovered targets because they also have:

- non-empty `file_path`
- non-empty `content_hash`
- non-empty `thumbnail_path`
- recovery lineage tags such as `recovered_from:<id>`

Use this practical rule instead:

1. Already recovered: archive has `recovered_from:<id>` and valid file-backed fields.
2. Needs recovery: archive is missing file-backed fields (`file_path`, `content_hash`, `thumbnail_path`) and is not already a recovered replacement.

## Live Findings

### Already recovered replacement archives

| Replacement archive | Historical source | Current state |
| --- | --- | --- |
| `199` | `189` | recovered and verified |
| `200` | `191` | recovered and verified |

### Current unresolved incomplete/fallback archives

| Archive | Print name | Filename | Status | Exact cache file present | Initial assessment |
| --- | --- | --- | --- | --- | --- |
| `19` | `2 AMS` | `2 AMS.3mf` | `completed` | yes | strong one-at-a-time recovery candidate |
| `34` | `Spiderman Hueforge - B&W` | `Adaptive Layers .  100% Infill.3mf` | `completed` | yes | review first; filename matches, print name does not |
| `66` | `0.08mm layer, 2 walls, 100% infill` | `0.08mm layer, 2 walls, 100% infill.3mf` | `cancelled` | yes | ambiguous generic profile filename |
| `105` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | `cancelled` | yes | paired ambiguity with archive `106` |
| `106` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill` | `Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | `completed` | yes | better candidate than `105` |
| `108` | `Laney Rivers 2026_Front_133x200` | `Laney Rivers 2026_Front_133x200.3mf` | `completed` | yes | strong one-at-a-time recovery candidate |
| `174` | `200mm x 200mm Deadpool & Wolverine Hueforge` | `200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | `completed` | yes | medium-confidence recovery candidate |
| `206` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `failed` | yes | ambiguous generic profile filename |
| `207` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `failed` | yes | ambiguous generic profile filename |
| `208` | `Batman B&W Hueforge` | `0.08mm layer, 2 walls, 100% infill.3mf` | `completed` | yes | ambiguous generic profile filename |

## Recovery Queue

### Queue A: approved for one-at-a-time recovery now

These have the cleanest current evidence and are suitable for the existing pairwise workflow.

| Queue order | Archive | Source file | Confidence | Notes |
| --- | --- | --- | --- | --- |
| `1` | `19` | `bambuddy/Backup SD Card - 2026-04-03/cache/2 AMS.3mf` | high | distinct filename, exact cache match |
| `2` | `108` | `bambuddy/Backup SD Card - 2026-04-03/cache/Laney Rivers 2026_Front_133x200.3mf` | high | distinct filename, exact cache match |
| `3` | `106` | `bambuddy/Backup SD Card - 2026-04-03/cache/Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | medium | exact file, but same file also relates to `105`; recover `106` first |

### Queue B: one-at-a-time recovery only after manual review

| Queue order | Archive | Source file | Confidence | Review concern |
| --- | --- | --- | --- | --- |
| `4` | `174` | `bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | medium | known collision with successful live archive `181`; provenance is strong, exact-run certainty is weaker |
| `5` | `34` | `bambuddy/Backup SD Card - 2026-04-03/cache/Adaptive Layers .  100% Infill.3mf` | medium | exact cache match, but print name and filename do not line up cleanly |
| `6` | `105` | `bambuddy/Backup SD Card - 2026-04-03/cache/Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf` | medium-low | same source file also maps to successful completed archive `106`; cancelled run needs extra care |

### Queue C: hold for now

Do not bulk or pairwise restore these yet with the current evidence.

| Archive | Current reason to hold |
| --- | --- |
| `66` | generic filename only; no distinct print-name evidence |
| `206` | generic filename only; no Batman-specific cache source found |
| `207` | generic filename only; no Batman-specific cache source found |
| `208` | generic filename only; no Batman-specific cache source found |

## Existing Processes Today

### One-at-a-time recovery process exists today

Yes. The existing process is already available today and is the recommended path for fallback-archive remediation.

Current pieces:

1. `tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1`
2. `tools/bambuddy/Test-RestoreFromSidecar.ps1`
3. `tests/phase3/print_history/Test-BambuddyArchiveCleanup.ps1`

Current recovery shape:

1. inspect fallback archive plus source file
2. upload or identify replacement archive
3. annotate old/new lineage tags and recovery audit notes
4. run sidecar restore-from to merge runtime/user metadata into the replacement archive
5. verify the pair
6. optionally remove the original fallback archive

### Bulk process exists today, but only for historical import

Yes, but it is not the same as bulk fallback recovery.

Existing bulk helper:

- `tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1 -Mode Backfill`

What it already does:

1. reads `tmp/archive_backfill_manifest.json`
2. dedupes by `content_hash`
3. bulk inspects candidates
4. bulk uploads candidates
5. optionally annotates imported archives with `historical_import` provenance notes/tags

What it does not do today:

1. it does not target existing fallback archive IDs
2. it does not patch old fallback archives with `replaced_by:*`
3. it does not call the runtime-repair sidecar restore-from API
4. it does not verify old/new archive pairs as fallback recoveries
5. it does not remove the original fallback archives

Conclusion:

- bulk historical import exists today
- bulk fallback recovery is net-new if you want upload + lineage + runtime merge + verify + cleanup to run end-to-end for multiple old archive IDs

## One-At-A-Time Recovery Commands

### Session setup

Run once in the VS Code PowerShell terminal before processing the queue:

```powershell
Set-Location C:\dev\hass-bambulab-config
Set-ExecutionPolicy -Scope Process Bypass

$baseUrl = 'http://bambuddy.socko.us'
$sidecarBaseUrl = 'http://bambuddy-runtime-repair.socko.us'
$printerId = 1
```

Assumed environment variables already present in the session:

- `$env:BAMBUDDY_API_KEY`
- `$env:REPAIR_API_TOKEN`

### Standard pairwise workflow

Use this exact sequence for queue items in Queue A and Queue B.

#### 1. Inspect candidate

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId <archive_id> \
  -SourceFilePath '<source_file_path>' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

#### 2. Upload replacement archive and capture new ID

```powershell
$upload = & '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Upload \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId <archive_id> \
  -SourceFilePath '<source_file_path>' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY | ConvertFrom-Json

$replacementArchiveId = $upload.uploaded_archive_id
$replacementArchiveId
```

#### 3. Apply lineage tags and audit notes

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Full \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId <archive_id> \
  -SourceFilePath '<source_file_path>' \
  -ExistingReplacementArchiveId $replacementArchiveId \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

#### 4. Run runtime restore merge

```powershell
& '.\tools\bambuddy\Test-RestoreFromSidecar.ps1' \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId <archive_id> \
  -TargetArchiveId $replacementArchiveId \
  -Apply \
  -CompactOutput
```

If the sidecar reports a broken source photo path, rerun with `-SkipPhotos`:

```powershell
& '.\tools\bambuddy\Test-RestoreFromSidecar.ps1' \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId <archive_id> \
  -TargetArchiveId $replacementArchiveId \
  -Apply \
  -SkipPhotos \
  -CompactOutput
```

#### 5. Verify

Use the same scope that you applied.

Without `-SkipPhotos`:

```powershell
& '.\tools\bambuddy\Test-RestoreFromSidecar.ps1' \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId <archive_id> \
  -TargetArchiveId $replacementArchiveId \
  -Verify \
  -CompactOutput
```

With `-SkipPhotos`:

```powershell
& '.\tools\bambuddy\Test-RestoreFromSidecar.ps1' \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId <archive_id> \
  -TargetArchiveId $replacementArchiveId \
  -Verify \
  -SkipPhotos \
  -CompactOutput
```

#### 6. Optional cleanup

Only after verify returns `verified: true` and `removable: true`.

```powershell
& '.\tools\bambuddy\Test-RestoreFromSidecar.ps1' \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId <archive_id> \
  -TargetArchiveId $replacementArchiveId \
  -Verify \
  -RemoveOriginal \
  -Apply \
  -CompactOutput
```

Or, if photos were intentionally skipped:

```powershell
& '.\tools\bambuddy\Test-RestoreFromSidecar.ps1' \
  -BaseUrl $sidecarBaseUrl \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId <archive_id> \
  -TargetArchiveId $replacementArchiveId \
  -Verify \
  -SkipPhotos \
  -RemoveOriginal \
  -Apply \
  -CompactOutput
```

## Queue-Specific Commands

### Queue item 1: archive `19`

Source file:

- `'.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf'`

Inspect:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId 19 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\2 AMS.3mf' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

### Queue item 2: archive `108`

Source file:

- `'.\bambuddy\Backup SD Card - 2026-04-03\cache\Laney Rivers 2026_Front_133x200.3mf'`

Inspect:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId 108 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Laney Rivers 2026_Front_133x200.3mf' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

### Queue item 3: archive `106`

Source file:

- `'.\bambuddy\Backup SD Card - 2026-04-03\cache\Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf'`

Inspect:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId 106 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

### Queue item 4: archive `174`

Source file:

- `'.\bambuddy\Backup SD Card - 2026-04-03\cache\200mm x 200mm Deadpool & Wolverine Hueforge.3mf'`

Inspect:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId 174 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\200mm x 200mm Deadpool & Wolverine Hueforge.3mf' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

### Queue item 5: archive `34`

Source file:

- `'.\bambuddy\Backup SD Card - 2026-04-03\cache\Adaptive Layers .  100% Infill.3mf'`

Inspect:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId 34 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Adaptive Layers .  100% Infill.3mf' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

### Queue item 6: archive `105`

Source file:

- `'.\bambuddy\Backup SD Card - 2026-04-03\cache\Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf'`

Inspect:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' \
  -Mode Inspect \
  -BaseUrl $baseUrl \
  -PrinterId $printerId \
  -FallbackArchiveId 105 \
  -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf' \
  -RecoverySource 'sd_cache_3mf' \
  -ApiKey $env:BAMBUDDY_API_KEY
```

## Recommended Next Actions

1. Process Queue A first in the order `19`, `108`, `106`.
2. After Queue A, decide whether `174` is acceptable as a provenance-quality recovery despite medium confidence.
3. Keep `34` and `105` manual until the inspect output looks credible.
4. Leave `66`, `206`, `207`, and `208` alone until stronger matching evidence exists.
5. If you want true bulk fallback remediation, design a new orchestrator around the current pairwise steps rather than reusing `Backfill` mode directly.