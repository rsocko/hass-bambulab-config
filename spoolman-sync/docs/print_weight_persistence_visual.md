# Print Weight Persistence - Visual Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BAMBU LAB PRINTER + MQTT                              │
│                                                                               │
│  ┌─────────────┐      ┌──────────────┐      ┌─────────────┐                │
│  │   Printer   │ MQTT │  pyBambu     │ MQTT │ ha_bambulab │                │
│  │   Hardware  │◄────►│   Library    │◄────►│ Integration │                │
│  └─────────────┘      └──────────────┘      └──────┬──────┘                │
│                                                      │                        │
└──────────────────────────────────────────────────────┼────────────────────────┘
                                                       │
                                                       │ Events & Sensors
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        HOME ASSISTANT                                        │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────┐          │
│  │                    SENSORS                                     │          │
│  │                                                                 │          │
│  │  ┌────────────────────────────────────────────────────────┐   │          │
│  │  │ sensor.print_weight                                     │   │          │
│  │  │   state: "25" (total grams)                            │   │          │
│  │  │   attributes:                                          │   │          │
│  │  │     "AMS 1 Tray 1": 15                                │   │          │
│  │  │     "AMS 1 Tray 3": 10                                │   │          │
│  │  │   ⚠️ LOST ON HA RESTART ⚠️                             │   │          │
│  │  └────────────────────────────────────────────────────────┘   │          │
│  │                                                                 │          │
│  │  sensor.task_name                                              │          │
│  │  sensor.ams_1_tray_1 (uuid, type, color)                      │          │
│  │  sensor.active_tray_index                                      │          │
│  └───────────────────────────────────────────────────────────────┘          │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────┐          │
│  │              PERSISTENCE LAYER (NEW)                          │          │
│  │                                                                 │          │
│  │  ┌────────────────────────────────────────────────────────┐   │          │
│  │  │ input_text.print_weight_backup                         │   │          │
│  │  │   Max: 1024 chars                                      │   │          │
│  │  │   Value: JSON of attributes                            │   │          │
│  │  │   Example: {"AMS 1 Tray 1": 15, "AMS 1 Tray 3": 10}  │   │          │
│  │  │   ✅ SURVIVES HA RESTART ✅                             │   │          │
│  │  └────────────────────────────────────────────────────────┘   │          │
│  │                                                                 │          │
│  │  ┌────────────────────────────────────────────────────────┐   │          │
│  │  │ input_text.print_metadata_backup                       │   │          │
│  │  │   Max: 255 chars                                       │   │          │
│  │  │   Value: "task|timestamp|total_weight"                 │   │          │
│  │  │   Example: "3DBenchy.3mf|2024-01-15T10:30:00|25"     │   │          │
│  │  │   ✅ SURVIVES HA RESTART ✅                             │   │          │
│  │  └────────────────────────────────────────────────────────┘   │          │
│  │                                                                 │          │
│  │  ┌────────────────────────────────────────────────────────┐   │          │
│  │  │ sensor.print_weight_data_status (template)             │   │          │
│  │  │   state: "stored" | "empty"                            │   │          │
│  │  │   attributes:                                          │   │          │
│  │  │     task_name, print_start_time, total_weight         │   │          │
│  │  └────────────────────────────────────────────────────────┘   │          │
│  └───────────────────────────────────────────────────────────────┘          │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow - Normal Operation (No HA Restart)

