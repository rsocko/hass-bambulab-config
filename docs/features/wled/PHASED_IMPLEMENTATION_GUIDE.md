# Phased Implementation Guide

## Overview

This guide provides a step-by-step approach to implementing the WLED system in manageable phases. Each phase builds on the previous one, allowing you to test and validate functionality before adding complexity.

## Prerequisites

Before starting any phase:
- [ ] Read [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)
- [ ] Read [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md)
- [ ] Hardware installed (711 LEDs across 5 GPIO pins)
- [ ] DigQuad controller connected and accessible
- [ ] WLED software installed on DigQuad
- [ ] Home Assistant with Bambu Lab integration configured

---

## Phase 1: Basic Lighting & Connectivity

**Goal**: Get basic LED functionality working with simple solid colors  
**Complexity**: Low  
**Estimated Time**: 2-4 hours  
**Success Criteria**: All LEDs light up in solid colors, can be controlled from WLED interface

### Phase 1 Steps

#### 1.1: Hardware Validation
- [ ] Verify all 711 LEDs are connected and working
- [ ] Test each GPIO pin independently with a test pattern
- [ ] Confirm LED counts match specification:
  - GPIO 15: 158 LEDs
  - GPIO 1: 140 LEDs
  - GPIO 3: 139 LEDs
  - GPIO 16: 136 LEDs
  - GPIO 4: 138 LEDs

#### 1.2: Configure WLED Basic Settings
- [ ] Set LED counts in WLED for each GPIO
- [ ] Configure LED type (WS2812B, SK6812, etc.)
- [ ] Test brightness and color settings
- [ ] Set power limits if needed

#### 1.3: Create Basic Segments (Simplified)
Create only the essential segments for testing:

| Segment | Name | LED Range | GPIO | Purpose |
|---------|------|-----------|------|---------|
| 0 | Printer Door (All) | 0-157 | 15 | Full door for testing |
| 1 | AMS 1 (All) | 158-297 | 1 | Full AMS 1 for testing |
| 2 | AMS 2 (All) | 298-436 | 3 | Full AMS 2 for testing |
| 3 | AMS 1 Tags (All) | 437-572 | 16 | Full AMS 1 tags for testing |
| 4 | AMS 2 Tags (All) | 573-710 | 4 | Full AMS 2 tags for testing |

**Total: 5 segments** (well within 16-segment limit)

#### 1.4: Create Phase 1 Presets

**Preset 1: All White**
- All segments: Bright White (255, 255, 255) at 50% brightness

**Preset 2: All Off**
- All segments: Off

**Preset 3: Test Pattern**
- Segment 0 (Door): Red
- Segment 1 (AMS 1): Green
- Segment 2 (AMS 2): Blue
- Segment 3 (AMS 1 Tags): Yellow
- Segment 4 (AMS 2 Tags): Cyan

#### 1.5: Add to Home Assistant
- [ ] Add WLED device to Home Assistant
- [ ] Verify entity is discovered (light.digquad or similar)
- [ ] Test turning on/off from Home Assistant
- [ ] Test applying presets from Home Assistant
- [ ] Test brightness control

#### 1.6: Create Basic Automation
```yaml
automation:
  - alias: "WLED Test - Turn On When Printer Powers On"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_printer_status
        to: "idle"
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 1
```

### Phase 1 Validation
- [ ] All LEDs light up correctly
- [ ] Each GPIO segment can be controlled independently
- [ ] Presets can be applied from WLED interface
- [ ] Home Assistant can control WLED
- [ ] Basic automation triggers correctly

---

## Phase 2: Progress Bar & Status Indicators

**Goal**: Implement front door progress bar and status indicators  
**Complexity**: Medium  
**Estimated Time**: 3-5 hours  
**Success Criteria**: Progress bar shows print progress, status segments show printer state

### Phase 2 Steps

#### 2.1: Refine Front Door Segments
Split the front door into functional segments:

| Segment | Name | LED Range | Purpose |
|---------|------|-----------|---------|
| 0 | Front Door Bottom | 0-49 | Progress bar |
| 1 | Front Door Left+Top | 50-157 | Status indicator (MERGED) |

**Update From Phase 1**: Replace Segment 0 with two segments (0 and 1)

#### 2.2: Create Progress Bar Presets

**Preset 10: Printing - 0% Progress**
- Segment 0: Off or dim green
- Segment 1: Green (solid)

**Preset 11: Printing - 50% Progress**
- Segment 0: Green (first 25 LEDs bright, rest dim)
- Segment 1: Green (solid)

