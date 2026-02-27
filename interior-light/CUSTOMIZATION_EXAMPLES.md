# Interior Light Customization Examples

This document provides advanced customization examples for the interior light reset functionality.

## Custom Light Scenes

### Warm White (Comfortable Viewing)
Perfect for late-night viewing or extended inspection sessions.

```yaml
script:
  interior_light_warm_white:
    alias: "Interior Light - Warm White"
    description: "Set interior light to comfortable warm white"
    icon: mdi:lightbulb-on-outline
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: 85
          rgb_color: [255, 244, 229]  # Warm color temperature
```

### Cool White (Bright Inspection)
Best for detailed inspection and color accuracy.

```yaml
script:
  interior_light_cool_white:
    alias: "Interior Light - Cool White"
    description: "Set interior light to bright cool white for inspection"
    icon: mdi:lightbulb
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: 100
          rgb_color: [240, 248, 255]  # Cool/daylight color
```

### Photography Mode
Optimized for taking photos of completed prints.

```yaml
script:
  interior_light_photo_mode:
    alias: "Interior Light - Photography Mode"
    description: "Set interior light to optimal settings for photography"
    icon: mdi:camera
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: 100
          rgb_color: [255, 255, 245]  # Neutral white
```

### Night Mode (Dim)
For checking on prints at night without bright light.

```yaml
script:
  interior_light_night_mode:
    alias: "Interior Light - Night Mode"
    description: "Set interior light to dim for night checking"
    icon: mdi:weather-night
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: 20
          rgb_color: [255, 200, 150]  # Warm, dim
```

## Multi-Button Dashboard Card

Create a card with multiple lighting presets:

```yaml
type: vertical-stack
cards:
  - type: markdown
    content: "## Interior Light Presets"
  
  - type: horizontal-stack
    cards:
      - type: button
        name: Bright
        icon: mdi:brightness-7
        tap_action:
          action: call-service
          service: script.reset_interior_light_to_white
        icon_height: 30px
      
      - type: button
        name: Warm
        icon: mdi:lightbulb-on-outline
        tap_action:
          action: call-service
          service: script.interior_light_warm_white
        icon_height: 30px
      
      - type: button
        name: Photo
        icon: mdi:camera
        tap_action:
          action: call-service
          service: script.interior_light_photo_mode
        icon_height: 30px
      
      - type: button
        name: Night
        icon: mdi:weather-night
        tap_action:
          action: call-service
          service: script.interior_light_night_mode
        icon_height: 30px
  
  - type: custom:mushroom-light-card
    entity: light.magwled
    name: Manual Control
    use_light_color: true
    show_brightness_control: true
    show_color_control: true
```

## Advanced Automations

### Smart Door Open Detection

If you don't have a physical door sensor, use this creative approach with the cover image:

```yaml
automation:
  - id: interior_light_smart_door_detection
    alias: "Interior Light - Smart Door Detection"
    description: "Detect potential door opens by monitoring cover image changes"
    mode: single
    
    trigger:
      # Trigger when cover image updates (happens when camera sees movement)
      - platform: state
        entity_id: image.ntk_ryansoffice_3dprinter_cover_image
    
    condition:
      # Only when not printing
      - condition: not
        conditions:
          - condition: state
            entity_id: sensor.ntk_ryansoffice_3dprinter_smart_status
            state: "Printing"
      
      # Only during reasonable hours
      - condition: time
        after: "07:00:00"
        before: "23:00:00"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

### Time-Based Auto-Reset

Automatically reset the light at certain times (e.g., morning prep):

```yaml
automation:
  - id: interior_light_morning_reset
    alias: "Interior Light - Morning Reset"
    description: "Reset interior light to white every morning for day prep"
    mode: single
    
    trigger:
      - platform: time
        at: "08:00:00"
    
    condition:
      # Only if printer is idle
      - condition: state
        entity_id: sensor.ntk_ryansoffice_3dprinter_smart_status
        state: "Idle"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

### Error Recovery

Reset light to white after error states are cleared:

