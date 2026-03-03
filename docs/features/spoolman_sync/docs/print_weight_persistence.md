# Print Weight Persistence - Solution for HA Restart During Print

## Problem Statement

When Home Assistant restarts during an active 3D print job, the `sensor.print_weight` attributes are lost. These attributes contain per-tray filament usage data (e.g., "AMS 1 Tray 1: 25g") that is essential for the print completion automation to update Spoolman with correct filament usage.

### Why This Happens

1. **Home Assistant Limitation**: Sensor attributes are not persisted to the database by default
2. **Integration Behavior**: The ha_bambulab integration populates print_weight attributes from MQTT messages during an active print
3. **State Loss**: When HA restarts, the integration has no print data to populate, so attributes remain empty
4. **Timing Issue**: The print_finished event fires with empty attributes, causing the automation to fail

### Root Cause

This is a known limitation documented in:
- This repository: [docs/features/spoolman_sync/docs/print_complete_update_filament_usage.md](print_complete_update_filament_usage.md) (line 20)
- Upstream issue: https://github.com/greghesp/ha-bambulab/issues/1048

## Solution Architecture

The solution uses a **backup and restore** mechanism with validation:

```
Print Starts → Backup Attributes → HA Restart (optional) → Print Ends → Use Backup if Needed
```

### Components

1. **Input Helpers** (`print_weight_persistence.yaml`)
   - `input_text.print_weight_backup`: Stores JSON of print_weight attributes
   - `input_text.print_metadata_backup`: Stores validation data (task name, start time, total weight)

2. **Print Started Automation** (`print_started-backup_print_weight.yaml`)
   - Triggers when print starts
   - Captures and stores print_weight sensor attributes
   - Stores metadata for validation

3. **Enhanced Print Complete Automation** (`print_complete-update_filament_usage.yaml`)
   - Triggers when print finishes
   - Checks if current sensor has attributes
   - Falls back to backup if attributes are missing
   - Validates data integrity
   - Updates Spoolman with filament usage
   - Clears backup after successful processing

4. **Template Sensor** (`print_weight_persistence.yaml`)
   - Provides easy access to backup status
   - Exposes metadata for troubleshooting

## Data Flow

### Normal Operation (No HA Restart)

```
1. Print Starts
   ↓
2. Backup attributes captured
   ↓
3. Print runs normally
   ↓
4. Print Finishes
   ↓
5. Use current sensor (has attributes)
   ↓
6. Update Spoolman
   ↓
7. Clear backup
```

### HA Restart During Print

```
1. Print Starts
   ↓
2. Backup attributes captured
   ↓
3. HA Restarts (attributes lost)
   ↓
4. Print continues
   ↓
5. Print Finishes
   ↓
6. Current sensor empty → Use backup
   ↓
7. Update Spoolman
   ↓
8. Clear backup
```

## Validation Logic

The solution includes multiple validation checks:

1. **Attribute Presence Check**: Verifies if current sensor has any tray attributes
2. **Backup Availability Check**: Ensures backup exists before using it
3. **Data Integrity**: Backup includes metadata (task name, timestamp, total weight)
4. **Weight Validation**: Only processes trays with weight > 0
5. **Entity Validation**: Skips empty tray names

## Installation

### Step 1: Add Input Helpers

Copy `print_weight_persistence.yaml` into a logical location inside your Home
Assistant `/config` directory and register it as a **package**.

**Recommended path:**

```
/config/packages/bambulab/print_weight_persistence.yaml
```

Add the following to `configuration.yaml` (create the `homeassistant.packages`
section if it does not already exist):

```yaml
homeassistant:
  packages:
    bambulab_print_weight: !include packages/bambulab/print_weight_persistence.yaml
```

> **Why packages?**  `print_weight_persistence.yaml` defines two top-level
> sections — `input_text:` **and** `template:`.  Using
> `input_text: !include ...` or `template: !include ...` directly would
> nest the file's own section keys inside the wrong parent key and will not work.
> The `homeassistant.packages` mechanism is the correct way to include a file
> that spans more than one integration domain.

> **Other helpers already in configuration.yaml?**  The packages mechanism is
> additive — it merges cleanly with any existing `input_text:` or other
> sections you have defined elsewhere.  No changes to those sections are needed.

### Step 2: Add Print Started Automation

Import `print_started-backup_print_weight.yaml`:
1. Go to Settings → Automations & Scenes
2. Click "Import Automation"
3. Paste the YAML contents
4. Update the `device_id` to match your printer

### Step 3: Replace Print Complete Automation

**Option A: Replace Existing** (Recommended)
1. Disable your current print_complete automation
2. Import `print_complete-update_filament_usage.yaml`
3. Update the `device_id` to match your printer
4. Test thoroughly before deleting old automation

**Option B: Run Both** (Testing)
1. Keep existing automation
2. Import v2 with a different name
3. Disable the old one once v2 is validated

### Step 4: Restart Home Assistant

```bash
# Restart to load input helpers and template sensors
ha core restart
```

## Configuration Notes

### Device ID

Both automations use `device_id` for the Bambu Lab printer. Find yours:

1. Go to Developer Tools → States
2. Search for your printer entities
3. Look for the device_id in the entity details
4. Update both YAML files with your device_id

### Printer Entity Names

The automations reference specific entity IDs. Update these to match your setup:

