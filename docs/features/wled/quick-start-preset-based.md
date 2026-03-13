# Quick Start: Preset-Based Segment Configuration

> **STATUS: FUTURE (Phase 3)** — This guide describes the preset-based segment approach which is planned for Phase 3. The current system uses the state machine (presets 101–109). See [phased-implementation-guide.md](phased-implementation-guide.md).

This is a quick reference guide for implementing preset-based segment configurations to enable full control of active tag top AND bottom LEDs.

## TL;DR

**Problem**: Can't highlight both top and bottom of a tag because bottoms are combined into one segment.

**Solution**: Create 8 preset configurations (50-57), each with a different segment layout optimized for one active tray. Switch between them automatically via Home Assistant.

**Result**: Full tag highlighting with both top and bottom showing filament color!

## Quick Implementation Steps

### Step 1: Create One Preset Configuration (Proof of Concept)

1. **Open WLED UI** for DigQuad controller
2. **Navigate to Segments tab**
3. **Clear existing segments** (don't worry, you'll restore them)
4. **Create new segments** following the layout for Preset 50 (A1):

```
Segment 0: Progress Bar (LEDs 0-49)
Segment 1: Front Door Status (LEDs 50-157)
Segment 2: AMS 1 Tray Top (LEDs 158-215)
Segment 3: AMS 1 Tray Bottom (LEDs 241-297)
Segment 4: AMS 2 Tray Top (LEDs 298-357)
Segment 5: AMS 2 Tray Bottom (LEDs 382-436)
Segment 6: A1 Tag Top (LEDs 442-453) ← ACTIVE TAG TOP
Segment 7: A1 Tag Bottom (LEDs 502-513) ← ACTIVE TAG BOTTOM
Segment 8: A2-A4 Tags Top Combined (LEDs 454-501)
Segment 9: B1-B4 Tags Top Combined (LEDs 579-643)
Segment 10: A2-A4 Tags Bottom Combined (LEDs 514-562)
Segment 11: B1-B4 Tags Bottom Combined (LEDs 644-698)
Segment 12: AMS 1 Hygrometer (LEDs 478-501)
Segment 13: AMS 2 Hygrometer (LEDs 620-643)
Segment 14: Spare
```

5. **Save as Preset 50**:
   - Go to Presets tab
   - Click "Save to preset"
   - Choose preset number: 50
   - **CRITICAL**: Check "Save segment bounds" option ✓
   - Name: "A1_Full_Highlight"
   - Save

6. **Test it**:
   - Load Preset 50
   - Turn on segment 6 only - verify A1 top LEDs light up
   - Turn on segment 7 only - verify A1 bottom LEDs light up
   - Set both segments 6 and 7 to the same color (e.g., red)
   - Success! You can now highlight both top and bottom of A1!

### Step 2: Create Home Assistant Automation

Add this to your `configuration.yaml` or `automations.yaml`:

```yaml
automation:
  - id: wled_tray_a1_full_highlight
    alias: "WLED - A1 Full Highlight (Test)"
    mode: restart
    
    trigger:
      - platform: state
        entity_id: sensor.bambu_active_tray
        to: "1"
    
    condition:
      - condition: state
        entity_id: sensor.bambu_printer_stage
        state: "printing"
    
    action:
      # Step 1: Load preset configuration
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 50
      
      # Step 2: Wait for segment reconfiguration
      - delay:
          milliseconds: 500
      
      # Step 3: Set active tag top to filament color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 6
          color_primary: "{{ state_attr('sensor.spoolman_spool_1', 'color_hex') | default('#FF0000') }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Step 4: Set active tag bottom to same color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 7
          color_primary: "{{ state_attr('sensor.spoolman_spool_1', 'color_hex') | default('#FF0000') }}"
          brightness_pct: 80
          effect: "Solid"
```

### Step 3: Test the Automation

1. Start a print using tray A1
2. Observe WLED automatically switches to Preset 50
3. Both A1 top and bottom should light up with filament color
4. Success!

## Next Steps (Optional)

Once you've validated the concept works:

1. **Create remaining presets** (51-57) for trays A2-A4 and B1-B4
2. **Enhance automation** to handle all 8 trays
3. **Add return to base** automation when printing completes
4. **Fine-tune LED ranges** if any segments don't light up correctly

## Full Automation (All 8 Trays)

Once you have all presets created:

```yaml
automation:
  - id: wled_active_tray_preset_switcher
    alias: "WLED - Switch to Active Tray Preset"
    mode: restart
    
    trigger:
      - platform: state
        entity_id: sensor.bambu_active_tray
    
    condition:
      - condition: state
        entity_id: sensor.bambu_printer_stage
        state: "printing"
      - condition: template
        value_template: "{{ states('sensor.bambu_active_tray') | int(0) in range(1, 9) }}"
    
    action:
      - variables:
          tray_number: "{{ states('sensor.bambu_active_tray') | int }}"
          preset_id: "{{ 49 + tray_number | int }}"  # Presets 50-57
          
          # Get color from Spoolman
          filament_color: >-
            {% set tray = tray_number | int %}
            {% if tray <= 4 %}
              {{ state_attr('sensor.spoolman_spool_ams1_tray_' ~ tray, 'color_hex') | default('#FFFFFF') }}
            {% else %}
              {{ state_attr('sensor.spoolman_spool_ams2_tray_' ~ (tray - 4), 'color_hex') | default('#FFFFFF') }}
            {% endif %}
      
      # Load preset configuration
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ preset_id }}"
      
      - delay:
          milliseconds: 500
      
      # Set active tag top
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 6
          color_primary: "{{ filament_color }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Set active tag bottom
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 7
          color_primary: "{{ filament_color }}"
          brightness_pct: 80
          effect: "Solid"
      
      # Set inactive tags to neutral
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: [8, 9, 10, 11]
          color_primary: [255, 220, 180]
          brightness_pct: 30
          effect: "Solid"
```

## Common Issues

### Issue: Preset doesn't change segments
**Cause**: Forgot to check "Save segment bounds"  
**Fix**: Recreate preset with the checkbox enabled

### Issue: Wrong LEDs light up
**Cause**: LED ranges don't match your physical strip  
**Fix**: Adjust start/stop LED numbers for the affected segment

### Issue: Colors don't apply after preset loads
**Cause**: Not enough delay after preset switch  
**Fix**: Increase delay from 500ms to 1000ms

### Issue: Automation doesn't trigger
**Cause**: Sensor entity ID doesn't exist or is named differently  
**Fix**: Check your sensor names in Developer Tools → States

## LED Range Reference

If your LEDs don't match the defaults, use these as starting points and adjust:

### AMS 1 Tags
- **A1 Top**: 442-453 (12 LEDs)
- **A1 Bottom**: 502-513 (12 LEDs estimated)
- **A2 Top**: 454-465 (12 LEDs)
- **A2 Bottom**: 514-525 (12 LEDs estimated)
- **A3 Top**: 466-477 (12 LEDs)
- **A3 Bottom**: 526-538 (13 LEDs estimated)
- **A4 Top**: 490-501 (12 LEDs)
- **A4 Bottom**: 551-562 (12 LEDs estimated)

### AMS 2 Tags
- **B1 Top**: 579-591 (13 LEDs)
- **B1 Bottom**: 644-656 (13 LEDs estimated)
- **B2 Top**: 592-605 (14 LEDs)
- **B2 Bottom**: 657-671 (15 LEDs estimated)
- **B3 Top**: 606-619 (14 LEDs)
- **B3 Bottom**: 672-686 (15 LEDs estimated)
- **B4 Top**: 632-643 (12 LEDs)
- **B4 Bottom**: 687-698 (12 LEDs estimated)

**Note**: Bottom ranges are estimated. Verify by testing each segment individually.

## Manual Testing Script

Use this Home Assistant script to test each preset manually:

```yaml
script:
  test_preset_manual:
    alias: "Test WLED Preset"
    fields:
      preset_number:
        example: "50"
      test_color:
        example: "#FF0000"
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ preset_number }}"
      
      - delay:
          milliseconds: 500
      
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: [6, 7]
          color_primary: "{{ test_color }}"
          brightness_pct: 80
          effect: "Solid"
```

Call it from Developer Tools → Services:
```yaml
service: script.test_preset_manual
data:
  preset_number: "50"
  test_color: "#FF0000"
```

## Resources

- **Full Documentation**: [preset-based-segments.md](preset-based-segments.md)
- **Automation Examples**: [ha-automation-preset-based.md](ha-automation-preset-based.md)
- **Example Configs**: `digquad-settings/wled_preset_*_full_highlight.json`
- **Main Specification**: [preset-specification.md](preset-specification.md)

## Benefits Recap

✅ **Full Tag Control**: Both top and bottom of active tag  
✅ **No Hardware Changes**: Pure software solution  
✅ **Within Segment Limit**: Each preset uses ≤16 segments  
✅ **Dynamic**: Automatically switches based on active tray  
✅ **Backward Compatible**: Base presets still work  

## Trade-offs

⚠️ **Switching Delay**: ~500ms when changing presets  
⚠️ **Inactive Tags Combined**: Non-active tags lose individual control  
⚠️ **More Presets**: Need to manage 8 configurations (50-57)  
⚠️ **Complex Automation**: More sophisticated Home Assistant logic  

---

**Remember**: This is an advanced technique. Start with one preset (Preset 50 for A1) to validate the concept before creating all 8!
