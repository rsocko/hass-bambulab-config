# Home Assistant Automation Examples for Preset-Based Segment Control

> **STATUS: FUTURE (Phase 3)** — These automations are designed for the preset-based segment approach (Phase 3). They have not been deployed. See [phased-implementation-guide.md](phased-implementation-guide.md).

This document provides complete Home Assistant automation examples for using preset-based WLED segment configurations.

## Overview

These automations enable dynamic switching between WLED preset configurations to provide full control over active tag top AND bottom segments during printing.

## Key Concepts

1. **Preset Numbers 50-57**: Each represents a different segment layout optimized for a specific active tray
2. **Segment 6**: Always contains the active tag TOP in preset layouts
3. **Segment 7**: Always contains the active tag BOTTOM in preset layouts
4. **Delay After Preset Load**: ~500ms needed for WLED to reconfigure segments

## Automation 1: Active Tray Preset Switcher

```yaml
automation:
  - id: wled_active_tray_preset_switcher
    alias: "WLED - Switch to Active Tray Preset Configuration"
    description: "Automatically load the appropriate preset configuration when active tray changes during printing"
    mode: restart  # Restart if triggered again while running
    
    trigger:
      - platform: state
        entity_id: sensor.bambu_active_tray
        # Only trigger if tray actually changes (not initial state)
        from: ~
    
    condition:
      # Only switch presets during printing
      - condition: state
        entity_id: sensor.bambu_printer_stage
        state: "printing"
      
      # Ensure active tray is valid (1-8)
      - condition: template
        value_template: "{{ states('sensor.bambu_active_tray') | int(0) in range(1, 9) }}"
    
    action:
      - variables:
          # Map tray number to preset configuration ID
          tray_number: "{{ states('sensor.bambu_active_tray') | int }}"
          preset_id: "{{ 49 + tray_number | int }}"  # Presets 50-57
          
          # Get filament color from Spoolman integration
          filament_color: >-
            {% set tray = tray_number | int %}
            {% if tray <= 4 %}
              {{ state_attr('sensor.spoolman_spool_ams1_tray_' ~ tray, 'color_hex') | default('#FFFFFF') }}
            {% else %}
              {{ state_attr('sensor.spoolman_spool_ams2_tray_' ~ (tray - 4), 'color_hex') | default('#FFFFFF') }}
            {% endif %}
      
      # Step 1: Load the preset configuration (changes segment definitions)
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ preset_id }}"
      
      # Step 2: Wait for segment reconfiguration to complete
      - delay:
          milliseconds: 500
      
      # Step 3: Set active tag TOP to filament color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 6  # Always the active tag TOP in our layouts
          color_primary: "{{ filament_color }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Step 4: Set active tag BOTTOM to same filament color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 7  # Always the active tag BOTTOM in our layouts
          color_primary: "{{ filament_color }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Step 5: Set inactive tag segments to neutral color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: [8, 9, 10, 11]  # Inactive tag segments
          color_primary: [255, 220, 180]  # Soft white
          brightness_pct: 30
          effect: "Solid"
      
      # Optional: Log the switch
      - service: logbook.log
        data:
          name: "WLED Preset Switcher"
          message: >-
            Switched to preset {{ preset_id }} for active tray {{ tray_number }} 
            with color {{ filament_color }}
```

## Automation 2: Return to Base Configuration

```yaml
automation:
  - id: wled_return_to_base_configuration
    alias: "WLED - Return to Base Preset When Not Printing"
    description: "Switch back to base segment layout when printing completes"
    mode: single
    
    trigger:
      - platform: state
        entity_id: sensor.bambu_printer_stage
        from: "printing"
    
    action:
      # Return to base idle preset (current configuration)
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 2  # Base idle preset with standard segment layout
      
      # Wait for reconfiguration
      - delay:
          milliseconds: 500
      
      # Set all tags to neutral
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: [6, 7, 8, 9, 10, 11, 12, 13]  # All tag segments in base layout
          color_primary: [255, 220, 180]
          brightness_pct: 25
          effect: "Solid"
```

