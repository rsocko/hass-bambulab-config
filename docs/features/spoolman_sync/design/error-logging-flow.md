# Error Logging Flow Diagram

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/error-logging-flow.md
Replaced By: none

## Print Job Flow with Error Handling

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRINT JOB LIFECYCLE                             │
└─────────────────────────────────────────────────────────────────────────┘

   Print Started Event
          │
          ▼
   ┌──────────────────────────────────┐
   │  Capture Print Data Automation   │
   │  (print_started-capture_print_   │
   │         data.yaml)                │
   └──────────────────────────────────┘
          │
          ├─► Store print job name & timestamp
          │   (input_text.print_job_current)
          │
                                   └─► Store AMS tray configuration (all 4 trays)
                                                 (sensor.print_job_ams_tray_storage attribute `data`)
              - UUID, Color, Type, Name for each tray

          │
          │ ... Print in progress ...
          │
          ▼
   Print Finished Event
          │
          ▼
   ┌──────────────────────────────────┐
   │ Print Complete Automation        │
   │ (print_complete-update_filament_ │
   │        usage.yaml)                │
   └──────────────────────────────────┘
          │
          ├─► For each AMS tray used:
          │   Extract tray data (UUID, color, type)
          │
          ├─► Call shared resolver script
          │   (resolve_matching_spool_from_tray_map)
          │
          ▼
   ┌──────────────────────────────────┐
   │    Spool Found?                  │
   └──────────────────────────────────┘
          │
          ├─YES─► Update Spoolman ✓
          │       └─► Log success
          │           └─► Persistent notification (success)
          │
          └─NO──► ERROR HANDLING PATH
                  │
                  ▼
           ┌────────────────────────────────────────┐
           │       Persistent Error Storage          │
           └────────────────────────────────────────┘
                  │
                  ├─► Store error details:
                  │   - Timestamp
                  │   - Tray name
                  │   - Error message
                  │   - Print weight
                  │   - Tray UUID/color/type
                  │   (input_text.spoolman_sync_last_error)
                  │
                  ├─► Set error flag
                  │   (input_boolean.spoolman_sync_error_active = ON)
                  │
                  ├─► Update error timestamp
                  │   (input_datetime.spoolman_sync_last_error_time)
                  │
                  ├─► Append to error log (last ~10)
                  │   (sensor.spoolman_sync_error_log_storage attribute `log`)
                  │
                  ├─► Log to logbook
                  │
                  └─► Create persistent notification with:
                      - Print job name
                      - Tray details
                      - Print weight
                      - Recovery instructions
                      - Tray UUID/color/type for manual lookup


┌─────────────────────────────────────────────────────────────────────────┐
│                        MANUAL RECOVERY FLOW                             │
└─────────────────────────────────────────────────────────────────────────┘

   User sees error notification
          │
          ▼
   User finds matching spool in Spoolman UI
   (using UUID, color, type from notification)
          │
          ▼
   User notes the Spoolman spool ID
          │
          ▼
   ┌──────────────────────────────────┐
   │  Manual Recovery Script          │
   │  (manual_spoolman_recovery-      │
   │        script.yaml)               │
   └──────────────────────────────────┘
          │
          ├─► Parse stored error data
          │   (input_text.spoolman_sync_last_error)
          │
          ├─► Validate spool ID provided
          │
          ├─► Call spoolman.use_spool_filament
          │   with stored print weight
          │
          ├─► Log success to logbook
          │
          ├─► Clear error flag
          │   (input_boolean.spoolman_sync_error_active = OFF)
          │
          └─► Show success notification ✓


┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA PERSISTENCE                                 │
└─────────────────────────────────────────────────────────────────────────┘

Input Helpers (survive HA restart):

┌───────────────────────────────────────────────────────────────────┐
│  input_text.print_job_current                                     │
│  Format: "task_name|start_time"                                   │
│  Example: "BentoBox_Print|2026-02-17T16:30:00"                    │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  sensor.print_job_ams_tray_storage (attribute: data)              │
│  Format: JSON array                                               │
│  [{"tray":1,"uuid":"abc...","color":"FF5733","type":"PLA",...}]   │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  input_text.spoolman_sync_last_error                              │
│  Format: "timestamp|tray|error|weight|uuid|color|type"            │
│  Example: "2026-02-17T...|AMS 1 Tray 2|No spools found|45|..."    │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  sensor.spoolman_sync_error_log_storage (attribute: log)          │
│  Format: Multiple lines, one error per line                       │
│  Keeps last ~10 errors for historical tracking                    │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  input_boolean.spoolman_sync_error_active                         │
│  Flag: ON = unresolved error, OFF = no errors                     │
│  Can be used in dashboard conditions or automations               │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  input_datetime.spoolman_sync_last_error_time                     │
│  Timestamp of most recent error                                   │
│  Can be displayed on dashboard or used in templates               │
└───────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────┐
│                         ERROR SCENARIOS                                  │
└─────────────────────────────────────────────────────────────────────────┘

1. "No spools found by Color & Type"
   ├─ Cause: No spool in Spoolman matches tray color and material
   └─ Resolution: Add spool to Spoolman, then run manual recovery

2. "Multiple spools found by Color & Type"
   ├─ Cause: Multiple spools match, system can't determine which was used
   └─ Resolution: Set unique UUID or move unused spools, then manual recovery

3. "Multiple spools have the same UUID"
   ├─ Cause: Duplicate UUIDs in Spoolman
   └─ Resolution: Fix duplicate UUIDs in Spoolman, then manual recovery

4. "Spool in use but not in AMS location"
   ├─ Cause: Matching spool exists but location != "AMS"
   └─ Resolution: Update spool location in Spoolman, or run manual recovery
```

## Benefits of This System

1. **No Lost Data**: Print weight information is never lost, even if automation fails
2. **Actionable Errors**: Notifications include all data needed for manual recovery
3. **Historical Tracking**: Error log provides insight into recurring issues
4. **Easy Recovery**: Single script call to apply stored error data
5. **Dashboard Integration**: Error flag can trigger dashboard warnings
6. **Survives Restarts**: All data persists across Home Assistant restarts

## Error Prevention Tips

- Keep Spoolman location field updated ("AMS" for active spools)
- Set UUID on Bambu Lab spools in Spoolman extra fields
- Avoid duplicate color+type combinations (or set unique UUIDs)
- Archive old/unused spools to reduce false matches
- Regularly review error log to identify patterns
