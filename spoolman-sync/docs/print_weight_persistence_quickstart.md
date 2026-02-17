# Print Weight Persistence - Quick Start Guide

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

Add this to your `configuration.yaml`:

```yaml
# Add at the end of configuration.yaml or in a package file
input_text: !include spoolman-sync/print_weight_persistence.yaml
template: !include spoolman-sync/print_weight_persistence.yaml
```

Or if you already have `input_text:` section, merge the contents.

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
4. Paste contents of `print_complete-update_filament_usage_v2.yaml`
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
- `sensor.p1s_01p00c460102350_ams_1_tray_1` → `sensor.[YOUR_PRINTER]_ams_1_tray_1`
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

## Troubleshooting

### Backup Not Created
- Check print_started automation is enabled
- Verify device_id is correct
- Check Home Assistant logs for errors

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
1. Disable the new v2 automation
2. Re-enable the original automation
3. Clear the input helpers (set to empty)
4. Restart is not needed

## Need Help?

See the full documentation:
- [Complete Documentation](print_weight_persistence.md)
- [Implementation Summary](../PRINT_WEIGHT_PERSISTENCE_IMPLEMENTATION.md)
- [Troubleshooting Guide](print_weight_persistence.md#troubleshooting)

## Success!

Once installed, your automation will:
- ✅ Work normally when HA doesn't restart
- ✅ Use backup data if HA restarts during print
- ✅ Update Spoolman correctly in both cases
- ✅ Log everything for troubleshooting
- ✅ Handle errors gracefully

You're now protected against HA restarts during prints! 🎉
