# WLED Backup and Restore Guide

Use this guide before firmware updates, segment redesigns, or major preset changes.

## Why backup

WLED usually keeps settings across reboots and most firmware upgrades, but settings can still be lost by:

- Factory reset
- Flash operations that erase settings/filesystem
- Corruption during unstable power events
- Failed migration between versions

Keep repository-backed snapshots as your source of truth.

## Required files to back up

For each controller, back up all of the following:

1. `cfg.json` (device configuration)
2. `presets.json` (presets and saved states)

Optional (only if your WLED version/UI exposes a single export file):

3. `backup-export.json`

## Repository backup structure

Store backups under:

- `wled/backups/digquad/YYYY-MM-DD_HHMM/`
- `wled/backups/magwled/YYYY-MM-DD_HHMM/`

Expected files per snapshot:

- `cfg.json`
- `presets.json`
- `NOTES.md` with firmware version, hostname/IP, and reason for backup

Optional snapshot file:

- `backup-export.json` (if available in your UI/version)

Template files for notes:

- `wled/backups/digquad/NOTES_TEMPLATE.md`
- `wled/backups/magwled/NOTES_TEMPLATE.md`

Copy the appropriate template into your timestamped snapshot folder as `NOTES.md`.

## Backup procedure

### Option A: UI backup (standard)

1. Open WLED web UI.
2. Go to `Config` -> `Security & Updates` -> `Backup`.
3. Click `Backup Configuration` and save as `cfg.json`.
4. Click `Backup Presets` and save as `presets.json`.

If your WLED build also provides a combined export, save that as `backup-export.json`.

### Option B: File-level backup (equivalent fallback)

1. Open `http://<wled-host>/edit`.
2. Download `/cfg.json` and `/presets.json`.
3. Save in the same timestamped backup folder.

## Restore procedure

### Preferred restore

1. Open `Config` -> `Security & Updates`.
2. Restore `cfg.json` using configuration restore.
3. Restore `presets.json` using presets restore.
4. Reboot controller.
5. Verify key presets, segment bounds, and LED outputs.

### File-level restore fallback

1. Upload `cfg.json` and `presets.json` via `http://<wled-host>/edit`.
2. Reboot controller.
3. Validate LED order, segment mapping, and preset behavior.

### Combined export restore (optional)

If you have a `backup-export.json` from a compatible WLED version/UI, you can restore that through the UI backup/restore flow.

## Validation checklist after restore

- Controller reachable and hostname/IP correct
- LED output counts match expected totals
- Segment bounds and IDs are correct
- Baseline presets (`Reset`, `Idle`, `Night`, `Error`) work
- Dynamic automation overlays still apply correctly

## Recommended cadence

Create backups:

- Before firmware updates
- Before bulk preset changes
- Before segment boundary changes
- After major stable milestones