## Automation 3: Enhanced Print Start with Preset

```yaml
automation:
  - id: wled_print_start_with_active_tray
    alias: "WLED - Print Start with Active Tray Highlight"
    description: "Set up WLED with correct preset and colors when print starts"
    mode: restart
    
    trigger:
      - platform: state
        entity_id: sensor.bambu_printer_stage
        to: "printing"
    
    action:
      - variables:
          active_tray: "{{ states('sensor.bambu_active_tray') | int(0) }}"
      
      - choose:
          # If we have an active tray, use preset-based configuration
          - conditions:
              - condition: template
                value_template: "{{ active_tray >= 1 and active_tray <= 8 }}"
            sequence:
              - service: automation.trigger
                target:
                  entity_id: automation.wled_active_tray_preset_switcher
        
        # Otherwise use base printing preset
        default:
          - service: light.turn_on
            target:
              entity_id: light.digquad
            data:
              preset: 7  # Base printing preset (no active tray)
```

## Automation 4: Progress Bar Update (Works with Any Preset)

```yaml
automation:
  - id: wled_progress_bar_update
    alias: "WLED - Update Progress Bar"
    description: "Update progress bar segment (segment 0) during printing"
    mode: restart
    
    trigger:
      - platform: state
        entity_id: sensor.bambu_print_progress
      
      # Also update every 30 seconds during printing
      - platform: time_pattern
        seconds: "/30"
    
    condition:
      - condition: state
        entity_id: sensor.bambu_printer_stage
        state: "printing"
    
    action:
      - variables:
          progress_pct: "{{ states('sensor.bambu_print_progress') | int(0) }}"
          progress_length: "{{ (50 * progress_pct / 100) | int }}"  # 50 LEDs in progress bar
      
      # Segment 0 is progress bar in ALL preset configurations
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 0
          color_primary: [0, 255, 0]  # Green
          brightness_pct: 80
          length: "{{ progress_length }}"
          effect: "Solid"
```

## Script: Manual Preset Test

```yaml
script:
  wled_test_preset_configuration:
    alias: "WLED - Test Preset Configuration"
    description: "Manually test a specific preset configuration"
    mode: single
    
    fields:
      tray_number:
        description: "Tray number (1-8)"
        example: "1"
        required: true
        selector:
          number:
            min: 1
            max: 8
            mode: slider
      
      test_color:
        description: "Test color (hex)"
        example: "#FF5733"
        required: false
        default: "#FF0000"
        selector:
          color_rgb:
    
    sequence:
      - variables:
          preset_id: "{{ 49 + (tray_number | int) }}"
      
      # Load preset
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ preset_id }}"
      
      # Wait for reconfiguration
      - delay:
          milliseconds: 500
      
      # Set active tag top
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 6
          color_primary: "{{ test_color }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Set active tag bottom
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 7
          color_primary: "{{ test_color }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Notification
      - service: notify.mobile_app
        data:
          title: "WLED Preset Test"
          message: >-
            Testing preset {{ preset_id }} for tray {{ tray_number }} 
            with color {{ test_color }}
```

## Script: Cycle Through All Presets (Testing)