```
┌──────────────┐
│ Print Starts │
│   (Event)    │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Automation: Print Started - Backup Print Weight     │
│                                                      │
│ Trigger: event_print_started                        │
│                                                      │
│ Actions:                                            │
│  1. Wait 5 seconds                                  │
│  2. Read sensor.print_weight.attributes             │
│  3. Store as JSON → input_text.print_weight_backup  │
│  4. Store metadata → input_text.print_metadata...   │
│  5. Log "Print Weight Backup"                       │
└──────┬──────────────────────────────────────────────┘
       │
       │                ┌─────────────────┐
       │                │  Print Running  │
       │                │   (5-60 mins)   │
       │                └────────┬────────┘
       │                         │
       ▼                         ▼
┌─────────────────────────────────────────────────────┐
│         Input Helpers Store Backup                   │
│                                                      │
│  input_text.print_weight_backup =                   │
│    {"AMS 1 Tray 1": 15, "AMS 1 Tray 3": 10}       │
│                                                      │
│  input_text.print_metadata_backup =                 │
│    "3DBenchy.3mf|2024-01-15T10:30:00|25"          │
└──────┬──────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│Print Finished│
│   (Event)    │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Automation: Print Complete - Enhanced               │
│                                                      │
│ Trigger: event_print_finished                       │
│                                                      │
│ Logic:                                              │
│  1. Check sensor.print_weight has attributes?       │
│     ✅ YES - Use current sensor data                │
│  2. Extract tray usage                              │
│  3. For each tray:                                  │
│     - Find spool in Spoolman                        │
│     - Update usage                                  │
│     - Log result                                    │
│  4. Clear backup                                    │
└──────┬──────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│              SPOOLMAN UPDATED ✅                     │
│                                                      │
│  Spool #123 (PLA Red) - Used 15g                   │
│  Spool #456 (PETG Black) - Used 10g                │
│                                                      │
│  Backup cleared: input_text helpers empty           │
└─────────────────────────────────────────────────────┘
```

## Data Flow - HA Restart During Print

```
┌──────────────┐
│ Print Starts │
│   (Event)    │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Automation: Print Started - Backup Print Weight     │
│                                                      │
│ Actions:                                            │
│  1. Wait 5 seconds                                  │
│  2. Read sensor.print_weight.attributes             │
│  3. Store as JSON → input_text.print_weight_backup  │
│  4. Store metadata → input_text.print_metadata...   │
│  5. Log "Print Weight Backup"                       │
└──────┬──────────────────────────────────────────────┘
       │
       │        ┌───────────────┐
       │        │ Print Running │
       │        │   (10 mins)   │
       │        └───────┬───────┘
       │                │
       ▼                ▼
┌─────────────────────────────────────────────────────┐
│         Backup Stored in Input Helpers               │
│                                                      │
│  {"AMS 1 Tray 1": 15, "AMS 1 Tray 3": 10}         │
└──────┬──────────────────────────────────────────────┘
       │
       │        ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️
       │        ⚠️  HOME ASSISTANT RESTARTS  ⚠️
       │        ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️ ⚠️
       │
       ▼
┌─────────────────────────────────────────────────────┐
│         After Restart - State Analysis               │
│                                                      │
│  sensor.print_weight.attributes = {} (EMPTY!) ❌    │
│                                                      │
│  input_text.print_weight_backup = {...} ✅          │
│    {"AMS 1 Tray 1": 15, "AMS 1 Tray 3": 10}       │
│    (SURVIVED RESTART!)                              │
│                                                      │
│  input_text.print_metadata_backup = {...} ✅        │
│    "3DBenchy.3mf|2024-01-15T10:30:00|25"          │
└──────┬──────────────────────────────────────────────┘
       │
       │        ┌──────────────┐
       │        │Print Continues│
       │        │  (40 mins)   │
       │        └──────┬───────┘
       │               │
       ▼               ▼
┌──────────────┐
│Print Finished│
│   (Event)    │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Automation: Print Complete - Enhanced               │
│                                                      │
│ Logic:                                              │
│  1. Check sensor.print_weight has attributes?       │
│     ❌ NO - Attributes empty!                        │
│  2. Check backup available?                         │
│     ✅ YES - Backup exists!                          │
│  3. Use backup data (from_json)                     │
│  4. Log "Will use backup data"                      │
│  5. Extract tray usage from backup                  │
│  6. For each tray:                                  │
│     - Find spool in Spoolman                        │
│     - Update usage                                  │
│     - Log result                                    │
│  7. Clear backup                                    │
└──────┬──────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│           SPOOLMAN UPDATED ✅                        │
│                                                      │
│  Spool #123 (PLA Red) - Used 15g                   │
│  Spool #456 (PETG Black) - Used 10g                │
│                                                      │
│  Data source: BACKUP (not current sensor)           │
│  Backup cleared: ready for next print               │
└─────────────────────────────────────────────────────┘
```

