# WLED Preset-Based Segment Configuration

## Overview

This document describes an advanced technique for working around the 16-segment-per-controller limitation in WLED by leveraging WLED's preset system to define **multiple segment layouts** that can be switched dynamically based on the scenario.

## The Core Concept

### Traditional Understanding (Limited)
Most users think of WLED presets as storing **colors and effects** for existing segments:
- Preset 1: All segments red
- Preset 2: All segments blue with breathing effect
- etc.

### Advanced Understanding (Powerful)
WLED presets can **also save segment definitions themselves**, including:
- Which LEDs belong to which segment
- How many segments are active
- The arrangement of segments

This means you can have **different 16-segment layouts** stored in different presets!

## How This Solves the Tag Top+Bottom Problem

### Current Limitation
In the current configuration:
- **Tag Tops**: Individual control (8 segments: DigQuad segments 6-13)
- **Tag Bottoms**: All combined into one neutral segment (DigQuad segment 14)
- **Result**: Cannot highlight BOTH top AND bottom of a specific tag simultaneously

### Solution Using Preset-Based Segments
Create multiple preset configurations, each optimized for a specific active tray:

#### Preset Configuration 50: "A1 Active - Full Highlight"
When tray A1 is active, load this preset which defines:
- Segment 0: Progress Bar (essential)
- Segment 1: Front Door Status (essential)
- **Segment 6: A1 Tag TOP** (LED range: 442-453)
- **Segment 7: A1 Tag BOTTOM** (LED range from current segment 14)
- Segment 8: A2-A4 Tags Combined (dim neutral)
- Segment 9: B1-B4 Tags Combined (dim neutral)
- Segment 10: AMS 1 Tray Top
- Segment 11: AMS 1 Tray Bottom
- Segment 12: AMS 2 Tray Top
- Segment 13: AMS 2 Tray Bottom
- Segment 14: Hygrometers + Other Backgrounds

**Result**: Full control of A1 top AND bottom!

#### Preset Configuration 51: "A2 Active - Full Highlight"
When tray A2 is active, load this preset which defines:
- Segment 0: Progress Bar (essential)
- Segment 1: Front Door Status (essential)
- **Segment 6: A2 Tag TOP** (LED range: 454-465)
- **Segment 7: A2 Tag BOTTOM** (LED range from current segment 14)
- Segment 8: A1, A3, A4 Tags Combined (dim neutral)
- Segment 9: B1-B4 Tags Combined (dim neutral)
- Segment 10: AMS 1 Tray Top
- Segment 11: AMS 1 Tray Bottom
- Segment 12: AMS 2 Tray Top
- Segment 13: AMS 2 Tray Bottom
- Segment 14: Hygrometers + Other Backgrounds

**Result**: Full control of A2 top AND bottom!

## Preset Segment Configuration Matrix

### Essential Segments (Always Present)
These segments appear in **every preset configuration** because they're critical:
1. **Segment 0**: Progress Bar (Front Door Bottom)
2. **Segment 1**: Status Indicator (Front Door Left+Top)
3. **Segment 2**: AMS 1 Tray Top
4. **Segment 3**: AMS 1 Tray Bottom
5. **Segment 4**: AMS 2 Tray Top
6. **Segment 5**: AMS 2 Tray Bottom

### Variable Segments (Change Per Preset)
These segments change based on which tray is active:
7. **Segments 6-13**: Reconfigured for active tray top+bottom control

## Complete Preset Configuration Set

### Configuration Family 1: AMS 1 Trays (A1-A4)

#### Preset Config 50: A1 Active with Full Control
```
Segment 0: Progress Bar (0-49)
Segment 1: Front Door Status (50-157)
Segment 2: AMS 1 Tray Top (158-215)
Segment 3: AMS 1 Tray Bottom (241-297)
Segment 4: AMS 2 Tray Top (298-357)
Segment 5: AMS 2 Tray Bottom (382-436)
Segment 6: A1 Tag Top (442-453)           ← ACTIVE TAG TOP
Segment 7: A1 Tag Bottom (502-513)        ← ACTIVE TAG BOTTOM
Segment 8: A2-A4 Tags Top (454-501)       ← Inactive tags combined
Segment 9: B1-B4 Tags Top (579-643)       ← AMS 2 tags combined
Segment 10: A2-A4 Tags Bottom (514-541)   ← Inactive bottoms combined
Segment 11: B1-B4 Tags Bottom (644-686)   ← AMS 2 bottoms combined
Segment 12: AMS 1 Hygrometer (478-501)
Segment 13: AMS 2 Hygrometer (620-643)
Segment 14: Spare / Future Use
Segment 15: MagWLED Interior Lid (different controller)
```