```yaml
script:
  wled_cycle_all_presets:
    alias: "WLED - Cycle Through All Preset Configurations"
    description: "Test all 8 preset configurations sequentially"
    mode: single
    
    sequence:
      - repeat:
          count: 8
          sequence:
            - variables:
                tray_num: "{{ repeat.index }}"
                preset_num: "{{ 49 + repeat.index }}"
                test_colors:
                  - "#FF0000"  # Red for A1
                  - "#00FF00"  # Green for A2
                  - "#0000FF"  # Blue for A3
                  - "#FFFF00"  # Yellow for A4
                  - "#FF00FF"  # Magenta for B1
                  - "#00FFFF"  # Cyan for B2
                  - "#FFA500"  # Orange for B3
                  - "#800080"  # Purple for B4
                current_color: "{{ test_colors[repeat.index - 1] }}"
            
            # Load preset
            - service: light.turn_on
              target:
                entity_id: light.digquad
              data:
                preset: "{{ preset_num }}"
            
            - delay:
                milliseconds: 500
            
            # Set colors
            - service: wled.effect
              target:
                entity_id: light.digquad
              data:
                segment_id: [6, 7]
                color_primary: "{{ current_color }}"
                brightness_pct: 80
                effect: "Solid"
            
            # Display for 3 seconds
            - delay:
                seconds: 3
            
            # Show tray number notification
            - service: persistent_notification.create
              data:
                title: "Testing Preset {{ preset_num }}"
                message: >-
                  Tray {{ tray_num }} - Preset {{ preset_num }}
                  Color: {{ current_color }}
                notification_id: "wled_preset_test"
      
      # Return to base
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 2
```

## Advanced: Dynamic Color from Spoolman

```yaml
script:
  wled_sync_active_tray_from_spoolman:
    alias: "WLED - Sync Active Tray Color from Spoolman"
    description: "Automatically sync active tray color from Spoolman database"
    mode: restart
    
    sequence:
      - variables:
          active_tray: "{{ states('sensor.bambu_active_tray') | int(0) }}"
          
          # Build Spoolman sensor entity ID based on active tray
          spoolman_entity: >-
            {% set tray = active_tray | int %}
            {% if tray >= 1 and tray <= 4 %}
              sensor.spoolman_spool_ams1_tray_{{ tray }}
            {% elif tray >= 5 and tray <= 8 %}
              sensor.spoolman_spool_ams2_tray_{{ tray - 4 }}
            {% else %}
              none
            {% endif %}
          
          # Get color from Spoolman
          filament_color: >-
            {{ state_attr(spoolman_entity, 'color_hex') | default('#FFFFFF') }}
          
          # Get filament name for logging
          filament_name: >-
            {{ state_attr(spoolman_entity, 'filament_name') | default('Unknown') }}
      
      - condition: template
        value_template: "{{ active_tray >= 1 and active_tray <= 8 }}"
      
      # Switch to appropriate preset
      - service: script.wled_test_preset_configuration
        data:
          tray_number: "{{ active_tray }}"
          test_color: "{{ filament_color }}"
      
      # Log the sync
      - service: logbook.log
        data:
          name: "WLED Spoolman Sync"
          message: >-
            Synced tray {{ active_tray }} with {{ filament_name }} 
            color {{ filament_color }} from Spoolman
```

## Sensor: Current Preset Configuration

```yaml
sensor:
  - platform: template
    sensors:
      wled_current_preset_config:
        friendly_name: "WLED Current Preset Configuration"
        value_template: >-
          {% set active_tray = states('sensor.bambu_active_tray') | int(0) %}
          {% set stage = states('sensor.bambu_printer_stage') %}
          
          {% if stage == 'printing' and active_tray >= 1 and active_tray <= 8 %}
            {% set tray_names = ['A1', 'A2', 'A3', 'A4', 'B1', 'B2', 'B3', 'B4'] %}
            Preset {{ 49 + active_tray }} ({{ tray_names[active_tray - 1] }} Full Highlight)
          {% else %}
            Base Configuration (No Active Tray)
          {% endif %}
        
        icon_template: >-
          {% if states('sensor.bambu_printer_stage') == 'printing' %}
            mdi:printer-3d
          {% else %}
            mdi:led-strip
          {% endif %}
```

## Input Select: Manual Preset Override

