# Smart Printer Status Mapping

> **Full reference**: See [SMART_STATUS.md](SMART_STATUS.md) for the complete stage mapping table, Bambuddy consistency analysis, and future-proofing details.

This repo now provides a reusable merged printer status sensor:

- `sensor.ntk_ryansoffice_3dprinter_smart_status`

Defined in [homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml), it combines:

- `sensor.ntk_ryansoffice_3dprinter_print_status` (ha_bambulab `gcode_state`)
- `sensor.ntk_ryansoffice_3dprinter_current_stage` (ha_bambulab stage description)

into one clean state (for example: `Printing`, `Preparing Print`, `Bed Leveling`, `Print Finished`, `Paused - Filament Runout`).

## Attributes

- `detail`: contextual detail string
  - Shows friendly stage detail while preparing/printing
  - Shows `Unmapped: status="...", stage="..."` for unknown combinations
- `status_raw`: raw `print_status` value
- `stage_raw`: raw `current_stage` value
- `status_class`: normalized class for UI/automation
  - `printing`, `preparing`, `paused`, `finished`, `failed`, `heating`, `leveling`, `idle`, `offline`, `unknown`, `unmapped`
- `is_active`: `true` when actively printing/preparing

## Reuse in Dashboards

Use this directly in cards:

- Entity: `sensor.ntk_ryansoffice_3dprinter_smart_status`
- Primary text: sensor state
- Secondary text: `state_attr('sensor.ntk_ryansoffice_3dprinter_smart_status', 'detail')`
- Icon/color logic: `status_class`

## Alert on Unmapped Values

Use this automation to catch newly introduced integration values:

```yaml
alias: Printer Smart Status - Unmapped Alert
mode: single
trigger:
  - platform: state
    entity_id: sensor.ntk_ryansoffice_3dprinter_smart_status
    to: "Unmapped Printer State"
condition: []
action:
  - service: persistent_notification.create
    data:
      title: "Unmapped Printer Status Detected"
      message: >-
        {{ state_attr('sensor.ntk_ryansoffice_3dprinter_smart_status', 'detail') }}
```

Or use the ready-made file in this repo:

- [homeassistant/packages/3d_printing/core/dashboard_cards/smart-status-unmapped-alert.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/smart-status-unmapped-alert.yaml)

It includes:

- a 30s debounce before alerting
- persistent notification updates while unmapped values change
- system log + logbook entry for troubleshooting
- automatic dismiss when state returns to mapped

If you use split-package automations, include/import that file from your Home Assistant automation configuration.

## For Additional Printers

Duplicate this template sensor block and replace the source entities:

- `sensor.<printer>_print_status`
- `sensor.<printer>_current_stage`

Then point cards/automations to the new `<printer>_smart_status` sensor.




