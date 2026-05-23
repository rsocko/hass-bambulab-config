# Print Weight Persistence Solution - Implementation Summary

Status: Archived
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/print-weight-persistence-implementation.md
Replaced By: none


## Overview

This implementation solves the issue where Home Assistant restarts during an active print job cause the loss of print_weight sensor attributes, preventing the print completion automation from correctly updating Spoolman with filament usage.

## Problem

**Issue**: Restarting HASS during a print fails to update filament usage

**Root Cause**: 
- Home Assistant does not persist sensor attributes by default
- The ha_bambulab integration populates print_weight attributes from MQTT during active prints
- When HA restarts, there's no MQTT data to restore, so attributes are lost
- The print_finished event fires with empty attributes, breaking the automation

**Upstream Status**: 
- Feature request filed: https://github.com/greghesp/ha-bambulab/issues/1048
- Proposes using FTP to reconstruct attributes from slice_info.config
- No implementation timeline available

## Solution Design

### Approach: Backup and Restore Pattern

Instead of waiting for an upstream fix, we implement a local workaround:

1. **Capture**: Store print_weight attributes when the printer is actually `printing`
2. **Persist**: Save in Home Assistant input helpers (survives restarts)
3. **Validate**: Include metadata for data integrity checks
4. **Restore**: Use backup if current sensor has no attributes
5. **Clean**: Clear backup after successful processing

### Architecture

```
┌─────────────────┐
│  Print Started / │
│  Status=Printing │
└────────┬────────┘
         │
         v
┌─────────────────────────────────────┐
│  Capture Print Weight Attributes     │
│  - JSON of all AMS tray weights      │
│  - Metadata (task name, time, total) │
│  - Wait/retry for delayed MQTT attrs │
└────────┬────────────────────────────┘
         │
         v
┌─────────────────────────────────────┐
│  Store in Input Helpers              │
│  - input_text.print_weight_backup    │
│  - input_text.print_metadata_backup  │
└─────────────────────────────────────┘
         │
         │  ┌──────────────────┐
         │  │  HA Restarts?    │
         │  │  (Optional)      │
         │  └──────────────────┘
         │
         v
┌─────────────────┐
│  Print Finished │
│     Event       │
└────────┬────────┘
         │
         v
┌─────────────────────────────────────┐
│  Check Current Sensor                │
│  Has attributes?                     │
└────────┬────────────────────────────┘
         │
    ┌────┴────┐
    │         │
    v         v
   YES       NO
    │         │
    │         v
    │    ┌─────────────────────┐
    │    │  Use Backup Data    │
    │    └──────────┬──────────┘
    │               │
    └───────┬───────┘
            │
            v
┌─────────────────────────────────────┐
│  Process Each Tray                   │
│  - Find matching spool               │
│  - Update Spoolman                   │
│  - Log results                       │
└────────┬────────────────────────────┘
         │
         v
┌─────────────────────────────────────┐
│  Clear Backup                        │
│  - Empty input helpers               │
│  - Ready for next print              │
└─────────────────────────────────────┘
```

## Implementation Files

### 1. Helper + Template Definitions
**Purpose**: Input helpers and template sensor definitions loaded via `spoolman_sync_loader.yaml`

**Contents**:
- `input_text.print_weight_backup`: Stores JSON of attributes (max 255 chars)
- `input_text.print_metadata_backup`: Stores validation data (max 255 chars)
- `sensor.print_weight_data_status`: Template sensor for monitoring

**Locations**:
- [homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/input_text_print_weight_backup.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/input_text_print_weight_backup.yaml)
- [homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/input_text_print_metadata_backup.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/input_text_print_metadata_backup.yaml)
- [homeassistant/packages/3d_printing/spoolman_sync/template_sensors/template_sensor_print_weight_data_status.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/template_sensors/template_sensor_print_weight_data_status.yaml)

### 2. print_started-backup_print_weight.yaml
**Purpose**: Automation to capture attributes only once print data is ready

**Triggers**:
- `sensor.<printer>_print_status` → `running` (5s stable)
- `event_print_started` fallback, gated by waiting for `print_status=running`

**Actions**:
1. Wait for actual printing state (if triggered early)
2. Wait up to 2 minutes for per-tray weight attributes to populate
3. Final short retry
4. Store attributes as JSON
5. Store metadata (task name, timestamp, total weight)
6. Log backup action and any warnings

**Location**: [homeassistant/packages/3d_printing/spoolman_sync/automations/print_started-backup_print_weight.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_started-backup_print_weight.yaml)

### 3. print_complete-update_filament_usage.yaml
**Purpose**: Enhanced print completion automation with backup support

**Trigger**: `event_print_finished` from Bambu Lab device

