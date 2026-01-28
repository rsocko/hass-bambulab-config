# Home Assistant Automation Examples for WLED Printer Lighting

This document provides example automations for controlling your WLED printer lighting based on Bambu Lab printer states.

## Prerequisites

1. Both WLED controllers added to Home Assistant
2. Bambu Lab integration installed and configured
3. Presets uploaded to both WLED controllers

## Entity Names

Adjust these entity names to match your Home Assistant configuration:

- WLED Digquad: `light.digquad` 
- WLED MagWLED: `light.magwled`
- Printer: `sensor.bambu_lab_x1c_*` (replace with your printer name)

## Automation 1: Print Started - Normal Printing Mode

```yaml
automation:
  - alias: "Printer: WLED Normal Printing Mode"
    description: "Activate normal printing preset when print starts"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "printing"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id:
            - light.digquad
            - light.magwled
        data:
          preset: 1  # Preset 1: Normal Printing
      - service: notify.mobile_app
        data:
          message: "Print started - Lighting activated"
          title: "3D Printer"
```

## Automation 2: Print Error - Error Mode

```yaml
automation:
  - alias: "Printer: WLED Print Error Mode"
    description: "Flash red when print encounters an error"
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
          preset: 2  # Preset 2: Print Error
      - service: notify.mobile_app
        data:
          message: "Print error detected!"
          title: "3D Printer Alert"
```

**Note**: The HMS error entity structure may vary depending on your Bambu Lab integration version. Adjust the entity name and condition to match your setup. Common variations:
- `sensor.bambu_lab_x1c_hms_errors` with state as error count
- `sensor.bambu_lab_x1c_hms` with attributes containing error list
- Check your entity's attributes in Developer Tools to verify the correct structure.

## Automation 3: Print Complete

```yaml
automation:
  - alias: "Printer: WLED Print Complete"
    description: "Celebrate print completion with green animation"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "complete"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id:
            - light.digquad
            - light.magwled
        data:
          preset: 3  # Preset 3: Print Complete
      - delay:
          seconds: 30
      - service: light.turn_on
        target:
          entity_id:
            - light.digquad
            - light.magwled
        data:
          preset: 4  # After celebration, return to idle
```

## Automation 4: Printer Idle

```yaml
automation:
  - alias: "Printer: WLED Idle Mode"
    description: "Set to idle/standby when printer is not printing"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_current_stage
        to: "idle"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id:
            - light.digquad
            - light.magwled
        data:
          preset: 4  # Preset 4: Idle Standby
```

## Automation 5: Maintenance Mode (Manual)

```yaml
automation:
  - alias: "Printer: WLED Maintenance Mode"
    description: "Manual trigger for maintenance mode - bright white"
    trigger:
      - platform: state
        entity_id: input_boolean.printer_maintenance_mode
        to: "on"
    condition: []
    action:
      - service: light.turn_on
        target:
          entity_id:
            - light.digquad
            - light.magwled
        data:
          preset: 5  # Preset 5: Maintenance Mode
```

## Automation 6: Active Spool Highlighting (AMS 1)

This automation highlights the active spool in AMS 1:

```yaml
automation:
  - alias: "Printer: Highlight Active AMS1 Spool"
    description: "Highlight the currently active spool in AMS 1"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_active_tray
    condition:
      - condition: template
        value_template: "{{ states('sensor.bambu_lab_x1c_active_tray') in ['1', '2', '3', '4'] }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: >
            {% set tray = states('sensor.bambu_lab_x1c_active_tray') | int %}
            {% if tray >= 1 and tray <= 4 %}
              {{ 6 + tray }}  {# Presets 7-10 for AMS1 spools A1-A4 #}
            {% else %}
              1  {# Default to normal printing #}
            {% endif %}
```

## Automation 7: Active Spool Highlighting (AMS 2)

This automation highlights the active spool in AMS 2:

