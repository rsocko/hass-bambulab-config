# Printer LED — Interior Light Auto-Reset Automations

## Overview

The `printer_led` package includes three optional automations that automatically reset the MagWLED interior light to bright white based on printer state changes. These are shipped **disabled** (commented out in the loader) so they don't interfere with custom WLED effects or other lighting workflows.

## Included Automations

| # | Automation ID | Trigger | Behavior |
|---|---|---|---|
| 1 | `interior_light_reset_on_door_open` | Door sensor opens | Resets light to white when the printer door opens — only when the printer is **not** actively printing. Requires a door sensor (or manual event trigger for testing). |
| 2 | `interior_light_reset_after_print_complete` | Print status → `finish` | Waits 10 seconds (for the completion animation), then resets to white so you can inspect the model. |
| 3 | `interior_light_reset_on_idle` | Print status → `idle` | Resets to white only when transitioning from `failed`, `paused`, or `pause` — clears error (red) or pause (yellow) indicator colors. |

All three call `script.reset_interior_light_to_white` (defined in the same package).

## How to Enable

1. Open `homeassistant/packages/3d_printing/printer_led/printer_led_loader.yaml`
2. Uncomment the automation include line:

   ```yaml
   automation: !include automations/printer_led_automations.yaml
   ```

3. Reload automations (Developer Tools → YAML → Reload Automations) or restart Home Assistant.
4. Verify the automations appear in Settings → Automations & Scenes.

## Customization

### Door sensor trigger (Automation 1)

The door-open automation ships with a **manual event trigger** (`interior_light_door_open_manual_trigger`) for testing. To use a real door sensor:

1. Open `automations/printer_led_automations.yaml`
2. Comment out the `platform: event` trigger
3. Uncomment the `platform: state` trigger and set your door sensor entity:

   ```yaml
   trigger:
     - platform: state
       entity_id: binary_sensor.bambu_printer_door
       to: "on"   # or "open" depending on your sensor
   ```

### Time-of-day guard

Each automation can optionally restrict to certain hours. Uncomment the time condition block in the YAML:

```yaml
- condition: time
  after: "07:00:00"
  before: "23:00:00"
```

### Entity IDs

The automations reference:
- `sensor.ntk_ryansoffice_3dprinter_print_status` — Bambu Lab print status sensor

Replace with your printer's entity ID if different.

## File Location

```
homeassistant/packages/3d_printing/printer_led/
├── printer_led_loader.yaml                       # Package loader (automation line commented out)
└── automations/
    └── printer_led_automations.yaml              # The 3 automations described above
```

## Related Docs

- [README.md](README.md) — Printer LED package overview
- [customization-examples.md](customization-examples.md) — Additional automation ideas and light presets

