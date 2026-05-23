# System Logging in Spoolman Sync Automations

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/system-logging.md
Replaced By: none


## Overview

The Spoolman Sync automations now include persistent system logging using Home Assistant's `system_log.write` service. This provides durable log retention that persists across Home Assistant restarts, unlike notifications which are cleared on reboot.

## Why System Logging?

**Problem:** Previously, the automations only used `persistent_notification.create` for status messages. These notifications:
- Are cleared when Home Assistant restarts
- Don't provide complete error context
- Aren't searchable in system logs
- Don't integrate with logging infrastructure

**Solution:** System logging provides:
- ✅ Persistent storage that survives HA restarts
- ✅ Complete error messages with full context
- ✅ Standard log levels (info, warning, error)
- ✅ Integration with Home Assistant's logging system
- ✅ Searchable and filterable logs

## Log Levels Used

### INFO Level
Used for successful operations:
- Filament usage successfully updated
- Spool last used time updated
- UUID updates in Spoolman

### WARNING Level
Used for non-critical issues:
- No matching spool found (may be expected in some cases)

### ERROR Level
Used for critical failures:
- Multiple spools with same UUID (data integrity issue)
- Cannot determine which spool to use (ambiguous matches)
- Failed to update filament usage

## Logger Name

All system log messages use the logger name:
```
homeassistant.components.bambulab.spoolman_sync
```

This allows you to filter logs specifically for Bambu Lab Spoolman sync operations.

## Log Messages by Automation

> Current architecture note: runtime matching in automations uses the shared
> resolver script `resolve_matching_spool_from_tray_map` (fed by
> `sensor.spoolman_tray_map`).

### Active Tray Changed (`active_tray_changed_update_spoolman.yaml`)

**Success Messages (INFO):**
- "Active Tray Changed: Successfully updated Spoolman last used for Spool ID {id} ({name}). Active Tray: {tray}, UUID: {uuid}"
- "Active Tray Changed: Updated UUID in Spoolman for Spool ID {id} with UUID {uuid}"

**Error Messages (ERROR):**
- "Active Tray Changed ERROR: Cannot find spool in Spoolman. Active Tray: {tray}, UUID: {uuid}, Type: {type}, Color: {color}. Error: {message}"

### Print Complete (`print_complete-update_filament_usage.yaml`)

**Success Messages (INFO):**
- "Print Complete: Successfully updated filament usage in Spoolman for {tray}. Task: {task_name}. Spool ID {id} ({name}). Used {weight} grams."

**Error Messages (ERROR):**
- "Print Complete ERROR: Cannot find spool in Spoolman for {tray}. Task: {task_name}. UUID: {uuid}, Type: {type}, Color: {color}. Used {weight} grams. Error: {message}"

### Legacy Comparator Script (`find_matching_spool_in_spoolman-script.yaml`)

This script is retained for validation/diagnostic comparison, not as the primary
runtime matching path for print-complete or active-tray automations.

**Warning Messages (WARNING):**
- "Find Matching Spool: No spools found. Target Type: {type}, Color: {color}, Name: {name}"

**Error Messages (ERROR):**
- "Find Matching Spool ERROR: Multiple spools ({count}) have the same UUID {uuid}. This is a data integrity issue that needs to be resolved."
- "Find Matching Spool ERROR: Multiple spools ({count}) found in the AMS with matching criteria. Type: {type}, Color: {color}, Name: {name}. Cannot determine which spool to use."
- "Find Matching Spool ERROR: Multiple spools ({count}) found with matching criteria, none in AMS. Either multiple are open/unsealed ({unsealed_count}) or none are open. Type: {type}, Color: {color}, Name: {name}. Cannot determine which spool to use."

## Viewing Logs

### Home Assistant UI
1. Go to **Settings** → **System** → **Logs**
2. Search for "bambulab.spoolman_sync"
3. Filter by log level (Info, Warning, Error)

### Configuration.yaml
To see these logs at a specific level, add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    homeassistant.components.bambulab.spoolman_sync: debug
```

### Log Files
Logs are written to `home-assistant.log` in your Home Assistant configuration directory.

## Benefits

1. **Troubleshooting**: Complete error context helps diagnose issues without needing to reproduce them
2. **Monitoring**: Track successful operations to verify automations are working
3. **Auditing**: Historical record of all filament updates and spool changes
4. **Persistence**: Logs survive Home Assistant restarts
5. **Integration**: Works with external log aggregation tools

## Example Log Output

```
2026-02-17 16:30:45 INFO (MainThread) [homeassistant.components.bambulab.spoolman_sync] Active Tray Changed: Successfully updated Spoolman last used for Spool ID 42 (Bambu PLA Basic Red). Active Tray: AMS 1 Tray 3, UUID: a1b2c3d4e5f6

2026-02-17 17:15:22 INFO (MainThread) [homeassistant.components.bambulab.spoolman_sync] Print Complete: Successfully updated filament usage in Spoolman for AMS 1 Tray 1. Task: test_print.3mf. Spool ID 15 (Polymaker PolyLite PLA). Used 125 grams.

2026-02-17 18:45:33 ERROR (MainThread) [homeassistant.components.bambulab.spoolman_sync] Find Matching Spool ERROR: Multiple spools (3) found in the AMS with matching criteria. Type: PLA, Color: 3F8E43, Name: Bambu PLA Basic. Cannot determine which spool to use.
```

## Backwards Compatibility

All existing notification messages remain in place. System logging is **additive** - it provides an additional, more persistent logging layer without removing the existing user-facing notifications.
