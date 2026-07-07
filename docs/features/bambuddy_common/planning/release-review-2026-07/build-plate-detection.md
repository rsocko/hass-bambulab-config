# Build Plate Detection — Spec

## Feature Summary

Bambuddy v0.1.6+ detects which build plate is installed on the printer. The v0.2.x branch refines this with UI feedback ("Plate 2 of 5 — Generating G-code") and integrates plate info into the queue scheduler/dispatcher.

## Current State in Our Config

We have **no build plate tracking** today. Our print history archives, print queue, and automations are plate-unaware.

## Where This Data Lives

### In Bambuddy

- **Archive records**: Each archive likely now includes a `plate_type` or `build_plate` field (e.g., "Cool Plate", "Engineering Plate", "High Temp Plate", "Textured PEI").
- **Printer status API**: `/api/v1/printers/{id}/status` may expose `current_plate` alongside existing `nozzle_temp`, `bed_temp`, etc.
- **Queue entries**: Queue jobs can be assigned to specific plate types.

### Proposed HASS Entities

| Entity | Type | Purpose |
|--------|------|---------|
| `sensor.3dprinter_current_build_plate` | Template sensor | Derived from Bambuddy printer status or Bambu Lab integration |
| `input_select.3dprinter_installed_plate` | Input select | Manual override / fallback if auto-detection is unavailable |
| `sensor.3dprinter_plate_print_count` | Template sensor | Track prints per plate for maintenance alerts |

### Storage Options

**Option A: Bambuddy-sourced (Recommended)**

Pull plate info from the Bambuddy printer status REST sensor we already poll every 30s:

```yaml
# In bambuddy/sensors.yaml — extend json_attributes for Printer Status
json_attributes:
  - status
  - current_print
  - maintenance
  - error
  - nozzle_temp
  - bed_temp
  - chamber_temp
  - print_progress
  - time_remaining_minutes
  - fan_speed
  - filament
  - build_plate          # <-- NEW
  - build_plate_type     # <-- NEW
```

Then derive a template sensor:

```yaml
sensor:
  - platform: template
    sensors:
      bambuddy_current_build_plate:
        friendly_name: "Current Build Plate"
        value_template: >-
          {{ state_attr('sensor.bambuddy_printer_status', 'build_plate_type')
             | default('Unknown') }}
        icon_template: mdi:tray-full
```

**Option B: Bambu Lab Integration Direct**

The Bambu Lab HASS integration may expose plate detection as a sensor directly. Check for `sensor.*_build_plate` entities after upgrading the HA integration.

**Option C: Hybrid**

Use Bambu Lab integration for real-time plate detection, store it in a helper for use in automations, and enrich Bambuddy archives with plate info during the `bambuddy_enrich_archive_on_complete` automation.

## Integration Points

### Print History Enrichment

Extend `bambuddy_enrich_archive_on_complete` to PATCH the build plate onto the archive:

```yaml
- action: rest_command.bambuddy_patch_archive
  data:
    archive_id: "{{ archive_id }}"
    payload:
      build_plate: "{{ states('sensor.3dprinter_current_build_plate') }}"
```

### Print Queue

If we adopt Bambuddy's queue scheduler, plate-type filtering becomes available — only dispatch jobs compatible with the currently installed plate.

### Maintenance Tracking

Track plate wear:
- Count prints per plate type via a counter or utility_meter
- Alert when a plate exceeds N prints without cleaning/replacement
- Could integrate with `printer_maintenance` package

## Recommended Approach

1. **Phase 1**: Add `build_plate` / `build_plate_type` to existing Bambuddy printer status `json_attributes`. Create a template sensor. No new entities needed beyond that.
2. **Phase 2**: Enrich print history archives with plate info at completion time.
3. **Phase 3**: Add plate-based maintenance counters if we find the data useful after a few weeks.

## Open Questions

- [ ] Does the Bambuddy API actually expose `build_plate` in the printer status response, or only in archives?
- [ ] Does the Bambu Lab HA integration provide a native plate sensor?
- [ ] What are the exact plate type string values? (Need API response samples)

## Dependencies

- Bambuddy v0.1.6+ (stable) or v0.2.x (beta)
- Possible: updated Bambu Lab HA custom integration
