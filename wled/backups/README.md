# WLED Backups

Status: Local operational artifacts
Canonical docs: docs/features/wled/reference/backup-and-restore.md
Historical policy: files under this folder are backup artifacts, not canonical architecture/design docs

This folder stores versioned backup snapshots exported from running WLED controllers.

For current implementation guidance, use `docs/features/wled/` (especially `reference/backup-and-restore.md`).

## What to back up

For each controller, capture all of the following:

1. Full WLED backup export from UI (recommended for restore speed).
2. `cfg.json` (device config).
3. `presets.json` (presets and related state).

## Directory layout

- `wled/backups/digquad/` - DigQuad snapshots
- `wled/backups/magwled/` - MagWLED snapshots

Use a timestamped folder per snapshot:

- `wled/backups/digquad/YYYY-MM-DD_HHMM/`
- `wled/backups/magwled/YYYY-MM-DD_HHMM/`

Suggested files inside each snapshot folder:

- `backup-export.json` (UI backup export)
- `cfg.json`
- `presets.json`
- `NOTES.md` (firmware version, IP/hostname, reason for backup)

Controller-specific notes templates are provided:

- `wled/backups/digquad/NOTES_TEMPLATE.md`
- `wled/backups/magwled/NOTES_TEMPLATE.md`

Copy the template into each timestamped snapshot folder as `NOTES.md`.

## Recommended workflow

1. Take a snapshot before firmware updates, major preset edits, or segment changes.
2. Commit snapshot files to git with a short message (for example: `wled backup before 0.15.0 update`).
3. Validate restore path on at least one non-production window.

## Quick restore guidance

1. Use WLED UI backup restore with `backup-export.json` first.
2. If needed, restore `cfg.json` and `presets.json` manually via the WLED file editor endpoint.
3. Reboot WLED and verify LED outputs, segment boundaries, and key presets.
