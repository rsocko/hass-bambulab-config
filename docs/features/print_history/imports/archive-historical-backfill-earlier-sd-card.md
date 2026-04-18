# Historical Archive Backfill From Earlier SD-Card Backup

## Purpose

Run the same historical archive backfill workflow against the earlier printer SD-card backup without merging it into the existing April 3 manifest lane.

This runbook keeps the ledger, batch outputs, and operator workflow separate while reusing the same manifest generator and backfill runner described in [archive-historical-backfill-from-sd-card.md](archive-historical-backfill-from-sd-card.md).

## Source And State Files

- source root: `C:\Users\rysock\OneDrive\3D Printing\_BACKUP MicroSD Card`
- manifest ledger: `bambuddy/backfill-state/archive_backfill_manifest_v2_earlier_sd_card.json`
- inspect result pattern: `tmp/archive_backfill_earlier_sd_<batch_id>_inspect.json`
- full/import result pattern: `tmp/archive_backfill_earlier_sd_<batch_id>_full.json`

## Guardrails

- Keep this manifest completely separate from `bambuddy/backfill-state/archive_backfill_manifest_v2.json`.
- Do not merge candidate rows across the two backups even when files overlap.
- Let Bambuddy exact `content_hash` dedupe decide whether a candidate is already represented.
- Use deterministic batches of 4 candidates at a time for review and import.

## Generate Parallel Manifest

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\generate_archive_backfill_manifest.py `
  --source-root 'C:\Users\rysock\OneDrive\3D Printing\_BACKUP MicroSD Card' `
  --output '.\bambuddy\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json' `
  --batch-size 4
```

## Inspect One Batch

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
  -Mode Backfill `
  -BaseUrl 'http://bambuddy.socko.us' `
  -PrinterId 1 `
  -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json' `
  -BackfillAction Inspect `
  -BatchId 'batch-001' `
  -UpdateManifest `
  -ResultPath '.\tmp\archive_backfill_earlier_sd_batch-001_inspect.json'
```

## Import One Batch

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
  -Mode Backfill `
  -BaseUrl 'http://bambuddy.socko.us' `
  -PrinterId 1 `
  -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json' `
  -BackfillAction Full `
  -BatchId 'batch-001' `
  -UpdateManifest `
  -ResultPath '.\tmp\archive_backfill_earlier_sd_batch-001_full.json'
```

## Secondary Artifact Analysis

Generate `.gcode` and `image` forensic analysis for the earlier backup and write it back into the isolated manifest:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\analyze_cache_secondary_artifacts.py `
  --source-root 'C:\Users\rysock\OneDrive\3D Printing\_BACKUP MicroSD Card' `
  --manifest '.\bambuddy\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json' `
  --pairings-output '.\tmp\earlier_sd_cache_gcode_pairing_analysis.json' `
  --write-manifest
```

Launch the forensics viewer against the earlier backup without manifest writeback:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\gcode_forensics_viewer.py `
  --source-root 'C:\Users\rysock\OneDrive\3D Printing\_BACKUP MicroSD Card' `
  --manifest '.\bambuddy\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json' `
  --pairings '.\tmp\earlier_sd_cache_gcode_pairing_analysis.json' `
  --port 8771
```

Launch the forensics viewer against the earlier backup with manifest writeback:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\gcode_forensics_viewer.py `
  --source-root 'C:\Users\rysock\OneDrive\3D Printing\_BACKUP MicroSD Card' `
  --manifest '.\bambuddy\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json' `
  --pairings '.\tmp\earlier_sd_cache_gcode_pairing_analysis.json' `
  --manifest-writeback `
  --port 8770
```

## Batch Workflow

1. Generate or refresh the isolated manifest.
2. Run `Inspect` for one `batch-00N` lane.
3. Review which rows are `batch_ready`, `already_in_archive`, or `manual_review_source_only`.
4. Run `Full` only for the batch you are ready to import.
5. Advance to the next batch in groups of 4 until the manifest is exhausted.

## Current Status

- Manifest generated from `C:\Users\rysock\OneDrive\3D Printing\_BACKUP MicroSD Card` with `batch_size: 4`.
- Inspect pass covered `batch-001` through `batch-005` and found all 20 candidates were initially net-new versus the pre-import Bambuddy archive set.
- Full import pass created archives `404` through `422`, with 19 candidates imported and annotated.
- One candidate collapsed by exact `content_hash` during the same run: `cache/Modular_10_Server_Rack.3mf` matched newly created archive `415` from `cache/Cover.3mf`.
- Runtime repair preview and apply were run through `http://bambuddy-runtime-repair.socko.us` for all 19 imported archives.
- Applied repair fields per archive were `started_at`, `completed_at`, `created_at`, plus the repair audit note in `notes`; all repaired entries landed with `repair_confidence: medium`.
- Archive `status` was intentionally left unchanged because this lane did not use `-RepairSetCompletedStatus`.
- Secondary artifact analysis is now written into the isolated manifest with `437` cache `.gcode`, `20` cache `.bbl`, `455` `image/*.png`, and `19` `model/*.gcode` files recorded.
- Current older-backup `.gcode` pairing summary is `21` exact cache-`.3mf` stem matches, `3` near-time-only matches, and `413` ambiguous `.gcode` files for forensic review.
- Final manifest summary: `completed: 19`, `already_in_archive: 1`.