- `sensor.ntk_ryansoffice_3dprinter_print_weight`
- `sensor.ntk_ryansoffice_3dprinter_task_name`
- `sensor.p1s_01p00c460102350_ams_[N]_tray_[SLOT]` (e.g., `..._ams_1_tray_1`, `..._ams_2_tray_3`)
- `sensor.ntk_ryansoffice_3dprinter_external_spool`

Search and replace with your printer's entity prefix.

## Testing

### Test 1: Normal Print (No Restart)

1. Start a print
2. Check `input_text.print_weight_backup` has data
3. Let print complete normally
4. Verify Spoolman updated correctly
5. Verify backup was cleared

### Test 2: HA Restart During Print

1. Start a print
2. Verify backup was created
3. Restart Home Assistant
4. Verify sensor attributes are empty
5. Let print complete
6. Verify automation used backup data
7. Verify Spoolman updated correctly

### Test 3: Multi-Filament Print

1. Start a multi-color print (multiple AMS trays)
2. Restart HA mid-print
3. Verify all trays are processed correctly
4. Verify each spool in Spoolman was updated

## Troubleshooting

### Backup Not Created

**Symptoms**: `input_text.print_weight_backup` is empty after print starts

**Solutions**:
1. Check print_started automation is enabled
2. Verify device_id matches your printer
3. Check Home Assistant logs for errors
4. Increase the 5-second delay if sensor not ready

### Attributes Still Missing

**Symptoms**: Both current sensor and backup are empty

**Solutions**:
1. Verify print_started automation triggered
2. Check if print_weight sensor exists and has data
3. Review logbook for backup messages
4. Check input_text size limits (increase max if needed)

### Wrong Filament Updated

**Symptoms**: Spoolman updated wrong spool

**Solutions**:
1. This is a `find_matching_spool` issue, not backup issue
2. Verify tray UUIDs match spool UUIDs in Spoolman
3. Check color matching logic
4. Review find_matching_spool script logs

### Backup Not Cleared

**Symptoms**: Old backup data persists

**Solutions**:
1. Manual clear: Set input_text.print_weight_backup to empty
2. Check if automation completed successfully
3. Review logs for errors in clearing step

## Error Handling

The solution includes comprehensive error handling:

### Missing Attributes
- Logs which data source is being used
- Falls back gracefully to backup
- Fails safely if neither available

### Missing Spools
- Creates persistent notification
- Logs detailed error to system log
- Continues processing other trays

### Runout/Swap UUID Missing Guard
- If an AMS tray UUID is missing at print completion (common after mid-print runout or spool swap), the print-complete automation skips automatic decrement for that tray.
- A user-visible notification and logs explain the skip reason so manual recovery can be performed safely.
- This fail-safe applies even when backup data is available, to avoid decrementing the wrong spool.

### Invalid Data
- Validates weight > 0
- Skips empty tray names
- Checks entity ID validity

## Logging

All operations are logged to help with troubleshooting:

### Backup Operations
- "Print Weight Backup": When attributes are stored
- "Print Weight Backup Cleared": When backup is cleaned up

### Processing
- "Print Weight Data Source": Which data source is used
- "Print Weight Processing": How many trays found
- "Spoolman [Tray Name]": Per-tray update results

### Errors
- System log warnings for spool not found
- Persistent notifications for user visibility

## Monitoring

### Check Backup Status

```yaml
# Template sensor
sensor.print_weight_data_status
  state: "stored" | "empty"
  attributes:
    task_name: "3DBenchy.3mf"
    print_start_time: "2024-01-15T10:30:00"
    total_weight: "25"
```

### Check Backup Data

Developer Tools → States → `input_text.print_weight_backup`

Example stored data:
```json
{
  "AMS 1 Tray 1": 15,
  "AMS 1 Tray 3": 10
}
```

## Advanced Usage

### Adjust Delay

If print_weight sensor needs more time to populate:

```yaml
# In print_started-backup_print_weight.yaml
- delay:
    seconds: 10  # Increase from 5 to 10
```

### Add More Metadata

Store additional validation data:

```yaml
# Add to metadata backup
value: >
  {{ states('sensor.task_name') }}|{{ now().isoformat() }}|{{ states('sensor.print_weight') }}|{{ states('sensor.print_length') }}
```

### Custom Notifications

Add notification to print_started automation:

```yaml
- action: notify.mobile_app
  data:
    message: "Print started, backup created"
```

## Limitations

1. **Single Printer**: Currently configured for one printer
2. **AMS Only**: External spool support included but not extensively tested
3. **Storage Size**: Input text limited to 1024 characters (sufficient for most prints)
4. **No History**: Only stores most recent print data

## Future Enhancements

Possible improvements:

1. **Multiple Prints**: Queue multiple backups
2. **Database Storage**: Use recorder for long-term storage
3. **Automatic Cleanup**: Age-out old backups
4. **Web UI**: Display backup status in dashboard
5. **Upstream Fix**: Contribute to ha_bambulab for native persistence

## Related Documentation

- [Print Complete - Update Filament Usage](print_complete_update_filament_usage.md)
- [Find Matching Spool](find_matching_spools.md)
- [Spoolman Sync README](../README.md)

## References

- GitHub Issue: https://github.com/greghesp/ha-bambulab/issues/1048
- ha_bambulab Integration: https://github.com/greghesp/ha-bambulab
- pyBambu Library: https://github.com/greghesp/pybambu


