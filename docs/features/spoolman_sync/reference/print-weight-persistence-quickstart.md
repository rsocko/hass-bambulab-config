# Print Weight Persistence - Quick Start Guide

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/print-weight-persistence-quickstart.md
Replaced By: none


## The Problem
When Home Assistant restarts during a print, the print weight attributes are lost, breaking the filament usage automation.

## The Solution
A backup and restore system that:
1. Captures print weight data when print starts
2. Stores it in input helpers (survives restarts)
3. Uses backup if needed when print completes
4. Updates Spoolman correctly

## Quick Installation

### Step 1: Add Input Helpers (5 minutes)

This automation set relies on the `spoolman_sync` package loader plus split
helper/template files. Copy the package folder into your Home Assistant
`/config` directory and register package loading.

**Recommended folder structure:**

```
/config/
├── configuration.yaml
└── packages/
  └── 3d_printing/
    ├── _feature_loaders.yaml
    └── spoolman_sync/
      ├── spoolman_sync_loader.yaml
      ├── helpers/
      └── template_sensors/
```

Add the following block to `configuration.yaml` (create the
`homeassistant.packages` section if it does not already exist):

```yaml
homeassistant:
  packages: !include packages/3d_printing/_feature_loaders.yaml
```

> **Why packages?**  Each helper file contains multiple top-level YAML sections
> (e.g. `input_text:` **and** `template:`).  Using
> `input_text: !include ...` or `template: !include ...` directly in
> `configuration.yaml` would nest the file's own section headers incorrectly and
> will not work.  The `homeassistant.packages` mechanism is the correct way to
> load a file that defines more than one integration domain.

> **Existing helper entities:** If you already have `input_text:`, `input_number:`,
> or other helper sections in `configuration.yaml` for unrelated purposes, the
> packages approach is safe — Home Assistant merges package keys with your
> existing configuration automatically.  No entries in those standalone sections
> need to be moved or modified.

### Critical Setting: Do Not Set `initial` on Backup Helpers