**Logic**:
1. Check if current sensor has attributes
2. Check if backup is available
3. Use current data if available, else backup
4. Validate data exists
5. Process each tray (find spool, update usage)
6. Log all operations
7. Clear backup

**Location**: [homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml)

### 4. print-weight-persistence.md
**Purpose**: Complete documentation of the solution

**Sections**:
- Problem statement and root cause
- Solution architecture
- Installation instructions
- Configuration notes
- Testing procedures
- Troubleshooting guide
- Error handling
- Monitoring

**Location**: [docs/features/spoolman_sync/print-weight-persistence.md](../reference/print-weight-persistence-overview.md)

## Key Features

### Data Integrity
- Stores complete attribute dictionary as JSON
- Includes metadata for validation
- Checks data presence before processing
- Rejects backup if metadata task does not match current task
- Rejects backup when numeric total print weights diverge beyond tolerance
- Clears stale backup from a previous task before capturing new print backup

### Fault Tolerance
- Gracefully handles missing data
- Falls back between current and backup
- Continues processing on individual failures
- Logs all operations for debugging

### User Experience
- Transparent operation (works automatically)
- Persistent notifications on errors
- Detailed logging in logbook
- Status sensor for monitoring

### Compatibility
- Works with existing print_complete automation
- Compatible with find_matching_spool script
- Maintains Spoolman integration interface
- No changes to dashboard required

## Validation & Testing

### Test Scenarios

1. **Normal Operation**: Print without HA restart
   - ✅ Backup created after printer reaches `running`
   - ✅ Current sensor used
   - ✅ Backup cleared
   
2. **HA Restart During Print**: Main scenario
   - ✅ Backup survives restart
   - ✅ Backup used when sensor empty
   - ✅ Spoolman updated correctly
   
3. **Multi-Filament Print**: Multiple AMS trays
   - ✅ All trays backed up
   - ✅ All trays processed
   - ✅ Each spool updated

4. **Error Conditions**:
   - ✅ Missing spool in Spoolman
   - ✅ Empty backup
   - ✅ Invalid data

## Logging & Monitoring

### Backup Operations
- Print Weight Backup: Attributes stored
- Print Weight Backup Cleared: Cleanup complete

### Data Processing
- Print Weight Data Source: Which source used
- Print Weight Processing: Number of trays
- Spoolman [Tray]: Per-tray results

### Errors
- System log warnings: Spool not found
- Persistent notifications: User-facing errors

### Status Monitoring
- `sensor.print_weight_data_status`
  - State: "stored" or "empty"
  - Attributes: task_name, start_time, total_weight

## Configuration Requirements

### User Must Update

1. **Device ID**: Match your Bambu Lab printer
2. **Entity Names**: Replace with your printer's entities
   - `sensor.[your_printer]_print_weight`
   - `sensor.[your_printer]_task_name`
   - `sensor.[your_printer]_ams_1_tray_X`
   - `sensor.[your_printer]_external_spool`

### Optional Adjustments

1. **Timeouts**: Increase wait time if your print status or tray MQTT data arrives slowly
2. **Storage Size**: Keep payload compact to stay within `input_text` limits (255)
3. **Notifications**: Add mobile notifications if desired
4. **Metadata**: Add more validation fields

## Limitations

1. **Single Print**: Only stores most recent print
2. **Storage Size**: Limited to input_text max (255 chars)
3. **AMS Configuration**: Assumes AMS 1 (Tray 1-4)
4. **External Spool**: Included but less tested

## Future Enhancements

### Possible Improvements
1. Queue multiple prints (FIFO backup)
2. Database storage for history
3. Dashboard integration
4. Multi-AMS support
5. Automatic cleanup of old backups

### Upstream Contribution
Once validated, could contribute to:
- ha_bambulab integration (native persistence)
- pyBambu library (state recovery)

## Success Criteria

✅ Solution prevents data loss on HA restart  
✅ Automations work with both current and backup data  
✅ All trays processed correctly  
✅ Spoolman updated accurately  
✅ Errors handled gracefully  
✅ Comprehensive logging for troubleshooting  
✅ Documentation complete and clear  

## References

- **Original Issue**: BUG - restarting HASS during a print fails to update filament usage
- **Upstream Issue**: https://github.com/greghesp/ha-bambulab/issues/1048
- **Integration**: https://github.com/greghesp/ha-bambulab
- **Library**: https://github.com/greghesp/pybambu

## Implementation Date
February 2026

## Author Notes

This solution provides a robust workaround until upstream integration adds native attribute persistence. The backup mechanism is transparent, fault-tolerant, and fully reversible. All error conditions are handled gracefully with appropriate logging and user notifications.

The architecture is extensible and can accommodate future enhancements like multi-print queuing or database storage if needed.