```yaml
automation:
  - id: interior_light_error_recovery
    alias: "Interior Light - Error Recovery"
    description: "Reset light after HMS errors are cleared"
    mode: single
    
    trigger:
      - platform: state
        entity_id: binary_sensor.ntk_ryansoffice_3dprinter_hms_errors
        from: "on"
        to: "off"
    
    action:
      # Wait a moment for error state to fully clear
      - delay:
          seconds: 5
      
      - service: script.reset_interior_light_to_white
        data: {}
      
      - service: persistent_notification.create
        data:
          title: "Printer Ready"
          message: "HMS errors cleared. Interior light reset to white."
          notification_id: "interior_light_error_cleared"
```

### Print Stage-Based Lighting

Automatically adjust lighting based on print stage:

```yaml
automation:
  - id: interior_light_stage_based
    alias: "Interior Light - Print Stage Based Lighting"
    description: "Adjust interior lighting based on current print stage"
    mode: restart
    
    trigger:
      - platform: state
        entity_id: sensor.ntk_ryansoffice_3dprinter_current_stage
    
    action:
      - choose:
          # First layer - bright for monitoring
          - conditions:
              - condition: template
                value_template: "{{ 'first' in trigger.to_state.state.lower() }}"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.magwled
                data:
                  brightness_pct: 100
                  rgb_color: [255, 255, 255]
          
          # Regular printing - moderate brightness
          - conditions:
              - condition: state
                entity_id: sensor.ntk_ryansoffice_3dprinter_current_stage
                state: "printing"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.magwled
                data:
                  brightness_pct: 60
                  rgb_color: [255, 255, 255]
          
          # Cooling - dim blue
          - conditions:
              - condition: template
                value_template: "{{ 'cool' in trigger.to_state.state.lower() }}"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.magwled
                data:
                  brightness_pct: 40
                  rgb_color: [100, 149, 237]
        
        # Default - white
        default:
          - service: script.reset_interior_light_to_white
            data: {}
```

## Input Helpers for User Preferences

Create input helpers to let users choose their preferred light settings:

```yaml
input_number:
  interior_light_brightness_pref:
    name: "Interior Light Brightness Preference"
    icon: mdi:brightness-6
    min: 10
    max: 100
    step: 5
    unit_of_measurement: "%"
    initial: 100

input_select:
  interior_light_color_pref:
    name: "Interior Light Color Preference"
    icon: mdi:palette
    options:
      - "Cool White"
      - "Neutral White"
      - "Warm White"
    initial: "Neutral White"
```

Then modify the script to use these preferences:

```yaml
script:
  reset_interior_light_to_white:
    alias: "Reset Interior Light to White"
    description: "Reset interior light using user preferences"
    icon: mdi:lightbulb-on
    mode: single
    sequence:
      - variables:
          brightness: "{{ states('input_number.interior_light_brightness_pref') | int }}"
          color_preset: "{{ states('input_select.interior_light_color_pref') }}"
          color_map:
            "Cool White": [240, 248, 255]
            "Neutral White": [255, 255, 255]
            "Warm White": [255, 244, 229]
          selected_color: "{{ color_map[color_preset] }}"
      
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: "{{ brightness }}"
          rgb_color: "{{ selected_color }}"
```

## Integration with Other Systems

### Node-RED Flow

Example Node-RED flow to add a button:

```json
[
  {
    "id": "button_node",
    "type": "ui_button",
    "name": "Reset Interior Light",
    "group": "printer_controls",
    "label": "Reset Light",
    "icon": "fa-lightbulb-o",
    "payload": "",
    "payloadType": "str",
    "topic": "",
    "x": 200,
    "y": 100,
    "wires": [["call_service"]]
  },
  {
    "id": "call_service",
    "type": "api-call-service",
    "name": "Call Reset Script",
    "server": "home_assistant",
    "service_domain": "script",
    "service": "reset_interior_light_to_white",
    "data": "{}",
    "x": 400,
    "y": 100,
    "wires": [[]]
  }
]
```

### Webhook Trigger

Create a webhook to trigger from external systems:

```yaml
automation:
  - id: interior_light_webhook
    alias: "Interior Light - Webhook Trigger"
    description: "Reset light via webhook (useful for external integrations)"
    mode: single
    
    trigger:
      - platform: webhook
        webhook_id: reset_interior_light_webhook_12345
        allowed_methods:
          - POST
          - GET
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
      
      # Return success response
      - service: script.respond_to_webhook
        data:
          webhook_id: "{{ trigger.webhook_id }}"
          response:
            status: "success"
            message: "Interior light reset to white"
```

