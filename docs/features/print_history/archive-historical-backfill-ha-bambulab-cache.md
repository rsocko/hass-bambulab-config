# Historical Archive Backfill From Home Assistant ha-bambulab Cache

## Purpose

Document the analysis lane built from the Home Assistant `ha_bambulab` local cache under `www/media/ha-bambulab/.../prints/cache`, plus supporting snapshot images from `www/printer_snapshots`.

This lane reuses the same manifest and inspect workflow as the earlier SD-card backfill runs, but the source files were exported directly from Home Assistant over SSH.

## Source And Export Paths

- Home Assistant cache source: `/config/www/media/ha-bambulab/01P00C460102350/prints`
- Home Assistant snapshot source: `/config/www/printer_snapshots`
- Local export root: `tmp/ha_bambulab_cache_export/01P00C460102350/prints`
- Local cache export folder: `tmp/ha_bambulab_cache_export/01P00C460102350/prints/cache`
- Local snapshot export folder: `tmp/ha_bambulab_cache_export/01P00C460102350/prints/image`
- Manifest ledger: `bambuddy/backfill-state/archive_backfill_manifest_v2_ha_bambulab_cache.json`
- Inspect result snapshot: `tmp/archive_backfill_ha_bambulab_cache_inspect.json`
- G-code pairing analysis: `tmp/ha_bambulab_cache_gcode_pairing_analysis.json`

## Export Workflow

The repo now includes a reusable SSH export helper:

- `tools/bambuddy/export_ha_bambulab_cache_via_ssh.py`

Example cache export:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\export_ha_bambulab_cache_via_ssh.py `
  --host 192.168.1.5 `
  --username hassio `
  --password "<ssh-password>" `
  --remote-root /config/www/media/ha-bambulab/01P00C460102350/prints `
  --output-root .\tmp\ha_bambulab_cache_export\01P00C460102350\prints `
  --clear-output
```

Example snapshot export:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\export_ha_bambulab_cache_via_ssh.py `
  --host 192.168.1.5 `
  --username hassio `
  --password "<ssh-password>" `
  --remote-root /config/www/printer_snapshots `
  --output-root .\tmp\ha_bambulab_cache_export\01P00C460102350\prints\image `
  --clear-output
```

## Manifest Generation And Inspect

Manifest generation:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\generate_archive_backfill_manifest.py `
  --source-root '.\tmp\ha_bambulab_cache_export\01P00C460102350\prints' `
  --output '.\bambuddy\backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json' `
  --batch-size 25
```

Secondary artifact analysis:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\analyze_cache_secondary_artifacts.py `
  --source-root '.\tmp\ha_bambulab_cache_export\01P00C460102350\prints' `
  --manifest '.\bambuddy\backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json' `
  --pairings-output '.\tmp\ha_bambulab_cache_gcode_pairing_analysis.json' `
  --write-manifest
```

Inspect pass against current Bambuddy archives:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
  -Mode Backfill `
  -BaseUrl 'http://bambuddy.socko.us' `
  -PrinterId 1 `
  -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json' `
  -BackfillAction Inspect `
  -UpdateManifest `
  -ResultPath '.\tmp\archive_backfill_ha_bambulab_cache_inspect.json'
```

Import one validated candidate with runtime repair apply:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
  -Mode Backfill `
  -BaseUrl 'http://bambuddy.socko.us' `
  -PrinterId 1 `
  -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json' `
  -ManifestEntryId '<entry_id>' `
  -BackfillAction Full `
  -RepairAction Apply `
  -RepairSidecarBaseUrl 'http://bambuddy-runtime-repair.socko.us' `
  -RepairSidecarToken $env:REPAIR_API_TOKEN `
  -ApiKey $env:BAMBUDDY_API_TOKEN `
  -UpdateManifest `
  -ResultPath '.\tmp\archive_backfill_ha_bambulab_cache_import.json'
```

Launch the forensics viewer against the HA-cache export lane:

```powershell
C:/Users/rysock/AppData/Local/Python/pythoncore-3.14-64/python.exe .\tools\bambuddy\gcode_forensics_viewer.py `
  --source-root '.\tmp\ha_bambulab_cache_export\01P00C460102350\prints' `
  --manifest '.\bambuddy\backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json' `
  --pairings '.\tmp\ha_bambulab_cache_gcode_pairing_analysis.json' `
  --decision-output '.\tmp\ha_bambulab_cache_gcode_forensics_decisions.json' `
  --manifest-writeback `
  --port 8772
```

## Current Findings