```yaml
input_select:
  wled_preset_override:
    name: "WLED Preset Override"
    options:
      - "Auto (Follow Active Tray)"
      - "Base Configuration"
      - "Preset 50 (A1)"
      - "Preset 51 (A2)"
      - "Preset 52 (A3)"
      - "Preset 53 (A4)"
      - "Preset 54 (B1)"
      - "Preset 55 (B2)"
      - "Preset 56 (B3)"
      - "Preset 57 (B4)"
    initial: "Auto (Follow Active Tray)"
    icon: mdi:palette

automation:
  - id: wled_manual_preset_override
    alias: "WLED - Manual Preset Override"
    description: "Allow manual control of preset configuration"
    mode: restart
    
    trigger:
      - platform: state
        entity_id: input_select.wled_preset_override
    
    action:
      - variables:
          selection: "{{ states('input_select.wled_preset_override') }}"
          
          preset_map:
            "Base Configuration": 2
            "Preset 50 (A1)": 50
            "Preset 51 (A2)": 51
            "Preset 52 (A3)": 52
            "Preset 53 (A4)": 53
            "Preset 54 (B1)": 54
            "Preset 55 (B2)": 55
            "Preset 56 (B3)": 56
            "Preset 57 (B4)": 57
      
      - choose:
          # Auto mode - let normal automation handle it
          - conditions:
              - condition: template
                value_template: "{{ selection == 'Auto (Follow Active Tray)' }}"
            sequence:
              - service: automation.trigger
                target:
                  entity_id: automation.wled_active_tray_preset_switcher
        
        # Manual preset selection
        default:
          - service: light.turn_on
            target:
              entity_id: light.digquad
            data:
              preset: "{{ preset_map[selection] }}"
```

## Troubleshooting Helper: Preset Validation

```yaml
script:
  wled_validate_preset_segments:
    alias: "WLED - Validate Preset Segments"
    description: "Test each segment individually to verify LED ranges"
    mode: single
    
    fields:
      preset_number:
        description: "Preset to validate (50-57)"
        example: "50"
        required: true
        selector:
          number:
            min: 50
            max: 57
    
    sequence:
      # Load the preset
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ preset_number }}"
      
      - delay:
          milliseconds: 500
      
      # Test each segment one by one
      - repeat:
          count: 14
          sequence:
            - variables:
                segment_num: "{{ repeat.index - 1 }}"
            
            # Turn on only this segment
            - service: wled.effect
              target:
                entity_id: light.digquad
              data:
                segment_id: "{{ segment_num }}"
                color_primary: [255, 255, 255]
                brightness_pct: 100
                effect: "Solid"
            
            # Turn off all other segments
            - service: wled.effect
              target:
                entity_id: light.digquad
              data:
                segment_id: >-
                  {{ range(0, 15) | reject('eq', segment_num | int) | list }}
                brightness_pct: 0
            
            # Notification
            - service: persistent_notification.create
              data:
                title: "Segment {{ segment_num }} Validation"
                message: >-
                  Testing segment {{ segment_num }} in preset {{ preset_number }}.
                  Verify correct LEDs are lit.
                notification_id: "wled_segment_test"
            
            # Wait for visual inspection
            - delay:
                seconds: 5
```

## Configuration Notes

### Required Sensors
Ensure these sensors exist in your Home Assistant:
- `sensor.bambu_active_tray` - Current active tray (1-8)
- `sensor.bambu_printer_stage` - Printer stage (idle, printing, etc.)
- `sensor.bambu_print_progress` - Print completion percentage
- `sensor.spoolman_spool_ams1_tray_X` - Spoolman spool data for AMS 1
- `sensor.spoolman_spool_ams2_tray_X` - Spoolman spool data for AMS 2

### WLED Entity
Replace `light.digquad` with your actual WLED entity ID throughout.

### Preset Numbers
- Presets 50-57: Preset-based segment configurations
- Preset 2: Base idle configuration
- Preset 7: Base printing configuration

### Customization
Adjust colors, brightness, delays, and other parameters to match your preferences and hardware response times.