Call it from anywhere:
```bash
curl -X POST https://your-ha-instance.com/api/webhook/reset_interior_light_webhook_12345
```

## Voice Assistant Phrases

### Google Assistant

Configure custom routines:
- "Reset printer light" → Call `script.reset_interior_light_to_white`
- "Printer photography mode" → Call `script.interior_light_photo_mode`
- "Printer night mode" → Call `script.interior_light_night_mode`

### Alexa

Create custom routines in Alexa app:
1. When I say: "Reset the printer light"
2. Add action: Smart Home → Control device → script.reset_interior_light_to_white

## Mobile App Notifications with Actions

Send a notification with action buttons:

```yaml
automation:
  - id: print_complete_notification_with_light_reset
    alias: "Print Complete - Notification with Light Reset Action"
    description: "Send notification with quick action to reset light"
    mode: single
    
    trigger:
      - platform: state
        entity_id: sensor.ntk_ryansoffice_3dprinter_smart_status
        to: "Print Finished"
    
    action:
      - service: notify.mobile_app
        data:
          title: "Print Complete!"
          message: "Your print is ready. Tap to reset light for viewing."
          data:
            actions:
              - action: "RESET_INTERIOR_LIGHT"
                title: "Reset Light to White"
              - action: "VIEW_CAMERA"
                title: "Open Camera"
            tag: "print_complete"

# Handler for the notification action
  - id: handle_light_reset_action
    alias: "Handle Interior Light Reset Action"
    mode: single
    
    trigger:
      - platform: event
        event_type: mobile_app_notification_action
        event_data:
          action: "RESET_INTERIOR_LIGHT"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

## Dashboard Widget with State Display

Advanced widget showing light state and multiple controls:

```yaml
type: custom:vertical-stack-in-card
cards:
  - type: custom:mushroom-title-card
    title: Interior Light Control
    subtitle: "Current: {{ state_attr('light.magwled', 'brightness') | int / 255 * 100 | round(0) }}%"
  
  - type: custom:mushroom-light-card
    entity: light.magwled
    use_light_color: true
    show_brightness_control: true
    show_color_temp_control: false
    show_color_control: true
    layout: horizontal
  
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-template-card
        primary: "100%"
        icon: mdi:brightness-7
        icon_color: amber
        layout: vertical
        tap_action:
          action: call-service
          service: script.reset_interior_light_to_white
      
      - type: custom:mushroom-template-card
        primary: "Warm"
        icon: mdi:lightbulb-on-outline
        icon_color: orange
        layout: vertical
        tap_action:
          action: call-service
          service: script.interior_light_warm_white
      
      - type: custom:mushroom-template-card
        primary: "Photo"
        icon: mdi:camera
        icon_color: blue
        layout: vertical
        tap_action:
          action: call-service
          service: script.interior_light_photo_mode
      
      - type: custom:mushroom-template-card
        primary: "Night"
        icon: mdi:weather-night
        icon_color: indigo
        layout: vertical
        tap_action:
          action: call-service
          service: script.interior_light_night_mode
  
  - type: conditional
    conditions:
      - entity: sensor.ntk_ryansoffice_3dprinter_smart_status
        state: "Printing"
    card:
      type: custom:mushroom-chip-card
      chips:
        - type: template
          icon: mdi:printer-3d
          content: "Printing - Light auto-managed"
          icon_color: green

> **Tip:** For simple UI and automation conditions, prefer `sensor.ntk_ryansoffice_3dprinter_smart_status` (and optionally its `detail` / `status_class` attributes). Keep using `sensor.ntk_ryansoffice_3dprinter_current_stage` only when you need stage-specific branching.
```

## Summary

These examples demonstrate the flexibility of the interior light control system. Mix and match components to create the perfect setup for your workflow:

- **Simple Setup**: Just the basic reset script and one button
- **Moderate Setup**: Multiple preset scripts with a multi-button card
- **Advanced Setup**: Full automation based on print stages, with mobile notifications
- **Power User Setup**: Input helpers for preferences, webhook integration, voice control

Choose what fits your needs and expand over time!
