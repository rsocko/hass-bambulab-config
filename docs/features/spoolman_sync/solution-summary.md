# Solution Summary: Print Weight Persistence for HA Restarts

## Problem Solved

**Issue**: When Home Assistant restarts during an active 3D print job, the print_weight sensor attributes (containing per-tray filament usage) are lost, causing the print completion automation to fail updating Spoolman.

**Root Cause**: Home Assistant does not persist sensor attributes by default. The ha_bambulab integration populates these from MQTT during active prints, but has no data to restore after a restart.

## Solution Overview

A **backup and restore mechanism** that:
1. Captures print_weight attributes when print starts
2. Stores them in input helpers (survives restarts)
3. Uses backup data if sensor is empty when print finishes
4. Updates Spoolman correctly in both scenarios

## What's Included

### Configuration Files
- **spoolman_sync_loader.yaml** - Package loader for automations, scripts, helpers, and template sensors
- **print_started-backup_print_weight.yaml** - Captures attributes on print start
- **print_complete-update_filament_usage.yaml** - Enhanced automation with backup support

### Documentation
- **print-weight-persistence.md** - Complete documentation (9,500+ words)
- **print-weight-persistence-quickstart.md** - Quick start guide
- **print-weight-persistence-visual.md** - Visual flow diagrams
- **print-weight-persistence-implementation.md** - Implementation summary

### Updates
- **README.md** - Updated with solution links and known issues section

## Installation (Quick)

1. Enable package loading via `homeassistant.packages`
2. Import two automations (print_started and print_complete)
3. Update device_id and entity names
4. Restart Home Assistant
5. Test with a print

See [Quick Start Guide](print-weight-persistence-quickstart.md) for detailed steps.

## Key Features

✅ **Transparent** - Works automatically, no user intervention needed  
✅ **Resilient** - Survives HA restarts during prints  
✅ **Validated** - Includes metadata checks for data integrity  
✅ **Fault-tolerant** - Graceful error handling and logging  
✅ **Compatible** - Doesn't modify existing automations  
✅ **Reversible** - Can be disabled and rolled back  
✅ **Well-documented** - Comprehensive guides and visual diagrams  

## How It Works

```
Normal Operation:
Print Starts → Backup Created → Print Finishes → Use Current Data → Update Spoolman

With HA Restart:
Print Starts → Backup Created → HA Restarts → Print Finishes → Use Backup Data → Update Spoolman
```

The automation automatically detects which scenario it's in and uses the appropriate data source.

## What Gets Backed Up

**Print Weight Attributes**:
```json
{
  "AMS 1 Tray 1": 15,
  "AMS 1 Tray 3": 10
}
```

**Metadata** (for validation):
```
"3DBenchy.3mf|2024-01-15T10:30:00|25"
```

Both are stored in input helpers that survive HA restarts.

## Testing

### Test 1: Normal Operation
1. Start a print
2. Verify backup created
3. Let print complete
4. Verify Spoolman updated
5. Verify backup cleared

### Test 2: HA Restart (Main Scenario)
1. Start a print
2. Restart Home Assistant
3. Let print complete
4. Verify backup was used
5. Verify Spoolman updated correctly

## Monitoring

**Check Status**: Developer Tools → States → `sensor.print_weight_data_status`

**View Logs**: Logbook → Search for:
- "Print Weight Backup"
- "Print Weight Data Source"
- "Print Weight Processing"

**Check Backup**: Developer Tools → States → `input_text.print_weight_backup`

## Error Handling

The solution handles:
- Missing attributes (uses backup)
- Missing backup (logs error)
- Missing spools (notifies user, continues)
- Invalid data (skips, logs warning)
- Zero weights (skips tray)

## Limitations

1. **Single Print**: Only stores most recent print
2. **Storage Size**: Limited to 255 characters for `input_text` helpers
3. **Single Printer**: Configured for one printer (easily extensible)

## Future Enhancements

Possible improvements:
- Multi-print queue
- Database storage for history
- Dashboard widget
- Multi-AMS support
- Automatic backup cleanup

## Support & Resources

- **Full Documentation**: [print-weight-persistence.md](print-weight-persistence.md)
- **Quick Start**: [print-weight-persistence-quickstart.md](print-weight-persistence-quickstart.md)
- **Visual Diagrams**: [print-weight-persistence-visual.md](print-weight-persistence-visual.md)
- **Implementation Details**: [print-weight-persistence-implementation.md](print-weight-persistence-implementation.md)
- **Upstream Issue**: https://github.com/greghesp/ha-bambulab/issues/1048

## Success Criteria

✅ Solution prevents data loss on HA restart  
✅ Works with both scenarios (restart and no restart)  
✅ All trays processed correctly  
✅ Spoolman updated accurately  
✅ Errors handled gracefully  
✅ Comprehensive logging  
✅ Complete documentation  
✅ Easy to install and test  

## Migration Path

**From Existing Automation**:
1. Keep existing automation enabled
2. Install new enhanced automation (disabled)
3. Test thoroughly
4. Switch when confident
5. Backup old automation before removing

**Rollback**:
1. Disable enhanced automation
2. Re-enable original
3. Clear input helpers
4. No restart needed

## Version History

- **v2.0.0** (2026-02-17) - Print Weight Persistence solution added
- **v1.0.0** (2025-05-23) - Initial release

## Conclusion

This solution provides a robust workaround for the print_weight attribute loss issue until upstream integration adds native persistence. It's:

- **Production-ready**: Comprehensive error handling and logging
- **User-friendly**: Transparent operation with clear documentation
- **Maintainable**: Well-documented code and architecture
- **Extensible**: Can be enhanced with additional features

The solution has been designed to be minimal, surgical, and non-invasive while providing maximum reliability for the critical use case of updating Spoolman filament usage after print completion.

---

**Ready to Install?** Start with the [Quick Start Guide](print-weight-persistence-quickstart.md)!