**Preset 12: Printing - 100% Progress**
- Segment 0: Green (all bright)
- Segment 1: Green (solid)

#### 2.3: Create Status Indicator Presets

**Preset 20: Idle**
- Segment 0: Off
- Segment 1: Soft Green (breathing effect)

**Preset 21: Heating**
- Segment 0: Off
- Segment 1: Orange (pulsing effect)

**Preset 22: Error**
- Segment 0: Red (blinking)
- Segment 1: Red (blinking fast)

#### 2.4: Create Dynamic Progress Automation
```yaml
automation:
  - alias: "WLED Progress Bar Update"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_print_progress
    action:
      - service: wled.effect
        data:
          entity_id: light.digquad
          segment_id: 0
          color_primary: [0, 255, 0]
          intensity: "{{ (states('sensor.bambu_lab_print_progress') | int * 255 / 100) | int }}"
```

#### 2.5: Create Status Automation
```yaml
automation:
  - alias: "WLED Status Indicator"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_current_stage
    action:
      - choose:
          - conditions:
              - condition: state
                entity_id: sensor.bambu_lab_current_stage
                state: "printing"
            sequence:
              - service: light.turn_on
                data:
                  preset: 10
          - conditions:
              - condition: state
                entity_id: sensor.bambu_lab_current_stage
                state: "idle"
            sequence:
              - service: light.turn_on
                data:
                  preset: 20
          - conditions:
              - condition: state
                entity_id: sensor.bambu_lab_current_stage
                state: "heating"
            sequence:
              - service: light.turn_on
                data:
                  preset: 21
```

### Phase 2 Validation
- [ ] Progress bar updates during a print
- [ ] Progress bar shows accurate percentage (visual check)
- [ ] Status indicator changes with printer state
- [ ] Breathing/pulsing effects work correctly
- [ ] Error state triggers red blinking

---

## Phase 3: AMS Basic Lighting

**Goal**: Add basic AMS tray and tag lighting without active tray highlighting  
**Complexity**: Medium  
**Estimated Time**: 4-6 hours  
**Success Criteria**: AMS trays light up, tags show neutral lighting

### Phase 3 Steps

#### 3.1: Add AMS Tray Segments
Expand segments for AMS tray lighting:

| Segment | Name | LED Range | Purpose |
|---------|------|-----------|---------|
| 2 | AMS 1 Tray Top | 158-215 | Combined tray top lighting |
| 3 | AMS 1 Tray Bottom | 241-297 | Neutral background |
| 4 | AMS 2 Tray Top | 298-357 | Combined tray top lighting |
| 5 | AMS 2 Tray Bottom | 382-436 | Neutral background |

**Update From Phase 1**: Replace Segments 1-2 with four segments (2-5)

#### 3.2: Configure Neutral Backgrounds
Set neutral segments to soft white:
- Segments 3, 5: Soft White (255, 220, 180) at 30% brightness

#### 3.3: Create AMS Lighting Presets

**Preset 30: AMS Idle**
- Segments 2, 4: Soft White at 30%
- Segments 3, 5: Soft White at 25%

**Preset 31: AMS Printing**
- Segments 2, 4: Bright White at 50%
- Segments 3, 5: Soft White at 30%

#### 3.4: Add AMS to Status Automation
Update the automation from Phase 2 to include AMS segments:
```yaml
- conditions:
    - condition: state
      entity_id: sensor.bambu_lab_current_stage
      state: "printing"
  sequence:
    - service: light.turn_on
      data:
        preset: 31  # AMS Printing
```

### Phase 3 Validation
- [ ] AMS tray tops light up during printing
- [ ] AMS tray bottoms show neutral soft white
- [ ] Lighting changes with printer state
- [ ] Brightness levels are appropriate

---

## Phase 4: Individual Tag Control

**Goal**: Add individual control for each of 8 tray tags  
**Complexity**: High  
**Estimated Time**: 5-8 hours  
**Success Criteria**: Each tag can be controlled independently

### Phase 4 Steps

#### 4.1: Add Individual Tag Segments
Create segments for each tray tag:

| Segment | Name | LED Range | Purpose |
|---------|------|-----------|---------|
| 6 | Tag A1 Top | 442-453 | AMS 1 Tray 1 tag |
| 7 | Tag A2 Top | 454-465 | AMS 1 Tray 2 tag |
| 8 | Tag A3 Top | 466-477 | AMS 1 Tray 3 tag |
| 9 | Tag A4 Top | 490-501 | AMS 1 Tray 4 tag |
| 10 | Tag B1 Top | 579-591 | AMS 2 Tray 1 tag |
| 11 | Tag B2 Top | 592-605 | AMS 2 Tray 2 tag |
| 12 | Tag B3 Top | 606-619 | AMS 2 Tray 3 tag |
| 13 | Tag B4 Top | 632-643 | AMS 2 Tray 4 tag |
| 14 | Tag Bottoms + Hygro | Various | Combined neutral segment |