- Exported cache inventory: `386` files under `cache/`, including `101` `.3mf` candidates and `285` secondary artifacts.
- Exported printer snapshots: `207` `.jpg` files under the local `image/` lane.
- Inspect pass compared `101` Home Assistant cache `.3mf` files against `419` existing Bambuddy archives.
- Exact `content_hash` dedupe found `86` candidates already represented in Bambuddy before manual duplicate cleanup.
- Of the remaining `15` candidates, `9` were valid zip-backed `.3mf` files and `6` were broken cache artifacts.
- The `9` valid candidates were initially imported as archives `425` through `433`.
- Operator review later removed archives `428` and `432` as duplicates of existing archives `181` and `209`, leaving `7` retained HA-cache imports.
- Runtime repair apply was run through `http://bambuddy-runtime-repair.socko.us` for the imported HA-cache archives that remained after review.
- Current manifest state is `88` already represented, `7` completed imports, and `6` manual-review broken artifacts.
- The `6` broken cache artifacts are now marked as `manual_review_non_importable` in the manifest so future backfill runs do not treat them as upload candidates.
- The exported raw cache `.gcode` set is fully explainable by the `.3mf` lane: `95` `.gcode` files, `95` exact `.3mf` matches, `0` ambiguous `.gcode` files.

## Already Represented

- `86` Home Assistant cache `.3mf` files matched existing Bambuddy archives by exact `content_hash`.
- This includes known previously imported or already archived items such as:
  - `Filament_spool_holder_-_shelf_with_one_pipe` -> archive `250`
  - `200mm x 200mm Deadpool & Wolverine Hueforge` -> archive `181`
  - `200mm x 400mm Luke Skywalker Light Saber 2-piece Hueforge` -> archive `177`
  - `Magnetic Wall Mount for Hueforge` cache variants -> existing archives including `122`, `126`, `155`, and `195`

## Imported HA-Cache Candidates

These `7` cache files remain as imported and annotated HA-cache additions:

- `cache/11292916-6x4 - 24 plates - 1200 mm x 800 mm.3mf` -> archive `425`
- `cache/11680927-0.08mm layer, 2 walls, 100% infill.3mf` -> archive `426`
- `cache/11802793-0.08mm layer, 2 walls, 100% infill.3mf` -> archive `427`
- `cache/333417-Modular Magnetic Frame System for Hueforge Art.3mf` -> archive `429`
- `cache/333497-Modular Magnetic Frame System for Hueforge Art.3mf` -> archive `430`
- `cache/333808-Modular Magnetic Frame System for Hueforge Art.3mf` -> archive `431`
- `cache/672209-Modular Magnetic Frame System for Hueforge Art.3mf` -> archive `433`

These two imports were intentionally removed after operator review and now point at retained existing archives instead:

- `cache/21969933-200mm x 200mm Deadpool & Wolverine Hueforge.3mf` -> existing archive `181` (duplicate import `428` deleted)
- `cache/5222426-6x4 - 24 plates - 1200 mm x 800 mm.3mf` -> existing archive `209` (duplicate import `432` deleted)

## Broken Or Non-Zip Cache Artifacts

These `6` candidates were not deduped by Bambuddy, but they are not valid archive-ready `.3mf` uploads in their current form:

- `cache/0-0.08mm layer, 2 walls, 100% infill.3mf` - zero bytes
- `cache/12175225-0.08mm layer, 2 walls, 100% infill.3mf` - non-zip payload
- `cache/12175256-0.08mm layer, 2 walls, 100% infill.3mf` - non-zip payload
- `cache/12452321-0.08mm layer, 1 walls, 100% infill.3mf` - non-zip payload
- `cache/7376280-6x4 - 24 plates - 1200 mm x 800 mm.3mf` - non-zip payload
- `cache/8558810-6x4 - 24 plates - 1200 mm x 800 mm.3mf` - non-zip payload

These are now marked in the manifest as `manual_review_non_importable` and should stay manual-review evidence only unless another valid source copy exists.

## Snapshot Image Findings

- `207` `.jpg` snapshot files were exported from `www/printer_snapshots` into the local `image/` lane.
- The current snapshot lane has `0` `.md5` sidecars, unlike the old SD-card `image/md5` layout.
- Timestamp-only image correlation is weak in this export: the manifest currently found `1` snapshot within the two-minute matching window of a cache candidate.
- Example timestamp match:
  - image `20260324_114700_ERROR_Modular_Magnetic_Frame_System_for_Hueforge_Art.jpg`
  - matched candidate `cache/672190-Modular Magnetic Frame System for Hueforge Art.3mf`
- Snapshot images are still worth retaining as supporting evidence for failure context, near-complete captures, and print provenance even though they are not canonical archive inputs.

## Interpretation

This Home Assistant cache lane is materially different from the old SD-card backups:

- the `cache/` folder already carries paired `.3mf` and `.gcode` artifacts for most entries
- supporting metadata appears as loose sibling files such as `.slice_info.config`
- printer snapshots are stored separately as `.jpg` files under `www/printer_snapshots`, not as the old `image/*.png` plus `image/md5/*.md5` structure

The practical result is:

- use the Home Assistant cache `.3mf` files as the canonical import candidates
- use the exported `printer_snapshots` folder only as supporting evidence
- `7` HA-cache-only `.3mf` files remain as retained imports in Bambuddy, while `2` reviewed duplicates now point back to existing archives
- do not import the `6` broken/non-zip cache artifacts without a better source file