# Persistent Error Logging for Spoolman Sync

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/persistent-error-logging.md
Replaced By: none

## Overview
This system provides persistent storage and logging of print job data and spoolman sync errors. When the automatic spoolman sync fails (e.g., spool not found), the system stores all necessary information for manual recovery.

## Components

### 1. Input Helpers (`spoolman_sync_loader.yaml`)

These helpers store persistent data that survives Home Assistant restarts:

- **`input_text.print_job_current`**: Current/last print job name and start time
- **`input_text.print_job_external_spool`**: External spool snapshot at print start
- **`input_text.spoolman_sync_last_error`**: Most recent sync error with all recovery details
- **`input_boolean.spoolman_sync_error_active`**: Flag indicating unresolved errors
- **`input_datetime.spoolman_sync_last_error_time`**: Timestamp of last error

Template-sensor storage used by automations:
- **`sensor.print_job_ams_tray_storage`**: AMS tray JSON stored in the `data` attribute
- **`sensor.spoolman_sync_error_log_storage`**: Rolling error log stored in the `log` attribute

### 2. Print Started Automation (`print_started-capture_print_data.yaml`)

**Trigger:** When a print job starts (`event_print_started`)

**Actions:**
1. Captures print job name and start time
2. Records AMS tray configuration for all 4 trays (UUID, color, type, name)
3. Captures external spool data using transition-safe detection logic
4. Stores data in input helpers for later reference

**External spool transition safety:**
- Treats external spool as active only when both conditions are true:
   - `active_tray == "none"`
   - `sensor.<printer>_external_spool` attribute `active` is `true`
- This avoids false positives during brief AMS tray-switch transition windows.

This ensures critical data is captured before the print completes, when entities might change.

### 3. Enhanced Print Complete Automation

**Modifications to `print_complete-update_filament_usage.yaml`:**

When spool lookup fails (`find_spool_response.success == false`):
1. Stores comprehensive error details in `input_text.spoolman_sync_last_error`:
   - Timestamp
   - Tray name
   - Error message
   - Print weight
   - Tray UUID, color, and type
2. Sets error flag (`input_boolean.spoolman_sync_error_active`)
3. Updates error timestamp
4. Appends to error log
5. Creates logbook entry
6. Shows detailed persistent notification with recovery instructions

### 4. Enhanced Active Tray Changed Automation

**Modifications to `active_tray_changed_update_spoolman.yaml`:**

Transition-safe behavior:
1. Treats `active_tray == "none"` as External Spool only when external spool is explicitly active
2. Skips spool matching during transient AMS transition states (`none` + external inactive)
3. Skips spool matching when tray data is incomplete

When spool lookup fails after valid matching input:
1. Logs error to logbook
2. Creates detailed persistent notification with tray information

### 5. Manual Recovery Script (`manual_spoolman_recovery-script.yaml`)

Allows users to manually apply stored error data to update Spoolman.

**Usage:**
1. Review the error details in the persistent notification or `input_text.spoolman_sync_last_error`
2. Manually find the matching spool in Spoolman (use UUID, color, type as search criteria)
3. Run the script with the spool ID as parameter
4. The script will apply the stored print weight to the spool

## Error Data Format

### Last Error (`input_text.spoolman_sync_last_error`)
Format: `timestamp|tray_name|error_message|print_weight|tray_uuid|tray_color|tray_type`

Example:
```
2026-02-17T16:30:45.123456|AMS 1 Tray 2|No spools found by Color & Type|45|abc123def456|FF5733|PLA
```

### Error Log (`sensor.spoolman_sync_error_log_storage` attribute `log`)
Multiple entries, one per line, same format as above. Keeps last ~10 errors.

### AMS Tray Data (`sensor.print_job_ams_tray_storage` attribute `data`)
JSON array format:
```json
[
  {
    "tray": 1,
    "uuid": "abc123def456",
    "color": "FF5733",
    "type": "PLA",
    "name": "Bambu PLA Basic"
  },
  ...
]
```

## Manual Recovery Process

### When You See an Error Notification:

1. **Identify the Problem**
   - Review the persistent notification details
   - Note the tray UUID, color, and type
   - Note the print weight that needs to be deducted

2. **Find the Spool in Spoolman**
   - Open Spoolman UI
   - Search for spools matching:
     - UUID (if available and not all zeros)
     - Color hex code
     - Material type (e.g., PLA)
   - Identify which spool was actually used

3. **Run Manual Recovery**
   - In Home Assistant, go to Developer Tools → Services
   - Call service: `script.manual_spoolman_recovery`
   - Provide the Spoolman spool ID as parameter
   - The script will apply the stored print weight

4. **Verify Success**
   - Check Spoolman to confirm weight was reduced
   - Error flag will be cleared automatically
   - Success notification will be shown

### Preventing Future Errors

Common causes and solutions:

1. **"No spools found by Color & Type"**
   - Ensure spool exists in Spoolman with matching color and material
   - Check that color hex codes match exactly
   - Verify spool is not archived

2. **"Multiple spools found"**
   - Set UUID on Bambu Lab spool in Spoolman extra fields
   - Move unused spools to different location (not "AMS")
   - Ensure only one matching spool is unsealed/open

3. **"Multiple spools have the same UUID"**
   - Fix duplicate UUIDs in Spoolman
   - Each spool should have unique UUID or no UUID

## Dashboard Integration (Optional)

You can add a card to your dashboard to show error status:

```yaml
type: conditional
conditions:
  - entity: input_boolean.spoolman_sync_error_active
    state: "on"
card:
  type: markdown
  content: |
    ## ⚠️ Spoolman Sync Error
    
    **Last Error:** {{ states('input_datetime.spoolman_sync_last_error_time') }}
    
    **Details:** {{ states('input_text.spoolman_sync_last_error').split('|')[1:3] | join(' - ') }}
    
    Check notifications for recovery instructions.
```

## Logbook Entries

All errors are also logged to the Home Assistant logbook for historical tracking:
- Search for "Spoolman Sync Error" in logbook
- Entries include tray, weight, and error message
- Useful for identifying patterns or recurring issues

## API Access (Advanced)

Error data can be accessed via Home Assistant REST API or templates:

```jinja2
{# Get last error details #}
{{ states('input_text.spoolman_sync_last_error') }}

{# Check if error is active #}
{{ is_state('input_boolean.spoolman_sync_error_active', 'on') }}

{# Get error log #}
{{ state_attr('sensor.spoolman_sync_error_log_storage', 'log') }}
```

## Troubleshooting

### Error data not being stored
- Verify input helpers are configured in Home Assistant
- Check automation is not in "single" mode blocking
- Review Home Assistant logs for errors

### Can't find matching spool
- Use `sensor.print_job_ams_tray_storage` attribute `data` to see what was in the AMS at print start
- Cross-reference with Spoolman spool list
- Consider if spool was added/removed during print

### Manual recovery doesn't work
- Verify spool ID is correct (check Spoolman UI)
- Ensure spool hasn't been archived
- Check Home Assistant logs for specific error

## Future Enhancements

Potential improvements:
- Notification action buttons for quick recovery
- Automatic retry logic with exponential backoff
- Integration with Home Assistant repairs system (when available for YAML automations)
- Machine learning to suggest matching spools
- Batch recovery for multiple errors