## Decision Logic

```
                     ┌──────────────────┐
                     │ Print Finished   │
                     │    Event         │
                     └────────┬─────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │ Check Current Sensor │
                   │   Has Attributes?    │
                   └──────────┬───────────┘
                              │
                 ┌────────────┴────────────┐
                 │                         │
                YES                       NO
                 │                         │
                 ▼                         ▼
    ┌─────────────────────┐   ┌─────────────────────┐
    │ Use Current Sensor  │   │ Check Backup Exists │
    │      Data           │   └──────────┬──────────┘
    └──────────┬──────────┘              │
               │            ┌─────────────┴─────────────┐
               │           YES                         NO
               │            │                           │
               │            ▼                           ▼
               │  ┌─────────────────────┐   ┌─────────────────────┐
               │  │  Use Backup Data    │   │    ERROR:           │
               │  │  (from_json)        │   │  No Data Available  │
               │  └──────────┬──────────┘   │  Send Notification  │
               │             │               └─────────────────────┘
               │             │
               └─────────┬───┘
                         │
                         ▼
              ┌────────────────────────┐
              │  Process Each Tray     │
              │  Update Spoolman       │
              │  Log Results           │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Clear Backup Data     │
              │  Ready for Next Print  │
              └────────────────────────┘
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────┐
│          Print Complete Automation                   │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
  ┌─────────┐ ┌────────┐ ┌────────┐
  │ Tray 1  │ │ Tray 2 │ │ Tray 3 │
  │  15g    │ │  0g    │ │  10g   │
  └────┬────┘ └───┬────┘ └────┬───┘
       │          │           │
       ▼          ▼           ▼
  ┌──────────────────────────────────────┐
  │ For Each Tray: Validation Checks     │
  │                                       │
  │ 1. Weight > 0?                       │
  │    ❌ NO → SKIP tray                  │
  │    ✅ YES → Continue                  │
  │                                       │
  │ 2. Tray name not empty?              │
  │    ❌ NO → SKIP tray                  │
  │    ✅ YES → Continue                  │
  └──────────────┬───────────────────────┘
                 │
                 ▼
  ┌──────────────────────────────────────┐
  │   Find Matching Spool in Spoolman    │
  └──────────────┬───────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
    FOUND             NOT FOUND
        │                 │
        ▼                 ▼
  ┌───────────────┐ ┌──────────────────────┐
  │ Update Spool  │ │ Persistent Notify    │
  │ Log Success   │ │ System Log Warning   │
  │ Continue      │ │ Continue Next Tray   │
  └───────────────┘ └──────────────────────┘
```

## Monitoring Points

```
Developer Tools → States
  │
  ├─► sensor.print_weight_data_status
  │     state: "stored" | "empty"
  │     attributes:
  │       - task_name
  │       - print_start_time  
  │       - total_weight
  │
  ├─► input_text.print_weight_backup
  │     Current backup JSON
  │
  └─► input_text.print_metadata_backup
        Current metadata string

Developer Tools → Logbook
  │
  ├─► "Print Weight Backup" (backup created)
  ├─► "Print Weight Data Source" (which source used)
  ├─► "Print Weight Processing" (trays found)
  ├─► "Spoolman [Tray]" (per-tray results)
  └─► "Print Weight Backup Cleared" (cleanup)

Notifications
  │
  ├─► Print completion success
  └─► Spoolman errors
```

## Legend

```
✅ = Success / Working
❌ = Failed / Not Working  
⚠️ = Warning / Caution
→ = Data Flow
▼ = Process Flow
├─► = Tree Branch
```