**Current Segment Count: 15 segments** (1 segment remaining)

#### 4.2: Set Default Tag States
Configure all tags to show soft white when not in use:
- Segments 6-13: Soft White at 30%
- Segment 14: Soft White at 25%

#### 4.3: Create Active Tray Highlight Presets
Create presets for each active tray (8 total):

**Preset 40: Active Tray A1**
- Segment 6: Filament Color at 80%
- Segments 7-13: Soft White at 30%

**Preset 41: Active Tray A2**
- Segment 7: Filament Color at 80%
- Segments 6, 8-13: Soft White at 30%

_(Continue for all 8 trays: Presets 40-47)_

#### 4.4: Configure Filament Color Mapping
If using Spoolman integration, create helpers to store filament colors:

```yaml
# configuration.yaml
input_text:
  tray_a1_color:
    name: "Tray A1 Filament Color"
    initial: "#FF0000"  # Default red
  tray_a2_color:
    name: "Tray A2 Filament Color"
    initial: "#00FF00"  # Default green
  # ... (continue for all 8 trays)
```

#### 4.5: Create Active Tray Automation
```yaml
automation:
  - alias: "WLED Active Tray Highlight"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_active_tray
    action:
      - service: wled.preset
        data:
          entity_id: light.digquad
          preset: >
            {% set tray = states('sensor.bambu_lab_active_tray') | int %}
            {{ 39 + tray }}  # Maps tray 1->40, 2->41, etc.
```

#### 4.6: Sync Filament Colors (Optional - Spoolman)
```yaml
automation:
  - alias: "Sync Filament Colors from Spoolman"
    trigger:
      - platform: state
        entity_id: sensor.spoolman_spool_1  # AMS 1 Tray 1
    action:
      - service: input_text.set_value
        target:
          entity_id: input_text.tray_a1_color
        data:
          value: "{{ state_attr('sensor.spoolman_spool_1', 'color_hex') }}"
```

### Phase 4 Validation
- [ ] All 8 tags can be controlled independently
- [ ] Active tray highlights correctly during printing
- [ ] Inactive tags remain dim
- [ ] Filament colors display correctly (if using Spoolman)
- [ ] Tag switching works when active tray changes

---

## Phase 5: Advanced Features & Error Handling

**Goal**: Add advanced scenarios, error states, and special effects  
**Complexity**: High  
**Estimated Time**: 6-10 hours  
**Success Criteria**: All error states work, special effects implemented

### Phase 5 Steps

#### 5.1: Add Interior Lid Light (Final Segment)
Add the 16th and final segment:

| Segment | Name | Purpose |
|---------|------|---------|
| 15 | Interior Lid Light | Simple interior lighting |

**Current Segment Count: 16 segments** (LIMIT REACHED)

#### 5.2: Create Error State Presets

**Preset 50: Filament Runout**
- Segment 0: Red (blinking)
- Segment 1: Red (blinking fast)
- Active tray tag: Red at 100% (strobe)
- All other segments: Red at 60%

**Preset 51: Temperature Error**
- All segments: Red (blinking) at 80%

**Preset 52: AMS Error**
- Affected AMS tray segments: Orange (strobe)
- Tag segments for affected AMS: Orange at 70%

#### 5.3: Create Loading/Unloading Animations

**Preset 60: Filament Loading**
- Active AMS tray top: Blue (chase effect)
- Active tag: Blue at 80%
- Other segments: Off or dim

**Preset 61: Filament Unloading**
- Active AMS tray top: Teal (reverse chase)
- Active tag: Teal at 80%

#### 5.4: Create Error Detection Automation
```yaml
automation:
  - alias: "WLED Error State Handler"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_hms_errors
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > 0 }}"
    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ 'runout' in trigger.to_state.attributes.error_list }}"
            sequence:
              - service: light.turn_on
                data:
                  preset: 50
          - conditions:
              - condition: template
                value_template: "{{ 'temperature' in trigger.to_state.attributes.error_list }}"
            sequence:
              - service: light.turn_on
                data:
                  preset: 51
```

#### 5.5: Implement Loading Animation Triggers
```yaml
automation:
  - alias: "WLED Filament Loading Animation"
    trigger:
      - platform: state
        entity_id: sensor.bambu_lab_ams_action
        to: "loading"
    action:
      - service: light.turn_on
        data:
          preset: 60
```