#### Preset Config 51: A2 Active with Full Control
```
Segment 0: Progress Bar (0-49)
Segment 1: Front Door Status (50-157)
Segment 2: AMS 1 Tray Top (158-215)
Segment 3: AMS 1 Tray Bottom (241-297)
Segment 4: AMS 2 Tray Top (298-357)
Segment 5: AMS 2 Tray Bottom (382-436)
Segment 6: A2 Tag Top (454-465)           ← ACTIVE TAG TOP
Segment 7: A2 Tag Bottom (514-525)        ← ACTIVE TAG BOTTOM
Segment 8: A1, A3, A4 Tags Top Combined   ← Inactive tags
Segment 9: B1-B4 Tags Top Combined        ← AMS 2 tags
Segment 10: A1, A3, A4 Tags Bottom Combined ← Inactive bottoms
Segment 11: B1-B4 Tags Bottom Combined    ← AMS 2 bottoms
Segment 12: AMS 1 Hygrometer
Segment 13: AMS 2 Hygrometer
Segment 14: Spare
```

#### Preset Config 52: A3 Active with Full Control
```
Similar pattern with A3 tag top (466-477) and bottom (526-538) split out
```

#### Preset Config 53: A4 Active with Full Control
```
Similar pattern with A4 tag top (490-501) and bottom (551-562) split out
```

### Configuration Family 2: AMS 2 Trays (B1-B4)

#### Preset Config 54: B1 Active with Full Control
```
Segment 0: Progress Bar
Segment 1: Front Door Status
Segment 2: AMS 1 Tray Top
Segment 3: AMS 1 Tray Bottom
Segment 4: AMS 2 Tray Top
Segment 5: AMS 2 Tray Bottom
Segment 6: B1 Tag Top (579-591)           ← ACTIVE TAG TOP
Segment 7: B1 Tag Bottom (644-656)        ← ACTIVE TAG BOTTOM
Segment 8: A1-A4 Tags Top Combined        ← AMS 1 tags
Segment 9: B2-B4 Tags Top Combined        ← Inactive AMS 2 tags
Segment 10: A1-A4 Tags Bottom Combined    ← AMS 1 bottoms
Segment 11: B2-B4 Tags Bottom Combined    ← Inactive bottoms
Segment 12: AMS 1 Hygrometer
Segment 13: AMS 2 Hygrometer
Segment 14: Spare
```

#### Preset Config 55-57: B2, B3, B4 Active
```
Similar patterns for each of the remaining AMS 2 trays
```

## LED Range Reference

### AMS 1 Tag LED Ranges
Based on the current DigQuad configuration:

| Tag | Top LEDs | Bottom LEDs (from segment 14) |
|-----|----------|-------------------------------|
| A1  | 442-453  | 502-513 (estimated)          |
| A2  | 454-465  | 514-525 (estimated)          |
| A3  | 466-477  | 526-538 (estimated)          |
| A4  | 490-501  | 551-562 (estimated)          |

**Note**: There is a gap at LEDs 478-489 which contains the AMS 1 hygrometer LEDs. This is physically embedded in the tag strip.

### AMS 2 Tag LED Ranges
| Tag | Top LEDs | Bottom LEDs (from segment 14) |
|-----|----------|-------------------------------|
| B1  | 579-591  | 644-656 (estimated)          |
| B2  | 592-605  | 657-671 (estimated)          |
| B3  | 606-619  | 672-686 (estimated)          |
| B4  | 632-643  | 687-698 (estimated)          |

**Note**: There is a gap at LEDs 620-631 which contains the AMS 2 hygrometer LEDs. This is physically embedded in the tag strip.

### Important LED Layout Notes

1. **Hygrometer LEDs are embedded**: The hygrometer LEDs are physically part of the tag LED strips, not separate strips.
2. **Cannot separate in combined segments**: When combining tags into a single segment (e.g., "A2-A4 combined"), we must either:
   - Exclude the hygrometer LEDs (creating non-contiguous ranges), OR
   - Include the hygrometer LEDs in the combined segment
3. **Practical solution**: In the preset configurations, we combine A1-A3 (excluding A4) and include A4+Hygrometer in segment 12. This keeps segments contiguous.

**Note**: Bottom LED ranges are estimated and should be verified against the actual LED strip installation. Refer to `digquad-led-segments.md` for exact measurements.

## Implementation in WLED

### Step 1: Create Preset Segment Configurations
For each preset configuration (50-57), you need to:

1. **Manually define segments in WLED UI**:
   - Navigate to the Segments tab in WLED
   - Delete all existing segments
   - Create new segments according to the preset configuration
   - Set start/stop LEDs for each segment
   - Assign colors/effects as needed

2. **Save as a Preset**:
   - Go to Presets tab
   - Click "Save to preset"
   - Choose preset number (e.g., 50 for A1)
   - **Important**: Check "Save segment bounds" option
   - Give it a descriptive name (e.g., "A1_Full_Highlight")
   - Save

3. **Repeat for all 8 tray configurations** (Presets 50-57)

### Step 2: Export Preset Configurations
After creating all presets in WLED UI:
```bash
# Export presets from WLED controller
curl http://[DIGQUAD_IP]/presets.json > wled_presets_with_segments.json
```

### Step 3: Backup and Version Control
```bash
# Save to repository
cp wled_presets_with_segments.json digquad-settings/
git add digquad-settings/wled_presets_with_segments.json
git commit -m "Add preset-based segment configurations for tag top+bottom control"
```

## Home Assistant Integration

### Automation Pattern
When the active tray changes, switch to the appropriate preset configuration:

```yaml
automation:
  - alias: "WLED - Switch to Active Tray Preset Configuration"
    id: wled_active_tray_preset_switcher
    trigger:
      - platform: state
        entity_id: sensor.bambu_active_tray
    action:
      - variables:
          # Map tray number to preset configuration ID
          preset_map:
            "1": 50  # A1 Active
            "2": 51  # A2 Active
            "3": 52  # A3 Active
            "4": 53  # A4 Active
            "5": 54  # B1 Active
            "6": 55  # B2 Active
            "7": 56  # B3 Active
            "8": 57  # B4 Active
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ preset_map[states('sensor.bambu_active_tray')] }}"
      
      # Wait for preset to load (segment definitions change)
      - delay:
          milliseconds: 500
      
      # Now set the active tag segments to filament color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 6  # Active tag TOP (always segment 6 in our layout)
          color_primary: "{{ state_attr('sensor.spoolman_active_spool', 'color_hex') }}"
          brightness: 204  # 80%
      
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 7  # Active tag BOTTOM (always segment 7 in our layout)
          color_primary: "{{ state_attr('sensor.spoolman_active_spool', 'color_hex') }}"
          brightness: 204  # 80%
```

### Color Synchronization Script
```yaml
script:
  wled_set_active_tag_color:
    alias: "WLED - Set Active Tag Color"
    description: "Set both top and bottom of active tag to filament color"
    fields:
      tray_number:
        description: "Active tray number (1-8)"
        example: "1"
      color_hex:
        description: "Hex color code"
        example: "#FF5733"
    sequence:
      # First switch to appropriate preset configuration
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: "{{ 49 + (tray_number | int) }}"  # Presets 50-57
      
      # Wait for segment reconfiguration
      - delay:
          milliseconds: 500
      
      # Set active tag top color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 6
          color_primary: "{{ color_hex }}"
          brightness: 204
      
      # Set active tag bottom color
      - service: wled.effect
        target:
          entity_id: light.digquad
        data:
          segment_id: 7
          color_primary: "{{ color_hex }}"
          brightness: 204
```

## Benefits of This Approach

### Advantages ✅
1. **Full Tag Control**: Can highlight BOTH top and bottom of active tag
2. **Within 16-Segment Limit**: Each preset stays within the limit
3. **No Hardware Changes**: Works with existing LED strips
4. **Dynamic Switching**: Automatically adapts to active tray
5. **Preserves Essentials**: Progress bar, status, and AMS lighting always available
6. **Flexible**: Can create specialized presets for different scenarios

