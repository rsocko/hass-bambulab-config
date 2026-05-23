# Example Error Notification

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/notification-example.md
Replaced By: none


This is what users will see when a Spoolman sync error occurs.

## Notification Example

**Title:**
```
Spoolman Update Error: Cannot Find Spool
```

**Message:**
```
**Print Job:** BentoBox_v2_Print

**Tray:** AMS 1 Tray 2

**Print Weight:** 45 grams

**Error:** No spools found by Color & Type


**Tray Details for Manual Recovery:**

- UUID: `00000000000000000000000000000000`

- Color: `FF5733`

- Type: `PLA`


To manually update Spoolman, find the matching spool and reduce its weight by 45g.

Error details stored in `input_text.spoolman_sync_last_error` for recovery.
```

## Notification Properties

- **Persistent**: Requires manual dismissal
- **Unique ID**: One per tray (e.g., `spoolman_sync_error_AMS_1_Tray_2`)
- **Location**: Home Assistant notifications panel (bell icon)
- **Markdown**: Supports formatting for readability

## What Users See in Home Assistant UI

```
┌──────────────────────────────────────────────────────────────┐
│ 🔔 Notifications (1)                                          │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ⚠️ Spoolman Update Error: Cannot Find Spool                  │
│                                                                │
│ Print Job: BentoBox_v2_Print                                   │
│                                                                │
│ Tray: AMS 1 Tray 2                                             │
│                                                                │
│ Print Weight: 45 grams                                         │
│                                                                │
│ Error: No spools found by Color & Type                        │
│                                                                │
│                                                                │
│ Tray Details for Manual Recovery:                             │
│                                                                │
│ • UUID: 00000000000000000000000000000000                      │
│                                                                │
│ • Color: FF5733                                                │
│                                                                │
│ • Type: PLA                                                    │
│                                                                │
│                                                                │
│ To manually update Spoolman, find the matching spool and      │
│ reduce its weight by 45g.                                      │
│                                                                │
│ Error details stored in input_text.spoolman_sync_last_error   │
│ for recovery.                                                  │
│                                                                │
│                                                [Dismiss]        │
└──────────────────────────────────────────────────────────────┘
```

## Error Types and Messages

### 1. No Spools Found
```
Error: No spools found by Color & Type
```
**Cause**: No spool in Spoolman matches the tray's color and material type.

### 2. Multiple Spools Found
```
Error: Multiple spools found by Color & Type, none in AMS and more than 1 open OR none open
```
**Cause**: Multiple spools match but system can't determine which was used.

### 3. Duplicate UUIDs
```
Error: Multiple spools have the same matching UUID
```
**Cause**: More than one spool in Spoolman has the same UUID.

### 4. Multiple in AMS
```
Error: Multiple spools found by Color & Type, but more than 1 is in the AMS
```
**Cause**: Multiple matching spools are marked with location "AMS".

## User Actions After Seeing Notification

1. **Note the Details**: Copy UUID, color, type from notification
2. **Open Spoolman**: Navigate to Spoolman web UI
3. **Search for Spool**: Use details to find the matching spool
   - Search by UUID (if not all zeros)
   - Filter by color hex code
   - Filter by material type
4. **Note Spool ID**: From Spoolman, note the spool's ID number
5. **Open Home Assistant**: Go to Developer Tools → Services
6. **Call Script**: 
   - Service: `script.manual_spoolman_recovery`
   - Parameter: `spool_id: [ID from Spoolman]`
7. **Verify**: Check Spoolman that weight was reduced
8. **Done**: Notification can be dismissed

## Logbook Entry Example

In addition to the notification, users see in their logbook:

```
┌──────────────────────────────────────────────────────────────┐
│ 📖 Logbook                                                     │
└──────────────────────────────────────────────────────────────┘

🔴 Spoolman Sync Error
Failed to update filament usage for AMS 1 Tray 2 after print 
"BentoBox_v2_Print". Weight: 45g. Error: No spools found by 
Color & Type

2026-02-17 4:30:45 PM
```

## Developer Tools State View

Users can also view the raw error data:

```
Entity: input_text.spoolman_sync_last_error
State: 2026-02-17T16:30:45.123456|AMS 1 Tray 2|No spools found by Color & Type|45|00000000000000000000000000000000|FF5733|PLA

Entity: input_boolean.spoolman_sync_error_active
State: on

Entity: input_datetime.spoolman_sync_last_error_time
State: 2026-02-17 16:30:45
```

## Dashboard Card Example

Optional dashboard card users can add:

```
┌──────────────────────────────────────────────────────────────┐
│ ⚠️ Spoolman Sync Error - Action Required                     │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│ Last Error: Feb 17, 2026 at 04:30 PM                          │
│                                                                │
│ Tray: AMS 1 Tray 2                                             │
│ Error: No spools found by Color & Type                        │
│ Weight: 45g                                                    │
│                                                                │
│ Tray Details:                                                  │
│ • UUID: 00000000000000000000000000000000                      │
│ • Color: FF5733                                                │
│ • Type: PLA                                                    │
│                                                                │
│ [View Notifications] [Run Recovery Script]                    │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

## Success Notification Example

After running manual recovery script:

**Title:**
```
Manual Recovery Successful
```

**Message:**
```
Successfully updated spool 123 with 45g usage from AMS 1 Tray 2.

Original error from 2026-02-17T16:30:45.123456 has been resolved.
```

## Benefits of This Notification Design

✅ **All Info Included**: Everything needed for recovery in one place  
✅ **Copy-Paste Ready**: UUID, color, type formatted for easy copying  
✅ **Clear Instructions**: Step-by-step guidance for recovery  
✅ **Persistent**: Won't disappear until manually dismissed  
✅ **Unique IDs**: Multiple errors don't overwrite each other  
✅ **Markdown Formatting**: Easy to read with bold/bullets/code blocks  

## Accessibility

- Screen readers will announce the notification
- Markdown formatting provides visual hierarchy
- Clear, concise language
- Actionable instructions
- References to stored data for later reference

---

This notification design ensures users have everything they need to manually recover from sync errors without losing any data.