#### 5.6: Add Print Lifecycle States

**Preset 70: Heating**
- Segment 1: Orange (breathing)
- Segment 15: Orange at 50%

**Preset 71: Leveling**
- Segment 1: Blue (chase)
- Segments 2, 4: Blue (pulse)

**Preset 72: Print Complete**
- All segments: Green (breathing) celebration

### Phase 5 Validation
- [ ] Error states trigger correctly
- [ ] Appropriate segments highlight for specific errors
- [ ] Loading/unloading animations play
- [ ] Heating and leveling states display
- [ ] Print complete celebration works

---

## Phase 6: Fine-Tuning & Optimization

**Goal**: Refine colors, brightness, effects, and add polish  
**Complexity**: Medium  
**Estimated Time**: 3-5 hours  
**Success Criteria**: System looks polished, colors are aesthetically pleasing

### Phase 6 Steps

#### 6.1: Brightness Optimization
- [ ] Test all presets at various ambient light levels
- [ ] Adjust brightness for each segment type:
  - Progress bar: 50-80%
  - Status indicators: 40-60%
  - AMS trays: 30-50%
  - Tags (inactive): 25-35%
  - Tags (active): 70-90%
  - Neutral backgrounds: 20-30%

#### 6.2: Color Refinement
- [ ] Test all colors in actual lighting conditions
- [ ] Adjust hues for better visibility
- [ ] Ensure sufficient contrast between states
- [ ] Verify filament colors match actual filament

#### 6.3: Effect Timing
- [ ] Adjust breathing rates (slower = calmer)
- [ ] Adjust blink rates (faster for urgent errors)
- [ ] Tune chase speeds for loading animations
- [ ] Test transition smoothness

#### 6.4: Create Night Mode
- [ ] Implement time-based brightness reduction
- [ ] Or create manual "Night Mode" preset with very dim lights
- [ ] Ensure critical alerts still visible in night mode

#### 6.5: Add Manual Controls
Create dashboard controls in Home Assistant:
```yaml
# In Lovelace UI
type: entities
entities:
  - entity: light.digquad
    name: "WLED Main"
  - type: custom:slider-entity-row
    entity: light.digquad
    name: Brightness
  - type: button
    name: "Apply Night Mode"
    tap_action:
      action: call-service
      service: light.turn_on
      data:
        preset: 31  # Night Mode preset
```

#### 6.6: Performance Testing
- [ ] Monitor WLED controller performance
- [ ] Check Home Assistant automation response times
- [ ] Verify no lag when changing presets
- [ ] Test with continuous print monitoring

### Phase 6 Validation
- [ ] All colors look good in real environment
- [ ] Brightness levels are comfortable
- [ ] Effects are smooth and pleasing
- [ ] System performs well under continuous use
- [ ] Manual controls work as expected

---

## Phase 7: Documentation & Maintenance

**Goal**: Document final configuration and create maintenance plan  
**Complexity**: Low  
**Estimated Time**: 2-3 hours  
**Success Criteria**: Complete documentation, backup created

### Phase 7 Steps

#### 7.1: Backup Configuration
- [ ] Export WLED configuration JSON
- [ ] Export all presets
- [ ] Save Home Assistant automations to files
- [ ] Create backup of segment definitions

#### 7.2: Document Final Setup
Create a document with:
- [ ] Final segment allocation (all 16 segments)
- [ ] Complete preset list with IDs
- [ ] Automation trigger mappings
- [ ] Any deviations from original plan
- [ ] Troubleshooting notes

#### 7.3: Create Quick Reference Card
- [ ] Preset ID to scenario mapping
- [ ] Segment ID to zone mapping
- [ ] Common manual override commands
- [ ] Emergency "all off" command

#### 7.4: Test Disaster Recovery
- [ ] Factory reset WLED (in test environment)
- [ ] Restore from backup
- [ ] Verify all presets and segments work
- [ ] Document recovery process

#### 7.5: Share Results
- [ ] Take photos/videos of system in action
- [ ] Document lessons learned
- [ ] Note any issues or improvements
- [ ] Share with community if desired

### Phase 7 Validation
- [ ] Backup files exist and are tested
- [ ] Documentation is complete
- [ ] Quick reference is accurate
- [ ] Recovery process is documented

---

## Rollback Plan

If any phase fails or doesn't work as expected:

