# Home Assistant Automation Examples for WLED Printer Lighting

This document provides example automations for controlling your WLED printer lighting based on Bambu Lab printer states.

For a complete catalog of all lighting scenarios, see [../light-scenarios.md](../light-scenarios.md).
For LED specifications, see [../digquad-led-segments.md](../digquad-led-segments.md).
For zone functions, see [../led-functions.md](../led-functions.md).

## Prerequisites

1. WLED Digquad controller added to Home Assistant
2. Bambu Lab integration installed and configured
3. Presets uploaded to WLED controller (based on light-scenarios.md)

## Entity Names

Adjust these entity names to match your Home Assistant configuration:

- WLED Digquad: `light.digquad` 
- Printer: `sensor.bambu_lab_x1c_*` (replace with your printer name)
- AMS Humidity: Configure if using AMS units with humidity sensors

## Automation Categories

Based on [light-scenarios.md](../light-scenarios.md), automations are organized into:

1. **Print Lifecycle States** - Heating, leveling, printing, paused, finished
2. **Error & Warning States** - Filament issues, temperature errors, door open
3. **AMS Operations** - Loading, unloading, drying, humidity warnings
4. **Maintenance States** - Cooling, cleaning, manual modes
5. **Environmental States** - Temperature warnings, power recovery

## Automation 1: Print Lifecycle - Heating Bed

```yaml
automation:
  - alias: "Printer: WLED Heating Bed"
    description: "Orange pulse when bed is heating (Scenario 2.1)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "heating_bed"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 4  # Preset 4: Heating Bed (orange pulse)
```

## Automation 2: Print Lifecycle - Bed Leveling

```yaml
automation:
  - alias: "Printer: WLED Bed Leveling"
    description: "Blue pulse when leveling (Scenario 2.3)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "auto_bed_leveling"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 6  # Preset 6: Bed Leveling (blue pulse/chase)
```

## Automation 3: Print Lifecycle - Active Printing

```yaml
automation:
  - alias: "Printer: WLED Normal Printing Mode"
    description: "Activate printing mode (Scenario 2.5)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "printing"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 8  # Preset 8: Printing (green status, progress bar, filament colors)
      - service: notify.mobile_app
        data:
          message: "Print started - Lighting activated"
          title: "3D Printer"
```

## Automation 4: Error State - Print Paused (Error)

```yaml
automation:
  - alias: "Printer: WLED Print Error Mode"
    description: "Red strobe when print encounters an error (Scenario 2.7)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_hms_errors
    condition:
      - condition: template
        value_template: >
          {{ trigger.to_state.state not in ['unavailable', 'unknown', '0', 0] }}
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 10  # Preset 10: Print Paused (Error) - red strobe
      - service: notify.mobile_app
        data:
          message: "Print error detected!"
          title: "3D Printer Alert"
```

**Note**: The HMS error entity structure may vary depending on your Bambu Lab integration version. Adjust the entity name and condition to match your setup. Common variations:
- `sensor.bambu_lab_x1c_hms_errors` with state as error count
- `sensor.bambu_lab_x1c_hms` with attributes containing error list
- Check your entity's attributes in Developer Tools to verify the correct structure.

## Automation 5: Error State - Filament Runout

```yaml
automation:
  - alias: "Printer: WLED Filament Runout"
    description: "Red on affected tray (Scenario 3.1)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_ams_tray_status
    condition:
      - condition: template
        value_template: >
          {{ 'runout' in trigger.to_state.state | lower or
             'empty' in trigger.to_state.state | lower }}
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 12  # Preset 12: Filament Runout
      - service: notify.mobile_app
        data:
          message: "Filament runout detected!"
          title: "3D Printer Alert"
```

## Automation 6: Print Lifecycle - Print Complete

```yaml
automation:
  - alias: "Printer: WLED Print Complete"
    description: "Green celebration (Scenario 2.8)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "complete"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 11  # Preset 11: Print Finished (green pulse)
      - delay:
          seconds: 30
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 2  # After celebration, return to idle
```

## Automation 7: Power State - Printer Idle

```yaml
automation:
  - alias: "Printer: WLED Idle Mode"
    description: "Soft blue breathing when idle (Scenario 1.2)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "idle"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 2  # Preset 2: Idle (soft blue breathing)
```

## Automation 8: AMS Operation - Filament Loading

```yaml
automation:
  - alias: "Printer: WLED Filament Loading"
    description: "Blue chase animation (Scenario 4.1)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_ams_status
        to: "loading"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 17  # Preset 17: Filament Loading (blue chase)
```

## Automation 9: AMS Operation - Humidity Warning

```yaml
automation:
  - alias: "Printer: WLED Humidity Warning"
    description: "Red hygrometer when humidity high (Scenario 4.4)"
    trigger:
      - platform: numeric_state
        entity_id: sensor.bambu_lab_ams1_humidity
        above: 60  # Adjust threshold as needed
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 20  # Preset 20: Humidity High (red hygrometer)
```

## Automation 10: Active Tray Highlighting

This automation highlights the active tray/tag based on which AMS tray is in use:

