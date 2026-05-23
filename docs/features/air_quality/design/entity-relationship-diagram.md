# Air Quality Entity Relationship Diagram

This document models the core entities and control relationships for the `air_quality` feature, including sensor ingestion, threshold evaluation, purifier control, Bento Box fan control, and filter tracking.

## ER Diagram

```mermaid
erDiagram
    AQ_SENSOR_READING {
        string reading_id
        datetime observed_at
        number pm25
        number co2
        number voc
        number temperature
        number humidity
    }

    AQ_THRESHOLD_POLICY {
        string policy_id
        number pm25_warn
        number co2_warn
        number voc_warn
        string severity_model
    }

    AQ_STATUS_EVALUATION {
        string evaluation_id
        datetime evaluated_at
        string aq_status
        string dominant_factor
    }

    PRINT_ACTIVITY_CONTEXT {
        string context_id
        string print_state
        string filament_type
        datetime updated_at
    }

    PURIFIER_COMMAND {
        string command_id
        datetime commanded_at
        bool power_on
        number speed_level
        string mode
        string reason
    }

    BENTO_FAN_COMMAND {
        string command_id
        datetime commanded_at
        number fan_percent
        string reason
    }

    FILTER_RUNTIME_COUNTER {
        string counter_id
        datetime updated_at
        number hepa_hours
        number carbon_hours
        bool tracking_enabled
    }

    FILTER_HEALTH_STATUS {
        string status_id
        datetime computed_at
        number hepa_usage_pct
        number carbon_usage_pct
        string overall_status
    }

    ALERT_EVENT {
        string alert_id
        datetime emitted_at
        string alert_type
        string severity
        string message
    }

    AQ_SENSOR_READING ||--o{ AQ_STATUS_EVALUATION : evaluated_into
    AQ_THRESHOLD_POLICY ||--o{ AQ_STATUS_EVALUATION : applies_rules
    PRINT_ACTIVITY_CONTEXT ||--o{ AQ_STATUS_EVALUATION : contextualizes

    AQ_STATUS_EVALUATION ||--o{ PURIFIER_COMMAND : drives
    AQ_STATUS_EVALUATION ||--o{ BENTO_FAN_COMMAND : drives
    PRINT_ACTIVITY_CONTEXT ||--o{ BENTO_FAN_COMMAND : adjusts_for_filament

    BENTO_FAN_COMMAND ||--o{ FILTER_RUNTIME_COUNTER : accrues_runtime
    FILTER_RUNTIME_COUNTER ||--o{ FILTER_HEALTH_STATUS : computes
    FILTER_HEALTH_STATUS ||--o{ ALERT_EVENT : emits_replacement_alert

    AQ_STATUS_EVALUATION ||--o{ ALERT_EVENT : emits_air_quality_alert
```

## Runtime Notes

- `AQ_STATUS_EVALUATION` is the decision boundary that converts raw sensor values and print context into actuator commands.
- `PRINT_ACTIVITY_CONTEXT` enables filament-aware fan behavior and post-print runtime windows.
- `FILTER_RUNTIME_COUNTER` and `FILTER_HEALTH_STATUS` provide maintenance state separate from real-time air quality control.

## Control Flow View

```mermaid
flowchart TD
    S[Air sensor reading] --> V[Evaluate thresholds]
    P[Print state or filament change] --> V
    V --> Q{Air quality status}
    Q --> C1[Set purifier mode and speed]
    Q --> C2[Set Bento fan speed]
    C2 --> R[Accumulate runtime hours]
    R --> H[Compute filter health]
    H --> A{Needs alert?}
    A -- Yes --> N[Notify replacement needed]
    A -- No --> K[No maintenance alert]
```