### Phase Rollback Steps
1. **Stop**: Stop implementing current phase
2. **Document**: Note what didn't work and why
3. **Restore**: Revert to previous phase configuration
4. **Analyze**: Determine root cause
5. **Adjust**: Modify approach or settings
6. **Retry**: Attempt phase again with adjustments

### Complete Rollback (Nuclear Option)
If system becomes unusable:
1. Factory reset WLED controller
2. Restore last known good backup
3. Restart from last successful phase
4. Contact community for help if needed

---

## Phase Implementation Timeline

### Minimum Viable Product (MVP)
- **Phases 1-3**: Basic lighting and progress bar
- **Time**: 9-15 hours
- **Result**: Functional LED system with basic features

### Full Feature Set
- **Phases 1-5**: All features including active tray highlighting
- **Time**: 20-35 hours
- **Result**: Complete LED system with all scenarios

### Production Ready
- **Phases 1-7**: Including optimization and documentation
- **Time**: 25-45 hours
- **Result**: Polished, documented, backed-up system

### Recommended Approach
**Weekend 1**: Phases 1-2 (Basic + Progress Bar)  
**Weekend 2**: Phase 3 (AMS Lighting)  
**Weekend 3**: Phase 4 (Tag Control)  
**Weekend 4**: Phases 5-7 (Advanced + Polish + Docs)

---

## Testing Checklist

Use this checklist to validate the complete system:

### Basic Functionality
- [ ] All 711 LEDs light up
- [ ] All 16 segments can be controlled
- [ ] WLED responds to Home Assistant commands
- [ ] Presets can be applied manually

### Print Lifecycle
- [ ] Idle state displays correctly
- [ ] Heating states show orange
- [ ] Leveling shows blue
- [ ] Printing activates green status
- [ ] Progress bar updates during print
- [ ] Print complete shows celebration
- [ ] Cooling state displays blue

### Active Tray Highlighting
- [ ] A1 tag highlights when tray 1 active
- [ ] A2 tag highlights when tray 2 active
- [ ] A3 tag highlights when tray 3 active
- [ ] A4 tag highlights when tray 4 active
- [ ] B1 tag highlights when tray 5 active
- [ ] B2 tag highlights when tray 6 active
- [ ] B3 tag highlights when tray 7 active
- [ ] B4 tag highlights when tray 8 active
- [ ] Filament colors match actual filament

### Error States
- [ ] Runout shows red blink on affected tag
- [ ] Temperature error shows red strobe all
- [ ] AMS error shows orange on affected AMS
- [ ] Door open shows bright white

### Advanced Features
- [ ] Loading animation plays during filament load
- [ ] Unloading animation plays during unload
- [ ] Hygrometer warnings work (degraded)
- [ ] Night mode dims appropriately
- [ ] Manual overrides work

---

## Troubleshooting Guide

### Common Issues by Phase

#### Phase 1 Issues
**Problem**: LEDs don't light up  
**Solution**: Check power supply, verify GPIO pins, check LED type setting

**Problem**: Wrong colors  
**Solution**: Try different LED type (GRB vs RGB vs BGR)

**Problem**: Only partial strip lights  
**Solution**: Verify LED count is correct, check for broken LEDs

#### Phase 2 Issues
**Problem**: Progress bar doesn't update  
**Solution**: Check automation triggers, verify sensor entity ID

**Problem**: Status indicator doesn't change  
**Solution**: Verify printer stage sensor is working, check automation conditions

#### Phase 3 Issues
**Problem**: AMS segments don't light  
**Solution**: Verify LED ranges are correct, check GPIO mapping

**Problem**: Neutral segments too bright/dim  
**Solution**: Adjust brightness percentages in presets

#### Phase 4 Issues
**Problem**: Wrong tag highlights  
**Solution**: Verify active tray sensor mapping, check preset IDs

**Problem**: Filament color doesn't match  
**Solution**: Check Spoolman integration, verify color hex values

#### Phase 5 Issues
**Problem**: Error states don't trigger  
**Solution**: Check HMS error sensor, verify automation conditions

**Problem**: Animations are choppy  
**Solution**: Reduce effect speed, lower FPS in WLED settings

---

## Conclusion

This phased approach allows you to:
1. **Build incrementally** with validation at each step
2. **Identify issues early** before adding complexity
3. **Learn the system** gradually
4. **Rollback easily** if something doesn't work
5. **Achieve MVP quickly** (Phases 1-3) then enhance

Start with Phase 1 and work your way through at your own pace. Each phase is designed to be completable in a few hours, making it suitable for weekend projects.

**Remember**: It's better to have a working basic system than a broken advanced one. Take your time, test thoroughly, and enjoy the process!