### Trade-offs ⚠️
1. **Segment Reconfiguration Delay**: ~500ms delay when switching presets
2. **Non-Active Tags Combined**: Inactive tags lose individual control (but they're dim anyway)
3. **Preset Management**: Need to maintain 8 different preset configurations
4. **More Complex Automation**: Home Assistant needs to manage preset switching
5. **WLED Preset Slots**: Uses 8 preset slots (50-57) for segment configurations

## Alternative: Hybrid Approach

For users who want a simpler setup, consider a **hybrid approach**:

### Base Configuration (Preset 1-49)
- Use current segment layout with individual tag tops
- Tag bottoms all combined (simpler, always available)
- Good for general use and non-printing scenarios

### Enhanced Configurations (Preset 50-57)
- Use preset-based segment layouts with tag top+bottom split
- Only activate during active printing
- Provides full highlight capability when it matters most

### Automation Logic
```yaml
automation:
  - alias: "WLED - Smart Preset Selection"
    trigger:
      - platform: state
        entity_id: sensor.bambu_printer_stage
      - platform: state
        entity_id: sensor.bambu_active_tray
    action:
      - choose:
          # When printing: Use enhanced presets with full tag control
          - conditions:
              - condition: state
                entity_id: sensor.bambu_printer_stage
                state: "printing"
              - condition: template
                value_template: "{{ states('sensor.bambu_active_tray') | int > 0 }}"
            sequence:
              - service: script.wled_set_active_tag_color
                data:
                  tray_number: "{{ states('sensor.bambu_active_tray') }}"
                  color_hex: "{{ state_attr('sensor.spoolman_active_spool', 'color_hex') }}"
          
          # When not printing: Use base configuration
          default:
            - service: light.turn_on
              target:
                entity_id: light.digquad
              data:
                preset: 2  # Base idle preset
```

## Comparison: Current vs Preset-Based

### Current Approach (Single Static Segment Layout)
```
Pros:
- Simple: One segment layout to manage
- Fast: No preset switching delays
- Straightforward: Easy to understand

Cons:
- Limited: Cannot highlight tag bottom individually
- Static: Same constraints for all scenarios
- Workarounds: Need to use tag top brightness tricks
```

### Preset-Based Approach (Multiple Dynamic Layouts)
```
Pros:
- Flexible: Full control of active tag top+bottom
- Context-Aware: Adapts to active tray automatically
- Powerful: Leverages WLED's full capabilities
- No Hardware Changes: Pure software solution

Cons:
- Complex: More presets to create and maintain
- Switching Delay: ~500ms when changing presets
- Automation: Requires more sophisticated Home Assistant logic
```

## Implementation Roadmap

### Phase 1: Proof of Concept (1-2 hours)
1. Create ONE preset configuration for A1 (Preset 50)
2. Manually test in WLED UI
3. Verify tag top and bottom can be controlled independently
4. Test switching between base preset and Preset 50

### Phase 2: Complete Configurations (3-4 hours)
1. Create all 8 preset configurations (Presets 50-57)
2. Document exact LED ranges for each segment
3. Export and backup preset configurations
4. Test each configuration manually

### Phase 3: Home Assistant Integration (2-3 hours)
1. Create automation to switch presets based on active tray
2. Create script to set active tag colors
3. Test automation with simulated tray changes
4. Fine-tune delays and transitions

### Phase 4: Testing and Refinement (2-3 hours)
1. Test with actual print jobs
2. Verify colors match Spoolman data
3. Adjust brightness levels
4. Optimize switching delays
5. Document any edge cases

### Phase 5: Documentation and Maintenance (1-2 hours)
1. Update main README with preset approach
2. Create troubleshooting guide
3. Document backup/restore procedures
4. Create preset templates for future modifications

## Troubleshooting

### Issue: Segments Don't Change When Switching Presets
**Cause**: "Save segment bounds" wasn't checked when creating preset  
**Solution**: Recreate the preset with "Save segment bounds" enabled

### Issue: Delay Too Long When Switching Presets
**Cause**: WLED needs time to reconfigure segments  
**Solution**: Tune the delay value (typically 200-500ms is sufficient)

### Issue: Colors Not Applying After Preset Switch
**Cause**: Trying to set colors before segment reconfiguration completes  
**Solution**: Increase delay after preset switch before setting colors

### Issue: Inactive Tags Show Wrong Color
**Cause**: Combined segments inherit last-set color  
**Solution**: Explicitly set combined segments to neutral color after preset switch

## Maintenance

### Regular Tasks
1. **Backup Presets**: Export `presets.json` monthly
2. **Verify LED Counts**: Check if physical LED strips changed
3. **Test All Presets**: Cycle through all 8 configurations quarterly
4. **Update Documentation**: Keep LED ranges current

### Updating a Preset Configuration
1. Load the preset in WLED UI
2. Make changes to segment definitions
3. Save preset (ensure "Save segment bounds" is checked)
4. Export updated presets.json
5. Commit to repository
6. Test in Home Assistant

## Conclusion

The preset-based segment configuration approach unlocks the full potential of WLED's segment system by allowing **multiple 16-segment layouts** that can be dynamically switched based on context. This enables highlighting both the top AND bottom of active tray tags without exceeding the per-controller segment limit.

While more complex than a static segment layout, this approach provides maximum flexibility and is a pure software solution requiring no hardware modifications. It's particularly powerful for scenarios where full visual feedback on the active tray is critical during multi-material prints.

---

**Key Takeaway**: WLED presets can save segment **definitions**, not just colors. This allows you to have different segment layouts for different scenarios, effectively multiplying your segment capacity!
