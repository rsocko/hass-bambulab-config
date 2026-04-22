# Manual Reconciliation Launchpad

Last updated: 2026-04-22

## Purpose

Single operator launch point for manual reconciliation and correction across the three source areas.

## Operational vs Versioned

- Operational (live triage): keep active manifests/state in OneDrive lane workspaces for fast iteration and local preview assets.
- Versioned (checkpoint): copy milestone snapshots into repo `bambuddy/backfill-state` for git history, rollback, and cross-session audit.

## Confirmed Current State

- `C:\Users\rysock\OneDrive\3D Printing Catalog` is related to the folder-catalog workflow and should be used.
- It currently contains:
  - `manifest.json` with reconciled records (includes `already_represented` rows)
  - `previews/` extracted preview images
  - `state/catalog_state.json` with saved operator edits
- This is currently the best canonical workspace for the OneDrive source-library lane.
- SD backups are now consolidated under:
  - `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups`
  - with two source folders:
    - `2025-08-14 - SD Card Backup`
    - `2026-04-03 - SD Card Backup`
  - and a shared manifest store:
    - `backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json`
    - `backfill-state\archive_backfill_manifest_v2.json`
    - `backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json`

## Canonical Lanes

### Lane A: OneDrive source 3MF library

- Source root:
  - `C:\Users\rysock\OneDrive\3D Printing`
- Workflow:
  - folder catalog (`generate_folder_3mf_catalog.py` + `reconcile_folder_3mf_catalog.py` + `folder_3mf_catalog_viewer.py`)
- Canonical working root:
  - `C:\Users\rysock\OneDrive\3D Printing Catalog`
- Canonical manifest:
  - `C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json`
- Canonical state:
  - `C:\Users\rysock\OneDrive\3D Printing Catalog\state\catalog_state.json`

Launch viewer (with Bambuddy archive thumbnails):

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" "c:\dev\hass-bambulab-config\tools\bambuddy\folder_3mf_catalog_viewer.py" --manifest "C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json" --state "C:\Users\rysock\OneDrive\3D Printing Catalog\state\catalog_state.json" --archive-base-url "http://bambuddy.socko.us"
```

Refresh scan for this lane (exclude `_SD Card Backups` to avoid overlap with SD lanes):

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" "c:\dev\hass-bambulab-config\tools\bambuddy\generate_folder_3mf_catalog.py" --source-root "C:\Users\rysock\OneDrive\3D Printing" --working-root "C:\Users\rysock\OneDrive\3D Printing Catalog" --output "C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json" --previous-manifest "C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json" --exclude-patterns "_sd card backups/**" "_backup microsd card/**" "backup sd card - 2026-04-03/**"
```

Reconcile against Bambuddy archives:

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" "c:\dev\hass-bambulab-config\tools\bambuddy\reconcile_folder_3mf_catalog.py" --manifest "C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json" --base-url "http://bambuddy.socko.us"
```

### Lane B1: OneDrive SD backup (`2025-08-14 - SD Card Backup`)

- Source root:
  - `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\2025-08-14 - SD Card Backup`
- Workflow:
  - SD-card historical backfill / forensics workflow
- Canonical manifest:
  - `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json`

Launch SD-card forensics viewer for this lane:

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" "c:\dev\hass-bambulab-config\tools\bambuddy\gcode_forensics_viewer.py" --source-root "C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\2025-08-14 - SD Card Backup" --manifest "C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json"
```

### Lane B2: OneDrive SD backup (`2026-04-03 - SD Card Backup`)

- Source root:
  - `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\2026-04-03 - SD Card Backup`
- Workflow:
  - SD-card historical backfill / forensics workflow
- Canonical manifest:
  - `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2.json`