```yaml
automation:
  - alias: "Printer: Highlight Active AMS2 Spool"
    description: "Highlight the currently active spool in AMS 2"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_x1c_active_tray
    condition:
      - condition: template
        value_template: "{{ states('sensor.bambu_lab_x1c_active_tray') in ['5', '6', '7', '8'] }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: >
            {% set tray = states('sensor.bambu_lab_x1c_active_tray') | int %}
            {% if tray >= 5 and tray <= 8 %}
              {{ 6 + tray }}  {# Presets 11-14 for AMS2 spools B1-B4 #}
            {% else %}
              1  {# Default to normal printing #}
            {% endif %}
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          preset: >
            {% set tray = states('sensor.bambu_lab_x1c_active_tray') | int %}
            {% if tray == 5 %}
              4  {# Active Tag B1 #}
            {% elif tray == 6 %}
              5  {# Active Tag B2 #}
            {% elif tray == 7 %}
              6  {# Active Tag B3 #}
            {% elif tray == 8 %}
              7  {# Active Tag B4 #}
            {% else %}
              1  {# Normal printing #}
            {% endif %}
```

## Automation 8: Print Progress Bar

Advanced automation to show print progress on the bottom printer segment:

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
          "id": 1,
          "i": [
            0, {{ ((progress | int) * 30 / 100) | int }}, "FF5500",
            {{ ((progress | int) * 30 / 100) | int }}, 30, "000000"
          ]
        }]
      }
```

Note: This assumes segment 1 (printer bottom) has 30 LEDs. Adjust based on your actual LED count.

## Input Boolean Helper

Create this helper in Home Assistant for manual maintenance mode:

```yaml
input_boolean:
  printer_maintenance_mode:
    name: Printer Maintenance Mode
    icon: mdi:tools
    initial: off
```

## Advanced: Multi-Color Filament Display

This script changes spool lighting to match filament colors (requires Spoolman integration):

```yaml
script:
  update_ams_spool_colors:
    alias: "Update AMS Spool Colors"
    sequence:
      - repeat:
          count: 8
          sequence:
            - variables:
                tray_id: "{{ repeat.index }}"
                spool_entity: "sensor.spoolman_spool_{{ tray_id }}"
                color_hex: "{{ state_attr(spool_entity, 'color_hex') }}"
            - condition: template
              value_template: "{{ color_hex is not none }}"
            - service: rest_command.wled_set_segment_color
              data:
                controller: >
                  {% if tray_id <= 4 %}digquad{% else %}magwled{% endif %}
                segment_id: >
                  {% if tray_id <= 4 %}
                    {{ tray_id + 3 }}  {# Segments 4-7 for AMS1 #}
                  {% else %}
                    {{ tray_id - 5 + 12 }}  {# Segments 12-15 for AMS2 #}
                  {% endif %}
                color: "{{ color_hex }}"
```

## Dashboard Card Example

Add this to your Lovelace dashboard for manual control:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Printer Lighting Control
    entities:
      - entity: light.digquad
        name: Digquad LEDs
      - entity: light.magwled
        name: MagWLED LEDs
      - entity: input_boolean.printer_maintenance_mode
        name: Maintenance Mode
  - type: button
    name: Normal Printing
    tap_action:
      action: call-service
      service: light.turn_on
      service_data:
        preset: 1
      target:
        entity_id: light.digquad
  - type: button
    name: Idle/Standby
    tap_action:
      action: call-service
      service: light.turn_on
      service_data:
        preset: 4
      target:
        entity_id: light.digquad
  - type: button
    name: Maintenance
    tap_action:
      action: call-service
      service: light.turn_on
      service_data:
        preset: 5
      target:
        entity_id:
          - light.digquad
          - light.magwled
```

## Tips and Best Practices

### Performance
- Update progress bar every 5-10 seconds, not every second
- Use condition checks to avoid unnecessary updates
- Group multiple REST commands when possible

### Reliability
- Add delays between commands to different controllers
- Use `continue_on_error: true` for non-critical automations
- Test each automation individually before combining

### Customization
- Adjust preset numbers based on your actual WLED configuration
- Change colors in presets to match your preferences
- Add more granular controls for specific segments

### Debugging
- Enable debug logging for WLED integration
- Monitor Home Assistant logs for errors
- Test with WLED web interface first before automation

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

- [Home Assistant Automations](https://www.home-assistant.io/docs/automation/)
- [WLED API Documentation](https://kno.wled.ge/interfaces/json-api/)
- [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab)
- [WLED Templates](https://kno.wled.ge/advanced/templates/)

## Contributing

If you create additional automations or improvements, please share them with the community!