```yaml
automation:
  - alias: "Printer: Highlight Active AMS Tray"
    description: "Highlight currently active tray (Scenarios 4.6-4.7)"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_active_tray
    condition:
      - condition: template
        value_template: "{{ states('sensor.bambu_lab_x1c_active_tray') in ['1', '2', '3', '4', '5', '6', '7', '8'] }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: >
            {% set tray = states('sensor.bambu_lab_x1c_active_tray') | int %}
            {% if tray >= 1 and tray <= 4 %}
              {{ 22 }}  {# Preset 22: Tray Selected (AMS1 trays 1-4) #}
            {% elif tray >= 5 and tray <= 8 %}
              {{ 22 }}  {# Preset 22: Tray Selected (AMS2 trays 5-8) #}
            {% else %}
              8  {# Default to printing #}
            {% endif %}
```

Note: This is a simplified version. For more advanced tray-specific presets, create separate presets for each tray and adjust the logic accordingly.

## Automation 11: Print Progress Bar

Advanced automation to show print progress on the bottom printer segment (LEDs 0-50):

```yaml
automation:
  - alias: "Printer: Update Progress Bar"
    description: "Update LED progress bar based on print percentage"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_print_progress
    condition:
      - condition: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        state: "printing"
    action:
      - service: rest_command.wled_digquad_progress
        data:
          progress: "{{ states('sensor.bambu_lab_x1c_print_progress') | int }}"
```

## REST Command for Progress Bar

Add this to your `configuration.yaml`:

```yaml
rest_command:
  wled_digquad_progress:
    url: "http://digquad.local/json/state"
    method: POST
    content_type: "application/json"
    payload: >
      {
        "seg": [{
          "id": 0,
          "i": [
            0, {{ ((progress | int) * 49 / 100) | int }}, "FF5500",
            {{ ((progress | int) * 49 / 100) | int }}, 49, "000000"
          ]
        }]
      }
```

Note: This uses segment 0 (printer door bottom) with 50 LEDs (range 0-49). The progress bar lights LEDs from 0 to the calculated progress position in orange, and the rest remain off.

## Scenario-Based Automation Summary

Reference [../light-scenarios.md](../light-scenarios.md) for complete scenario details. Key automation mappings:

| Printer State | Scenario # | Preset # | Behavior |
|---------------|------------|----------|----------|
| Offline | 1.1 | 1 | Dim amber |
| Idle | 1.2 | 2 | Soft blue breathing |
| Heating Bed | 2.1 | 4 | Orange pulse |
| Heating Nozzle | 2.2 | 5 | Yellow pulse |
| Bed Leveling | 2.3 | 6 | Blue pulse/chase |
| Purge Line | 2.4 | 7 | Cyan pulse |
| Printing | 2.5 | 8 | Green + progress + filament colors |
| Paused (User) | 2.6 | 9 | Yellow blink |
| Paused (Error) | 2.7 | 10 | Red strobe |
| Print Finished | 2.8 | 11 | Green celebration |
| Filament Runout | 3.1 | 12 | Red on affected tray |
| Filament Jam | 3.2 | 13 | Orange strobe |
| AMS Error | 3.3 | 14 | Purple pulse |
| Temperature Error | 3.4 | 15 | Red strobe |
| Door Open | 3.5 | 16 | Bright white |
| Loading | 4.1 | 17 | Blue chase |
| Unloading | 4.2 | 18 | Teal chase |
| AMS Drying | 4.3 | 19 | Warm amber |
| Humidity High | 4.4 | 20 | Red hygrometer |
| Humidity Normal | 4.5 | 21 | White hygrometer |
| Tray Selected | 4.6 | 22 | Filament color |
| Tray Feeding | 4.7 | 23 | Bright filament color |
| Cooling | 5.1 | 24 | Blue pulse |
| Manual Light | 5.2 | 25 | White on all |

## Tips and Best Practices

### Performance
- Update progress bar every 5-10 seconds, not every second
- Use condition checks to avoid unnecessary updates
- Group multiple actions when possible

### Reliability
- Add delays between commands if needed
- Use `continue_on_error: true` for non-critical automations
- Test each automation individually before combining

### Customization Based on Specifications
- **LED Counts**: Use actual counts from [../digquad-led-segments.md](../digquad-led-segments.md)
- **Functions**: Reference [../led-functions.md](../led-functions.md) for zone purposes
- **Scenarios**: See [../light-scenarios.md](../light-scenarios.md) for all behaviors
- Adjust preset numbers based on your actual WLED configuration
- Change colors in presets to match your preferences
- Add more granular controls for specific segments

### Debugging
- Enable debug logging for WLED integration
- Monitor Home Assistant logs for errors
- Test with WLED web interface first before automation
- Verify sensor entity IDs and states in Developer Tools

## Troubleshooting

### Automations Not Triggering
1. Check entity IDs match your configuration
2. Verify triggers are correct
3. Enable automation traces
4. Check condition templates

### Wrong Presets Activating
1. Verify preset numbers in WLED
2. Check automation logic
3. Test presets manually first

### Delayed Updates
1. Reduce number of automations
2. Optimize REST command payloads
3. Check network latency

### Colors Not Matching
1. Verify color hex values
2. Check LED type in WLED config
3. Adjust gamma correction

## Additional Resources

- [LED Specifications](../digquad-led-segments.md) - Exact LED counts and GPIO mapping
- [LED Functions](../led-functions.md) - Function specifications for each zone
- [Light Scenarios](../light-scenarios.md) - Complete catalog of 33+ scenarios
- [Home Assistant Automations](https://www.home-assistant.io/docs/automation/)
- [WLED API Documentation](https://kno.wled.ge/interfaces/json-api/)
- [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab)
- [WLED Templates](https://kno.wled.ge/advanced/templates/)

## Contributing

If you create additional automations or improvements based on the scenarios, please share them with the community!