Launch SD-card forensics viewer for this lane:

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" "c:\dev\hass-bambulab-config\tools\bambuddy\gcode_forensics_viewer.py" --source-root "C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\2026-04-03 - SD Card Backup" --manifest "C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2.json"
```

### Lane C: Repo mirror/reference set (optional)

- Source root:
  - `c:\dev\hass-bambulab-config\bambuddy\Backup SD Card - 2026-04-03`
- Workflow:
  - Optional reference/validation lane only (use when comparing OneDrive and repo copies)
- Reference manifest:
  - `c:\dev\hass-bambulab-config\bambuddy\backfill-state\archive_backfill_manifest_v2.json`

## Recommended Triage Order

1. Lane A first (OneDrive source library), because this is where your saved folder-catalog state and preview workflow already exists.
2. Lane B1 next (`2025-08-14 - SD Card Backup`) for older cache-level artifact reconciliation.
3. Lane B2 next (`2026-04-03 - SD Card Backup`) for newer cache-level artifact reconciliation.
4. Lane C only when you need to compare against the repo mirror.

## Live Status Board

Update this section as the operational source of truth before and after each triage session.

| Lane | Current Status | Last Session | Progress Snapshot | Main Blocker | Next Action |
| --- | --- | --- | --- | --- | --- |
| A: OneDrive source 3MF library | In progress | 2026-04-22 | Manifest reconciled, previews present, saved state exists in `state/catalog_state.json` | None confirmed | Continue manual triage in viewer and mark remaining ambiguous records |
| B1: OneDrive `2025-08-14 - SD Card Backup` | Not started | - | Historical SD-card manifest exists in consolidated backfill-state | Needs active triage pass in forensics viewer | Launch lane B1 forensics viewer and classify top ambiguous groups |
| B2: OneDrive `2026-04-03 - SD Card Backup` | Not started | - | Historical SD-card manifest exists in consolidated backfill-state | Needs active triage pass in forensics viewer | Launch lane B2 forensics viewer and validate candidate bucket statuses |
| C: Repo mirror/reference set | Optional | - | Repo copy of 2026-04-03 backup remains available for cross-checks | Usually not needed for primary triage | Use only to compare OneDrive versus repo artifact parity |

### Session Checklist

1. Pick exactly one lane for the session.
2. Confirm the lane's canonical manifest path before opening a viewer.
3. Run the lane's verification check before making triage edits.
4. Record blocker + next action in the table above before ending the session.
5. Do not mix artifacts between lanes in the same commit/session unless intentionally doing cross-lane dedupe.

## Workspace Convention (Reduce Scatter)

Use one manifest/state/preview workspace per lane family:

1. Folder-catalog workspace (Lane A):
  - `C:\Users\rysock\OneDrive\3D Printing Catalog`
2. SD backup manifests (Lane B1/B2):
  - `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state`
3. Repo lane (Lane C):
  - Keep read-only/reference unless you are explicitly validating or migrating artifacts.

Rule of thumb: store manifests and state next to the lane they describe, but keep generated previews/cache under the lane-specific working root only.

## Snapshot Workflow (Versioned Checkpoints)

Create a repo checkpoint snapshot from OneDrive operational manifests/state:

```powershell
& "c:\dev\hass-bambulab-config\tools\bambuddy\snapshot_reconciliation_manifests.ps1"
```

Update the latest repo baseline files at the same time:

```powershell
& "c:\dev\hass-bambulab-config\tools\bambuddy\snapshot_reconciliation_manifests.ps1" -UpdateLatest
```

What gets snapshotted:

1. `C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json`
2. `C:\Users\rysock\OneDrive\3D Printing Catalog\state\catalog_state.json`
3. `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json`
4. `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2.json`
5. `C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups\backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json`

## Reorganization Guidance

Short answer: optional but recommended for clarity.

Recommended changes:

1. Keep Lane A and Lane B as separate logical datasets.
2. Always scan Lane A with `_SD Card Backups/**` excluded.
3. Keep B1/B2 manifests in the consolidated OneDrive `backfill-state` folder.
4. Continue using one working root per lane so previews/state/manifests do not mix.

## Quick Verification Checks

Lane A manifest sanity:

```powershell
$m = Get-Content "C:\Users\rysock\OneDrive\3D Printing Catalog\manifest.json" -Raw | ConvertFrom-Json
$c = @($m.candidates)
"already_represented=" + @($c | ? { $_.reconciliation_status -eq 'already_represented' }).Count
"preview_rows=" + @($c | ? { $_.preview_images -and $_.preview_images.Count -gt 0 }).Count
```
