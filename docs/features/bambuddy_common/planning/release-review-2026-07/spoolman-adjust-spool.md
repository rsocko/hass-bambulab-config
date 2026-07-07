# Spoolman Adjust Spool / Measured Weight — API & Coordination Spec

## Feature Summary

Spoolman v0.23.0 adds:
1. **"Adjust Spool" button** in the UI — allows users to manually adjust a spool's remaining weight
2. **"Measured Weight" option** — users can enter an actual measured weight (e.g., from a scale) rather than relying on calculated remaining weight

## Current State in Our Config

We have extensive automatic spool usage tracking:

### Automatic Usage Updates (print completion)

`spoolman_sync/automations/print_complete-update_filament_usage.yaml`:
- Triggered on print finish/fail/idle
- Reads `sensor.ntk_ryansoffice_3dprinter_print_weight` attributes per AMS tray
- Calculates usage per spool from tray weight data
- PATCHes Spoolman to subtract used weight from remaining

### Spool PATCH Commands

`spoolman_sync/rest_commands/spoolman_patch_spool_extra.yaml`:
- PATCHes spool extra fields (metadata)

### Tray-Spool Assignment

Multiple automations handle AMS tray ↔ Spoolman spool binding:
- `active_tray_changed_update_spoolman.yaml`
- `spool_location_change_assign_tray.yaml`
- `clear_manual_spool_override_on_tray_change.yaml`

## API Changes in Spoolman 0.23.x

### What Changed

The Spoolman REST API likely now supports:

```
PATCH /api/v1/spool/{id}
{
  "remaining_weight": 750.0,        // existing field
  "measured_weight": 750.0,         // NEW: actual scale reading
  "weight_adjustment_source": "measured"  // NEW: how weight was set
}
```

Or possibly a dedicated endpoint:

```
POST /api/v1/spool/{id}/adjust
{
  "new_weight": 750.0,
  "method": "measured" | "manual" | "calculated"
}
```

### What Did NOT Change

- `GET /api/v1/spool` — still returns spools with `remaining_weight` ✓
- `PATCH /api/v1/spool/{id}` with `used_weight` delta — still supported ✓
- Our `spoolman_getspools.yaml` REST command is unaffected ✓

## Risk: Conflicting Weight Updates

### Scenario

1. User weighs a spool on a scale → enters 680g in Spoolman UI ("Adjust Spool")
2. Shortly after, our automation fires `print_complete-update_filament_usage`
3. Automation subtracts 15g from what it thinks `remaining_weight` was (old cached value)
4. Result: Weight goes from user's accurate 680g to incorrect value

### Mitigation Strategies

**Strategy A: Use Delta-Based Updates Only (Current Approach)**

Our current automation uses `used_weight` (a delta/subtraction), not absolute `remaining_weight`. If Spoolman correctly applies deltas against current server state:

```
# Our PATCH request (conceptual):
PATCH /api/v1/spool/42
{ "used_weight": 15.2 }   # Subtract this from current remaining
```

This is **safe** — regardless of what the user adjusted to, we subtract the correct delta. The user's manual adjustment and our automatic subtraction compose correctly.

**Strategy B: Read-Before-Write (if using absolute weight)**

If our automation writes absolute `remaining_weight`:
1. Read current weight from Spoolman
2. Subtract usage
3. Write new absolute weight

This has a race condition window but is better than using cached values.

**Strategy C: Event-Driven Sync**

Listen for Spoolman websocket events to detect manual adjustments and update our cached sensor data before computing deltas.

## Verification Needed

1. [ ] **Confirm our PATCH uses delta (`used_weight`) vs absolute (`remaining_weight`)**
   - Review the actual PATCH payload in the print-complete automation
   - If delta-based → no risk
   - If absolute → needs coordination logic

2. [ ] **Test the "Adjust Spool" API call** — what does it actually send?
   - Does it set `remaining_weight` directly?
   - Does it create an audit trail / event?

3. [ ] **Check for new API fields** in `GET /api/v1/spool/{id}` response:
   - `last_adjusted_at`?
   - `adjustment_method`?
   - `measured_weight`?
   - These could help us detect recent manual adjustments

## Opportunities

### Leverage Measured Weight

If we add a filament scale (many exist as ESPHome projects):

```yaml
sensor:
  - platform: esphome
    name: "Filament Scale Weight"

automation:
  - alias: "Sync Scale Weight to Spoolman"
    trigger:
      - platform: state
        entity_id: sensor.filament_scale_weight
        for: minutes: 5  # Debounce
    action:
      - service: rest_command.spoolman_adjust_spool_weight
        data:
          spool_id: "{{ current_spool_id }}"
          measured_weight: "{{ states('sensor.filament_scale_weight') | float }}"
```

### Surface Adjustment History

If Spoolman tracks adjustment events, we could show in our dashboard:
- "Last manual adjustment: 2 days ago (680g measured)"
- Warning if calculated weight diverges significantly from last measured weight

## Recommendations

1. **Verify our update mechanism is delta-based** (it likely is, given the `print_weight` sensor approach). If so, no conflict risk.
2. **Don't duplicate the "Adjust Spool" UI in HA** — let users do that in Spoolman's native UI (now PWA-capable).
3. **Consider adding a "weight confidence" indicator** — if time since last measured weight exceeds a threshold, show "estimated" vs "verified" in our dashboard.
4. **Future**: A filament scale integration could auto-call the new measured-weight API, giving us ground-truth data continuously.

## Affected Files

- `homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/rest_commands/spoolman_patch_spool_extra.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/template_sensors/` (various weight-related sensors)
