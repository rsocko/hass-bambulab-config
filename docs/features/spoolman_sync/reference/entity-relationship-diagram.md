# Spoolman Sync Entity Relationship Diagram

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/entity-relationship-diagram.md
Replaced By: none

This document models the core runtime entities and relationships for the `spoolman_sync` feature. It focuses on operational contracts used by automations, helpers, and Spoolman API writes.

## ER Diagram

```mermaid
erDiagram
    PRINTER_EVENT {
        string event_id
        string event_type
        datetime occurred_at
        string task_name
    }

    AUTOMATION_RUN {
        string run_id
        string automation_id
        datetime started_at
        string trigger_id
        string result_state
    }

    PRINT_JOB_CONTEXT {
        string task_name
        datetime print_started_at
        number total_weight_g
        string archive_id
    }

    TRAY_USAGE_SNAPSHOT {
        string snapshot_id
        datetime captured_at
        string source_entity
        string tray_json
    }

    TRAY_MAP_MATCH {
        string tray_key
        string match_tier
        string match_state
        number candidate_count
        bool pin_applied
    }

    SPOOLMAN_SPOOL {
        number spool_id
        string filament_name
        string vendor_name
        string spool_uuid
        string location
    }

    SPOOL_USAGE_WRITE {
        string write_id
        datetime written_at
        number spool_id
        number used_weight_g
        string write_source
    }

    SYNC_ERROR_RECORD {
        string error_id
        datetime error_at
        string tray_name
        string error_message
        number print_weight_g
        string tray_uuid
        string tray_color
        string tray_type
    }

    ERROR_LOG_STORAGE {
        string storage_id
        datetime updated_at
        string log_payload
    }

    MANUAL_RECOVERY_ACTION {
        string recovery_id
        datetime recovered_at
        number target_spool_id
        number recovered_weight_g
        string status
    }

    PRINTER_EVENT ||--o{ AUTOMATION_RUN : triggers
    AUTOMATION_RUN ||--|| PRINT_JOB_CONTEXT : resolves_context
    AUTOMATION_RUN ||--o| TRAY_USAGE_SNAPSHOT : reads_or_restores
    AUTOMATION_RUN ||--o{ TRAY_MAP_MATCH : evaluates
    TRAY_MAP_MATCH }o--|| SPOOLMAN_SPOOL : selects
    AUTOMATION_RUN ||--o{ SPOOL_USAGE_WRITE : emits
    SPOOLMAN_SPOOL ||--o{ SPOOL_USAGE_WRITE : receives_usage

    AUTOMATION_RUN ||--o{ SYNC_ERROR_RECORD : emits_on_failure
    SYNC_ERROR_RECORD }o--|| ERROR_LOG_STORAGE : appended_to
    SYNC_ERROR_RECORD ||--o{ MANUAL_RECOVERY_ACTION : resolved_by
    MANUAL_RECOVERY_ACTION }o--|| SPOOLMAN_SPOOL : applies_to
```

## Runtime Notes

- `PRINT_JOB_CONTEXT` and `TRAY_USAGE_SNAPSHOT` are restart-safe state anchors used to survive Home Assistant restarts during active prints.
- `TRAY_MAP_MATCH` is authoritative for spool resolution in production paths (`sensor.spoolman_tray_map` + resolver script).
- `SYNC_ERROR_RECORD` is the handoff contract for manual recovery and persistent notification payloads.
- `SPOOL_USAGE_WRITE` is the final side-effect boundary to Spoolman.

## Orchestration View

```mermaid
flowchart TD
    E[Printer Event] --> A[Automation Run]
    A --> C[Resolve Print Job Context]
    C --> B{Current print-weight attributes available?}
    B -- Yes --> U[Use current tray usage]
    B -- No --> R[Use backup snapshot]
    U --> M[Resolve tray_map match]
    R --> M
    M --> F{Matched spool?}
    F -- Yes --> W[Write usage to Spoolman]
    F -- No --> X[Persist sync error + log]
    X --> Y[Manual recovery action]
    Y --> W
```