For restart-safe persistence, ensure these helpers do **not** define `initial`:
- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`

If `initial` is set (for example `initial: ""`), HA startup will initialize the
helper to that value and previous backup state will not restore from recorder.

### Step 2: Add Automations (10 minutes)

#### A. Print Started Automation
1. Go to Settings → Automations & Scenes → Create Automation
2. Click ⋮ (three dots) → Edit in YAML
3. Paste contents of `print_started-backup_print_weight.yaml`
4. Update `device_id` to match your printer (see Configuration Notes below)
5. Save as "Print Started - Backup Print Weight"

#### B. Print Complete Automation
1. **Disable** your existing print_complete automation (don't delete yet!)
2. Create new automation
3. Click ⋮ → Edit in YAML
4. Paste contents of `print_complete-update_filament_usage.yaml`
5. Update `device_id` and entity names (see Configuration Notes below)
6. Save as "Print Complete - Update Filament Usage (Enhanced)"

### Step 3: Configuration Notes

#### Find Your Device ID
1. Go to Developer Tools → States
2. Search for your printer (e.g., "ntk_ryansoffice_3dprinter")
3. Click any printer entity
4. Look for `device_id` in the attributes
5. Copy and replace in both YAML files

#### Update Entity Names
Replace these with your printer's entities (search and replace):
- `sensor.ntk_ryansoffice_3dprinter_print_weight` → `sensor.[YOUR_PRINTER]_print_weight`
- `sensor.ntk_ryansoffice_3dprinter_task_name` → `sensor.[YOUR_PRINTER]_task_name`
- `sensor.p1s_01p00c460102350_ams_[N]_tray_[SLOT]` → `sensor.[YOUR_PRINTER]_ams_[N]_tray_[SLOT]`
- etc.

### Step 4: Restart Home Assistant
```bash
Developer Tools → YAML → Restart
```

Wait for restart to complete.

### Step 5: Test

#### Test 1: Basic Operation
1. Start a print
2. Go to Developer Tools → States
3. Check `input_text.print_weight_backup` has data (should be JSON)
4. Let print complete
5. Check logbook for "Print Weight Data Source" entry
6. Verify Spoolman was updated
7. Verify backup was cleared (input_text empty)

#### Test 2: HA Restart (The Main Scenario)
1. Start a print
2. Verify backup was created
3. Developer Tools → YAML → Restart Home Assistant
4. Wait for HA to come back up
5. Let print complete
6. Check logbook - should say "Will use backup data"
7. Verify Spoolman was updated correctly
8. Check backup was cleared

## Monitoring

### Check Backup Status
Developer Tools → States → `sensor.print_weight_data_status`

Should show:
- **State**: "stored" (during print) or "empty" (no active print)
- **Attributes**: task_name, start_time, total_weight

### View Backup Data
Developer Tools → States → `input_text.print_weight_backup`

Example:
```json
{"AMS 1 Tray 1": 15, "AMS 1 Tray 3": 10}
```

### Run Manual Self-Test Script
1. Go to **Developer Tools → Services**
2. Select service: `script.print_weight_persistence_self_test`
3. Click **Call Service**
4. Review results in:
  - Logbook entry: **Print Weight Persistence Self-Test**
  - Persistent notification: **Print Weight Persistence Self-Test**

### Optional: Auto-Run Self-Test at Print Start/Finish
1. Create a new automation
2. Click ⋮ → **Edit in YAML**
3. Paste contents of `print_weight_persistence_auto_self_test.yaml`
4. Update `device_id` to match your printer
5. Save and enable

This creates phase-specific notifications so results do not overwrite each other:
- `print_weight_persistence_self_test_start`
- `print_weight_persistence_self_test_finish`

## Troubleshooting

### Backup Not Created
- Check print_started automation is enabled
- Verify device_id is correct
- Confirm the automation uses `input_text.set_value` (not `text.set_value`)
- Check Home Assistant logs/traces for service call errors

### `from_json got invalid input 'unknown'`
- This means `input_text.print_weight_backup` contains `unknown` instead of JSON
- Ensure `spoolman_sync_loader.yaml` is loaded via `homeassistant.packages`
- Ensure both backup helpers do **not** set `initial`
- Confirm backup automation wrote JSON before print completion

### Temporary Startup Diagnostic (Remove After Testing)
If you are actively debugging restart behavior:
1. Enable `temporary_startup_diagnostic_print_weight_persistence.yaml`
2. Restart Home Assistant
3. Review logbook/system log + notification for startup backup helper values
4. Disable or remove this diagnostic automation after confirmation

### Verify Backup Data Is Valid JSON
1. Developer Tools → States → `input_text.print_weight_backup`
2. Value should look like `{"AMS 1 Tray 1": 12}` (or `{}` when no tray data)
3. It should never be `unknown`/`unavailable`

### Verify 255-char Limit Is Not Exceeded
1. Developer Tools → Template
2. Run: `{{ states('input_text.print_weight_backup') | length }}`
3. Value must be `<= 255`
4. If larger, reduce stored keys (store only non-zero tray usage)

### "No attributes" Error
- Verify both automations are running
- Check entity names are correct
- Review logbook for error messages

### Wrong Filament Updated
- This is likely a spool matching issue
- Check your find_matching_spool configuration
- Verify UUIDs in Spoolman match tray UUIDs

## What's Logged

All operations are logged to the logbook:

- **"Print Weight Backup"**: When backup is created
- **"Print Weight Data Source"**: Which data source is used (current or backup)
- **"Print Weight Processing"**: How many trays found
- **"Spoolman [Tray Name]"**: Results for each tray
- **"Print Weight Backup Cleared"**: Cleanup complete

## Rollback

If you need to go back to the old automation:
1. Disable the enhanced automation
2. Re-enable the original automation
3. Clear the input helpers (set to empty)
4. Restart is not needed

## Need Help?

See the full documentation:
- [Complete Documentation](\docs\features\spoolman_sync\reference\print-weight-persistence-overview.md)
- [Implementation Summary](\docs\features\spoolman_sync\archive\print-weight-persistence-implementation.md)
- [Troubleshooting Guide](\docs\features\spoolman_sync\reference\print-weight-persistence-overview.md#troubleshooting)

## Success!

Once installed, your automation will:
- ✅ Work normally when HA doesn't restart
- ✅ Use backup data if HA restarts during print
- ✅ Update Spoolman correctly in both cases
- ✅ Log everything for troubleshooting
- ✅ Handle errors gracefully

You're now protected against HA restarts during prints! 🎉


